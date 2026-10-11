"""Typed loader for configs/config_app.json (seeded from its .example)."""

from __future__ import annotations

import json
import math
import re
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.seed import seed_from_example

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "config_app.json"
SITUATION_SOURCES = ("heuristic", "laya")


class ConfigError(ValueError):
    """config_app.json is missing a field or holds a bad value."""


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    database_path: Path
    situation_source: str
    laya_timeout_seconds: float
    laya_min_confidence: float
    emblem_prompt_seconds: float
    encounter_cooldown_seconds: float
    faint_seconds: float
    ember_api_url: str
    ember_origin: str
    session_hours: float
    game_id: str
    dev_fake_owner: str


def _number(raw: dict[str, Any], key: str, kind: type, minimum: float, maximum: float | None = None) -> Any:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"{key} must be a finite number")
    if kind is int and value != int(value):
        raise ConfigError(f"{key} must be a whole number")
    if value < minimum:
        raise ConfigError(f"{key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{key} must be at most {maximum}")
    return kind(value)


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def _path(raw: dict[str, Any], key: str, root: Path) -> Path:
    path = Path(_text(raw, key))
    return path if path.is_absolute() else root / path


class GameHostConfigParser:
    """Validate new host settings, including the single origin used by CSP."""
    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    def url(self, key: str, *, origin: bool = False) -> str:
        value = _text(self._raw, key)
        if any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
            raise ConfigError(f"{key} must be an http(s) URL")
        try:
            parts = urlsplit(value)
            port = parts.port
        except ValueError as error:
            raise ConfigError(f"{key} must be an http(s) URL") from error
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None or parts.password is not None:
            raise ConfigError(f"{key} must be an http(s) URL without credentials")
        if parts.query or parts.fragment or (origin and parts.path not in ("", "/")):
            raise ConfigError(f"{key} must be {'an origin' if origin else 'a base URL'}")
        host = parts.hostname.lower()
        if any(c in host for c in ";,%*"):
            raise ConfigError(f"{key} must be an http(s) URL")
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        return urlunsplit((parts.scheme, authority, parts.path.rstrip("/"), "", ""))

    def game_id(self) -> str:
        value = _text(self._raw, "game_id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
            raise ConfigError("game_id must be a lowercase game slug")
        return value

    def dev_owner(self) -> str:
        value = self._raw.get("dev_fake_owner")
        if not isinstance(value, str):
            raise ConfigError("dev_fake_owner must be a string (empty disables it)")
        return value


def parse_config(raw: Any, root: Path = PROJECT_ROOT) -> AppConfig:
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object")
    host_config = GameHostConfigParser(raw)
    source = _text(raw, "situation_source")
    if source not in SITUATION_SOURCES:
        raise ConfigError(f"situation_source must be one of {', '.join(SITUATION_SOURCES)}")
    return AppConfig(
        host=_text(raw, "host"),
        port=_number(raw, "port", int, 1, 65535),
        database_path=_path(raw, "database_path", root),
        situation_source=source,
        laya_timeout_seconds=_number(raw, "laya_timeout_seconds", float, 0.1),
        laya_min_confidence=_number(raw, "laya_min_confidence", float, 0.01, 1.0),
        emblem_prompt_seconds=_number(raw, "emblem_prompt_seconds", float, 0.1),
        encounter_cooldown_seconds=_number(raw, "encounter_cooldown_seconds", float, 0.0),
        faint_seconds=_number(raw, "faint_seconds", float, 0.0),
        ember_api_url=host_config.url("ember_api_url"),
        ember_origin=host_config.url("ember_origin", origin=True),
        session_hours=_number(raw, "session_hours", float, 0.01),
        game_id=host_config.game_id(),
        dev_fake_owner=host_config.dev_owner(),
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
    return parse_config(raw)
