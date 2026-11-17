# apps/treasury/tests/test_service_catalog.py
import pytest

from src import service_catalog as catalog


@pytest.fixture
def db(tmp_path):
    return tmp_path / "settings.db"


def test_nothing_registered_means_an_empty_effective_catalog_and_defaults_in_the_view(db):
    assert catalog.effective(db) == {}
    names = {row["name"]: row for row in catalog.view(db)["services"]}
    assert set(names) == {"portcullis", "stronghold", "armory", "legion"}
    assert names["armory"]["source"] == "default" and names["armory"]["url"] == "http://127.0.0.1:29600"


def test_a_registration_is_kept_and_a_pin_beats_it(db):
    catalog.register(db, "armory", "http://armory:29600/")
    assert catalog.effective(db) == {"armory": "http://armory:29600"}
    catalog.pin(db, "armory", "http://armory.lan:29600")
    assert catalog.effective(db) == {"armory": "http://armory.lan:29600"}
    row = {r["name"]: r for r in catalog.view(db)["services"]}["armory"]
    assert (row["source"], row["registered"], row["pinned"]) == ("pinned", "http://armory:29600", "http://armory.lan:29600")
    catalog.unpin(db, "armory")
    assert catalog.effective(db) == {"armory": "http://armory:29600"}


@pytest.mark.parametrize("name", ["bard", "treasury", "", "Armory"])
def test_only_catalog_services_are_accepted(db, name):
    with pytest.raises(catalog.ServiceCatalogError):
        catalog.register(db, name, "http://x:1")


def test_a_bad_address_is_refused(db):
    with pytest.raises(catalog.ServiceCatalogError):
        catalog.register(db, "armory", "http://u:p@x:1")
    with pytest.raises(catalog.ServiceCatalogError):
        catalog.pin(db, "armory", "ftp://x")

import httpx
from src.api import create_app
from src.backends.factory import build_backend
from src.registry import ConnectionRegistry, InstanceManager
from src.citadel_auth import ServiceAuth
from src.citadel_auth.testing import make_stack


@pytest.fixture
async def client_as(tmp_path):
    stack = await make_stack(tmp_path)
    manager = InstanceManager({}, ConnectionRegistry({}, build_backend))
    app = create_app(manager, keyring=stack["treasury"], settings_db=tmp_path / "settings.db")

    def caller(name):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://treasury",
                                 auth=ServiceAuth(stack[name], "treasury"))

    yield caller
    await manager.close()


async def test_a_service_registers_only_itself(client_as):
    async with client_as("stronghold") as stronghold, client_as("armory") as armory:
        assert (await stronghold.put("/services/stronghold", json={"url": "http://stronghold:29650"})).status_code == 200
        assert (await stronghold.put("/services/armory", json={"url": "http://evil:1"})).status_code == 403
        assert (await armory.get("/services")).json() == {"services": {"stronghold": "http://stronghold:29650"}}


async def test_only_portcullis_pins_and_a_pin_shows_in_the_catalog(client_as):
    async with client_as("stronghold") as stronghold, client_as("portcullis") as portcullis, client_as("legion") as legion:
        assert (await stronghold.put("/admin/services/armory", json={"url": "http://x:1"})).status_code == 403
        assert (await portcullis.put("/admin/services/armory", json={"url": "http://armory.lan:29600"})).status_code == 200
        assert (await legion.get("/services")).json()["services"]["armory"] == "http://armory.lan:29600"
        assert (await portcullis.get("/admin/services")).status_code == 200
        assert (await portcullis.delete("/admin/services/armory")).status_code == 200
        assert "armory" not in (await legion.get("/services")).json()["services"]


@pytest.mark.parametrize("method,path,body", [
    ("PUT", "/services/armory", {"url": "http://x/path"}),
    ("PUT", "/admin/services/armory", {"url": "http://u:p@x"}),
    ("DELETE", "/admin/services/bard", None),
])
async def test_invalid_changes_are_refused(client_as, method, path, body):
    async with client_as("armory" if path == "/services/armory" else "portcullis") as client:
        response = await client.request(method, path, json=body)
        assert response.status_code == 400
