"""One behaviour contract, run against every backend that is available.

SQLite always runs. Postgres runs when DB_GATEWAY_TEST_POSTGRES_DSN is set, Firestore when
FIRESTORE_EMULATOR_HOST is set (the emulator, never a real project). Each run uses a
collection name of its own and deletes what it wrote.

    DB_GATEWAY_TEST_POSTGRES_DSN=postgresql://user:pass@localhost/testdb pytest tests/test_backend_contract.py
    FIRESTORE_EMULATOR_HOST=localhost:8080 GOOGLE_CLOUD_PROJECT=demo-test pytest tests/test_backend_contract.py
"""

import os
import uuid

import pytest

from src.backends.base import DatabaseBackend
from src.backends.sqlite import SqliteBackend

POSTGRES_DSN = os.getenv("DB_GATEWAY_TEST_POSTGRES_DSN")
FIRESTORE_EMULATOR = os.getenv("FIRESTORE_EMULATOR_HOST")


def _make(kind: str) -> DatabaseBackend:
    if kind == "sqlite":
        return SqliteBackend(":memory:")
    if kind == "postgres":
        from src.backends.postgres import PostgresBackend

        return PostgresBackend(POSTGRES_DSN or "", max_pool_size=2)
    from src.backends.firestore import FirestoreBackend

    return FirestoreBackend(project=os.getenv("GOOGLE_CLOUD_PROJECT") or "demo-test")


KINDS = [
    "sqlite",
    pytest.param("postgres", marks=pytest.mark.skipif(not POSTGRES_DSN, reason="DB_GATEWAY_TEST_POSTGRES_DSN not set")),
    pytest.param("firestore", marks=pytest.mark.skipif(not FIRESTORE_EMULATOR, reason="FIRESTORE_EMULATOR_HOST not set")),
]


@pytest.fixture(params=KINDS)
async def backend(request):
    db = _make(request.param)
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
async def col(backend):
    """A collection name no other run uses; its records are removed afterwards."""
    name = f"contract_{uuid.uuid4().hex[:12]}"
    yield name
    for doc in await backend.query(name, {}, limit=1000):
        await backend.delete(name, doc["id"])


def record(key: str, **fields) -> dict:
    return {"id": key, **fields}


async def test_get_missing_is_none(backend, col):
    assert await backend.get(col, "nope") is None


async def test_put_get_replace_delete(backend, col):
    await backend.put(col, "a", record("a", n=1, tags=["x"], nested={"k": "v"}, text="héllo ✓"))
    assert await backend.get(col, "a") == record("a", n=1, tags=["x"], nested={"k": "v"}, text="héllo ✓")

    await backend.put(col, "a", record("a", n=2))  # replaces, does not merge
    assert await backend.get(col, "a") == record("a", n=2)

    assert await backend.delete(col, "a") is True
    assert await backend.delete(col, "a") is False
    assert await backend.get(col, "a") is None


async def test_create_only_when_absent(backend, col):
    assert await backend.create(col, "a", record("a", n=1)) is True
    assert await backend.create(col, "a", record("a", n=2)) is False  # taken: left unchanged
    assert await backend.get(col, "a") == record("a", n=1)


async def test_query_filters_order_limit_offset(backend, col):
    for key, role in (("1", "admin"), ("2", "user"), ("3", "user"), ("4", "user")):
        await backend.put(col, key, record(key, role=role))

    assert [d["id"] for d in await backend.query(col, {"role": "user"})] == ["2", "3", "4"]
    assert [d["id"] for d in await backend.query(col, {"role": "user"}, limit=1, offset=1)] == ["3"]
    assert [d["id"] for d in await backend.query(col, {})] == ["1", "2", "3", "4"]
    assert await backend.query(col, {"role": "nobody"}) == []


async def test_query_with_two_filters(backend, col):
    await backend.put(col, "1", record("1", role="user", active=True))
    await backend.put(col, "2", record("2", role="user", active=False))

    found = await backend.query(col, {"role": "user", "active": True})

    assert [d["id"] for d in found] == ["1"]


async def test_collections_are_separate(backend, col):
    await backend.put(col, "a", record("a"))

    assert await backend.get(col + "_other", "a") is None
