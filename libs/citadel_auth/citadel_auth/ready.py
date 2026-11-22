"""Dependency report for /ready: each dependency with state and last error. Never raises, never fails a container."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from dataclasses import dataclass

import httpx

PROBE_TIMEOUT = 2.0


@dataclass(frozen=True)
class Dependency:
    name: str
    address: Callable[[], str | None | Awaitable[str | None]]
    path: str = "/health"


class Probe:
    """Probes dependencies at the same time and keeps the last report for `ttl` seconds."""

    def __init__(self, service: str, *, client_factory: Callable[[], httpx.AsyncClient] | None = None,
                 ttl: float = 10.0) -> None:
        self._service = service
        self._factory = client_factory or (lambda: httpx.AsyncClient(timeout=PROBE_TIMEOUT, trust_env=False))
        self._ttl = ttl
        self._cached: dict | None = None
        self._at = 0.0
        self._lock = asyncio.Lock()

    async def check(self, dependencies: list[Dependency]) -> dict:
        async with self._lock:
            now = time.monotonic()
            if self._cached is not None and now - self._at < self._ttl:
                return self._cached
            rows = []
            if dependencies:
                async with self._factory() as client:
                    rows = await asyncio.gather(*(self._one(client, dependency) for dependency in dependencies))
            self._cached = {"service": self._service, "status": "up", "dependencies": list(rows)}
            self._at = time.monotonic()
            return self._cached

    async def _one(self, client: httpx.AsyncClient, dependency: Dependency) -> dict:
        try:
            async with asyncio.timeout(PROBE_TIMEOUT):
                value = dependency.address()
                address = await value if isawaitable(value) else value
                url = httpx.URL(address) if address else None
                if url is not None and (
                    url.scheme not in ("http", "https") or not url.host
                    or url.userinfo or url.query or url.fragment
                ):
                    address = None
        except Exception:  # an address lookup that fails is "not configured", never a crash
            address = None
        row = {"name": dependency.name, "state": "not_configured", "address": address, "last_error": None}
        if not address:
            return row
        try:
            async with asyncio.timeout(PROBE_TIMEOUT):
                async with client.stream("GET", address.rstrip("/") + dependency.path, timeout=PROBE_TIMEOUT) as response:
                    status = response.status_code
        except (httpx.TimeoutException, TimeoutError):
            return {**row, "state": "unreachable", "last_error": "timeout"}
        except httpx.HTTPError:
            return {**row, "state": "unreachable", "last_error": "unavailable"}
        if status in (401, 403):
            return {**row, "state": "unreachable", "last_error": "rejected"}
        if not 200 <= status < 300:
            return {**row, "state": "unreachable", "last_error": "error"}
        return {**row, "state": "reachable"}
