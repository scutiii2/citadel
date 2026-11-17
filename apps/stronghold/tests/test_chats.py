"""/chats and /chat-folders: chat history, folders and search, kept in Treasury."""

from __future__ import annotations

from tests.auth_helpers import identity, caller, requester

import pytest
from fastapi.testclient import TestClient

from src.chats import store as chat_store
from tests.conftest import FakeDbGateway
from tests.helpers import login, uid_of

A = "chat-0001-aaaa"
B = "chat-0002-bbbb"
C = "chat-0003-cccc"
MESSAGES = [{"role": "user", "content": "hello there"}, {"role": "assistant", "content": "Hi!", "model": "m", "total_tokens": 9}]
ANONYMOUS = identity(uid="")


def put(client: TestClient, chat_id: str = A, title: str = "First chat", messages=None, **extra):
    return client.put(f"/chats/{chat_id}", json={"title": title, "messages": MESSAGES if messages is None else messages, **extra})


def folder(client: TestClient, name: str = "Work") -> dict:
    response = client.post("/chat-folders", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def remove_folder(client: TestClient, folder_id: int, running: list[str] | None = None):
    return client.request("DELETE", f"/chat-folders/{folder_id}", json={"running": running or []})


# --- access ----------------------------------------------------------------------------------


def test_every_route_needs_the_requester(client: TestClient) -> None:
    for method, url, body in [("GET", "/chats", None), ("DELETE", "/chats", None), ("GET", "/chats/search?q=hi", None),
                              ("GET", f"/chats/{A}", None), ("PUT", f"/chats/{A}", {"title": "t", "messages": []}),
                              ("PATCH", f"/chats/{A}", {"pinned": True}), ("POST", f"/chats/{A}/branch", {"upto": 1}),
                              ("PUT", f"/chats/{A}/messages", {"messages": []}), ("DELETE", f"/chats/{A}", None),
                              ("GET", "/chat-folders", None), ("POST", "/chat-folders", {"name": "x"}),
                              ("PATCH", "/chat-folders/1", {"name": "x"}), ("DELETE", "/chat-folders/1", None)]:
        assert client.request(method, url, json=body, headers=ANONYMOUS).status_code == 400, (method, url)


# --- chats -----------------------------------------------------------------------------------


def test_put_creates_then_replaces(client: TestClient) -> None:
    created = put(client)
    assert created.status_code == 200
    assert created.json()["title"] == "First chat" and created.json()["message_count"] == 2
    assert (created.json()["folder_id"], created.json()["pinned"], created.json()["second_brain_scope"]) == (None, False, "instance")

    replaced = put(client, title="  Renamed   chat ", messages=MESSAGES[:1], agent_id="claude-agent").json()

    assert (replaced["title"], replaced["message_count"], replaced["agent_id"]) == ("Renamed chat", 1, "claude-agent")
    assert replaced["created_at"] == created.json()["created_at"]
    assert client.get(f"/chats/{A}").json()["messages"] == MESSAGES[:1]


def test_messages_keep_everything_a_turn_recorded(client: TestClient) -> None:
    rich = [{"role": "assistant", "content": "x", "steps": [{"tool": "t", "ok": True}], "context_tokens": 3, "at": "2026-11-15T10:00:00.000Z"}]

    put(client, messages=rich)

    assert client.get(f"/chats/{A}").json()["messages"] == rich


@pytest.mark.parametrize("body", [
    {"title": "", "messages": []}, {"title": "   ", "messages": []}, {"title": "t" * 121, "messages": []},
    {"title": "t", "messages": [{"role": "system", "content": "x"}]}, {"title": "t", "messages": [{"role": "user"}]},
    {"messages": []},
])
def test_bad_chats_are_refused(client: TestClient, body: dict) -> None:
    assert client.put(f"/chats/{A}", json=body).status_code == 422
    assert client.get("/chats").json() == []


def test_chat_ids_are_validated(client: TestClient) -> None:
    assert client.get("/chats/short").status_code == 422
    assert client.put("/chats/has%20space%20in%20it", json={"title": "t", "messages": []}).status_code == 422


def test_list_is_newest_first_and_has_no_transcripts(client: TestClient, monkeypatch) -> None:
    ticks = iter(range(100))
    from datetime import datetime, timedelta
    monkeypatch.setattr(chat_store, "utcnow", lambda: datetime(2026, 1, 1) + timedelta(seconds=next(ticks)))
    put(client, A, "old")
    put(client, B, "new")
    put(client, A, "old again")  # touching a chat moves it to the top

    listed = client.get("/chats").json()

    assert [c["chat_id"] for c in listed] == [A, B]
    assert all("messages" not in c for c in listed)
    assert set(listed[0]) == {"chat_id", "title", "agent_id", "message_count", "folder_id", "pinned",
                              "save_to_second_brain", "second_brain_scope", "created_at", "updated_at"}


def test_chats_are_private_per_account(client: TestClient) -> None:
    login(client, "alice")
    put(client)
    login(client, "bob")

    assert client.get("/chats").json() == []
    assert client.get(f"/chats/{A}").status_code == 404
    assert client.delete(f"/chats/{A}").status_code == 404
    assert client.patch(f"/chats/{A}", json={"pinned": True}).status_code == 404
    assert client.post(f"/chats/{A}/branch", json={"upto": 1}).status_code == 404
    assert client.put(f"/chats/{A}/messages", json={"messages": []}).status_code == 404
    assert put(client, title="Bob's own, same id").status_code == 200  # ids clash only per account
    login(client, "alice")
    assert client.get(f"/chats/{A}").json()["title"] == "First chat"


def test_replace_messages_keeps_the_title_and_sets_the_agent_only_when_given(client: TestClient) -> None:
    put(client, agent_id="one")

    kept = client.put(f"/chats/{A}/messages", json={"messages": MESSAGES[:1]}).json()
    changed = client.put(f"/chats/{A}/messages", json={"messages": MESSAGES, "agent_id": "two"}).json()

    assert (kept["title"], kept["agent_id"], kept["message_count"]) == ("First chat", "one", 1)
    assert (changed["agent_id"], changed["message_count"]) == ("two", 2)


def test_a_chat_over_2_mb_and_too_many_chats_are_refused(client: TestClient, monkeypatch) -> None:
    big = [{"role": "user", "content": "x" * (2 * 1024 * 1024)}]
    assert put(client, messages=big).status_code == 413
    assert client.get("/chats").json() == []

    monkeypatch.setattr(chat_store, "MAX_CHATS_PER_ACCOUNT", 2)
    put(client, A), put(client, B)
    refused = put(client, C)
    assert refused.status_code == 413 and "At most 2 chats" in refused.json()["detail"]
    assert put(client, A, "same chat again").status_code == 200  # replacing needs no room
    assert client.put(f"/chats/{A}/messages", json={"messages": big}).status_code == 413


def test_update_changes_only_what_is_sent_and_leaves_the_time_alone(client: TestClient) -> None:
    before = put(client).json()

    pinned = client.patch(f"/chats/{A}", json={"pinned": True, "title": " New  name "}).json()
    brain = client.patch(f"/chats/{A}", json={"save_to_second_brain": True, "second_brain_scope": "personal"}).json()

    assert (pinned["pinned"], pinned["title"]) == (True, "New name")
    assert (brain["save_to_second_brain"], brain["second_brain_scope"], brain["pinned"]) == (True, "personal", True)
    assert brain["updated_at"] == before["updated_at"] and brain["message_count"] == 2


@pytest.mark.parametrize("body", [{}, {"title": ""}, {"second_brain_scope": "everyone"}, {"pinned": "maybe"}])
def test_an_empty_or_bad_update_is_refused(client: TestClient, body: dict) -> None:
    put(client)
    assert client.patch(f"/chats/{A}", json=body).status_code == 422


def test_filing_a_chat_and_taking_it_out(client: TestClient) -> None:
    put(client)
    work = folder(client)

    filed = client.patch(f"/chats/{A}", json={"folder_id": work["id"]}).json()
    assert filed["folder_id"] == work["id"]
    assert client.get("/chat-folders").json()[0]["chat_count"] == 1
    assert client.patch(f"/chats/{A}", json={"folder_id": None}).json()["folder_id"] is None
    assert client.get("/chat-folders").json()[0]["chat_count"] == 0
    assert client.patch(f"/chats/{A}", json={"folder_id": 4242}).json() == {"detail": "Folder not found"}


def test_another_accounts_folder_cannot_be_used(client: TestClient) -> None:
    login(client, "alice")
    theirs = folder(client)
    login(client, "bob")
    put(client)

    assert client.patch(f"/chats/{A}", json={"folder_id": theirs["id"]}).status_code == 404


# --- branch ----------------------------------------------------------------------------------


def test_branching_copies_up_to_an_answer_and_keeps_agent_and_folder_but_not_the_pin(client: TestClient) -> None:
    messages = [*MESSAGES, {"role": "user", "content": "more"}, {"role": "assistant", "content": "Sure."}]
    put(client, messages=messages, agent_id="claude-agent")
    work = folder(client)
    client.patch(f"/chats/{A}", json={"folder_id": work["id"], "pinned": True})

    branch = client.post(f"/chats/{A}/branch", json={"upto": 1})

    assert branch.status_code == 201
    new = branch.json()
    assert new["chat_id"] != A and new["title"] == "Branch of First chat"
    assert (new["agent_id"], new["folder_id"], new["pinned"], new["message_count"]) == ("claude-agent", work["id"], False, 2)
    assert new["messages"] == MESSAGES
    assert client.get(f"/chats/{A}").json()["message_count"] == 4  # the original is untouched
    assert client.get("/chat-folders").json()[0]["chat_count"] == 2


def test_a_branch_must_end_on_a_plain_answer(client: TestClient) -> None:
    put(client, messages=[*MESSAGES, {"role": "assistant", "content": "sum", "kind": "summary"}])

    for upto in (0, 2, 9):
        assert client.post(f"/chats/{A}/branch", json={"upto": upto}).status_code == 422
    assert client.post(f"/chats/{A}/branch", json={"upto": -1}).status_code == 422
    assert len(client.get("/chats").json()) == 1


def test_a_long_title_is_cut_for_the_branch(client: TestClient) -> None:
    put(client, title="t" * 120)

    new = client.post(f"/chats/{A}/branch", json={"upto": 1}).json()

    assert len(new["title"]) == 120 and new["title"].endswith("…")


# --- deleting --------------------------------------------------------------------------------


def test_deleting_a_chat_removes_its_transcript_and_its_share_links(client: TestClient, db_gateway: FakeDbGateway) -> None:
    put(client), put(client, B, "kept")
    token = client.post("/shares", json={"chat_id": A, "title": "t", "messages": MESSAGES}).json()["token"]
    other = client.post("/shares", json={"chat_id": B, "title": "t", "messages": MESSAGES}).json()["token"]

    assert client.delete(f"/chats/{A}").status_code == 204

    assert client.get(f"/chats/{A}").status_code == 404
    assert client.get(f"/shares/public/{token}").status_code == 404 and client.get(f"/shares/public/{other}").status_code == 200
    assert {c for c, _ in db_gateway.records if c in ("chats", "chat_messages")} == {"chats", "chat_messages"}
    assert not any(key.endswith(A) for _c, key in db_gateway.records)
    assert client.delete(f"/chats/{A}").status_code == 404


def test_a_failed_share_revoke_deletes_nothing(client: TestClient, monkeypatch) -> None:
    put(client)

    async def broken(*args, **kwargs):
        raise RuntimeError("shares down")

    monkeypatch.setattr(client.app.state.shares, "revoke_chats", broken)

    with pytest.raises(RuntimeError):
        client.delete(f"/chats/{A}")
    assert client.get(f"/chats/{A}").status_code == 200


def test_delete_all_removes_every_chat_and_link_of_the_account_only(client: TestClient) -> None:
    login(client, "alice")
    put(client), put(client, B)
    link = client.post("/shares", json={"chat_id": A, "title": "t", "messages": MESSAGES}).json()["token"]
    login(client, "bob")
    put(client)
    login(client, "alice")

    assert client.delete("/chats").status_code == 204

    assert client.get("/chats").json() == [] and client.get(f"/shares/public/{link}").status_code == 404
    login(client, "bob")
    assert len(client.get("/chats").json()) == 1


def test_purging_an_account_removes_chats_transcripts_and_folders(client: TestClient, db_gateway: FakeDbGateway) -> None:
    login(client, "alice")
    put(client), folder(client)
    login(client, "bob")
    put(client), folder(client)

    assert client.delete(f"/chats/accounts/{uid_of('alice')}").status_code == 204

    assert {doc["owner"] for doc in db_gateway.records.values()} == {uid_of("bob")}
    assert client.delete("/chats/accounts/has%20space").status_code == 422


# --- search ----------------------------------------------------------------------------------


def test_search_finds_titles_and_messages_with_a_snippet(client: TestClient, monkeypatch) -> None:
    from datetime import datetime, timedelta
    ticks = iter(range(100))
    monkeypatch.setattr(chat_store, "utcnow", lambda: datetime(2026, 1, 1) + timedelta(seconds=next(ticks)))
    put(client, A, "Holiday plans", [{"role": "user", "content": "where should we go?"}, {"role": "assistant", "content": "Try Lisbon in spring. Lisbon is lovely."}])
    put(client, B, "Taxes", [{"role": "user", "content": "[[ATTACHMENT a.txt]]\nlisbon hidden in a file\n[[/ATTACHMENT]]\nhow much?"}])
    put(client, C, "LISBON trip", [{"role": "user", "content": "x"}])

    hits = client.get("/chats/search", params={"q": "lisbon"}).json()

    assert [h["id"] for h in hits] == [C, A]  # newest first; the attachment text does not count
    by_id = {h["id"]: h for h in hits}
    assert by_id[C]["title_match"] == {"start": 0, "length": 6} and by_id[C]["snippet"] is None
    assert by_id[A]["title_match"] is None and by_id[A]["message_index"] == 1 and by_id[A]["message_matches"] == 1
    assert by_id[A]["snippet"] == {"text": "Try Lisbon in spring. Lisbon is lovely.", "start": 4, "length": 6}
    assert set(by_id[A]) == {"id", "folder_id", "title", "updated_at", "title_match", "snippet", "message_index", "message_matches"}


def test_search_is_literal_and_private(client: TestClient) -> None:
    login(client, "alice")
    put(client, A, "a.b*c", [{"role": "user", "content": "x"}])
    put(client, B, "axbbc", [{"role": "user", "content": "x"}])
    login(client, "bob")
    put(client, C, "a.b*c bob", [{"role": "user", "content": "x"}])
    login(client, "alice")

    assert [h["id"] for h in client.get("/chats/search", params={"q": "a.b*c"}).json()] == [A]
    assert client.get("/chats/search", params={"q": "x"}).status_code == 422  # too short
    assert client.get("/chats/search", params={"q": "x" * 101}).status_code == 422


def test_search_returns_at_most_50_hits(client: TestClient) -> None:
    for i in range(52):
        put(client, f"chat-9999-{i:04d}", "many", [{"role": "user", "content": "many"}])

    assert len(client.get("/chats/search", params={"q": "many"}).json()) == 50


def test_search_scans_every_transcript_not_just_the_first_page(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(chat_store, "_SCAN_PAGE", 2)
    for i in range(5):
        put(client, f"chat-1111-000{i}", f"chat {i}", [{"role": "user", "content": "needle" if i == 4 else "hay"}])

    assert [h["id"] for h in client.get("/chats/search", params={"q": "needle"}).json()] == ["chat-1111-0004"]


# --- folders ---------------------------------------------------------------------------------


def test_folders_are_listed_in_order_with_their_chat_counts(client: TestClient) -> None:
    first, second = folder(client, "Work"), folder(client, "Home")

    assert (first["position"], second["position"]) == (0, 1)
    assert [(f["name"], f["chat_count"]) for f in client.get("/chat-folders").json()] == [("Work", 0), ("Home", 0)]


def test_folder_names_are_cleaned_unique_ignoring_case_and_limited(client: TestClient, monkeypatch) -> None:
    assert folder(client, "  My   folder ")["name"] == "My folder"
    assert client.post("/chat-folders", json={"name": "MY FOLDER"}).status_code == 409
    for body in ({"name": ""}, {"name": "   "}, {"name": "x" * 61}, {}):
        assert client.post("/chat-folders", json=body).status_code == 422

    monkeypatch.setattr(chat_store, "MAX_FOLDERS_PER_ACCOUNT", 2)
    folder(client, "Two")
    refused = client.post("/chat-folders", json={"name": "Three"})
    assert refused.status_code == 409 and "At most 2 folders" in refused.json()["detail"]


def test_folders_are_private_per_account(client: TestClient) -> None:
    login(client, "alice")
    mine = folder(client)
    login(client, "bob")

    assert client.get("/chat-folders").json() == []
    assert folder(client)["name"] == "Work"  # the same name is free in another account
    assert client.patch(f"/chat-folders/{mine['id']}", json={"name": "x"}).status_code == 404
    assert remove_folder(client, mine["id"]).status_code == 404


def test_rename_reorder_and_move(client: TestClient) -> None:
    a, b, c = folder(client, "A"), folder(client, "B"), folder(client, "C")

    assert client.patch(f"/chat-folders/{a['id']}", json={"name": "Alpha"}).json()["name"] == "Alpha"
    assert client.patch(f"/chat-folders/{a['id']}", json={"name": "b"}).status_code == 409
    assert client.patch(f"/chat-folders/{a['id']}", json={"name": "Alpha"}).status_code == 200  # its own name is free
    assert client.patch(f"/chat-folders/{c['id']}", json={"direction": "up"}).json()["position"] == 1
    assert [f["name"] for f in client.get("/chat-folders").json()] == ["Alpha", "C", "B"]
    client.patch(f"/chat-folders/{c['id']}", json={"direction": "up"})
    assert client.patch(f"/chat-folders/{c['id']}", json={"direction": "up"}).json()["position"] == 0  # already first
    assert client.patch(f"/chat-folders/{b['id']}", json={"position": 50}).json()["position"] == 50
    assert [f["name"] for f in client.get("/chat-folders").json()] == ["C", "Alpha", "B"]
    assert client.patch("/chat-folders/999", json={"name": "x"}).status_code == 404


@pytest.mark.parametrize("body", [{}, {"direction": "left"}, {"direction": "up", "name": "x"}, {"position": -1}, {"name": ""}])
def test_bad_folder_updates_are_refused(client: TestClient, body: dict) -> None:
    work = folder(client)
    assert client.patch(f"/chat-folders/{work['id']}", json=body).status_code == 422


def test_deleting_a_folder_deletes_its_chats_and_their_links(client: TestClient, platform) -> None:
    work = folder(client)
    put(client), put(client, B, "outside")
    client.patch(f"/chats/{A}", json={"folder_id": work["id"]})
    token = client.post("/shares", json={"chat_id": A, "title": "t", "messages": MESSAGES}).json()["token"]

    assert remove_folder(client, work["id"]).status_code == 204

    assert client.get(f"/chats/{A}").status_code == 404 and client.get(f"/chats/{B}").status_code == 200
    assert client.get(f"/shares/public/{token}").status_code == 404 and client.get("/chat-folders").json() == []
    assert ("u-1", "chat_folder.delete", 'Deleted folder "Work" and its 1 chat(s)') in platform.actions


def test_a_folder_with_a_running_chat_is_not_deleted(client: TestClient) -> None:
    work = folder(client)
    put(client)
    client.patch(f"/chats/{A}", json={"folder_id": work["id"]})

    busy = remove_folder(client, work["id"], running=[A])

    assert busy.status_code == 409 and "still writing" in busy.json()["detail"]
    assert client.get(f"/chats/{A}").status_code == 200 and len(client.get("/chat-folders").json()) == 1
    assert remove_folder(client, work["id"], running=[B]).status_code == 204  # another chat's answer does not matter


def test_folder_changes_are_logged_without_chat_text(client: TestClient, platform) -> None:
    work = folder(client)
    client.patch(f"/chat-folders/{work['id']}", json={"name": "Jobs"})
    client.patch(f"/chat-folders/{work['id']}", json={"direction": "down"})

    assert [(a, m) for _u, a, m in platform.actions] == [
        ("chat_folder.create", 'Created folder "Work"'), ("chat_folder.rename", 'Renamed a folder to "Jobs"'),
        ("chat_folder.move", 'Moved folder "Jobs" down')]
