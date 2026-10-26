"""Validated runtime tuning overlay, saved atomically and applied on the next turn."""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

OVERLAY_NAME = "tuning_overrides.json"
PATH = Path(__file__).resolve().parent.parent.parent / "configs" / OVERLAY_NAME


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
_add(r"classifier\.auto_(?:tier|route)\.min_confidence", Rule("int", 0, 100))


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




def load(path: Path = PATH) -> dict[str, Any]:
    """What the overlay sets. An unreadable file is empty; a bad entry is skipped and logged."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        _log.warning("%s is unreadable and ignored: %s", path.name, error)
        return {}
    if not isinstance(data, dict):
        _log.warning("%s must be an object and is ignored", path.name)
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


def save(changes: dict[str, Any], path: Path = PATH) -> dict[str, Any]:
    """Apply `changes` (dotted path -> value; None = back to the file's value) and write
    the overlay atomically. Raises TuningError before writing if any change is bad."""
    current = load(path)
    for key, value in changes.items():
        _rule_for(key)
        if value is None:
            current.pop(key, None)
        else:
            current[key] = check(key, value)
    # Docker exposes the required configs path as a link into the persistent data volume.
    # Replace the target atomically, retaining the link across successive saves.
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(json.dumps(current, indent=2) + "\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return current


def signature(path: Path = PATH) -> int | None:
    """Changes whenever the overlay is rewritten; None when it does not exist."""
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
