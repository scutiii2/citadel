"""A service's run-time settings in one SQLite file under `.data/<service>/`.

Each table maps a key to one JSON document. Admin routes write here, so nothing under
configs/ changes while the service runs. Each call opens a short connection; the volume is a few rows a day.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

_NAME = re.compile(r"^[a-z_]+$")


def _check(table: str) -> str:
    if not _NAME.match(table):
        raise ValueError(f"Unknown settings table {table!r}")
    return table


def _connect(path: Path, table: str) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    for name in {_check(table), "settings"}:
        connection.execute(f"CREATE TABLE IF NOT EXISTS {name} (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return connection


def read_all(path: Path, table: str) -> dict[str, Any]:
    """Every document of `table`, keyed by its key. A missing file is an empty store."""
    if not path.exists():
        return {}
    with closing(_connect(path, table)) as connection:
        return {key: json.loads(value) for key, value in connection.execute(f"SELECT key, value FROM {table}")}


def put(path: Path, table: str, key: str, value: Any) -> None:
    """Insert or replace one document."""
    with closing(_connect(path, table)) as connection, connection:
        connection.execute(
            f"INSERT INTO {table} (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def delete(path: Path, table: str, key: str) -> None:
    """Remove one document; an absent key is not an error."""
    if not path.exists():
        return
    with closing(_connect(path, table)) as connection, connection:
        connection.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
