import json

import pytest

from src.brain.stack import STACKS
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
    assert client.get("/usage/records").json()[0]["total_tokens"] == 10


@pytest.mark.parametrize("how", ["single", "all", "folder"])
def test_deleting_the_chat_deletes_its_stack(client, chat, how, db_gateway):
    client.post(f"/stack/{chat}/items", json={"text": "a"})
    target = "/chats" if how == "all" else f"/chats/{chat}"
    if how == "folder":
        folder_id = folder(client)["id"]
        assert client.patch(f"/chats/{chat}", json={"folder_id": folder_id}).status_code == 200
        target = f"/chat-folders/{folder_id}"
    assert client.delete(target).status_code == 204
    assert client.get(f"/stack/{chat}").status_code == 404
    assert client.portal.call(db_gateway.get, STACKS, f"{IDENTITY['uid']}:{chat}") is None


def test_purge_removes_every_stack_of_an_account(client, chat):
    client.post(f"/stack/{chat}/items", json={"text": "a"})
    assert client.delete(f"/stack/accounts/{IDENTITY['uid']}").status_code == 204
    assert client.get(f"/stack/{chat}").json()["used"] == 0


def test_validation_errors_do_not_echo_stack_text(client, chat):
    text = "sample private note " * 120
    answer = client.post(f"/stack/{chat}/items", json={"text": text})
    assert answer.status_code == 422
    assert "sample private note" not in answer.text


def test_treasury_error_is_a_safe_503(client, chat, db_gateway, monkeypatch):
    from src.document_store import DbGatewayError

    async def unavailable(*args):
        raise DbGatewayError("sample upstream error")

    monkeypatch.setattr(db_gateway, "get", unavailable)
    answer = client.get(f"/stack/{chat}")
    assert (answer.status_code, answer.json()) == (503, {"detail": "Storage is unavailable"})


def test_manual_compaction_accounts_for_usage_and_obeys_the_cap(make_client, tmp_path, agent):
    from src.usage.settings import UsageSettings
    from tests.test_turns import add_summarizer

    client = make_client(usage=UsageSettings(six_hour_token_limit=10))
    add_summarizer(tmp_path)
    assert put(client, CHAT).status_code == 200
    assert client.post(f"/stack/{CHAT}/items", json={"text": "example note"}).status_code == 201
    assert client.post(f"/stack/{CHAT}/compact").status_code == 200
    rows = client.get("/usage/records").json()
    assert [(row["kind"], row["total_tokens"]) for row in rows] == [("compaction", 10)]

    assert client.post(f"/stack/{CHAT}/items", json={"text": "third example"}).status_code == 201
    blocked = client.post(f"/stack/{CHAT}/compact")
    assert blocked.status_code == 429 and blocked.headers["Retry-After"]
    assert len(agent.interprets) == 1


def test_recreated_chat_cannot_see_an_orphaned_stack(client, chat, db_gateway, monkeypatch):
    original_delete = db_gateway.delete

    async def fail_stack_deletion(collection, key):
        if collection == "brain_stacks":
            raise OSError("example cleanup failure")
        return await original_delete(collection, key)

    assert client.post(f"/stack/{chat}/items", json={"text": "example old note"}).status_code == 201
    monkeypatch.setattr(db_gateway, "delete", fail_stack_deletion)
    assert client.delete(f"/chats/{chat}").status_code == 204
    assert put(client, chat).status_code == 200
    assert client.get(f"/stack/{chat}").json()["used"] == 0
