"""Admin overrides of Garrison's tuning, kept in .data/tuning_overrides.json.

It lives in .data/ (runtime state, the `agent_data` volume in Docker) rather than configs/, because configs/ is
baked into the image and an admin's change there would be lost on every rebuild.

One key so far: `classifier.triage_strategy`, the Laya service strategy the Triage Assistant uses when a request
names none. The file is read on every use, so every agent process sees a change at once and none needs a restart.
An unreadable or invalid file counts as "nothing set" and is logged; the next write replaces it. The write is
atomic (temporary file, then replace) like config_files.seed_tuning."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

OVERRIDES_PATH = Path(__file__).resolve().parent.parent.parent / ".data" / "tuning_overrides.json"

_log = logging.getLogger(__name__)


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _log.warning("%s is unreadable and ignored: %s", path.name, error)
        return {}
    if not isinstance(raw, dict):
        _log.warning("%s must be an object and is ignored", path.name)
        return {}
    return raw


def triage_strategy(path: Path | None = None) -> str | None:
    path = path or OVERRIDES_PATH
    section = _read(path).get("classifier")
    value = section.get("triage_strategy") if isinstance(section, dict) else None
    if value is not None and not (isinstance(value, str) and value.strip()):
        _log.warning("%s: classifier.triage_strategy must be a non-empty string and is ignored", path.name)
        return None
    return value


def set_triage_strategy(value: str | None, path: Path | None = None) -> None:
    path = path or OVERRIDES_PATH
    raw = _read(path)
    section = raw.get("classifier")
    section = dict(section) if isinstance(section, dict) else {}
    if value is None:
        section.pop("triage_strategy", None)
    else:
        section["triage_strategy"] = value
    raw["classifier"] = section
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump(raw, output, indent=2)
            output.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    kind: str  # "int" | "number" | "bool"
    low: float = 0.0
    high: float = 0.0
    low_open: bool = False
    high_open: bool = False


_ID = r"[a-z0-9][a-z0-9_-]{0,39}"
_VOTERS = "laya-english|laya-typed|jev"
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
_add(r"classifier\.triage_(?:fallback|trace)", Rule("bool"))
_add(r"classifier\.triage_window", Rule("int", 512, 32_768))
_add(r"classifier\.triage_prune_ratio", Rule("number", 0, 1, high_open=True))
_add(r"classifier\.triage_pair_ratio", Rule("number", 0, 1, low_open=True))
_add(rf"classifier\.triage_thresholds\.(?:2|3\+)\.(?:{_VOTERS})", Rule("number", 0, 1, low_open=True))
_add(rf"classifier\.triage_enabled\.(?:{_VOTERS})\.(?:choice|noul|score)", Rule("bool"))


def _rule_for(path: str) -> Rule:
    for pattern, rule in _RULES:
        if pattern.fullmatch(path):
            return rule
    raise TuningError(f"{path!r} cannot be edited here")


def check(path: str, value: Any) -> bool | int | float:
    """The value as it will be stored, or TuningError."""
    rule = _rule_for(path)
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
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
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
