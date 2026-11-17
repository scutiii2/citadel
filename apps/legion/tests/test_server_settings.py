"""The MCP servers Legion connects to: stored in its settings database, edited through /agents/servers."""

import pytest
from starlette.testclient import TestClient

from src import server
from src.citadel_auth import settings_store
from src.runtime import config_files
from src.tools.mcp_client.config import ConfigError, load_servers_config

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
