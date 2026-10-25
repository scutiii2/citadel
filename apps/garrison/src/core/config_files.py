"""Paths and the shared seed-and-parse step for ai_agent's startup config
files under configs/. Each consumer keeps its own validation; this only
locates the file and reads one top-level section of it."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from src.core import tuning_overrides
from src.core.seed import seed_from_example

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "configs"

# Runtime tuning shares one file; the MCP server list stays separate.
TUNING_PATH = CONFIGS_DIR / "config_tuning.json"  # token_limits
SERVERS_PATH = CONFIGS_DIR / "config_servers.json"  # servers

_REQUIRED = object()


def read_section(path: Path, section: str, default: Any = _REQUIRED) -> Any:
    """`section` of the JSON object in `path` (seeded from its .example if
    missing). Raises ValueError if the file is not an object or the section
    is absent and no `default` was given."""
    if path.name == TUNING_PATH.name:
        seed_tuning(path)
    else:
        seed_from_example(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be an object")
    if path.name == TUNING_PATH.name:
        raw = tuning_overrides.apply(raw, path.with_name(tuning_overrides.OVERLAY_NAME))
    if section not in raw:
        if default is _REQUIRED:
            raise ValueError(f"{path.name} must contain a '{section}' section")
        return default
    return raw[section]


def seed_tuning(path: Path = TUNING_PATH) -> None:
    """Seed shared tuning, preserving a legacy config_limits.json and keeping it
    as a rollback backup. An existing tuning file is always authoritative.
    Publish the complete JSON atomically so parallel agent starts never
    read a partially written migration.
    """
    if path.exists():
        return
    legacy = path.parent / "config_limits.json"
    if not legacy.exists():
        seed_from_example(path)
        return
    example = path.with_name(path.name + ".example")
    raw = json.loads(example.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{example.name} must be an object")
    raw["token_limits"] = read_section(legacy, "token_limits")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump(raw, output, indent=2)
            output.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


# classifier keys an admin edits only in the file: endpoints, models and routing.
_FILE_ONLY_CLASSIFIER = ("typesafe", "vercel", "chains", "triage_order", "auto_tier", "auto_route")


def _editable(raw: dict[str, Any]) -> dict[str, Any]:
    out = {name: raw[name] for name in ("token_limits", "gateway_failover") if name in raw}
    classifier = raw.get("classifier")
    if isinstance(classifier, dict):
        out["classifier"] = {k: v for k, v in classifier.items() if k not in _FILE_ONLY_CLASSIFIER}
    return out


def tuning_view(path: Path = TUNING_PATH) -> dict[str, Any]:
    """What the admin page shows: the file's editable values, the admin's changes, and the two merged."""
    seed_tuning(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be an object")
    overlay = path.with_name(tuning_overrides.OVERLAY_NAME)
    return {
        "defaults": _editable(raw),
        "overrides": tuning_overrides.load(overlay),
        "effective": _editable(tuning_overrides.apply(raw, overlay)),
    }
