"""Shared fixtures. Tests never read the real configs/ or .env files."""

import pytest

from src.backends.base import DatabaseBackend
from src.backends.sqlite import SqliteBackend
from src.cache import CacheSettings
from src.config import ConnectionSpec


class CountingBackend(DatabaseBackend):
    """Wraps a backend and counts calls that reach the database."""

    def __init__(self, inner: DatabaseBackend) -> None:
        self.inner = inner
        self.calls: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    async def connect(self) -> None:
        await self.inner.connect()

    async def close(self) -> None:
        await self.inner.close()

    async def get(self, collection, key):
        self._count("get")
        return await self.inner.get(collection, key)

    async def put(self, collection, key, doc):
        self._count("put")
        await self.inner.put(collection, key, doc)

    async def delete(self, collection, key):
        self._count("delete")
        return await self.inner.delete(collection, key)

    async def query(self, collection, filters=None, limit=100, offset=0):
        self._count("query")
        return await self.inner.query(collection, filters, limit, offset)

    async def execute_sql(self, sql, params=None):
        self._count("sql")
        return await self.inner.execute_sql(sql, params)


def memory_spec(name: str, *, raw_sql: bool = False, ttl: float = 30.0) -> ConnectionSpec:
    return ConnectionSpec(name, "sqlite", {"path": ":memory:"}, CacheSettings(ttl_seconds=ttl), raw_sql)


@pytest.fixture
async def sqlite_backend():
    backend = SqliteBackend(":memory:")
    await backend.connect()
    yield backend
    await backend.close()
