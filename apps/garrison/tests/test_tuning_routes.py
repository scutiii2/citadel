# apps/garrison/tests/test_tuning_routes.py
"""/agents/tuning: what ember_api's admin page reads and writes."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src import server
from src.runtime import config_files, tuning_overrides


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "config_tuning.json"
    examples = Path(config_files.__file__).resolve().parents[2] / "configs"
    path.with_suffix(".json.example").write_bytes((examples / "config_tuning.json.example").read_bytes())
    monkeypatch.setattr(config_files, "TUNING_PATH", path)
    monkeypatch.setattr(tuning_overrides, "_seen", None)
    return TestClient(server.mcp.streamable_http_app())


def test_get_returns_defaults_overrides_and_effective(client):
    body = client.get("/agents/tuning").json()
    assert body["overrides"] == {}
    assert body["defaults"]["token_limits"]["default"]["max_tool_rounds"] == 15
    assert body["effective"] == body["defaults"]
    assert "chains" not in body["defaults"]["classifier"]


def test_put_saves_and_returns_the_merged_view(client):
    response = client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["overrides"] == {"token_limits.default.max_tool_rounds": 20}
    assert body["effective"]["token_limits"]["default"]["max_tool_rounds"] == 20
    assert body["defaults"]["token_limits"]["default"]["max_tool_rounds"] == 15


def test_put_null_resets_a_path(client):
    client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": 20})
    body = client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": None}).json()
    assert body["overrides"] == {}


def test_put_refuses_a_bad_change_and_saves_nothing(client):
    response = client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": 500, "classifier.triage_trace": True})
    assert response.status_code == 400
    assert "max_tool_rounds" in response.json()["error"]
    assert client.get("/agents/tuning").json()["overrides"] == {}


def test_put_refuses_a_body_that_is_not_an_object(client):
    assert client.put("/agents/tuning", json=[1]).status_code == 400
