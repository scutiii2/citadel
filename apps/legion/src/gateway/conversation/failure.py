"""Upstream status and text to a GatewayError a caller can act on. Never retries."""
from __future__ import annotations

import math
from typing import Iterable

from src.gateway.conversation.errors import GatewayError

QUOTA_WORDS = ("credit", "quota", "billing", "insufficient", "balance", "exceeded your current")
SECRET_KEYS = ("api_key", "token", "aws_access_key_id", "aws_secret_access_key")


def scrub(text: str, secrets: Iterable[str], limit: int = 500) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return " ".join(str(text).split())[:limit]


def _wait(value: str | None) -> int:
    try:
        return max(1, min(60, math.ceil(float(value))))
    except (TypeError, ValueError, OverflowError):
        return 1


def upstream_error(status: int, text: str, retry_after: str | None = None, secrets: Iterable[str] = ()) -> GatewayError:
    message = scrub(text, secrets) or "The model service refused the request."
    quota = any(word in text.lower() for word in QUOTA_WORDS)
    if status == 402 or (status in (400, 429) and quota):
        return GatewayError(402, "gateway_quota", message, kind="quota")
    if status in (401, 403):
        return GatewayError(502, "gateway_auth", message, kind="auth")
    if status == 429:
        return GatewayError(429, "gateway_rate_limit", message, kind="rate_limit", retry_after=_wait(retry_after))
    if status == 413:
        return GatewayError(413, "too_large", message)
    if status in (400, 404, 422):
        return GatewayError(422, "gateway_refused", message)
    if status >= 500:
        return GatewayError(502, "gateway_unavailable", message, kind="unavailable")
    return GatewayError(502, "gateway_error", message)
