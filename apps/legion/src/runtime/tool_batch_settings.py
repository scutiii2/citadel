"""Run-time settings of the tool-call executor, kept in Legion's settings database.

They are edited on the Tuning page of the admin app, which saves them through `/agents/tuning`
(paths `tool_batch.<name>`), so no config file or environment variable holds them. A missing row
means the default below. Each agent process re-reads the table when its file changes, so an edit
applies from the next round of tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.citadel_auth import settings_store
from src.runtime import tuning_overrides
from src.runtime.config_files import SETTINGS_DB

TABLE = "tool_batch"
PREFIX = "tool_batch."

DEFAULTS: dict[str, Any] = {
    "parallel": True,
    "max_parallel": 8,
    "batch_tool": True,
    "max_steps": 10,
    "max_result_chars": 20_000,
    "max_total_chars": 60_000,
}

for _field, _rule in {
    "parallel": tuning_overrides.Rule("bool"),
    "max_parallel": tuning_overrides.Rule("int", 1, 16),
    "batch_tool": tuning_overrides.Rule("bool"),
    "max_steps": tuning_overrides.Rule("int", 2, 20),
    "max_result_chars": tuning_overrides.Rule("int", 1_000, 100_000),
    "max_total_chars": tuning_overrides.Rule("int", 5_000, 200_000),
}.items():
    tuning_overrides.add_rule(rf"tool_batch\.{_field}", _rule)


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
    """The values an admin set, as `tool_batch.<name>` paths. A row that no longer passes its rule is ignored."""
    good: dict[str, Any] = {}
    for key, value in settings_store.read_all(db or SETTINGS_DB, TABLE).items():
        try:
            good[PREFIX + key] = tuning_overrides.check(PREFIX + key, value)
        except tuning_overrides.TuningError:
            continue
    return good


def validate(changes: dict[str, Any]) -> None:
    """Raise TuningError when any change is not an editable path or fails its rule (None clears one)."""
    for path, value in changes.items():
        tuning_overrides.check(path, DEFAULTS.get(path[len(PREFIX):]) if value is None else value)


def save(changes: dict[str, Any], db: Path | None = None) -> None:
    """Write `changes` (`tool_batch.<name>` -> value; None puts the default back). Nothing is written if one is refused."""
    validate(changes)
    path = db or SETTINGS_DB
    for key, value in changes.items():
        name = key[len(PREFIX):]
        if value is None:
            settings_store.delete(path, TABLE, name)
        else:
            settings_store.put(path, TABLE, name, tuning_overrides.check(key, value))


_cache: tuple[int | None, Settings] | None = None


def current(db: Path | None = None) -> Settings:
    """The effective settings; the table is read again only when the database file has changed."""
    global _cache
    path = db or SETTINGS_DB
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
