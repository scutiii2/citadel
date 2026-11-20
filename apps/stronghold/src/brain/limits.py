"""Short-term memory limits: built-in defaults, optionally overridden in settings.db."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.citadel_auth import settings_store

_CEILINGS = {"max_items": 200, "max_item_chars": 2000, "compact_item_chars": 6000}


@dataclass(frozen=True)
class StackLimits:
    max_items: int = 40
    max_item_chars: int = 500
    compact_item_chars: int = 1500
    warn_ratio: float = 0.8


def _whole(value: object, low: int, high: int, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(low, min(high, value))


def load_limits(path: Path) -> StackLimits:
    """Built-in defaults for anything missing or unusable; a bad file never stops Stronghold."""
    try:
        saved = settings_store.read_all(path, "brain").get("stack", {})
    except Exception:  # noqa: BLE001 - unreadable settings fall back to the defaults
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    base = StackLimits()
    ratio = saved.get("warn_ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio != ratio:
        ratio = base.warn_ratio
    else:
        ratio = max(0.3, min(0.95, ratio))
    return StackLimits(
        max_items=_whole(saved.get("max_items"), 2, _CEILINGS["max_items"], base.max_items),
        max_item_chars=_whole(saved.get("max_item_chars"), 20, _CEILINGS["max_item_chars"], base.max_item_chars),
        compact_item_chars=_whole(saved.get("compact_item_chars"), 100, _CEILINGS["compact_item_chars"], base.compact_item_chars),
        warn_ratio=ratio,
    )
