"""The checks an outside call passes before it reaches Legion: key, service, the client's own IP list,
rate and budget, in that order. Any check that cannot decide refuses. A known client's refusal is audited
(an event with no text); an unknown or malformed key is not, and looks the same as a disabled client."""

from __future__ import annotations

import ipaddress
import math
from collections import deque
from datetime import datetime
from time import monotonic

from src.db import utcnow
from src.models.outside_client import OutsideClient
from src.services.outside_clients import OutsideClients

INVALID_KEY = "Invalid or missing key."
WINDOW_SECONDS = 60
MAX_TRACKED = 1000


class OutsideRefused(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None,
                 client: OutsideClient | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.retry_after, self.client = status, code, message, retry_after, client


class ClientRateLimiter:
    """A sliding 60-second window per client id, in memory. Refused calls are not counted."""

    def __init__(self, clock=monotonic) -> None:
        self._clock = clock
        self._calls: dict[int, deque[float]] = {}

    def retry_after(self, client_id: int, per_minute: int) -> int | None:
        now = self._clock()
        calls = self._calls.get(client_id)
        if calls is None:
            if len(self._calls) >= MAX_TRACKED:
                self._evict(now)
            calls = self._calls[client_id] = deque()
        while calls and calls[0] <= now - WINDOW_SECONDS:
            calls.popleft()
        if len(calls) >= per_minute:
            return max(1, math.ceil(calls[0] + WINDOW_SECONDS - now))
        calls.append(now)
        return None

    def _evict(self, now: float) -> None:
        for client_id in [c for c, calls in self._calls.items() if not calls or calls[-1] <= now - WINDOW_SECONDS]:
            del self._calls[client_id]
        while len(self._calls) >= MAX_TRACKED:  # all busy: drop the least recently active
            del self._calls[min(self._calls, key=lambda c: self._calls[c][-1] if self._calls[c] else 0.0)]


def _ip_in(ip: str, networks: list[str]) -> bool:
    try:
        address = ipaddress.ip_address(ip)
        return any(address in ipaddress.ip_network(net, strict=False) for net in networks)
    except ValueError:
        return False


class OutsideGuard:
    def __init__(self, limiter: ClientRateLimiter) -> None:
        self.limiter = limiter

    async def admit(self, clients: OutsideClients, key: str | None, service: str, ip: str) -> OutsideClient:
        client = await clients.authenticate(key or "")
        if client is None:
            raise OutsideRefused(401, "invalid_key", INVALID_KEY)
        if not client.enabled:
            await self._refuse(clients, client, service, ip, 401, "disabled", INVALID_KEY, code="invalid_key")
        if service not in client.services:
            await self._refuse(clients, client, service, ip, 403, "service_not_allowed", "This service is not allowed for this client.")
        if client.ip_allow and not _ip_in(ip, client.ip_allow):
            await self._refuse(clients, client, service, ip, 403, "ip_not_allowed", "This address is not allowed for this client.")
        wait = self.limiter.retry_after(client.id, client.rate_per_minute)
        if wait is not None:
            await self._refuse(clients, client, service, ip, 429, "rate_limited", "Too many calls; try again later.", wait)
        try:
            used, resets_at = await clients.spent(client)
        except Exception:
            await self._refuse(clients, client, service, ip, 503, "budget_unavailable", "The budget cannot be checked right now.")
        # shortcut: the cap is checked before the call, so one call can overshoot; add a per-call token ceiling from Legion's limits if that matters.
        if used >= client.budget_tokens:
            await self._refuse(clients, client, service, ip, 429, "budget_exhausted", "The token budget is used up.",
                               _seconds_until(resets_at))
        return client

    @staticmethod
    async def _refuse(clients: OutsideClients, client: OutsideClient, service: str, ip: str, status: int, reason: str,
                      message: str, retry_after: int | None = None, *, code: str | None = None) -> None:
        try:
            await clients.record(client, service=service, action="refused", reason=reason, status=status, ip=ip)
        except Exception:  # noqa: BLE001 - a failed audit write never turns a refusal into an admit
            pass
        raise OutsideRefused(status, code or reason, message, retry_after, client)


def _seconds_until(moment: datetime | None) -> int:
    if moment is None:
        return 1
    return max(1, math.ceil((moment - utcnow()).total_seconds()))
