"""The connections and cache defaults an administrator edits on the Connections page of Treasury Admin.

A saved connection replaces the built-in one of its name (or adds one); removing it brings the built-in back. A secret
never lives here: a Postgres `dsn` must be a `${NAME}` placeholder whose value is in Treasury's `.env`. A new
connection is offered to the instances at once; changing or removing one that may be open is used from the next start.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from src import config
from src.backends.factory import BACKEND_TYPES
from src.cache import CacheSettings
from src.citadel_auth import settings_store
from src.registry import InstanceManager

NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_PLACEHOLDER_ONLY = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
# The options each type reads (factory.py); anything else is refused so a typo is not saved silently.
OPTIONS = {
    "sqlite": {"path"},
    "postgres": {"dsn", "max_pool_size"},
    "firestore": {"project", "credentials_file", "database"},
}
COMMON = {"type", "allow_raw_sql", "cache"}


class ConnectionAdminError(ValueError):
    """A change is refused; the message is safe to show."""


def _env() -> dict[str, str]:
    return {k: v for k, v in {**dotenv_values(config.ENV_PATH), **os.environ}.items() if v is not None}


def default_cache(settings_db: Path) -> CacheSettings:
    saved = config.stored_default_cache(settings_db)
    return config.parse_cache(saved, CacheSettings()) if saved is not None else CacheSettings()


def check(name: str, spec: Any, settings_db: Path) -> dict[str, Any]:
    """The spec as it is saved, or ConnectionAdminError. The same parser and builder that start Treasury must accept it."""
    if not isinstance(name, str) or not NAME.match(name):
        raise ConnectionAdminError("The name must be lowercase letters, digits and _, starting with a letter.")
    if not isinstance(spec, dict) or not isinstance(spec.get("type"), str):
        raise ConnectionAdminError("A connection needs a type.")
    kind = spec["type"]
    if kind not in OPTIONS:
        raise ConnectionAdminError(f"Unknown type {kind!r} (use {', '.join(sorted(OPTIONS))}).")
    unknown = set(spec) - COMMON - OPTIONS[kind]
    if unknown:
        raise ConnectionAdminError(f"A {kind} connection takes no {', '.join(sorted(unknown))}.")
    if kind == "postgres" and not (isinstance(spec.get("dsn"), str) and _PLACEHOLDER_ONLY.match(spec["dsn"])):
        raise ConnectionAdminError('The dsn must be a placeholder like "${POSTGRES_DSN}"; keep the value in Treasury\'s .env.')
    try:
        parsed = config.parse_connections({"connections": {name: spec}}, default_cache(settings_db), _env(), config.data_dir(config.ROOT))
        BACKEND_TYPES[kind](parsed.connections[name].options)  # builds the adapter without connecting
    except config.ConfigError as error:
        raise ConnectionAdminError(str(error)) from error
    except (ValueError, TypeError) as error:
        raise ConnectionAdminError(str(error)) from error
    return spec


def view(settings_db: Path, manager: InstanceManager) -> dict[str, Any]:
    saved = config.stored_connections(settings_db)
    used = manager.describe()
    rows = []
    for name in sorted({**config.DEFAULT_CONNECTIONS, **saved}):
        spec = saved.get(name) or config.DEFAULT_CONNECTIONS[name]
        builtin = name in config.DEFAULT_CONNECTIONS
        rows.append({
            "name": name, "spec": spec,
            "source": ("changed" if name in saved else "built-in") if builtin else "saved",
            "used_by": sorted(instance for instance, members in used.items() if name in members),
        })
    cache = default_cache(settings_db)
    return {"connections": rows,
            "default_cache": {"ttl_seconds": cache.ttl_seconds, "max_entries": cache.max_entries,
                              "negative_ttl_seconds": cache.negative_ttl_seconds},
            "default_cache_stored": config.stored_default_cache(settings_db) is not None}


def save_connection(settings_db: Path, manager: InstanceManager, name: str, spec: Any) -> str:
    """Save one connection. Returns "now" when a new connection is already offered to the instances, else "next start"."""
    spec = check(name, spec, settings_db)
    settings_store.put(settings_db, config.CONNECTIONS_TABLE, name, spec)
    parsed = config.parse_connections({"connections": {name: spec}}, default_cache(settings_db), _env(), config.data_dir(config.ROOT))
    return "now" if manager.add_connection(parsed.connections[name]) else "next start"


def remove_connection(settings_db: Path, manager: InstanceManager, name: str) -> str:
    """Remove a saved connection (a built-in one comes back). Refused while an instance uses a connection that is not built-in."""
    saved = config.stored_connections(settings_db)
    if name not in saved:
        raise ConnectionAdminError("Nothing is saved for this connection." if name in config.DEFAULT_CONNECTIONS else "No such connection.")
    users = sorted(instance for instance, members in manager.describe().items() if name in members)
    if users and name not in config.DEFAULT_CONNECTIONS:
        raise ConnectionAdminError(f"Instances still use it: {', '.join(users)}.")
    settings_store.delete(settings_db, config.CONNECTIONS_TABLE, name)
    return "next start"


def save_default_cache(settings_db: Path, changes: Any) -> None:
    """Merge `changes` (ttl_seconds, max_entries, negative_ttl_seconds) into the saved cache defaults. None removes them.
    A connection that sets its own cache keeps it. Used from the next start."""
    if changes is None:
        settings_store.delete(settings_db, config.SETTINGS_TABLE, config.CACHE_KEY)
        return
    if not isinstance(changes, dict) or not changes or set(changes) - {"ttl_seconds", "max_entries", "negative_ttl_seconds"}:
        raise ConnectionAdminError("Send ttl_seconds, max_entries and/or negative_ttl_seconds.")
    current = default_cache(settings_db)
    merged = {"ttl_seconds": current.ttl_seconds, "max_entries": current.max_entries,
              "negative_ttl_seconds": current.negative_ttl_seconds, **changes}
    try:
        config.parse_cache(merged, CacheSettings())
    except config.ConfigError as error:
        raise ConnectionAdminError(str(error)) from error
    settings_store.put(settings_db, config.SETTINGS_TABLE, config.CACHE_KEY, merged)
