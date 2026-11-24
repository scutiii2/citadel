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
    assert answer["ok"] is False and "nope" in answer["message"] and answer["code"] == "404"


def test_chat_presets_carry_their_template_tiers_and_descriptions(client):
    presets = client.get("/agents/model-gateways/conversation").json()["presets"]
    assert presets["claude"]["models"]["light"] == "claude-haiku-5-5"
    assert presets["claude"]["descriptions"]["standard"] == "most tasks"
    assert "models" not in presets["minicpm"]


def test_a_body_tests_the_unsaved_form_and_saves_nothing(client):
    bad = client.post("/agents/model-gateways/decision/new/test", json={"kind": "ollama"}).json()
    assert bad["ok"] is False and bad["code"] == "422" and "address" in bad["message"].lower()
    refused = client.post("/agents/model-gateways/decision/new/test", json={"kind": "ollama", "url": "http://127.0.0.1:9", "model": "m"}).json()
    assert refused["ok"] is False and refused["code"]
    assert client.get("/agents/model-gateways/decision").json()["gateways"] == []


def test_a_failed_test_names_the_real_cause_not_502(client):
    entry = {"provider": "anthropic", "auth": "key", "api_key": "k", "base_url": "http://127.0.0.1:9", "model": "m"}
    answer = client.post("/agents/model-gateways/conversation/new/test", json=entry).json()
    assert answer["ok"] is False and answer["code"] == "NET"
    assert "could not be reached" in answer["message"]


def test_a_gateway_cannot_be_untrusted_or_deleted_while_an_agent_depends_on_it(client):
    claude = {"provider": "anthropic", "api_key": "k", "model": "claude-sonnet-5-5"}
    assert client.put("/agents/model-gateways/conversation/claude", json=claude).json()["trusted"] is True
    refused = client.put("/agents/model-gateways/conversation/claude", json={**claude, "trusted": False})
    assert refused.status_code == 409 and "at least one trusted gateway" in refused.json()["error"]
    assert client.delete("/agents/model-gateways/conversation/claude").status_code == 409
    other = {"provider": "openai", "base_url": "http://host.docker.internal:29652/v1", "model": "m"}
    assert client.put("/agents/model-gateways/conversation/freellmapi", json={**other, "trusted": True}).json()["trusted"] is True
    assert client.put("/agents/model-gateways/conversation/freellmapi", json={**other, "trusted": False}).status_code == 200


def test_presets_say_whether_they_start_trusted(client):
    chat = client.get("/agents/model-gateways/conversation").json()["presets"]
    assert chat["claude"]["trusted"] and chat["gemini"]["trusted"] and chat["minicpm"]["trusted"]
    assert not chat["omniroute"]["trusted"] and not chat["freellmapi"]["trusted"]
    decision = client.get("/agents/model-gateways/decision").json()["presets"]
    assert decision["jev"]["trusted"] and not decision["freellmapi"]["trusted"]
