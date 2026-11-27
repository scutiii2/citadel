"""The 429 an account gets when a question would go over its token limit."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status

from src.usage.service import LimitBlock


def limit_reached(block: LimitBlock) -> HTTPException:
    minutes = max(1, int((block.reset_at - datetime.now(UTC).replace(tzinfo=None)).total_seconds() // 60) + 1)
    wait = f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60} min"
    hint = " You have a free reset: use it from the usage ring." if block.resettable else ""
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"You've reached your {block.reason}. It frees up in about {wait}.{hint}",
        headers={"Retry-After": str(minutes * 60)},
    )
