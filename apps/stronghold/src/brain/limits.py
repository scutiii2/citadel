"""Brain limits: built-in defaults, optionally overridden in settings.db (table `brain`).

Short-term memory (key `stack`) and long-term memory (key `long_term`) each have a frozen limits object.
The ranges below are the one source for clamping a stored value and for refusing a bad admin change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.citadel_auth import settings_store

STACK_RANGES = {"max_items": (2, 200), "max_item_chars": (20, 2000), "compact_item_chars": (100, 6000)}
WARN_RANGE = (0.3, 0.95)
LONG_TERM_RANGES = {
    "max_record_chars": (200, 100_000),
    "max_files": (1, 5_000),
    "max_total_bytes": (10_000, 100_000_000),
    "search_limit": (1, 30),
}


@dataclass(frozen=True)
class StackLimits:
    max_items: int = 40
    max_item_chars: int = 500
    compact_item_chars: int = 1500
    warn_ratio: float = 0.8


@dataclass(frozen=True)
class LongTermLimits:
    max_record_chars: int = 20_000
    max_files: int = 500
    max_total_bytes: int = 5_000_000
    search_limit: int = 8


def _whole(value: object, low: int, high: int, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(low, min(high, value))


def _saved(path: Path, key: str) -> dict:
    try:
        saved = settings_store.read_all(path, "brain").get(key, {})
    except Exception:  # noqa: BLE001 - unreadable settings fall back to the defaults
        return {}
    return saved if isinstance(saved, dict) else {}


def load_limits(path: Path) -> StackLimits:
    """Built-in defaults for anything missing or unusable; a bad file never stops Stronghold."""
    saved = _saved(path, "stack")
    base = StackLimits()
    ratio = saved.get("warn_ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio != ratio:
        ratio = base.warn_ratio
    else:
        ratio = max(WARN_RANGE[0], min(WARN_RANGE[1], ratio))
    return StackLimits(
        max_items=_whole(saved.get("max_items"), *STACK_RANGES["max_items"], base.max_items),
        max_item_chars=_whole(saved.get("max_item_chars"), *STACK_RANGES["max_item_chars"], base.max_item_chars),
        compact_item_chars=_whole(saved.get("compact_item_chars"), *STACK_RANGES["compact_item_chars"], base.compact_item_chars),
        warn_ratio=ratio,
    )


def load_long_term(path: Path) -> LongTermLimits:
    saved = _saved(path, "long_term")
    base = LongTermLimits()
    return LongTermLimits(**{
        name: _whole(saved.get(name), *LONG_TERM_RANGES[name], getattr(base, name)) for name in LONG_TERM_RANGES
    })


def brain_root(data_dir: Path, settings_path: Path) -> Path:
    """Where the account folders live: STRONGHOLD_BRAIN_ROOT, else the `brain/root` setting, else <data dir>/brain."""
    from_env = os.environ.get("STRONGHOLD_BRAIN_ROOT", "").strip()
    if from_env:
        return Path(from_env)
    try:
        saved = settings_store.read_all(settings_path, "brain").get("root")
    except Exception:  # noqa: BLE001 - same fallback as the limits
        saved = None
    if isinstance(saved, str) and saved.strip():
        return Path(saved.strip())
    return data_dir / "brain"
