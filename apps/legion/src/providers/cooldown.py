"""Process-wide rate-limit cooldown tracking.

This is intentionally a plain module-level dict, not per-session state,
and it's the one deliberate exception to this project's "no module-level
mutable state" rule. The test is whose fact it is: a cache of one user's
query results has no business being global, but a provider's rate-limit
status is genuinely process-wide - if OpenAI 429s this process once, it's
429ing every user of this process, not just whoever triggered it. Sharing
that state is correct here.

Cooldowns are also written to Legion's settings database (tables `cooldowns` and `gateway_health`), so every
agent process, and a restart, sees a gateway that failed. Each process re-reads the table every couple of seconds. A
database that cannot be read or written never stops a turn: the in-memory state still works.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from src.citadel_auth import settings_store

_log = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 60.0
SYNC_SECONDS = 2.0  # how often a process re-reads the shared table
HISTORY_LIMIT = 50  # failures kept per gateway
DAY = 86400.0

_cooldown_until: dict[str, float] = {}
_synced_at = float("-inf")
# The settings database; None means Legion's own (resolved late: config_files imports this package's neighbours).
DB: Path | None = None


def _db() -> Path:
    if DB is not None:
        return DB
    from src.runtime.config_files import SETTINGS_DB

    return SETTINGS_DB


def _sync() -> None:
    """Take over cooldowns another process wrote. Best effort."""
    global _synced_at
    now = time.monotonic()
    if now - _synced_at < SYNC_SECONDS:
        return
    _synced_at = now
    try:
        rows = settings_store.read_all(_db(), "cooldowns")
    except Exception:  # noqa: BLE001 - a bad database must not stop a turn
        return
    wall = time.time()
    for key, row in rows.items():
        remaining = (row.get("until", 0) if isinstance(row, dict) else 0) - wall
        if remaining > 0:
            _cooldown_until[key] = max(_cooldown_until.get(key, 0.0), now + remaining)


def gateway_key(provider_id: str, gateway: str) -> str:
    """Scope a gateway failure without blocking its provider's other gateways."""
    return f"{provider_id}:{gateway}"


def start_cooldown(provider_id: str, seconds: float = DEFAULT_COOLDOWN_SECONDS, kind: str | None = None) -> None:
    seconds = max(seconds, 1.0)
    _cooldown_until[provider_id] = time.monotonic() + seconds
    wall = time.time()
    try:
        settings_store.put(_db(), "cooldowns", provider_id, {"until": wall + seconds, "kind": kind})
        history = settings_store.read_all(_db(), "gateway_health").get(provider_id, {})
        events = [e for e in history.get("events", []) if isinstance(e, list)][-(HISTORY_LIMIT - 1):]
        settings_store.put(_db(), "gateway_health", provider_id, {"events": [*events, [wall, kind or "unknown"]]})
    except Exception:  # noqa: BLE001
        _log.debug("could not record the cooldown of %s", provider_id, exc_info=True)


def health(key: str) -> dict[str, Any]:
    """What the admin page shows about one gateway key: its cooldown and its recent failures."""
    try:
        events = settings_store.read_all(_db(), "gateway_health").get(key, {}).get("events", [])
    except Exception:  # noqa: BLE001
        events = []
    wall = time.time()
    recent = [e for e in events if isinstance(e, list) and len(e) == 2 and wall - e[0] <= DAY]
    return {"cooldown_seconds": round(seconds_remaining(key)), "failures_24h": len(recent),
            "last_failure_at": recent[-1][0] if recent else None, "last_kind": recent[-1][1] if recent else None}


def seconds_remaining(provider_id: str) -> float:
    _sync()
    until = _cooldown_until.get(provider_id)
    if until is None:
        return 0.0
    return max(0.0, until - time.monotonic())


def is_in_cooldown(provider_id: str) -> bool:
    return seconds_remaining(provider_id) > 0


def reset(provider_id: str | None = None) -> None:
    """Clear cooldown state - used by tests, and available for an admin
    'force retry now' action later if that turns out to be useful."""
    global _synced_at
    if provider_id is None:
        _cooldown_until.clear()
    else:
        _cooldown_until.pop(provider_id, None)
    _synced_at = float("-inf") if provider_id is None else _synced_at
    try:
        for key in [provider_id] if provider_id else list(settings_store.read_all(_db(), "cooldowns")):
            settings_store.delete(_db(), "cooldowns", key)
    except Exception:  # noqa: BLE001
        pass


def extract_retry_after_seconds(error: Exception) -> float | None:
    """The delay the gateway reported (GatewayCallError.retry_after), else a
    Retry-After header on an attached response - prefer the server's own
    answer over guessing a fixed cooldown length."""
    direct = getattr(error, "retry_after", None)
    if isinstance(direct, (int, float)) and not isinstance(direct, bool):
        return float(direct)
    response = getattr(error, "response", None)
    if response is None:
        return None
    header = response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None
