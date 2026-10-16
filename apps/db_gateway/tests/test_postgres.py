"""Postgres adapter against a fake asyncpg pool: checks the SQL and argument shapes,
not a real server."""

import json

import pytest

from src.backends.factory import BACKEND_TYPES
from src.backends.postgres import PostgresBackend
from src.config import ConfigError


class FakePool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple]] = []
        self.value = None
        self.status = "DELETE 1"
        self.rows: list[dict] = []

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        return self.value

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return self.status

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.rows

    async def close(self):
        self.calls.append(("close", "", ()))


@pytest.fixture
def pg():
    backend = PostgresBackend("postgresql://x")
    backend._pool = FakePool()
    return backend, backend._pool


async def test_get_handles_text_and_decoded_jsonb(pg):
    backend, pool = pg
    pool.value = '{"a": 1}'
    assert await backend.get("c", "k") == {"a": 1}
    pool.value = {"a": 2}
    assert await backend.get("c", "k") == {"a": 2}
    pool.value = None
    assert await backend.get("c", "k") is None
    assert pool.calls[0][2] == ("c", "k")


async def test_put_sends_json_text(pg):
    backend, pool = pg
    await backend.put("c", "k", {"a": 1})
    sql, args = pool.calls[0][1], pool.calls[0][2]
    assert "ON CONFLICT" in sql and args[:2] == ("c", "k") and json.loads(args[2]) == {"a": 1}


async def test_delete_reads_status(pg):
    backend, pool = pg
    assert await backend.delete("c", "k") is True
    pool.status = "DELETE 0"
    assert await backend.delete("c", "k") is False


async def test_query_uses_containment_and_params(pg):
    backend, pool = pg
    pool.rows = [{"body": '{"r": "x"}'}, {"body": {"r": "y"}}]
    assert await backend.query("c", {"r": "x"}, limit=5, offset=2) == [{"r": "x"}, {"r": "y"}]
    sql, args = pool.calls[0][1], pool.calls[0][2]
    assert "@>" in sql and args[0] == "c" and json.loads(args[1]) == {"r": "x"} and args[2:] == (5, 2)


async def test_raw_sql_passes_params(pg):
    backend, pool = pg
    pool.rows = [{"n": 1}]
    assert await backend.execute_sql("SELECT $1::int AS n", [1]) == [{"n": 1}]
    assert pool.calls[0][2] == (1,)


async def test_close_and_not_connected_guard(pg):
    backend, pool = pg
    await backend.close()
    assert pool.calls[-1][0] == "close"
    with pytest.raises(RuntimeError):
        await backend.get("c", "k")


def test_factory_validates_options():
    with pytest.raises(ConfigError, match="dsn"):
        BACKEND_TYPES["postgres"]({})
    with pytest.raises(ConfigError, match="max_pool_size"):
        BACKEND_TYPES["postgres"]({"dsn": "postgresql://x", "max_pool_size": 0})
    assert isinstance(BACKEND_TYPES["postgres"]({"dsn": "postgresql://x"}), PostgresBackend)
