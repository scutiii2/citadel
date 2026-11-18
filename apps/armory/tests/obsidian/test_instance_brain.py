import asyncio
import json

import httpx
import pytest
from cryptography.fernet import Fernet
from starlette.applications import Starlette
from starlette.testclient import TestClient

from tests import auth_helpers
from tests.auth_helpers import FreshHeaders


@pytest.fixture
def allow_management(monkeypatch):
    from src.capabilities.obsidian.utils import brain_resolver

    async def allowed():
        return None

    monkeypatch.setattr(brain_resolver, "authorize_management", allowed, raising=False)


def test_portcullis_requester_must_hold_live_management_permission(tmp_path, monkeypatch):
    from src.capabilities.obsidian import brain_admin
    from src.capabilities.obsidian.utils import brain_resolver
    from src.capabilities.obsidian.utils.gateway import ObsidianGatewayError
    from src.capabilities.obsidian.utils.instance_brain import InstanceBrainStore

    async def denied():
        raise ObsidianGatewayError("Missing permission: settings.manage", status=403)

    monkeypatch.setattr(brain_resolver, "authorize_management", denied, raising=False)
    store = InstanceBrainStore(tmp_path / "settings.db", Fernet(Fernet.generate_key()))
    store.import_once(None)
    app = Starlette()
    brain_admin.install(app, store)
    with TestClient(app) as client:
        assert client.get("/admin/brain", headers=FreshHeaders(uid="member")).status_code == 403


def test_admin_tests_only_the_candidate_and_never_returns_the_saved_key(tmp_path, monkeypatch, allow_management):
    from src.capabilities.obsidian import brain_admin
    from src.capabilities.obsidian.utils import brain_resolver
    from src.capabilities.obsidian.utils.instance_brain import InstanceBrainStore

    reads = []

    class Probe:
        def list(self, folder):
            reads.append((self.endpoint, folder))

    def gateway(snapshot):
        probe = Probe()
        probe.endpoint = snapshot["endpoint"]
        return probe

    monkeypatch.setattr(brain_resolver, "gateway", gateway)
    store = InstanceBrainStore(tmp_path / "settings.db", Fernet(Fernet.generate_key()))
    store.import_once(None)
    app = Starlette()
    brain_admin.install(app, store)
    path = "/admin/brain"
    headers = FreshHeaders(uid="one")
    draft = {"label": "Shared", "endpoint": "https://vault.lan", "api_key": "fixture-credential"}
    with TestClient(app) as client:
        assert client.get(path, headers=FreshHeaders()).status_code == 403
        assert client.get(path, headers=headers).json()["status"] == "legacy"
        invalid = client.put(path, headers=headers, json={**draft, "endpoint": "http://vault.lan"})
        assert invalid.status_code == 422 and draft["api_key"] not in invalid.text
        saved = client.put(path, headers=headers, json=draft)
        assert saved.status_code == 200 and saved.json()["credential_configured"]
        assert draft["api_key"] not in saved.text
        assert draft["api_key"] not in client.get(path, headers=headers).text
        assert draft["api_key"].encode() not in (tmp_path / "settings.db").read_bytes()
        candidate = {**draft, "endpoint": "https://candidate.lan", "expected_revision": 1}
        without_key = {name: value for name, value in candidate.items() if name != "api_key"}
        assert client.post(f"{path}/test", headers=headers, json=without_key).status_code == 400
        assert reads == []
        assert client.post(f"{path}/test", headers=headers, json=candidate).json()["status"] == "connected"
        assert reads == [("https://candidate.lan", "")]
        assert client.get(path, headers=headers).json()["endpoint"] == draft["endpoint"]
        assert client.get(f"{path}/status", headers=headers).json()["status"] == "connected"
        assert reads[-1] == (draft["endpoint"], "")
        assert client.put(path, headers=headers, json=draft).status_code == 409
        assert client.post(f"{path}/disable", headers=headers, json={"expected_revision": 1}).json()["status"] == "disabled"


@pytest.mark.parametrize("vault_status", [302, 401])
def test_a_vault_refusal_is_an_admin_test_error(tmp_path, monkeypatch, vault_status, allow_management):
    from src.capabilities.obsidian import brain_admin
    from src.capabilities.obsidian.utils import brain_resolver
    from src.capabilities.obsidian.utils.gateway import ObsidianGatewayError
    from src.capabilities.obsidian.utils.instance_brain import InstanceBrainStore

    class Refused:
        def list(self, folder):
            raise ObsidianGatewayError("Obsidian refused the read", status=vault_status)

    monkeypatch.setattr(brain_resolver, "gateway", lambda _: Refused())
    store = InstanceBrainStore(tmp_path / "settings.db", Fernet(Fernet.generate_key()))
    store.import_once(None)
    app = Starlette()
    brain_admin.install(app, store)
    with TestClient(app, follow_redirects=False) as client:
        response = client.post("/admin/brain/test", headers=FreshHeaders(uid="one"),
                               json={"label": "Shared", "endpoint": "https://vault.lan", "api_key": "fixture"})
    assert response.status_code == 400
    assert response.json() == {"error": "Obsidian refused the read"}


def test_missing_storage_key_is_a_recovery_error_for_an_existing_credential(tmp_path):
    from src.capabilities.obsidian.utils.instance_brain import ConnectionInput, InstanceBrainStore, load_box

    identity = tmp_path / "identity"
    identity.mkdir()
    database = tmp_path / "settings.db"
    store = InstanceBrainStore(database, Fernet(Fernet.generate_key()))
    store.import_once(None)
    store.save(ConnectionInput(label="Shared", endpoint="https://vault.lan", api_key="fixture"))
    with pytest.raises(OSError, match="Restore the Armory identity backup"):
        load_box(identity, database)
    assert list(identity.iterdir()) == []


def test_destination_is_not_writable_if_the_stored_key_cannot_be_decrypted(tmp_path):
    from src.capabilities.obsidian import brain_admin
    from src.capabilities.obsidian.utils.instance_brain import ConnectionInput, InstanceBrainStore

    path = tmp_path / "settings.db"
    store = InstanceBrainStore(path, Fernet(Fernet.generate_key()))
    store.import_once(None)
    store.save(ConnectionInput(label="Shared", endpoint="https://vault.lan",
                               api_key="fixture-credential", allow_write=True))
    app = Starlette()
    brain_admin.install(app, InstanceBrainStore(path, Fernet(Fernet.generate_key())))
    with TestClient(app) as client:
        result = client.get("/brains/destination", headers=FreshHeaders(uid="one", caller="stronghold"))
        assert result.status_code == 200
        assert result.json()["writable"] is False


def test_first_import_keeps_generation_and_never_overwrites_a_saved_edit(tmp_path):
    from src.capabilities.obsidian.utils.instance_brain import ConnectionInput, InstanceBrainStore

    box = Fernet(Fernet.generate_key())
    path = tmp_path / "settings.db"
    previous = {"label": "Old", "endpoint": "https://original.test", "api_key": "fixture-credential",
                "folder": "Published", "allow_write": True, "enabled": True, "revision": 5,
                "generation": "old-generation", "updated_at": "2026-11-18T00:00:00+00:00"}
    store = InstanceBrainStore(path, box)
    store.import_once(previous)
    assert store.view()["generation"] == previous["generation"]
    assert store.snapshot()["api_key"] == previous["api_key"]
    store.save(ConnectionInput(label="Renamed", endpoint=previous["endpoint"], expected_revision=5))
    restarted = InstanceBrainStore(path, box)
    restarted.import_once(previous)
    assert restarted.view()["label"] == "Renamed"
    assert restarted.view()["revision"] == 6


@pytest.mark.asyncio
async def test_startup_waits_for_migration_and_acknowledges_only_after_persistence(tmp_path, monkeypatch):
    from src.capabilities.obsidian.utils import instance_migration
    from src.capabilities.obsidian.utils.gateway import ObsidianGatewayError
    from src.capabilities.obsidian.utils.instance_brain import InstanceBrainStore
    from src.citadel_auth.brain_migration import seal, verify_acknowledgement

    path = tmp_path / "settings.db"
    box = Fernet(Fernet.generate_key())
    store = InstanceBrainStore(path, box)
    armory, stronghold = (auth_helpers.stack[name] for name in ("armory", "stronghold"))
    source = {"label": "Migrated", "endpoint": "https://vault.lan", "api_key": "fixture-credential",
              "revision": 3, "generation": "old-generation", "updated_at": "2026-11-18T00:00:00+00:00"}
    attempted = asyncio.Event()
    available = False

    class Catalog:
        def url(self, name):
            assert name == "stronghold"
            return "http://stronghold.test"

        def refresh_soon(self):
            attempted.set()

    async def load():
        return source

    async def handler(request):
        proof = json.loads(request.content)["proof"]
        if not available:
            return httpx.Response(503)
        if request.url.path.endswith("/ack"):
            assert await verify_acknowledgement(stronghold, proof) == (3, "old-generation")
            assert InstanceBrainStore(path, box).view()["revision"] == 3
            return httpx.Response(204)
        reply = await seal(stronghold, proof, load)
        assert source["api_key"] not in str(reply)
        return httpx.Response(200, json=reply)

    real_client = instance_migration.service_client
    monkeypatch.setattr(instance_migration, "service_client",
                        lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(handler), **kwargs))
    first = asyncio.create_task(instance_migration.migrate(store, armory, Catalog()))
    try:
        await asyncio.wait_for(attempted.wait(), 3)
        with pytest.raises(ObsidianGatewayError, match="migration is pending"):
            await asyncio.to_thread(store.view)
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)

    available = True
    await asyncio.wait_for(instance_migration.migrate(store, armory, Catalog()), 3)
    assert store.migration() == (True, None)
    assert store.snapshot()["api_key"] == source["api_key"]
