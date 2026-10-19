"""Firestore adapter against a fake client: checks call shapes, not a real project.
Needs the google-cloud-firestore package (for FieldFilter and NotFound)."""

import pytest

pytest.importorskip("google.cloud.firestore")
from google.api_core.exceptions import AlreadyExists, NotFound  # noqa: E402

from src.backends.factory import BACKEND_TYPES  # noqa: E402
from src.backends.firestore import FirestoreBackend  # noqa: E402
from src.config import ConfigError  # noqa: E402


class Snapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class FakeRef:
    def __init__(self, store, name, key):
        self.store, self.name, self.key = store, name, key

    async def get(self):
        return Snapshot(self.store.get((self.name, self.key)))

    async def set(self, doc):
        self.store[(self.name, self.key)] = doc

    async def create(self, doc):
        if (self.name, self.key) in self.store:
            raise AlreadyExists("taken")
        self.store[(self.name, self.key)] = doc

    async def delete(self, option=None):
        assert option == "exists-true"
        if (self.name, self.key) not in self.store:
            raise NotFound("missing")
        del self.store[(self.name, self.key)]


class FakeQuery:
    def __init__(self, store, name):
        self.store, self.name = store, name
        self.filters, self.order, self.max, self.skip = [], None, None, 0

    def where(self, filter):
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field):
        self.order = field
        return self

    def limit(self, n):
        self.max = n
        return self

    def offset(self, n):
        self.skip = n
        return self

    async def stream(self):
        rows = sorted((k, d) for (c, k), d in self.store.items() if c == self.name)
        rows = [d for _, d in rows if all(d.get(f) == v for f, _, v in self.filters)]
        for doc in rows[self.skip : self.skip + self.max]:
            yield Snapshot(doc)


class FakeClient:
    def __init__(self):
        self.store = {}
        self.closed = False
        self.last_query = None

    def collection(self, name):
        client = self

        class Collection(FakeQuery):
            def document(self, key):
                return FakeRef(client.store, name, key)

            def where(self, filter):
                query = FakeQuery(client.store, name)
                client.last_query = query
                return query.where(filter)

            def order_by(self, field):
                query = FakeQuery(client.store, name)
                client.last_query = query
                return query.order_by(field)

        return Collection(self.store, name)

    def write_option(self, exists):
        return f"exists-{str(exists).lower()}"

    def close(self):
        self.closed = True


@pytest.fixture
def fs():
    backend = FirestoreBackend()
    backend._client = FakeClient()
    return backend, backend._client


async def test_create_only_when_absent(fs):
    backend, _ = fs
    assert await backend.create("users", "a", {"n": 1}) is True
    assert await backend.create("users", "a", {"n": 2}) is False
    assert await backend.get("users", "a") == {"n": 1}


async def test_put_get_delete(fs):
    backend, _ = fs
    await backend.put("users", "a", {"n": 1})
    assert await backend.get("users", "a") == {"n": 1}
    assert await backend.get("users", "zz") is None
    assert await backend.delete("users", "a") is True
    assert await backend.delete("users", "a") is False


async def test_query_builds_equality_filters_ordered_by_id(fs):
    backend, client = fs
    for key, role in (("1", "x"), ("2", "y"), ("3", "y")):
        await backend.put("users", key, {"role": role})
    assert await backend.query("users", {"role": "y"}, limit=1, offset=1) == [{"role": "y"}]
    assert client.last_query.filters == [("role", "==", "y")]
    assert client.last_query.order == "__name__"


async def test_rejects_bad_document_ids(fs):
    backend, _ = fs
    for key in ("", "a/b", ".."):
        with pytest.raises(ValueError):
            await backend.get("users", key)


async def test_close_handles_sync_close_and_guards(fs):
    backend, client = fs
    await backend.close()
    assert client.closed
    with pytest.raises(RuntimeError):
        await backend.get("users", "a")


async def test_raw_sql_unsupported(fs):
    from src.backends.base import UnsupportedOperation

    with pytest.raises(UnsupportedOperation):
        await fs[0].execute_sql("SELECT 1")


def test_factory_validates_options():
    with pytest.raises(ConfigError, match="project"):
        BACKEND_TYPES["firestore"]({"project": 5})
    assert isinstance(BACKEND_TYPES["firestore"]({}), FirestoreBackend)
