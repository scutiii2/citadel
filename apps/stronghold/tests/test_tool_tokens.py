"""Stronghold no longer accepts administrative tool credentials."""

from fastapi.testclient import TestClient


def test_tool_credentials_only_live_in_armory(client: TestClient) -> None:
    path = "/admin/tool-tokens"
    assert client.get(path).status_code == 404
    assert client.put(path, json={"bard": "unused-fixture-token"}).status_code == 404
    assert hasattr(client.app.state, "connections")
    assert not hasattr(client.app.state, "env_tokens")
