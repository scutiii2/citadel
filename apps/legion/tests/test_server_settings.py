"""The MCP servers Legion connects to: stored in its settings database, edited through /agents/servers."""

import pytest
from starlette.testclient import TestClient

from src import server
from src.citadel_auth import settings_store
from src.runtime import config_files
from src.tools.mcp_client.config import ConfigError, OriginRef, load_servers_config, validate_server

ENTRY = {"label": "Tools", "description": "d", "transport": "http", "url": "http://armory:29600/mcp"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "settings.db"
    monkeypatch.setattr(config_files, "SETTINGS_DB", path)
    return path


@pytest.fixture
def client(db):
    return TestClient(server.mcp.streamable_http_app())


def test_servers_load_from_the_database(db):
    settings_store.put(db, "servers", "main", ENTRY)

    servers = load_servers_config(db, {"main": "http://other/mcp"})

    assert servers["main"].url == "http://other/mcp"


def test_a_bad_stored_entry_is_refused_at_load(db):
    settings_store.put(db, "servers", "main", {"transport": "carrier-pigeon"})

    with pytest.raises(ConfigError):
        load_servers_config(db)


def test_put_validates_saves_and_delete_removes(client, db):
    assert client.put("/agents/servers/bad", json={"transport": "carrier-pigeon"}).status_code == 400
    assert client.put("/agents/servers/main", json=ENTRY).status_code == 200

    assert client.get("/agents/servers").json() == {"servers": {"main": ENTRY}}
    assert client.delete("/agents/servers/main").status_code == 200
    assert client.get("/agents/servers").json() == {"servers": {}}


def test_the_model_name_routes_are_removed(client):
    assert client.get("/agents/models").status_code == 404
    assert client.put("/agents/models", json={"VLLM_MODEL_DEFAULT": "x"}).status_code == 404


def test_the_treasury_address_routes_are_removed(client):
    assert client.get("/agents/treasury-address").status_code == 404
    assert client.put("/agents/treasury-address", json={"url": "http://treasury:29602"}).status_code == 404


ORIGIN_ENTRY = {"label": "Bard", "transport": "http", "service_id": "s-bard", "path": "/mcp",
                "auth": {"type": "header", "header_name": "X-Internal-Token", "header_value": "parent"},
                "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}


def test_an_origin_entry_loads_with_ordered_origins_and_no_url():
    config = validate_server("bard", ORIGIN_ENTRY)
    assert config.url is None and config.service_id == "s-bard" and config.path == "/mcp"
    assert config.origins == (OriginRef("o1"), OriginRef("o2", "second"))
    assert "second" not in repr(config.origins[1])


@pytest.mark.parametrize("change", [
    {"url": "http://x:1/mcp"},                 # url and origins together
    {"origins": []},                            # no origin
    {"service_id": ""},                         # no service
    {"origins": [{"origin_id": "o1"}, {"origin_id": "o1"}]},  # listed twice
    {"origins": [{}]},                          # no id
    {"path": "mcp"}, {"path": "/m?x=1"},        # bad path
    {"transport": "stdio", "command": "x"},     # origins need http
])
def test_a_bad_origin_entry_is_refused(change):
    with pytest.raises(ConfigError):
        validate_server("bard", {**ORIGIN_ENTRY, **change})


def test_the_main_defaults_do_not_touch_an_origin_entry(db):
    settings_store.put(db, "servers", "main", {k: v for k, v in ORIGIN_ENTRY.items() if k != "auth"})
    servers = load_servers_config(db, {"main": "http://other/mcp"})
    assert servers["main"].url is None and len(servers["main"].origins) == 2
