"""Legion's client for its built-in ConversationGateway (src/gateway/conversation).

The gateway holds provider keys and speaks to Anthropic, OpenAI and the CNV
model services. Legion sends one chat request per model round and runs the
tools itself. A failure arrives as GatewayCallError carrying the gateway's
own `kind` (rate_limit, quota, auth, unavailable), which gateway_failover.py
turns into a cooldown and a switch.
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from src import gateway
from src.gateway.conversation.contract import Limits, parse_request
from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.settings import Settings

_IDS_TTL_SECONDS = 60.0
_LIMITS = Limits.from_settings(Settings())

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


def _call_error(error: GatewayError) -> GatewayCallError:
    return GatewayCallError(error.status, error.code, error.message, kind=error.kind,
                            retry_after=float(error.retry_after) if error.retry_after else None)


class ConversationGatewayClient:
    """One chat round per call. Holds no state between calls."""

    async def stream(self, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """The round's events in order; the last one is `done`."""
        finished = False
        try:
            request = parse_request({**body, "stream": True}, _LIMITS)
            async for event in gateway.stream(gateway.chat_service().stream(request)):
                finished = event.get("type") == "done"
                yield event
        except GatewayError as error:
            raise _call_error(error) from error
        if not finished:
            raise GatewayCallError(502, "gateway_unavailable", "ConversationGateway ended the stream early.",
                                   kind="unavailable")

    def chat_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        """One non-streamed reply, for the sync `interpret` path."""
        try:
            request = parse_request({**body, "stream": False}, _LIMITS)
            return gateway.call_sync(gateway.chat_service().chat(request), 300)
        except GatewayError as error:
            raise _call_error(error) from error


def saved_gateway_ids() -> frozenset[str]:
    """Ids of the gateways saved on the Model gateways page, cached for a minute."""
    global _ids, _ids_until
    if _ids is not None and time.monotonic() < _ids_until:
        return _ids
    _ids = frozenset(gateway.chat_store().all())
    _ids_until = time.monotonic() + _IDS_TTL_SECONDS
    return _ids


def is_saved(gateway_id: str) -> bool:
    """Whether a gateway named `gateway_id` is saved."""
    return gateway_id in saved_gateway_ids()


def reset_cache() -> None:
    """Forget the saved ids (tests, or after an admin edits gateways)."""
    global _ids, _ids_until
    _ids, _ids_until = None, 0.0
