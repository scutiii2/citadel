"""Typed loaders for configs/config_app.json and configs/config_connections.json
(each seeded from its .example on first run)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from src.cache import CacheSettings
from src.seed import seed_from_example

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "configs" / "config_app.json"
CONNECTIONS_PATH = ROOT / "configs" / "config_connections.json"
ENV_PATH = ROOT / ".env"
PORT_ENV_VAR = "DB_GATEWAY_PORT"
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(ValueError):
    """A config file is missing a field or holds a bad value."""


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    default_cache: CacheSettings


@dataclass(frozen=True)
class ConnectionSpec:
    name: str
    type: str
    options: dict[str, Any]
    cache: CacheSettings
    allow_raw_sql: bool = False


@dataclass(frozen=True)
class ConnectionsConfig:
    connections: dict[str, ConnectionSpec] = field(default_factory=dict)
    instances: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _number(raw: dict[str, Any], key: str, default: float, minimum: float = 0) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(f"{key} must be a number of at least {minimum}")
    return float(value)


def parse_cache(raw: Any, base: CacheSettings) -> CacheSettings:
    """Cache settings, with any missing key taken from `base`."""
    if raw is None:
        return base
    if not isinstance(raw, dict):
        raise ConfigError("cache must be an object")
    return CacheSettings(
        ttl_seconds=_number(raw, "ttl_seconds", base.ttl_seconds),
        max_entries=int(_number(raw, "max_entries", base.max_entries)),
        negative_ttl_seconds=_number(raw, "negative_ttl_seconds", base.negative_ttl_seconds),
    )


def parse_app_config(raw: Any) -> AppConfig:
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object")
    host = raw.get("host")
    if not isinstance(host, str) or not host:
        raise ConfigError("host must be a non-empty string")
    return AppConfig(
        host=host,
        port=int(_number(raw, "port", 0, 1)),
        default_cache=parse_cache(raw.get("default_cache"), CacheSettings()),
    )


def _expand(value: Any, env: dict[str, str]) -> Any:
    """Replace ${NAME} in strings (recursively) with values from the environment or .env."""
    if isinstance(value, str):
        def lookup(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in env:
                raise ConfigError(f"${{{name}}} is not set in the environment or .env")
            return env[name]

        return _PLACEHOLDER.sub(lookup, value)
    if isinstance(value, dict):
        return {k: _expand(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, env) for v in value]
    return value


def parse_connections(raw: Any, default_cache: CacheSettings, env: dict[str, str] | None = None) -> ConnectionsConfig:
    if not isinstance(raw, dict):
        raise ConfigError("connections config must be a JSON object")
    env = env or {}
    connections: dict[str, ConnectionSpec] = {}
    for name, spec in (raw.get("connections") or {}).items():
        if not isinstance(spec, dict) or not isinstance(spec.get("type"), str):
            raise ConfigError(f"connection {name!r} needs a string 'type'")
        options = {k: v for k, v in _expand(spec, env).items() if k not in ("type", "cache", "allow_raw_sql")}
        allow_sql = spec.get("allow_raw_sql", False)
        if not isinstance(allow_sql, bool):
            raise ConfigError(f"connection {name!r}: allow_raw_sql must be true or false")
        connections[name] = ConnectionSpec(
            name, spec["type"], options, parse_cache(spec.get("cache"), default_cache), allow_sql
        )
    instances: dict[str, tuple[str, ...]] = {}
    for name, members in (raw.get("instances") or {}).items():
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            raise ConfigError(f"instance {name!r} must list connection names")
        unknown = [m for m in members if m not in connections]
        if unknown:
            raise ConfigError(f"instance {name!r} references unknown connection(s): {', '.join(unknown)}")
        instances[name] = tuple(dict.fromkeys(members))
    return ConnectionsConfig(connections, instances)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error


def load_config(path: Path | None = None) -> AppConfig:
    """Load the app config. With no path, use configs/config_app.json and create
    it from the .example on first run."""
    if path is None:
        path = CONFIG_PATH
        seed_from_example(path)
    config = parse_app_config(_read_json(path))
    override = os.getenv(PORT_ENV_VAR)
    if override:  # a launcher or container passes the port it assigned
        try:
            port = int(override)
        except ValueError as error:
            raise ConfigError(f"{PORT_ENV_VAR} must be a port number, got {override!r}") from error
        if not 1 <= port <= 65535:
            raise ConfigError(f"{PORT_ENV_VAR} must be from 1 to 65535, got {port}")
        config = replace(config, port=port)
    return config


def load_connections(default_cache: CacheSettings, path: Path | None = None) -> ConnectionsConfig:
    """Load connections and instances. With no path, use configs/config_connections.json
    (seeded from its .example) and resolve ${NAME} from the environment and .env."""
    env: dict[str, str] = {}
    if path is None:
        path = CONNECTIONS_PATH
        seed_from_example(path)
        seed_from_example(ENV_PATH)
        env = {k: v for k, v in {**dotenv_values(ENV_PATH), **os.environ}.items() if v is not None}
    return parse_connections(_read_json(path), default_cache, env)
