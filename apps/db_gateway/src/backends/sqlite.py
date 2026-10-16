"""SQLite adapter: every collection lives in one `documents` table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from src.backends.base import DatabaseBackend, Document

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    key TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (collection, key)
)
"""


def _json_path(field: str) -> str:
    """A safe JSON path for a top-level field name."""
    if not field or not field.replace("_", "").isalnum():
        raise ValueError(f"filter field must be letters, digits or underscores, got {field!r}")
    return f"$.{field}"


class SqliteBackend(DatabaseBackend):
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        # WAL + busy timeout let several readers and one writer share the file.
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("backend is not connected")
        return self._db

    async def get(self, collection: str, key: str) -> Document | None:
        async with self._conn().execute(
            "SELECT body FROM documents WHERE collection = ? AND key = ?", (collection, key)
        ) as cursor:
            row = await cursor.fetchone()
        return json.loads(row["body"]) if row else None

    async def put(self, collection: str, key: str, doc: Document) -> None:
        db = self._conn()
        await db.execute(
            "INSERT INTO documents (collection, key, body) VALUES (?, ?, ?) "
            "ON CONFLICT(collection, key) DO UPDATE SET body = excluded.body",
            (collection, key, json.dumps(doc)),
        )
        await db.commit()

    async def delete(self, collection: str, key: str) -> bool:
        db = self._conn()
        cursor = await db.execute("DELETE FROM documents WHERE collection = ? AND key = ?", (collection, key))
        await db.commit()
        return cursor.rowcount > 0

    async def query(
        self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        sql = "SELECT body FROM documents WHERE collection = ?"
        params: list[Any] = [collection]
        for field, value in (filters or {}).items():
            sql += f" AND json_extract(body, '{_json_path(field)}') IS ?"
            params.append(json.dumps(value) if isinstance(value, (dict, list)) else value)
        sql += " ORDER BY key LIMIT ? OFFSET ?"
        params += [limit, offset]
        async with self._conn().execute(sql, params) as cursor:
            return [json.loads(row["body"]) async for row in cursor]

    async def execute_sql(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        db = self._conn()
        async with db.execute(sql, params or []) as cursor:
            rows = [dict(row) async for row in cursor]
        await db.commit()
        return rows
