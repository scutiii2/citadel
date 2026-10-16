"""Typed loader for configs/config_app.json (seeded from its .example)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from src.seed import seed_from_example

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "config_app.json"
PICKER_NAMES = ("engine", "variety", "laya")
MAX_CANDIDATES = 10
PORT_ENV_VAR = "CHESS_PORT"


class ConfigError(ValueError):
    """config_app.json is missing a field or holds a bad value."""


@dataclass(frozen=True)
class Difficulty:
    depth: int
    k: int
    time_limit: float
    trust_uncertain: bool


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    session_ttl_seconds: float
    max_sessions_per_user: int
    laya_timeout_seconds: float
    default_picker: dict[str, str]
    difficulties: dict[str, Difficulty]


def _number(raw: dict[str, Any], key: str, kind: type, minimum: float) -> Any:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(f"{key} must be a number of at least {minimum}")
    return kind(value)


def _difficulty(name: str, raw: Any) -> Difficulty:
    if not isinstance(raw, dict):
        raise ConfigError(f"difficulty {name!r} must be an object")
    depth = _number(raw, "depth", int, 1)
    k = _number(raw, "k", int, 1)
    if k > MAX_CANDIDATES:
        raise ConfigError(f"difficulty {name!r}: k must be at most {MAX_CANDIDATES}")
    trust = raw.get("trust_uncertain")
    if not isinstance(trust, bool):
        raise ConfigError(f"difficulty {name!r}: trust_uncertain must be true or false")
    return Difficulty(depth, k, _number(raw, "time_limit", float, 0.1), trust)


def parse_config(raw: Any) -> AppConfig:
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object")
    host = raw.get("host")
    if not isinstance(host, str) or not host:
        raise ConfigError("host must be a non-empty string")
    pickers = raw.get("default_picker")
    if not isinstance(pickers, dict) or any(v not in PICKER_NAMES for v in pickers.values()):
        raise ConfigError(f"default_picker must map game ids to one of {', '.join(PICKER_NAMES)}")
    difficulties = raw.get("difficulties")
    if not isinstance(difficulties, dict) or not difficulties:
        raise ConfigError("difficulties must be a non-empty object")
    return AppConfig(
        host=host,
        port=_number(raw, "port", int, 1),
        session_ttl_seconds=_number(raw, "session_ttl_seconds", float, 1),
        max_sessions_per_user=_number(raw, "max_sessions_per_user", int, 1),
        laya_timeout_seconds=_number(raw, "laya_timeout_seconds", float, 0.1),
        default_picker=dict(pickers),
        difficulties={name: _difficulty(name, spec) for name, spec in difficulties.items()},
    )


def load_config(path: Path | None = None) -> AppConfig:
    """Load and validate the config. With no path, use configs/config_app.json
    and create it from the .example on first run."""
    if path is None:
        path = CONFIG_PATH
        seed_from_example(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    config = parse_config(raw)
    override = os.getenv(PORT_ENV_VAR)
    if override:  # server_launcher passes the port it assigned
        try:
            port = int(override)
        except ValueError as error:
            raise ConfigError(f"{PORT_ENV_VAR} must be a port number, got {override!r}") from error
        if not 1 <= port <= 65535:
            raise ConfigError(f"{PORT_ENV_VAR} must be from 1 to 65535, got {port}")
        config = replace(config, port=port)
    return config
