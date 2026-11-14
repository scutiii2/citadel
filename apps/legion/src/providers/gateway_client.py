"""Legion's HTTP client for ConversationGateway (AI/ModelProviders/ConversationGateway).

The gateway holds provider keys and speaks to Anthropic, OpenAI and the CNV
model services. Legion sends one chat request per model round and runs the
tools itself. A failure arrives as GatewayCallError carrying the gateway's
own `kind` (rate_limit, quota, auth, unavailable), which gateway_failover.py
turns into a cooldown and a switch.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from src.runtime import gateway_settings, internal_auth
from src.runtime.gateway_settings import GatewaySettings

# No read timeout: a round streams for as long as the model writes. The turn
# guard and Stop end a slow turn; connect, write and pool still fail fast.
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
_SYNC_TIMEOUT = httpx.Timeout(300.0, connect=10.0)
_IDS_TIMEOUT = httpx.Timeout(5.0)
_IDS_TTL_SECONDS = 60.0
# Tests replace this to answer saved_gateway_ids() without a network.
_SYNC_TRANSPORT: httpx.BaseTransport | None = None

_ids: frozenset[str] | None = None
_ids_until = 0.0


class GatewayCallError(Exception):
    """ConversationGateway refused or failed a call. `kind` is None for a
    request the gateway rejected as invalid, which must not be retried."""

    def __init__(self, status: int, code: str, message: str,
                 kind: str | None = None, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.kind = kind
        self.retry_after = retry_after


def _headers(settings: GatewaySettings) -> dict[str, str]:
    headers = {"X-Requester-Username": internal_auth.current_requester().username or "legion"}
    if settings.token:
        headers["X-Internal-Token"] = settings.token
    return headers


def _unavailable(message: str) -> GatewayCallError:
    return GatewayCallError(502, "gateway_unavailable", message, kind="unavailable")


def _seconds(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _error(status: int, payload: Any, retry_after: str | None = None) -> GatewayCallError:
    """The gateway's `{error: {code, message, kind?}}` as an exception."""
    detail = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(detail, dict):
        detail = {}
    return GatewayCallError(
        status,
        str(detail.get("code") or "gateway_error"),
        str(detail.get("message") or f"ConversationGateway answered {status}"),
        kind=detail.get("kind") if isinstance(detail.get("kind"), str) else None,
        retry_after=_seconds(retry_after),
    )


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


class ConversationGatewayClient:
    """One chat round per call. Holds no state between calls."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None,
                 sync_transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport
        self._sync_transport = sync_transport

    async def stream(self, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """The round's NDJSON events in order; the last one is `done`."""
        finished = False
        settings = await gateway_settings.current()
        try:
            # shortcut: one HTTP client per round, safe across Legion's event loops;
            # pool per loop if connection setup shows up in round latency.
            async with httpx.AsyncClient(transport=self._transport, timeout=_STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST", f"{settings.url}/api/chat", json={**body, "stream": True}, headers=_headers(settings),
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise _error(response.status_code, _json(response.text), response.headers.get("retry-after"))
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        event = _json(line)
                        if not isinstance(event, dict):
                            raise _unavailable("ConversationGateway sent an unreadable stream line.")
                        if event.get("type") == "error":
                            raise _error(int(event.get("status") or 502), event)
                        finished = event.get("type") == "done"
                        yield event
        except httpx.HTTPError as error:
            raise _unavailable(f"ConversationGateway is unreachable: {type(error).__name__}") from error
        if not finished:
            raise _unavailable("ConversationGateway ended the stream early.")

    def chat_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        """One non-streamed reply, for the sync `interpret` path."""
        settings = gateway_settings.current_sync()
        try:
            with httpx.Client(transport=self._sync_transport, timeout=_SYNC_TIMEOUT) as client:
                response = client.post(f"{settings.url}/api/chat", json={**body, "stream": False},
                                       headers=_headers(settings))
        except httpx.HTTPError as error:
            raise _unavailable(f"ConversationGateway is unreachable: {type(error).__name__}") from error
        payload = _json(response.text)
        if response.status_code != 200:
            raise _error(response.status_code, payload, response.headers.get("retry-after"))
        if not isinstance(payload, dict):
            raise _unavailable("ConversationGateway sent an unreadable reply.")
        return payload


def saved_gateway_ids() -> frozenset[str] | None:
    """Ids of the gateways saved in ConversationGateway, cached for a minute.
    None (and not cached) when the service cannot be asked: the caller then
    assumes a gateway exists and lets the call itself report the outage, so
    Legion can start before the gateway does."""
    global _ids, _ids_until
    if _ids is not None and time.monotonic() < _ids_until:
        return _ids
    settings = gateway_settings.current_sync()
    try:
        with httpx.Client(transport=_SYNC_TRANSPORT, timeout=_IDS_TIMEOUT) as client:
            response = client.get(f"{settings.url}/api/gateways", headers=_headers(settings))
        entries = response.json().get("gateways") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        entries = None
    if not isinstance(entries, list):
        return None
    _ids = frozenset(str(entry["id"]) for entry in entries if isinstance(entry, dict) and entry.get("id"))
    _ids_until = time.monotonic() + _IDS_TTL_SECONDS
    return _ids


def is_saved(gateway: str) -> bool:
    """Whether ConversationGateway has `gateway` saved; True when it cannot be asked."""
    ids = saved_gateway_ids()
    return ids is None or gateway in ids


def reset_cache() -> None:
    """Forget the saved ids (tests, or after an admin edits gateways)."""
    global _ids, _ids_until
    _ids, _ids_until = None, 0.0
