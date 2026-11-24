"""Run-time settings of the tool-call executor.

They are `tool_batch.<name>` paths of the Tuning page (runtime/tuning_overrides.py, table `tuning` of
Legion's settings database), so no config file or environment variable holds them. A missing row means
the default below. Each agent process re-reads the table when the database file changes, so an edit
applies from the next round of tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.runtime import tuning_overrides

PREFIX = "tool_batch."

DEFAULTS: dict[str, Any] = {
    "parallel": True,
    "max_parallel": 8,
    "batch_tool": True,
    "max_steps": 10,
    "max_result_chars": 20_000,
    "max_total_chars": 60_000,
}


@dataclass(frozen=True)
class Settings:
    parallel: bool = True
    max_parallel: int = 8
    batch_tool: bool = True
    max_steps: int = 10
    max_result_chars: int = 20_000
    max_total_chars: int = 60_000


def is_ours(path: str) -> bool:
    return path.startswith(PREFIX)


def overrides(db: Path | None = None) -> dict[str, Any]:
    """The values an admin set, as `tool_batch.<name>` paths."""
    return {key: value for key, value in tuning_overrides.load(db or tuning_overrides.PATH).items() if is_ours(key)}


_cache: tuple[int | None, Settings] | None = None


def current(db: Path | None = None) -> Settings:
    """The effective settings; the table is read again only when the database file has changed."""
    global _cache
    path = db or tuning_overrides.PATH
    try:
        stamp: int | None = path.stat().st_mtime_ns
    except OSError:
        stamp = None
    if db is None and _cache is not None and _cache[0] == stamp:
        return _cache[1]
    values = {**DEFAULTS, **{key[len(PREFIX):]: value for key, value in overrides(path).items()}}
    result = Settings(**values)
    if db is None:
        _cache = (stamp, result)
    return result
