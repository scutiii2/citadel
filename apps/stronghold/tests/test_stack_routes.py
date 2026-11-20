import json

import pytest

from tests.auth_helpers import identity
from tests.conftest import AGENTS, IDENTITY
from tests.test_chats import A as CHAT, folder, put

@pytest.fixture
def chat(client):
    """A chat the account owns (create it the way tests/test_chats.py does)."""
    assert put(client, CHAT).status_code == 200
    return CHAT


@pytest.fixture
def summarizer(client):
    registry = client.app.state.settings.agents_registry_path
    helper = {"id": "context-summarizer", "label": "Context Summarizer", "url": "http://summarizer.internal/mcp"}
    registry.write_text(json.dumps({"agents": [*AGENTS, helper]}), encoding="utf-8")


def test_a_chat_the_account_does_not_own_has_no_stack(client):
    assert client.get("/stack/nope").status_code == 404
    assert client.post("/stack/nope/items", json={"text": "x"}).status_code == 404


def test_add_list_pin_and_remove(client, chat):
    added = client.post(f"/stack/{chat}/items", json={"text": "likes tea"})
    assert added.status_code == 201
    item = added.json()
    assert item["source"] == "user"
    view = client.get(f"/stack/{chat}").json()
    assert view["used"] == 1 and view["warn"] is False
    assert client.put(f"/stack/{chat}/items/{item['id']}", json={"pinned": True}).json()["pinned"] is True
    assert client.delete(f"/stack/{chat}/items/{item['id']}").status_code == 204
    assert client.get(f"/stack/{chat}").json()["used"] == 0


def test_bad_bodies_and_missing_items(client, chat):
    assert client.post(f"/stack/{chat}/items", json={"text": " "}).status_code == 422
    assert client.post(f"/stack/{chat}/items", json={}).status_code == 422
    assert client.delete(f"/stack/{chat}/items/99").status_code == 404


def test_another_account_cannot_see_the_stack(client, chat):
    client.post(f"/stack/{chat}/items", json={"text": "private"})
    other = identity(uid="u-2", username="bo", email="bo@example.com")
    assert client.get(f"/stack/{chat}", headers=other).status_code == 404


def test_compact_replaces_items_and_reports(client, chat, agent, summarizer):
    agent.summary = "merged"
    for text in ("a", "b", "c"):
        client.post(f"/stack/{chat}/items", json={"text": text})
    body = client.post(f"/stack/{chat}/compact").json()
    assert body["compacted"] is True and body["replaced"] == 3
    assert [i["text"] for i in body["items"]] == ["merged"]


def test_compaction_failure_is_a_502_and_changes_nothing(client, chat, agent, summarizer):
    agent.summary = ""
    client.post(f"/stack/{chat}/items", json={"text": "a"})
    assert client.post(f"/stack/{chat}/compact").status_code == 502
    assert client.get(f"/stack/{chat}").json()["used"] == 1


@pytest.mark.parametrize("how", ["single", "all", "folder"])
def test_deleting_the_chat_deletes_its_stack(client, chat, how):
    client.post(f"/stack/{chat}/items", json={"text": "a"})
    target = "/chats" if how == "all" else f"/chats/{chat}"
    if how == "folder":
        folder_id = folder(client)["id"]
        assert client.patch(f"/chats/{chat}", json={"folder_id": folder_id}).status_code == 200
        target = f"/chat-folders/{folder_id}"
    assert client.delete(target).status_code == 204
    view = client.portal.call(client.app.state.stacks.view, IDENTITY["uid"], chat)
    assert view["used"] == 0


def test_purge_removes_every_stack_of_an_account(client, chat):
    client.post(f"/stack/{chat}/items", json={"text": "a"})
    assert client.delete(f"/stack/accounts/{IDENTITY['uid']}").status_code == 204
    assert client.get(f"/stack/{chat}").json()["used"] == 0


def test_validation_errors_do_not_echo_stack_text(client, chat):
    text = "sample private note " * 120
    answer = client.post(f"/stack/{chat}/items", json={"text": text})
    assert answer.status_code == 422
    assert "sample private note" not in answer.text
