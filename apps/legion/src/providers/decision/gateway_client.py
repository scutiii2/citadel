"""Legion's client for its built-in DecisionGateway (src/gateway/decision).

The gateway holds the upstream addresses and keys (TypeSafe Jev, the Laya
model service) and answers typed questions for a saved gateway id. Legion
keeps only the arrangement: which saved gateway is asked first (strategy.py).
Calls are synchronous: every caller already runs decisions off the event loop.
"""

from __future__ import annotations

import time
from typing import Any

from src import gateway
from src.gateway import trust
from src.gateway.decision.contract import parse_request
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.settings import Settings
from src.providers.decision.contract import DecisionError

# The service itself keeps reachability for 15 seconds.
_LIST_TTL_SECONDS = 15.0
_MAX_CHARS = Settings().max_chars

_listed: dict[str, bool | None] | None = None
_listed_until = 0.0


def decide(gateway_id: str, text: str, questions: dict[str, Any], *,
           min_confidence: float | None = None, timeout: float) -> dict[str, Any]:
    """One decision: `{gateway, model, answers, tokens, streamed}`.
    `trace` is always asked for; the decision provider drops it unless its caller wanted it."""
    body: dict[str, Any] = {"gateway": gateway_id, "text": text, "questions": questions, "trace": True}
    if min_confidence is not None:
        body["min_confidence"] = min_confidence
    try:
        reply = gateway.call_sync(gateway.decision_service().decide(parse_request(body, _MAX_CHARS)), timeout)
    except GatewayError as error:
        raise DecisionError(error.message) from error
    except TimeoutError as error:
        raise DecisionError("DecisionGateway did not answer in time") from error
    if not isinstance(reply, dict) or not isinstance(reply.get("answers"), dict):
        raise DecisionError("DecisionGateway's answer has an unexpected shape")
    return reply


def saved_gateways() -> dict[str, bool | None]:
    """Saved gateway id -> whether its upstream answers (None: not probed)."""
    global _listed, _listed_until
    if _listed is not None and time.monotonic() < _listed_until:
        return _listed
    try:
        entries = gateway.call_sync(gateway.decision_service().gateways(), 10)
    except (GatewayError, TimeoutError):
        return {}
    _listed = {str(entry["id"]): entry.get("reachable") for entry in entries if entry.get("id")}
    _listed_until = time.monotonic() + _LIST_TTL_SECONDS
    return _listed


def is_trusted(gateway_id: str) -> bool:
    """Whether confidential data may go to this decision gateway (src/gateway/trust.py)."""
    saved = gateway.decision_store().all().get(gateway_id)
    return trust.decision(gateway_id, saved if isinstance(saved, dict) else None)


def is_usable(gateway_id: str) -> bool:
    """Saved and not known to be down."""
    listed = saved_gateways()
    return gateway_id in listed and listed[gateway_id] is not False


def is_reachable(gateway_id: str) -> bool:
    """Strictly: the gateway reports this one's upstream as up. For status pages."""
    return saved_gateways().get(gateway_id) is True


def reset_cache() -> None:
    """Forget the listing (tests, or after an admin edits an entry)."""
    global _listed, _listed_until
    _listed, _listed_until = None, 0.0
