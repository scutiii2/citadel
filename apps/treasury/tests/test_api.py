import httpx
import pytest

from src.api import create_app
from src.backends.factory import build_backend
from src.registry import ConnectionRegistry, InstanceManager
from tests.conftest import memory_spec
from src.citadel_auth import ServiceAuth
from src.citadel_auth.testing import make_stack, signed

REC = "/instances/one/connections/a/collections/users/records"


@pytest.fixture
async def client(tmp_path):
    registry = ConnectionRegistry({"a": memory_spec("a"), "b": memory_spec("b", raw_sql=True)}, build_backend)
    manager = InstanceManager({"one": ("a", "b"), "two": ("a",)}, registry)
    stack = await make_stack(tmp_path)
    app = create_app(manager, keyring=stack["treasury"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                auth=ServiceAuth(stack["stronghold"], "treasury")) as http:
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


async def test_put_if_absent_conflicts_when_key_taken(client):
    assert (await client.put(f"{REC}/u1?if_absent=true", json={"doc": {"n": 1}})).status_code == 200
    taken = await client.put(f"{REC}/u1?if_absent=true", json={"doc": {"n": 2}})
    assert taken.status_code == 409 and "already exists" in taken.json()["error"]
    assert (await client.get(f"{REC}/u1")).json() == {"doc": {"n": 1}}
    assert (await client.put(f"{REC}/u1", json={"doc": {"n": 3}})).status_code == 200  # plain put still replaces


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


async def test_assertion_required_and_health_open(tmp_path):
    registry = ConnectionRegistry({"a": memory_spec("a")}, build_backend)
    stack = await make_stack(tmp_path)
    app = create_app(InstanceManager({"one": ("a",)}, registry), keyring=stack["treasury"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
        assert (await http.get("/health")).status_code == 200
        assert (await http.get("/instances")).status_code == 401
        assert (await http.get("/instances", headers=signed(stack["stronghold"], "treasury"))).status_code == 200


@pytest.mark.parametrize("caller", ["portcullis", "stronghold", "legion", "armory"])
async def test_policy_allows_data_callers(tmp_path, caller):
    stack = await make_stack(tmp_path)
    manager = InstanceManager({}, ConnectionRegistry({}, build_backend))
    app = create_app(manager, keyring=stack["treasury"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
        assert (await http.get("/instances", headers=signed(stack[caller], "treasury"))).status_code == 200


async def test_policy_denies_self_unknown_and_requester_forwarding(tmp_path):
    import jwt
    import time
    from src.citadel_auth import sign_assertion
    from src.citadel_auth.testing import requester_headers
    stack = await make_stack(tmp_path)
    app = create_app(InstanceManager({}, ConnectionRegistry({}, build_backend)), keyring=stack["treasury"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
        assert (await http.get("/instances", headers=signed(stack["treasury"], "treasury"))).status_code == 403
        token = sign_assertion(stack["armory"], "treasury")
        claims = jwt.decode(token, options={"verify_signature": False})
        claims["iss"] = "unknown"
        unknown = jwt.encode(claims, stack["armory"].private_key, algorithm="EdDSA", headers={"kid": stack["armory"].kid})
        assert (await http.get("/instances", headers={"Authorization": "Bearer " + unknown})).status_code == 401
        forwarded = {**signed(stack["stronghold"], "treasury"),
                     **requester_headers(stack["portcullis"], "uid", aud=["treasury"])}
        assert (await http.get("/instances", headers=forwarded)).status_code == 403
        forged = {**signed(stack["stronghold"], "treasury"), "X-Requester-Uid": "forged"}
        assert (await http.get("/instances", headers=forged)).status_code == 200


@pytest.fixture
async def registering(tmp_path):
    registry = ConnectionRegistry({"a": memory_spec("a"), "b": memory_spec("b")}, build_backend)
    manager = InstanceManager({}, registry)
    stack = await make_stack(tmp_path)
    db = tmp_path / "settings.db"
    app = create_app(manager, keyring=stack["treasury"], settings_db=db)

    def caller(name):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                 auth=ServiceAuth(stack[name], "treasury"))

    yield caller, db
    await manager.close()


async def test_a_service_registers_its_own_instance_and_uses_it_at_once(registering):
    from src.citadel_auth import settings_store

    caller, db = registering
    async with caller("stronghold") as stronghold:
        saved = await stronghold.put("/instances/stronghold", json={"connections": ["a", "a"]})
        assert saved.status_code == 200
        assert (await stronghold.get("/instances")).json() == {"stronghold": ["a"]}
        written = await stronghold.put("/instances/stronghold/connections/a/collections/c/records/k", json={"doc": {"n": 1}})
        assert written.status_code == 200
        # registering again replaces the instance
        await stronghold.put("/instances/stronghold", json={"connections": ["a", "b"]})
        assert (await stronghold.get("/instances")).json() == {"stronghold": ["a", "b"]}
    assert settings_store.read_all(db, "instances") == {"stronghold": ["a", "b"]}


async def test_a_service_may_not_register_another_services_instance(registering):
    caller, _ = registering
    async with caller("stronghold") as stronghold, caller("portcullis") as portcullis:
        assert (await stronghold.put("/instances/armory", json={"connections": ["a"]})).status_code == 403
        assert (await stronghold.put("/instances/ember", json={"connections": ["a"]})).status_code == 403
        assert (await portcullis.put("/instances/ember", json={"connections": ["a"]})).status_code == 200


async def test_an_unknown_connection_is_refused(registering):
    caller, _ = registering
    async with caller("legion") as legion:
        refused = await legion.put("/instances/legion", json={"connections": ["zzz"]})
        assert refused.status_code == 404
        assert (await legion.get("/instances")).json() == {}
