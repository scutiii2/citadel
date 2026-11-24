"""Validated runtime tuning overrides, kept in Legion's settings database and applied on the next turn.

An admin's edits on the Tuning page are rows of the `tuning` table in `.data/legion/settings.db`, keyed by
dotted path (`token_limits.default.max_tool_rounds`). config_tuning.json holds the defaults they sit on."""
from __future__ import annotations

import copy
import json
import logging
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.citadel_auth import data_dir, settings_store

_log = logging.getLogger(__name__)

TABLE = "tuning"
# Admin edits are runtime state: they live in the Citadel .data folder, not in the tracked configs/.
PATH = data_dir(Path(__file__).resolve().parents[2]) / "settings.db"
# Where earlier versions kept them: read once into the table, then renamed.
LEGACY_FILE = "tuning_overrides.json"
# Rows of the short-lived `tool_batch` table, now `tool_batch.*` paths of this one.
LEGACY_TABLE = "tool_batch"


class TuningError(Exception):
    """A rejected change; the message is safe to show."""


@dataclass(frozen=True)
class Rule:
    kind: str  # "int" | "number" | "bool" | "enum"
    low: float = 0.0
    high: float = 0.0
    low_open: bool = False
    high_open: bool = False


_ID = r"[a-z0-9][a-z0-9_-]{0,39}"
_RULES: list[tuple[re.Pattern[str], Rule]] = []


def _add(pattern: str, rule: Rule) -> None:
    _RULES.append((re.compile(pattern), rule))



for _field, _rule in {
    "max_output_tokens": Rule("int", 1, 200_000),
    "max_context_tokens": Rule("int", 1_000, 2_000_000),
    "max_tool_rounds": Rule("int", 1, 100),
}.items():
    _add(rf"token_limits\.{_ID}\.{_field}", _rule)
    _add(rf"token_limits\.{_ID}\.gateways\.{_ID}\.{_field}", _rule)
_add(r"gateway_failover\.(?:quota|auth|unavailable)_cooldown_seconds", Rule("number", 0, 604_800))
_add(r"classifier\.timeout_seconds", Rule("number", 0, 60, low_open=True))
_add(r"classifier\.max_input_chars", Rule("int", 1, 1_000_000))
_add(r"classifier\.auto_(?:tier|route)\.strategy", Rule("enum"))
_add(r"classifier\.auto_(?:tier|route)\.min_confidence", Rule("int", 1, 100))
for _field, _rule in {
    "parallel": Rule("bool"), "max_parallel": Rule("int", 1, 16), "batch_tool": Rule("bool"),
    "max_steps": Rule("int", 2, 20), "max_result_chars": Rule("int", 1_000, 100_000),
    "max_total_chars": Rule("int", 5_000, 200_000),
}.items():
    _add(rf"tool_batch\.{_field}", _rule)  # the executor's limits (tool_batch_settings.py)


def _rule_for(path: str) -> Rule:
    for pattern, rule in _RULES:
        if pattern.fullmatch(path):
            return rule
    raise TuningError(f"{path!r} cannot be edited here")


def check(path: str, value: Any) -> bool | int | float | str:
    """The value as it will be stored, or TuningError."""
    rule = _rule_for(path)
    if rule.kind == "enum":
        from src.providers.decision import strategy

        if not isinstance(value, str) or value not in strategy.STRATEGIES:
            raise TuningError(f"{path} must be one of {', '.join(strategy.STRATEGIES)}")
        return value
    if rule.kind == "bool":
        if not isinstance(value, bool):
            raise TuningError(f"{path} must be true or false")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (rule.kind == "int" and not isinstance(value, int)):
        raise TuningError(f"{path} must be a {'whole ' if rule.kind == 'int' else ''}number")
    above = value > rule.low if rule.low_open else value >= rule.low
    below = value < rule.high if rule.high_open else value <= rule.high
    if not (above and below):  # NaN fails both
        raise TuningError(f"{path} must be {'above' if rule.low_open else 'from'} {rule.low:g} and {'below' if rule.high_open else 'up to'} {rule.high:g}")
    return value if rule.kind == "int" else float(value)




_migrated: set[Path] = set()


def _migrate(path: Path) -> None:
    """Once per process: copy the legacy overlay file and `tool_batch` rows into the table. A path an admin
    already stored wins over a legacy one. The legacy file is renamed, never deleted."""
    if path in _migrated:
        return
    _migrated.add(path)
    legacy = path.with_name(LEGACY_FILE)
    old: dict[str, Any] = {}
    try:
        if legacy.exists():
            data = json.loads(legacy.read_text(encoding="utf-8"))
            old = data if isinstance(data, dict) else {}
        if path.exists():
            old.update({f"tool_batch.{key}": value for key, value in settings_store.read_all(path, LEGACY_TABLE).items()})
        if not old:
            return
        stored = settings_store.read_all(path, TABLE)
        for key, value in old.items():
            try:
                if key not in stored:
                    settings_store.put(path, TABLE, key, check(key, value))
            except TuningError as error:
                _log.warning("ignoring legacy tuning %s: %s", key, error)
            if key.startswith("tool_batch."):
                settings_store.delete(path, LEGACY_TABLE, key[len("tool_batch."):])
        if legacy.exists():
            legacy.rename(legacy.with_suffix(".json.migrated"))
    except (OSError, ValueError, sqlite3.Error) as error:
        _log.warning("could not carry the old tuning overrides over: %s", error)
        _migrated.discard(path)


def load(path: Path = PATH) -> dict[str, Any]:
    """What the admin set. An unreadable store is empty; a bad entry is skipped and logged."""
    try:
        _migrate(path)
        data = settings_store.read_all(path, TABLE)
    except (OSError, ValueError, sqlite3.Error) as error:
        _log.warning("%s is unreadable and ignored: %s", path.name, error)
        return {}
    good: dict[str, Any] = {}
    for key, value in data.items():
        try:
            good[key] = check(key, value)
        except TuningError as error:
            _log.warning("ignoring %s in %s: %s", key, path.name, error)
    return good


def apply(raw: dict[str, Any], path: Path = PATH) -> dict[str, Any]:
    """`raw` (config_tuning.json's object) with the overlay set on top; `raw` itself is not changed."""
    changes = load(path)
    if not changes:
        return raw
    merged = copy.deepcopy(raw)
    for dotted, value in changes.items():
        *parents, leaf = dotted.split(".")
        node = merged
        for part in parents:
            child = node.get(part)
            if not isinstance(child, dict):
                child = node[part] = {}
            node = child
        node[leaf] = value
    return merged


def validate(changes: dict[str, Any]) -> None:
    """Raise TuningError when any change names a path that cannot be edited or fails its rule (None resets one)."""
    for key, value in changes.items():
        _rule_for(key)
        if value is not None:
            check(key, value)


def save(changes: dict[str, Any], path: Path = PATH) -> dict[str, Any]:
    """Apply `changes` (dotted path -> value; None = back to the file's value) to the table.
    Raises TuningError before writing if any change is bad."""
    validate(changes)
    _migrate(path)
    for key, value in changes.items():
        if value is None:
            settings_store.delete(path, TABLE, key)
        else:
            settings_store.put(path, TABLE, key, check(key, value))
    return load(path)


def signature(path: Path = PATH) -> int | None:
    """Changes whenever the settings database is written; None when it does not exist."""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


_resets: list[Callable[[], None]] = []
_seen: int | None = None  # the overlay signature this process last acted on


def on_change(reset: Callable[[], None]) -> None:
    """Run `reset` (a reader's reset_cache) when poll() sees the overlay changed."""
    _resets.append(reset)


def poll(path: Path | None = None) -> None:
    """Call at the start of a turn. One stat; runs the registered resets only when the
    overlay was rewritten since the last call in this process. A failing reset is logged,
    never raised: a turn must not break because an edit was bad."""
    global _seen
    current = signature(path or PATH)
    if current == _seen:
        return
    _seen = current
    for reset in _resets:
        try:
            reset()
        except Exception:
            _log.exception("tuning reset %s failed", getattr(reset, "__name__", reset))
