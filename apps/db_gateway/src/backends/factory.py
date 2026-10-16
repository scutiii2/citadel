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


BACKEND_TYPES: dict[str, Callable[[dict[str, Any]], DatabaseBackend]] = {"sqlite": _sqlite}


def build_backend(spec: ConnectionSpec) -> DatabaseBackend:
    try:
        factory = BACKEND_TYPES[spec.type]
    except KeyError:
        known = ", ".join(sorted(BACKEND_TYPES))
        raise ConfigError(f"connection {spec.name!r}: unknown type {spec.type!r} (known: {known})") from None
    backend = factory(spec.options)
    return CachedBackend(backend, spec.cache) if spec.cache.enabled else backend
