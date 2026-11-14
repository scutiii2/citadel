"""Legion's HTTP client for DecisionGateway (AI/ModelProviders/DecisionGateway).

The gateway holds the upstream addresses and keys (TypeSafe Jev, the Laya
model service) and answers typed questions for a saved gateway id. Legion
keeps only the arrangement: which saved gateway is asked first (strategy.py).
Calls are synchronous: every caller already runs decisions off the event loop.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from src.providers.decision.contract import DecisionError
from src.runtime import gateway_settings, internal_auth

_LIST_TIMEOUT = httpx.Timeout(5.0)
# The service itself keeps reachability for 15 seconds.
_LIST_TTL_SECONDS = 15.0
# Tests replace this to answer without a network.
_TRANSPORT: httpx.BaseTransport | None = None

_listed: dict[str, bool | None] | None = None
_listed_until = 0.0


def _settings() -> gateway_settings.GatewaySettings:
    return gateway_settings.current_sync(gateway_settings.DECISION_KEY)


def _headers(settings: gateway_settings.GatewaySettings) -> dict[str, str]:
    headers = {"X-Requester-Username": internal_auth.current_requester().username or "legion"}
    if settings.token:
        headers["X-Internal-Token"] = settings.token
    return headers


def _message(response: httpx.Response) -> str:
    """The gateway's own `message`; it never carries upstream bodies or credentials."""
    try:
        message = response.json().get("message")
    except (ValueError, AttributeError):
        message = None
    return str(message) if message else f"DecisionGateway answered {response.status_code}"


def decide(gateway: str, text: str, questions: dict[str, Any], *,
           min_confidence: float | None = None, timeout: float) -> dict[str, Any]:
    """One `POST /api/decide`: `{gateway, model, answers, tokens, streamed}`.
    `trace` is always asked for; the decision provider drops it unless its caller wanted it."""
    body: dict[str, Any] = {"gateway": gateway, "text": text, "questions": questions, "trace": True}
    if min_confidence is not None:
        body["min_confidence"] = min_confidence
    settings = _settings()
    try:
        with httpx.Client(transport=_TRANSPORT, timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0))) as client:
            response = client.post(f"{settings.url}/api/decide", json=body, headers=_headers(settings))
    except httpx.HTTPError as error:
        raise DecisionError(f"DecisionGateway could not be reached: {type(error).__name__}") from error
    if response.status_code != 200:
        raise DecisionError(_message(response))
    try:
        reply = response.json()
    except ValueError as error:
        raise DecisionError("DecisionGateway sent something that is not JSON") from error
    if not isinstance(reply, dict) or not isinstance(reply.get("answers"), dict):
        raise DecisionError("DecisionGateway's answer has an unexpected shape")
    return reply


def saved_gateways() -> dict[str, bool | None] | None:
    """Saved gateway id -> whether its upstream answers (None: not probed).
    None, and not cached, when the service cannot be asked: the caller then assumes
    a gateway exists and lets the call itself report the outage."""
    global _listed, _listed_until
    if _listed is not None and time.monotonic() < _listed_until:
        return _listed
    settings = _settings()
    try:
        with httpx.Client(transport=_TRANSPORT, timeout=_LIST_TIMEOUT) as client:
            response = client.get(f"{settings.url}/api/gateways", headers=_headers(settings))
        entries = response.json().get("gateways") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        entries = None
    if not isinstance(entries, list):
        return None
    _listed = {str(entry["id"]): entry.get("reachable") for entry in entries
               if isinstance(entry, dict) and entry.get("id")}
    _listed_until = time.monotonic() + _LIST_TTL_SECONDS
    return _listed


def is_usable(gateway: str) -> bool:
    """Saved and not known to be down; True when the service cannot be asked."""
    listed = saved_gateways()
    return listed is None or (gateway in listed and listed[gateway] is not False)


def is_reachable(gateway: str) -> bool:
    """Strictly: the service answered and reports this gateway's upstream as up. For status pages."""
    listed = saved_gateways()
    return bool(listed) and listed.get(gateway) is True


def reset_cache() -> None:
    """Forget the listing (tests, or after an admin edits the connection)."""
    global _listed, _listed_until
    _listed, _listed_until = None, 0.0
