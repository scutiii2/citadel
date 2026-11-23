"""/agents/model-gateways: what Legion admin's Model gateways page reads and writes."""

import pytest
from starlette.testclient import TestClient

from src import gateway, server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "_database", lambda: tmp_path / "settings.db")
    for name in ("_chat", "_chat_store", "_decision", "_decision_store"):
        monkeypatch.setattr(gateway, name, None)
    return TestClient(server.mcp.streamable_http_app())


def test_an_entry_is_saved_listed_and_deleted(client):
    entry = {"provider": "openai", "url": "http://host.docker.internal:11434/v1", "model": "m", "api_key": "secret"}
    saved = client.put("/agents/model-gateways/conversation/local", json=entry)
    assert saved.status_code == 200
    assert "secret" not in saved.text
    listed = client.get("/agents/model-gateways/conversation").json()
    assert [row["id"] for row in listed["gateways"]] == ["local"]
    assert "presets" in listed and "form" in listed
    assert client.delete("/agents/model-gateways/conversation/local").status_code == 200
    assert client.delete("/agents/model-gateways/conversation/local").status_code == 404
    assert client.get("/agents/model-gateways/conversation").json()["gateways"] == []


def test_an_invalid_entry_is_refused_with_a_message(client):
    response = client.put("/agents/model-gateways/decision/Bad Id", json={"kind": "ollama"})
    assert response.status_code == 422 and response.json()["error"]


def test_the_decision_list_has_its_kinds(client):
    body = client.get("/agents/model-gateways/decision").json()
    assert set(body["kinds"]) == {"typesafe", "ollama", "scuti", "freellmapi"}


def test_unknown_kind_and_unknown_entry(client):
    assert client.get("/agents/model-gateways/other").status_code == 404
    answer = client.post("/agents/model-gateways/decision/nope/test").json()
    assert answer["ok"] is False and "nope" in answer["message"]
