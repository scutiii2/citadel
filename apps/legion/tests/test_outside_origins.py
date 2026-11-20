"""Saving an MCP connection by address: Legion registers each origin in Treasury and stores only ids."""

import httpx
import pytest
from starlette.testclient import TestClient

from src import server
from src.citadel_auth import settings_store
from src.runtime import config_files, outside_origins


class FakeTreasury:
    def __init__(self):
        self.origins, self.calls = {}, []  # origin -> (service_id, origin_id)

    @staticmethod
    def _split(address):
        parts = address.split("/", 3)
        return "/".join(parts[:3]), ("/" + parts[3]) if len(parts) > 3 else ""

    async def post(self, path, body):
        self.calls.append((path, body))
        origin, tail = self._split(body.get("address") or body["origin"])
        if path == "/outside/origins" and origin not in self.origins:
            if not body.get("name"):
                return httpx.Response(400, json={"error": "this address is new: give it a name"})
            self.origins[origin] = ("s-" + body["name"], f"o{len(self.origins) + 1}")
        found = self.origins.get(origin)
        group = None
        if found is not None:
            group = {"service_id": found[0], "name": found[0][2:], "used_by": ["legion"], "origins": [
                {"origin_id": oid, "origin": registered}
                for registered, (sid, oid) in self.origins.items() if sid == found[0]
            ]}
        if path == "/outside/origins":
            return httpx.Response(200, json=group)
        return httpx.Response(200, json={"found": found is not None, "origin": origin, "path": tail,
                                         "origin_id": found[1] if found else None, "group": group})


@pytest.fixture
def treasury(monkeypatch):
    fake = FakeTreasury()
    monkeypatch.setattr(outside_origins, "_post", fake.post)
    monkeypatch.setattr(outside_origins, "origin_address", lambda origin_id: {"o1": "http://bard:29400"}.get(origin_id))
    async def refresh():
        return True

    monkeypatch.setattr(outside_origins.catalog, "refresh", refresh)
    return fake


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "settings.db"
    monkeypatch.setattr(config_files, "SETTINGS_DB", path)
    return path


@pytest.fixture
def client(db):
    return TestClient(server.mcp.streamable_http_app())


BODY = {"label": "Bard", "transport": "http",
        "auth": {"type": "header", "header_name": "X-Internal-Token", "header_value": "parent"},
        "addresses": [{"address": "http://bard:29400/mcp", "name": "bard"},
                      {"address": "http://bard2:29400/mcp", "name": "bard", "header_value": "second"}]}


def test_lookup_passes_treasurys_answer_on(client, treasury):
    assert client.post("/agents/servers/lookup", json={"address": "http://x:1/mcp"}).json()["found"] is False
    treasury.origins["http://x:1"] = ("s-x", "o9")
    found = client.post("/agents/servers/lookup", json={"address": "http://x:1/mcp"}).json()
    assert found["found"] is True and found["path"] == "/mcp" and found["group"]["name"] == "x"


def test_saving_addresses_registers_them_and_stores_only_ids_and_tokens(client, treasury, db):
    assert client.put("/agents/servers/bard", json=BODY).status_code == 200
    stored = settings_store.read_all(db, "servers")["bard"]
    assert stored == {"label": "Bard", "transport": "http", "service_id": "s-bard", "path": "/mcp",
                      "auth": BODY["auth"],
                      "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}
    assert "addresses" not in stored and "http://bard" not in str(stored)
    assert [call[0] for call in treasury.calls].count("/outside/origins") == 2


def test_an_override_that_is_not_retyped_is_kept(client, treasury, db):
    client.put("/agents/servers/bard", json=BODY)
    again = {**BODY, "addresses": [{"address": "http://bard:29400/mcp"}, {"address": "http://bard2:29400/mcp"}]}
    assert client.put("/agents/servers/bard", json=again).status_code == 200
    assert settings_store.read_all(db, "servers")["bard"]["origins"][1] == {"origin_id": "o2", "header_value": "second"}


def test_a_new_address_needs_a_name_and_all_addresses_need_one_service(client, treasury, db):
    unnamed = {**BODY, "addresses": [{"address": "http://new:1/mcp"}]}
    refused = client.put("/agents/servers/bard", json=unnamed)
    assert refused.status_code == 400 and "give it a name" in refused.json()["error"]
    mixed = {**BODY, "addresses": [{"address": "http://a:1/mcp", "name": "a"}, {"address": "http://b:1/mcp", "name": "b"}]}
    assert "same outside service" in client.put("/agents/servers/bard", json=mixed).json()["error"]
    assert settings_store.read_all(db, "servers") == {}


def test_treasury_down_refuses_the_save_and_writes_nothing(client, monkeypatch, db):
    async def down(path, body):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(outside_origins, "_post", down)
    refused = client.put("/agents/servers/bard", json=BODY)
    assert refused.status_code == 502 and refused.json()["error"].startswith("[1002]")
    assert settings_store.read_all(db, "servers") == {}


def test_the_list_shows_the_resolved_address_of_each_origin(client, treasury, db):
    client.put("/agents/servers/bard", json=BODY)
    origins = client.get("/agents/servers").json()["servers"]["bard"]["origins"]
    assert [o["origin"] for o in origins] == ["http://bard:29400", None]


def test_leaving_the_parent_token_blank_keeps_it_without_returning_either_token(client, treasury, db):
    assert client.put("/agents/servers/bard", json=BODY).status_code == 200
    update = {**BODY, "auth": {"type": "header", "header_name": "X-Internal-Token"}}
    assert client.put("/agents/servers/bard", json=update).status_code == 200
    stored = settings_store.read_all(db, "servers")["bard"]
    assert stored["auth"]["header_value"] == "parent"
    shown = client.get("/agents/servers").json()["servers"]["bard"]
    assert shown["auth"] == {"type": "header", "header_name": "X-Internal-Token", "has_value": True}
    assert shown["origins"][1] == {"origin_id": "o2", "origin": None, "has_override": True}


def test_a_connection_with_different_paths_is_refused_before_registering(client, treasury, db):
    mixed = {**BODY, "addresses": [BODY["addresses"][0], {"address": "http://bard2:29400/other", "name": "bard"}]}
    assert client.put("/agents/servers/bard", json=mixed).status_code == 400
    assert treasury.origins == {}
    assert settings_store.read_all(db, "servers") == {}


def test_an_override_with_no_connection_token_is_refused_before_registering(client, treasury, db):
    without_parent = {key: value for key, value in BODY.items() if key != "auth"}
    response = client.put("/agents/servers/bard", json=without_parent)
    assert response.status_code == 400
    assert "connection token" in response.json()["error"]
    assert treasury.origins == {}
    assert settings_store.read_all(db, "servers") == {}


def test_invalid_local_settings_leave_the_treasury_catalog_untouched(client, treasury, db):
    refused = client.put("/agents/servers/bard", json={**BODY, "label": ""})
    assert refused.status_code == 400
    assert treasury.calls == []
    assert settings_store.read_all(db, "servers") == {}
