"""Build a backend from a connection spec. Add a new database type by adding one entry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.backends.base import DatabaseBackend
from src.backends.sqlite import SqliteBackend
from src.cache import CachedBackend
from src.config import ROOT, ConfigError, ConnectionSpec


def _sqlite(options: dict[str, Any]) -> DatabaseBackend:
    path = options.get("path")
    if not isinstance(path, str) or not path:
        raise ConfigError("sqlite connection needs a 'path'")
    return SqliteBackend(path if path == ":memory:" else ROOT / path)


def _postgres(options: dict[str, Any]) -> DatabaseBackend:
    from src.backends.postgres import PostgresBackend

    dsn = options.get("dsn")
    if not isinstance(dsn, str) or not dsn:
        raise ConfigError("postgres connection needs a 'dsn' (use \"${NAME}\" and keep the value in .env)")
    size = options.get("max_pool_size", 5)
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ConfigError("postgres max_pool_size must be a whole number of at least 1")
    return PostgresBackend(dsn, size)


def _firestore(options: dict[str, Any]) -> DatabaseBackend:
    from src.backends.firestore import FirestoreBackend

    values: dict[str, str | None] = {}
    for name in ("project", "credentials_file", "database"):
        value = options.get(name)
        if value is not None and (not isinstance(value, str) or not value):
            raise ConfigError(f"firestore {name} must be a non-empty string")
        values[name] = value
    return FirestoreBackend(**values)


BACKEND_TYPES: dict[str, Callable[[dict[str, Any]], DatabaseBackend]] = {
    "sqlite": _sqlite,
    "postgres": _postgres,
    "firestore": _firestore,
}


def build_backend(spec: ConnectionSpec) -> DatabaseBackend:
    try:
        factory = BACKEND_TYPES[spec.type]
    except KeyError:
        known = ", ".join(sorted(BACKEND_TYPES))
        raise ConfigError(f"connection {spec.name!r}: unknown type {spec.type!r} (known: {known})") from None
    backend = factory(spec.options)
    return CachedBackend(backend, spec.cache) if spec.cache.enabled else backend
