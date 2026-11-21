"""Caps and lifetimes of the PDF and video capabilities, kept in `.data/armory/settings.db` (table `tuning`).

An administrator edits them on the Limits page of Armory Admin; nothing is read from a file. A stored document only
holds what was changed; every other value is the default below. A capability reads its document once, when its
engine first starts, so a change is used from Armory's next start.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable

from src.citadel_auth import settings_store

TABLE = "tuning"

DEFAULTS: dict[str, dict[str, Any]] = {
    "pdf_merger": {
        "file_ttl_hours": 1,
        "sweep_interval_minutes": 10,
        "download_link_minutes": 60,
        "mcp_wait_seconds": 100,
        "limits": {
            "max_file_mb": 100,
            "max_session_mb": 500,
            "max_segments": 50,
            "max_output_pages": 2000,
            "max_image_megapixels": 80,
            "max_concurrent_merges": 2,
            "job_timeout_seconds": 120,
        },
    },
    "media_downloader": {
        "file_ttl_hours": 1,
        "sweep_interval_minutes": 10,
        "download_link_minutes": 60,
        "limits": {
            "max_file_mb": 500,
            "max_duration_minutes": 120,
            "max_session_mb": 2048,
            "max_concurrent_downloads": 2,
            "max_queued_downloads": 8,
            "job_timeout_minutes": 30,
            "max_caller_downloads": 2,
        },
    },
}


class TuningError(ValueError):
    """A change is refused; the message names the setting and is safe to show."""


def _merged(name: str, stored: Any) -> dict[str, Any]:
    document = copy.deepcopy(DEFAULTS[name])
    if isinstance(stored, dict):
        for key, value in stored.items():
            if key == "limits" and isinstance(value, dict):
                document["limits"].update(value)
            else:
                document[key] = value
    return document


def document(path: Path, name: str) -> dict[str, Any]:
    """The effective document of one capability: the defaults with what was saved on top."""
    if name not in DEFAULTS:
        raise KeyError(name)
    return _merged(name, settings_store.read_all(path, TABLE).get(name))


def is_stored(path: Path, name: str) -> bool:
    return name in settings_store.read_all(path, TABLE)


def save(path: Path, name: str, changes: Any, validate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Merge `changes` into the stored document, check the whole result with `validate` (raises ValueError) and keep it.
    Nothing is saved if the result is refused. Only known keys are accepted, and every value must be a number."""
    if name not in DEFAULTS:
        raise TuningError(f"Unknown capability: {name}.")
    if not isinstance(changes, dict) or not changes:
        raise TuningError("Send at least one setting to change.")
    known = DEFAULTS[name]
    stored = settings_store.read_all(path, TABLE).get(name)
    stored = copy.deepcopy(stored) if isinstance(stored, dict) else {}
    for key, value in changes.items():
        if key == "limits":
            if not isinstance(value, dict):
                raise TuningError("limits must be an object.")
            for limit, number in value.items():
                _check(known["limits"], limit, number, f"limits.{limit}")
                stored.setdefault("limits", {})[limit] = number
        else:
            _check({k: v for k, v in known.items() if k != "limits"}, key, value, key)
            stored[key] = value
    try:
        validate(_merged(name, stored))
    except ValueError as error:
        raise TuningError(str(error)) from error
    settings_store.put(path, TABLE, name, stored)
    return _merged(name, stored)


def reset(path: Path, name: str) -> dict[str, Any]:
    """Drop what was saved; the defaults apply again."""
    if name not in DEFAULTS:
        raise TuningError(f"Unknown capability: {name}.")
    settings_store.delete(path, TABLE, name)
    return _merged(name, None)


def _check(known: dict[str, Any], key: str, value: Any, label: str) -> None:
    if key not in known:
        raise TuningError(f"Unknown setting: {label}.")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TuningError(f"{label}: use a number.")
