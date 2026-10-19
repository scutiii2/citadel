"""PostgreSQL adapter (asyncpg). Same `documents` table shape as SQLite, body as jsonb.

asyncpg is imported on connect, so the package is only needed for Postgres connections.
Filters use jsonb containment (`body @> filters`): equal for scalar fields; for an array
field, a filter value matches when the array contains it.
"""

from __future__ import annotations

import json
from typing import Any

from src.backends.base import DatabaseBackend, Document

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    key TEXT NOT NULL,
    body JSONB NOT NULL,
    PRIMARY KEY (collection, key)
)
"""


def _doc(raw: Any) -> Document:
    return json.loads(raw) if isinstance(raw, str) else raw


class PostgresBackend(DatabaseBackend):
    def __init__(self, dsn: str, max_pool_size: int = 5) -> None:
        self._dsn = dsn
        self._max = max_pool_size
        self._pool: Any = None

    async def connect(self) -> None:
        try:
            import asyncpg
        except ImportError as error:
            raise RuntimeError("Postgres connections need asyncpg: pip install -e \".[postgres]\"") from error
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=self._max)
        await self._pool.execute(_SCHEMA)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _db(self) -> Any:
        if self._pool is None:
            raise RuntimeError("backend is not connected")
        return self._pool

    async def get(self, collection: str, key: str) -> Document | None:
        raw = await self._db().fetchval("SELECT body FROM documents WHERE collection = $1 AND key = $2", collection, key)
        return None if raw is None else _doc(raw)

    async def put(self, collection: str, key: str, doc: Document) -> None:
        await self._db().execute(
            "INSERT INTO documents (collection, key, body) VALUES ($1, $2, $3::jsonb) "
            "ON CONFLICT (collection, key) DO UPDATE SET body = EXCLUDED.body",
            collection, key, json.dumps(doc),
        )

    async def create(self, collection: str, key: str, doc: Document) -> bool:
        status = await self._db().execute(
            "INSERT INTO documents (collection, key, body) VALUES ($1, $2, $3::jsonb) "
            "ON CONFLICT (collection, key) DO NOTHING",
            collection, key, json.dumps(doc),
        )
        return status.endswith(" 1")  # asyncpg returns e.g. "INSERT 0 1"

    async def delete(self, collection: str, key: str) -> bool:
        status = await self._db().execute("DELETE FROM documents WHERE collection = $1 AND key = $2", collection, key)
        return status.endswith(" 1")  # asyncpg returns e.g. "DELETE 1"

    async def query(
        self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        rows = await self._db().fetch(
            "SELECT body FROM documents WHERE collection = $1 AND body @> $2::jsonb "
            "ORDER BY key LIMIT $3 OFFSET $4",
            collection, json.dumps(filters or {}), limit, offset,
        )
        return [_doc(row["body"]) for row in rows]

    async def execute_sql(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Parameters are $1, $2, ... (asyncpg style), not `?`."""
        rows = await self._db().fetch(sql, *(params or []))
        return [dict(row) for row in rows]
