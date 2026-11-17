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


def test_model_names_are_listed_saved_used_by_gateways_and_removable(client, db, monkeypatch):
    from src.providers import llm_config

    monkeypatch.delenv("VLLM_MODEL_DEFAULT", raising=False)
    names = {row["name"]: row for row in client.get("/agents/models").json()["models"]}
    assert "VLLM_MODEL_DEFAULT" in names and "AZURE_OPENAI_DEPLOYMENT_HEAVY" in names
    assert names["VLLM_MODEL_DEFAULT"] == {"name": "VLLM_MODEL_DEFAULT", "value": "", "stored": False}

    saved = client.put("/agents/models", json={"VLLM_MODEL_DEFAULT": " llama-3 "})

    assert saved.status_code == 200 and saved.json()["applies"] == "next agent start"
    assert llm_config.gateway("openai", "vllm")["model"] == "llama-3"
    monkeypatch.setenv("VLLM_MODEL_DEFAULT", "from-env")
    assert llm_config.gateway("openai", "vllm")["model"] == "llama-3"  # a saved name wins over the environment

    assert client.put("/agents/models", json={"VLLM_MODEL_DEFAULT": None}).status_code == 200
    assert llm_config.gateway("openai", "vllm")["model"] == "from-env"


def test_a_bad_model_name_change_saves_nothing(client, db):
    for bad in ({}, {"NOT_A_NAME": "x"}, {"VLLM_MODEL_DEFAULT": "  "}, {"VLLM_MODEL_DEFAULT": "x" * 201}):
        assert client.put("/agents/models", json=bad).status_code == 400
    refused = client.put("/agents/models", json={"VLLM_MODEL_LIGHT": "ok", "NOT_A_NAME": "x"})

    assert refused.json()["error"] == "Unknown model name: NOT_A_NAME."
    assert settings_store.read_all(db, "models") == {}


def test_the_treasury_address_routes_are_removed(client):
    assert client.get("/agents/treasury-address").status_code == 404
    assert client.put("/agents/treasury-address", json={"url": "http://treasury:29602"}).status_code == 404
