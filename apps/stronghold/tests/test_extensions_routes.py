"""/api/user-extensions: an account's own MCP servers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.extensions import service as svc
from tests.conftest import FakeAgent
from tests.helpers import login

URL = "/user-extensions"
EXT_URL = "https://notes.example.com/mcp"


def add(client: TestClient, label: str = "Notes", url: str = EXT_URL, **extra):
    return client.post(URL, json={"label": label, "url": url, **extra})


def test_the_requester_is_required(client: TestClient) -> None:
    anonymous = {"X-Requester-Uid": ""}
    assert client.get(URL, headers=anonymous).status_code == 400
    assert client.post(URL, json={"label": "x", "url": EXT_URL}, headers=anonymous).status_code == 400


def test_add_returns_the_extension_with_its_live_status(client: TestClient, agent: FakeAgent) -> None:
    agent.probe_results[EXT_URL] = {"status": "connected", "error": None, "tools": ["search", "add"]}

    created = add(client, headers={"X-Key": "s3cret", "Authorization": "Bearer t0ken"})

    assert created.status_code == 201
    assert created.json() == {
        "id": "notes", "label": "Notes", "description": "", "url": EXT_URL,
        "header_names": ["Authorization", "X-Key"], "enabled": True,
        "status": "connected", "error": None, "tools": ["search", "add"],
    }
    assert agent.probes[-1]["extension_url"] == EXT_URL
    assert agent.probes[-1]["headers"] == {"X-Key": "s3cret", "Authorization": "Bearer t0ken"}


def test_no_reply_ever_contains_a_header_value(client: TestClient) -> None:
    created = add(client, headers={"X-Key": "s3cret-value"})
    listed = client.get(URL)
    patched = client.patch(f"{URL}/notes", json={"label": "Renamed"})

    for response in (created, listed, patched):
        assert "s3cret-value" not in response.text


def test_an_unreachable_extension_is_still_saved(client: TestClient, agent: FakeAgent) -> None:
    agent.probe_results[EXT_URL] = {"status": "error", "error": "That address is not allowed", "tools": []}

    created = add(client)

    assert created.status_code == 201
    assert (created.json()["status"], created.json()["error"]) == ("error", "That address is not allowed")
    assert [e["id"] for e in client.get(URL).json()] == ["notes"]


def test_an_agent_that_cannot_be_asked_leaves_the_status_unknown(client: TestClient, agent: FakeAgent) -> None:
    agent.probe_fail = "Could not reach the agent: refused"

    created = add(client)

    assert created.status_code == 201
    assert (created.json()["status"], created.json()["error"]) == ("unknown", "Couldn't check right now")


def test_slugs_are_made_from_the_label_and_stay_unique(client: TestClient) -> None:

    assert add(client, label="My Notes!").json()["id"] == "my_notes"
    assert add(client, label="My Notes!").json()["id"] == "my_notes_2"


def test_bad_input_is_refused_with_a_message(client: TestClient) -> None:

    for body in (
        {"label": "x", "url": "ftp://x.com/m"},
        {"label": "x", "url": "https://u:p@x.com/m"},
        {"label": "  ", "url": EXT_URL},
        {"label": "x", "url": EXT_URL, "headers": {"Host": "evil"}},
        {"label": "x", "url": EXT_URL, "headers": {"X": ""}},
        {"label": "x", "url": EXT_URL, "headers": {"bad name": "v"}},
    ):
        response = client.post(URL, json=body)
        assert response.status_code == 422, body
        assert isinstance(response.json()["detail"], str) and response.json()["detail"]
    assert client.post(URL, json={"url": EXT_URL}).status_code == 422  # a label is required


def test_the_limit_is_a_conflict(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "MAX_EXTENSIONS", 1)
    add(client)

    assert add(client, label="Two").status_code == 409


def test_an_account_only_sees_and_changes_its_own(client: TestClient) -> None:
    login(client, "alice")
    add(client, headers={"X-Key": "s3cret"})

    login(client, "bob")
    assert client.get(URL).json() == []
    assert client.patch(f"{URL}/notes", json={"enabled": False}).status_code == 404
    assert client.delete(f"{URL}/notes").status_code == 404
    assert add(client).json()["id"] == "notes"  # slugs are per account

    login(client, "alice")
    assert [e["id"] for e in client.get(URL).json()] == ["notes"]


def test_patch_changes_fields_and_enabled(client: TestClient) -> None:
    add(client, headers={"X-Key": "s3cret"})

    renamed = client.patch(f"{URL}/notes", json={"label": "My notes", "description": "work"}).json()
    off = client.patch(f"{URL}/notes", json={"enabled": False}).json()

    assert (renamed["label"], renamed["description"], renamed["id"]) == ("My notes", "work", "notes")
    assert off["enabled"] is False
    assert off["header_names"] == ["X-Key"]  # headers untouched


def test_patch_headers_replace_them_and_a_new_host_clears_them(client: TestClient) -> None:
    add(client, headers={"X-Key": "one"})

    replaced = client.patch(f"{URL}/notes", json={"headers": {"Authorization": "Bearer two"}}).json()
    same_host = client.patch(f"{URL}/notes", json={"url": "https://notes.example.com/other"}).json()
    moved = client.patch(f"{URL}/notes", json={"url": "https://elsewhere.example.org/mcp"}).json()

    assert replaced["header_names"] == ["Authorization"]
    assert same_host["header_names"] == ["Authorization"]
    assert moved["header_names"] == []


def test_patch_needs_something_to_change(client: TestClient) -> None:
    add(client)

    assert client.patch(f"{URL}/notes", json={}).status_code == 422
    assert client.patch(f"{URL}/Bad_Slug", json={"enabled": False}).status_code == 422


def test_delete(client: TestClient) -> None:
    add(client)

    assert client.delete(f"{URL}/notes").status_code == 204
    assert client.get(URL).json() == []
    assert client.delete(f"{URL}/notes").status_code == 404


def test_the_status_is_cached_and_an_edit_asks_again(client: TestClient, agent: FakeAgent) -> None:
    add(client)
    asked = len(agent.probes)

    client.get(URL)
    client.get(URL)
    assert len(agent.probes) == asked  # served from the cache

    client.patch(f"{URL}/notes", json={"url": "https://notes.example.com/v2"})
    assert len(agent.probes) == asked + 1


def test_a_disabled_extension_is_not_probed(client: TestClient, agent: FakeAgent) -> None:
    add(client)
    client.patch(f"{URL}/notes", json={"enabled": False})
    asked = len(agent.probes)

    listed = client.get(URL).json()[0]

    assert len(agent.probes) == asked
    assert (listed["enabled"], listed["status"], listed["tools"]) == (False, "unknown", [])


def test_the_headers_are_encrypted_in_the_gateway(client: TestClient, db_gateway) -> None:
    add(client, headers={"X-Key": "s3cret-value"})

    (doc,) = [d for (collection, _), d in db_gateway.records.items() if collection == "user_extensions"]
    token = doc["headers_encrypted"]

    assert token and "s3cret-value" not in token


def test_unreadable_headers_show_an_error_and_can_be_repaired(client: TestClient, db_gateway) -> None:
    add(client, headers={"X-Key": "one"})
    add(client, label="Wiki", url="https://wiki.example.com/mcp")
    for (collection, _), doc in db_gateway.records.items():
        if collection == "user_extensions" and doc["slug"] == "notes":
            doc["headers_encrypted"] = "garbage"

    broken = next(e for e in client.get(URL).json() if e["id"] == "notes")
    wiki = next(e for e in client.get(URL).json() if e["id"] == "wiki")
    repaired = client.patch(f"{URL}/notes", json={"headers": {"X-Key": "two"}}).json()

    assert (broken["status"], broken["header_names"]) == ("error", [])
    assert "can't be read" in broken["error"]
    assert wiki["status"] == "connected"
    assert (repaired["status"], repaired["header_names"]) == ("connected", ["X-Key"])


def test_gateway_down_gives_503(client: TestClient, db_gateway, monkeypatch) -> None:
    from src.document_store import DbGatewayUnavailable


    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("db_gateway is not reachable")

    for method in ("get", "put", "create", "delete", "query"):
        monkeypatch.setattr(db_gateway, method, down)

    assert client.get(URL).status_code == 503
    assert client.post(URL, json={"label": "Notes", "url": "https://notes.example.com/mcp"}).status_code == 503


def test_for_turn_hands_over_enabled_extensions_with_their_headers(client: TestClient) -> None:
    add(client, headers={"X-Key": "s3cret"})
    add(client, label="Wiki", url="https://wiki.example.com/mcp")
    client.patch(f"{URL}/wiki", json={"enabled": False})

    turn = client.get(f"{URL}/for-turn").json()

    assert turn["items"] == [{"id": "notes", "label": "Notes", "url": EXT_URL, "headers": {"X-Key": "s3cret"}}]
    assert turn["skipped"] == []


def test_purge_removes_every_extension_of_the_account(client: TestClient) -> None:
    add(client)
    add(client, label="Wiki", url="https://wiki.example.com/mcp")

    assert client.delete(f"{URL}/accounts/u-1").status_code == 204
    assert client.get(URL).json() == []
