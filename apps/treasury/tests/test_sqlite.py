import pytest

from src.backends.base import UnsupportedOperation


async def test_put_get_delete(sqlite_backend):
    await sqlite_backend.put("users", "a", {"name": "Ann", "age": 30})
    assert await sqlite_backend.get("users", "a") == {"name": "Ann", "age": 30}
    await sqlite_backend.put("users", "a", {"name": "Ann", "age": 31})
    assert (await sqlite_backend.get("users", "a"))["age"] == 31
    assert await sqlite_backend.delete("users", "a") is True
    assert await sqlite_backend.delete("users", "a") is False
    assert await sqlite_backend.get("users", "a") is None


async def test_collections_are_separate(sqlite_backend):
    await sqlite_backend.put("users", "a", {"v": 1})
    assert await sqlite_backend.get("pets", "a") is None


async def test_query_filters_limit_offset(sqlite_backend):
    for key, role in (("1", "admin"), ("2", "user"), ("3", "user"), ("4", "user")):
        await sqlite_backend.put("users", key, {"id": key, "role": role})
    users = await sqlite_backend.query("users", {"role": "user"})
    assert [d["id"] for d in users] == ["2", "3", "4"]
    page = await sqlite_backend.query("users", {"role": "user"}, limit=1, offset=1)
    assert [d["id"] for d in page] == ["3"]
    assert len(await sqlite_backend.query("users")) == 4


async def test_query_rejects_unsafe_field(sqlite_backend):
    with pytest.raises(ValueError):
        await sqlite_backend.query("users", {"a'); DROP TABLE documents;--": 1})


async def test_raw_sql(sqlite_backend):
    await sqlite_backend.put("users", "a", {"n": 1})
    rows = await sqlite_backend.execute_sql("SELECT key FROM documents WHERE collection = ?", ["users"])
    assert rows == [{"key": "a"}]


async def test_base_backend_has_no_raw_sql():
    from src.backends.base import DatabaseBackend

    class Bare(DatabaseBackend):
        async def connect(self): ...
        async def close(self): ...
        async def get(self, collection, key): ...
        async def put(self, collection, key, doc): ...
        async def create(self, collection, key, doc): ...
        async def delete(self, collection, key): ...
        async def query(self, collection, filters=None, limit=100, offset=0): ...

    with pytest.raises(UnsupportedOperation):
        await Bare().execute_sql("SELECT 1")
