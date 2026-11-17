"""Paths and the shared parse step for Legion's startup config
files under configs/. Each consumer keeps its own validation; this only
locates the file and reads one top-level section of it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.runtime import tuning_overrides

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "configs"

# Runtime tuning shares one file; the MCP server list stays separate.
TUNING_PATH = CONFIGS_DIR / "config_tuning.json"  # token_limits
SERVERS_PATH = CONFIGS_DIR / "config_servers.json"  # servers

_REQUIRED = object()


def read_section(path: Path, section: str, default: Any = _REQUIRED) -> Any:
    """`section` of the JSON object in `path`. Raises ValueError if the file is
    not an object or the section is absent and no `default` was given."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be an object")
    if path.name == TUNING_PATH.name:
        overlay = tuning_overrides.PATH if path == TUNING_PATH else path.with_name(tuning_overrides.OVERLAY_NAME)
        raw = tuning_overrides.apply(raw, overlay)
    if section not in raw:
        if default is _REQUIRED:
            raise ValueError(f"{path.name} must contain a '{section}' section")
        return default
    return raw[section]


def _editable(raw: dict[str, Any]) -> dict[str, Any]:
    out = {name: raw[name] for name in ("token_limits", "gateway_failover") if name in raw}
    classifier = raw.get("classifier", {})
    if isinstance(classifier, dict):
        section = {k: classifier[k] for k in ("timeout_seconds", "max_input_chars") if k in classifier}
        from src.providers.decision.settings import AutoTierSettings, AutoRouteSettings

        for feature, defaults in (("auto_tier", AutoTierSettings()), ("auto_route", AutoRouteSettings())):
            value = classifier.get(feature, {})
            if isinstance(value, dict):
                section[feature] = {k: value.get(k, getattr(defaults, k)) for k in ("strategy", "min_confidence")}
        out["classifier"] = section
    return out


def tuning_view(path: Path = TUNING_PATH) -> dict[str, Any]:
    """What the admin page shows: the file's editable values, the admin's changes, and the two merged."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be an object")
    overlay = tuning_overrides.PATH if path == TUNING_PATH else path.with_name(tuning_overrides.OVERLAY_NAME)
    return {
        "defaults": _editable(raw),
        "overrides": tuning_overrides.load(overlay),
        "effective": _editable(tuning_overrides.apply(raw, overlay)),
    }
