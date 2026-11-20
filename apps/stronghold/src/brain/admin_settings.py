"""The brain limits an administrator can change: short-term memory (`stack`) and long-term memory (`long_term`).

A change is checked against the ranges in `src.brain.limits`, saved in settings.db and used at once. The brain root
is shown here but set only by STRONGHOLD_BRAIN_ROOT or the `brain/root` setting, because moving it needs a restart.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from src.brain.files import BrainFiles
from src.brain.limits import LONG_TERM_RANGES, SHARING_RANGES, STACK_RANGES, WARN_RANGE
from src.brain.stack import StackStore
from src.citadel_auth import settings_store

_RANGES = {"stack": {**STACK_RANGES, "warn_ratio": WARN_RANGE}, "long_term": LONG_TERM_RANGES, "sharing": SHARING_RANGES}


class BrainSettingsError(ValueError):
    """A change is refused; the message names the setting and is safe to show."""


def view(stacks: StackStore, files: BrainFiles, root: Path, path: Path, *, shares=None) -> dict[str, Any]:
    saved = settings_store.read_all(path, "brain")
    shown = {
        "stack": dataclasses.asdict(stacks.limits), "long_term": dataclasses.asdict(files.limits),
        "ranges": {part: {name: list(span) for name, span in spans.items()} for part, spans in _RANGES.items()},
        "root": str(root), "stored": {"stack": "stack" in saved, "long_term": "long_term" in saved},
    }
    if shares is not None:
        shown["sharing"] = dataclasses.asdict(shares.limits)
        shown["stored"]["sharing"] = "sharing" in saved
    return shown


def _checked(part: str, values: Any) -> dict[str, Any]:
    spans = _RANGES[part]
    if not isinstance(values, dict) or not values:
        raise BrainSettingsError(f"Send at least one value for {part}.")
    if set(values) - spans.keys():
        raise BrainSettingsError(f"Unknown {part} setting.")
    for name, value in values.items():
        low, high = spans[name]
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        whole = isinstance(value, int) and not isinstance(value, bool)
        if not number or (name != "warn_ratio" and not whole) or not low <= value <= high:
            raise BrainSettingsError(f"{name} must be a {'number' if name == 'warn_ratio' else 'whole number'} from {low} to {high}.")
    return values


def update(stacks: StackStore, files: BrainFiles, path: Path, changes: Any, *,
           shares=None, global_files: BrainFiles | None = None) -> None:
    """Validate all changes before saving and applying the new limits."""
    if not isinstance(changes, dict) or not changes or not set(changes) <= _RANGES.keys():
        raise BrainSettingsError("Send stack, long_term or sharing.")
    parts = {part: _checked(part, values) for part, values in changes.items()}
    saved = settings_store.read_all(path, "brain")
    for part, values in parts.items():
        stored = saved.get(part)
        settings_store.put(path, "brain", part, {**(stored if isinstance(stored, dict) else {}), **values})
        if part == "stack":
            stacks.limits = dataclasses.replace(stacks.limits, **values)
        elif part == "long_term":
            files.limits = dataclasses.replace(files.limits, **values)
            if global_files is not None:
                global_files.limits = dataclasses.replace(global_files.limits, **values)
        elif shares is not None:
            shares.limits = dataclasses.replace(shares.limits, **values)
