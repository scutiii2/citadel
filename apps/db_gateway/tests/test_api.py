import httpx
import pytest

from src.api import create_app
from src.backends.factory import build_backend
from src.registry import ConnectionRegistry, InstanceManager
from tests.conftest import memory_spec

REC = "/instances/one/connections/a/collections/users/records"


@pytest.fixture
async def client():
    registry = ConnectionRegistry({"a": memory_spec("a"), "b": memory_spec("b", raw_sql=True)}, build_backend)
    manager = InstanceManager({"one": ("a", "b"), "two": ("a",)}, registry)
    app = create_app(manager)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
        yield http
    await manager.close()


async def test_health_and_instances(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/instances")).json() == {"one": ["a", "b"], "two": ["a"]}


async def test_record_crud(client):
    assert (await client.put(f"{REC}/u1", json={"doc": {"n": 1}})).status_code == 200
    assert (await client.get(f"{REC}/u1")).json() == {"doc": {"n": 1}}
    assert (await client.delete(f"{REC}/u1")).status_code == 200
    assert (await client.get(f"{REC}/u1")).status_code == 404
    assert (await client.delete(f"{REC}/u1")).status_code == 404


async def test_query(client):
    for key, role in (("1", "x"), ("2", "y")):
        await client.put(f"{REC}/{key}", json={"doc": {"role": role}})
    response = await client.post("/instances/one/connections/a/collections/users/query", json={"filters": {"role": "y"}})
    assert response.json() == {"docs": [{"role": "y"}]}


async def test_other_instance_sees_same_connection(client):
    await client.put(f"{REC}/u1", json={"doc": {"n": 1}})
    other = await client.get("/instances/two/connections/a/collections/users/records/u1")
    assert other.json() == {"doc": {"n": 1}}


async def test_errors(client):
    assert (await client.get("/instances/nope/connections/a/collections/c/records/k")).status_code == 404
    assert (await client.get("/instances/two/connections/b/collections/c/records/k")).status_code == 404
    assert (await client.put(f"{REC}/u1", json={"doc": "not an object"})).status_code == 400
    bad = await client.post("/instances/one/connections/a/collections/c/query", json={"filters": {"x; --": 1}})
    assert bad.status_code == 400


async def test_raw_sql_permissions(client):
    denied = await client.post("/instances/one/connections/a/sql", json={"sql": "SELECT 1"})
    assert denied.status_code == 403
    ok = await client.post("/instances/one/connections/b/sql", json={"sql": "SELECT 1 AS n"})
    assert ok.json() == {"rows": [{"n": 1}]}
    broken = await client.post("/instances/one/connections/b/sql", json={"sql": "SELEC"})
    assert broken.status_code == 400


async def test_token_required_when_configured():
    registry = ConnectionRegistry({"a": memory_spec("a")}, build_backend)
    app = create_app(InstanceManager({"one": ("a",)}, registry), token="secret")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
        assert (await http.get("/health")).status_code == 200
        assert (await http.get("/instances")).status_code == 401
        assert (await http.get("/instances", headers={"X-Internal-Token": "secret"})).status_code == 200
