"""The clock the stored times use."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC, the form every stored time has."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
