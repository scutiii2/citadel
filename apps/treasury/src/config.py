"""Typed loaders for configs/config_app.json (host and port), the connections and the registered instances.

The connections are built-in defaults (the four local SQLite databases) with what an administrator saved on the
Connections page of Treasury Admin on top, kept in the settings database. The cache defaults are saved there too."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from src.cache import CacheSettings
from src.citadel_auth import apply_root_env, data_dir, settings_store
from src.seed import seed_from_example

ROOT = Path(__file__).resolve().parent.parent
apply_root_env(ROOT)  # the Citadel root .env overrides this service's .env
CONFIG_PATH = ROOT / "configs" / "config_app.json"
# Which connections an instance may use is registered by the service that owns the instance (PUT /instances/{name}).
# The registrations are kept in the `instances` table of Treasury's settings database, so a restart keeps them.
SETTINGS_DB = data_dir(ROOT) / "settings.db"
ENV_PATH = ROOT / ".env"
PORT_ENV_VAR = "DB_GATEWAY_PORT"
CONNECTIONS_TABLE = "connections"
SETTINGS_TABLE = "settings"
CACHE_KEY = "default_cache"
# Every install starts with these, so the other services can store their data before anyone has opened the admin page.
# A saved connection of the same name replaces one; "Use the built-in" on the page removes the saved one.
DEFAULT_CONNECTIONS: dict[str, dict[str, Any]] = {
    "main": {"type": "sqlite", "path": "main.db", "allow_raw_sql": False},
    "data": {"type": "sqlite", "path": "ember.db"},
    "stronghold": {"type": "sqlite", "path": "stronghold.db"},
    "scratch": {"type": "sqlite", "path": "scratch.db", "allow_raw_sql": True, "cache": {"ttl_seconds": 0}},
}
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


def parse_connections(raw: Any, default_cache: CacheSettings, env: dict[str, str] | None = None,
                      data_root: Path | None = None) -> ConnectionsConfig:
    """`data_root`: a relative sqlite `path` is placed under it (Treasury's runtime data folder)."""
    if not isinstance(raw, dict):
        raise ConfigError("connections config must be a JSON object")
    env = env or {}
    connections: dict[str, ConnectionSpec] = {}
    for name, spec in (raw.get("connections") or {}).items():
        if not isinstance(spec, dict) or not isinstance(spec.get("type"), str):
            raise ConfigError(f"connection {name!r} needs a string 'type'")
        options = {k: v for k, v in _expand(spec, env).items() if k not in ("type", "cache", "allow_raw_sql")}
        if data_root is not None and spec["type"] == "sqlite" and isinstance(options.get("path"), str):
            if options["path"] != ":memory:" and not Path(options["path"]).is_absolute():
                options["path"] = str(data_root / options["path"])
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


def stored_connections(settings_db: Path) -> dict[str, dict[str, Any]]:
    return {name: spec for name, spec in settings_store.read_all(settings_db, CONNECTIONS_TABLE).items() if isinstance(spec, dict)}


def stored_default_cache(settings_db: Path) -> dict[str, Any] | None:
    saved = settings_store.read_all(settings_db, SETTINGS_TABLE).get(CACHE_KEY)
    return saved if isinstance(saved, dict) else None


def connections_raw(settings_db: Path) -> dict[str, dict[str, Any]]:
    """The built-in connections with the saved ones on top (a saved one replaces the built-in of its name)."""
    return {**DEFAULT_CONNECTIONS, **stored_connections(settings_db)}


def load_config(path: Path | None = None) -> AppConfig:
    """Load the app config. With no path, use configs/config_app.json, and the cache defaults saved in Treasury Admin."""
    use_stored = path is None
    if path is None:
        path = CONFIG_PATH
    config = parse_app_config(_read_json(path))
    if use_stored and (saved := stored_default_cache(SETTINGS_DB)) is not None:
        config = replace(config, default_cache=parse_cache(saved, config.default_cache))
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
    """Load connections and instances. With no path, the connections are the built-in ones with the saved ones on
    top (${NAME} resolved from the environment and .env) and the instances are the ones registered so far, all from
    the settings database. With a path, one file holds both."""
    env: dict[str, str] = {}
    data_root = None
    if path is None:
        data_root = data_dir(ROOT)
        seed_from_example(ENV_PATH)
        env = {k: v for k, v in {**dotenv_values(ENV_PATH), **os.environ}.items() if v is not None}
        raw = {"connections": connections_raw(SETTINGS_DB), "instances": settings_store.read_all(SETTINGS_DB, "instances")}
        return parse_connections(raw, default_cache, env, data_root)
    return parse_connections(_read_json(path), default_cache, env, data_root)
