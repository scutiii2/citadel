"""The connections page: built-in connections, saved ones on top, new ones offered at once, secrets never stored."""

import httpx
import pytest

from src.api import create_app
from src.backends.factory import build_backend
from src.citadel_auth import ServiceAuth, settings_store
from src.citadel_auth.testing import make_stack
from src.registry import ConnectionRegistry, InstanceManager
from tests.conftest import memory_spec


@pytest.fixture
async def admin(tmp_path):
    registry = ConnectionRegistry({"data": memory_spec("data"), "main": memory_spec("main")}, build_backend)
    manager = InstanceManager({"ember": ("data",)}, registry)
    stack = await make_stack(tmp_path)
    db = tmp_path / "settings.db"
    app = create_app(manager, keyring=stack["treasury"], settings_db=db)

    def caller(name):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                 auth=ServiceAuth(stack[name], "treasury"))

    yield caller, db, manager
    await manager.close()


def row(body, name):
    return next(item for item in body["connections"] if item["name"] == name)


async def test_the_builtin_connections_are_listed_with_who_uses_them(admin):
    caller, _, _ = admin
    async with caller("portcullis") as portcullis:
        body = (await portcullis.get("/admin/connections")).json()
    assert [item["name"] for item in body["connections"]] == ["data", "main", "scratch", "stronghold"]
    assert row(body, "data")["source"] == "built-in" and row(body, "data")["used_by"] == ["ember"]
    assert row(body, "scratch")["spec"]["allow_raw_sql"] is True
    assert body["default_cache"]["ttl_seconds"] == 30 and body["default_cache_stored"] is False


async def test_a_new_connection_is_saved_and_offered_to_the_instances_at_once(admin):
    caller, db, manager = admin
    async with caller("portcullis") as portcullis:
        saved = await portcullis.put("/admin/connections/reports", json={"type": "sqlite", "path": "reports.db"})
        assert saved.status_code == 200 and saved.json()["applies"] == "now"
        assert row(saved.json(), "reports")["source"] == "saved"
    assert "reports" in manager.connection_names()
    assert settings_store.read_all(db, "connections")["reports"] == {"type": "sqlite", "path": "reports.db"}
    async with caller("stronghold") as stronghold:  # a service can now register an instance that uses it
        assert (await stronghold.put("/instances/stronghold", json={"connections": ["reports"]})).status_code == 200


async def test_changing_a_builtin_connection_is_used_from_the_next_start_and_removing_it_brings_it_back(admin):
    caller, db, _ = admin
    async with caller("portcullis") as portcullis:
        changed = await portcullis.put("/admin/connections/data", json={"type": "sqlite", "path": "mine.db"})
        assert changed.json()["applies"] == "next start" and row(changed.json(), "data")["source"] == "changed"
        back = await portcullis.delete("/admin/connections/data")
        assert back.status_code == 200 and row(back.json(), "data")["source"] == "built-in"
        assert settings_store.read_all(db, "connections") == {}
        assert (await portcullis.delete("/admin/connections/data")).status_code == 400  # nothing saved to remove


async def test_a_connection_an_instance_uses_cannot_be_removed(admin):
    caller, _, _ = admin
    async with caller("portcullis") as portcullis:
        await portcullis.put("/admin/connections/reports", json={"type": "sqlite", "path": "r.db"})
    async with caller("legion") as legion:
        await legion.put("/instances/legion", json={"connections": ["reports"]})
    async with caller("portcullis") as portcullis:
        refused = await portcullis.delete("/admin/connections/reports")
    assert refused.status_code == 400 and "legion" in refused.json()["error"]


async def test_a_postgres_dsn_must_be_a_placeholder_so_no_secret_is_stored(admin, monkeypatch):
    caller, db, _ = admin
    monkeypatch.setenv("REPORTS_DSN", "postgresql://u:p@h/db")
    async with caller("portcullis") as portcullis:
        literal = await portcullis.put("/admin/connections/pg", json={"type": "postgres", "dsn": "postgresql://u:secret@h/db"})
        assert literal.status_code == 400 and "placeholder" in literal.json()["error"]
        missing = await portcullis.put("/admin/connections/pg", json={"type": "postgres", "dsn": "${NOT_SET_ANYWHERE}"})
        assert missing.status_code == 400 and "NOT_SET_ANYWHERE" in missing.json()["error"]
        fine = await portcullis.put("/admin/connections/pg", json={"type": "postgres", "dsn": "${REPORTS_DSN}", "max_pool_size": 2})
        assert fine.status_code == 200
    assert settings_store.read_all(db, "connections")["pg"]["dsn"] == "${REPORTS_DSN}"
    assert "secret" not in str(settings_store.read_all(db, "connections"))


async def test_a_bad_connection_is_refused_and_saves_nothing(admin):
    caller, db, _ = admin
    async with caller("portcullis") as portcullis:
        for name, spec in [
            ("Bad_Name", {"type": "sqlite", "path": "x.db"}), ("x", {}), ("x", {"type": "mongo"}),
            ("x", {"type": "sqlite"}), ("x", {"type": "sqlite", "path": "a.db", "dsn": "${X}"}),
            ("x", {"type": "sqlite", "path": "a.db", "allow_raw_sql": "yes"}),
            ("x", {"type": "sqlite", "path": "a.db", "cache": {"ttl_seconds": -1}}),
            ("x", {"type": "postgres", "dsn": "${PATH}", "max_pool_size": 0}),
        ]:
            refused = await portcullis.put(f"/admin/connections/{name}", json=spec)
            assert refused.status_code in (400, 404, 422), (name, spec)
    assert settings_store.read_all(db, "connections") == {}


async def test_the_cache_defaults_are_saved_merged_and_reset(admin):
    caller, db, _ = admin
    async with caller("portcullis") as portcullis:
        saved = await portcullis.put("/admin/default-cache", json={"ttl_seconds": 10})
        assert saved.json()["default_cache"] == {"ttl_seconds": 10.0, "max_entries": 1000, "negative_ttl_seconds": 5.0}
        assert saved.json()["default_cache_stored"] is True and saved.json()["applies"] == "next start"
        assert (await portcullis.put("/admin/default-cache", json={"ttl_seconds": -1})).status_code == 400
        assert (await portcullis.put("/admin/default-cache", json={"made_up": 1})).status_code == 400
        reset = await portcullis.put("/admin/default-cache")
        assert reset.json()["default_cache_stored"] is False and reset.json()["default_cache"]["ttl_seconds"] == 30.0


async def test_only_portcullis_may_change_connections(admin):
    caller, db, _ = admin
    async with caller("stronghold") as stronghold:
        assert (await stronghold.get("/admin/connections")).status_code == 403
        assert (await stronghold.put("/admin/connections/x", json={"type": "sqlite", "path": "x.db"})).status_code == 403
        assert (await stronghold.delete("/admin/connections/data")).status_code == 403
        assert (await stronghold.put("/admin/default-cache", json={"ttl_seconds": 1})).status_code == 403
    assert settings_store.read_all(db, "connections") == {}
