"""/api/chats/{id}/turns and friends: Portcullis checks login and permission, adds the `trusted` block and
passes the rest to Stronghold (which runs the turn; its own tests cover that). FakeTurns records what it got."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeEmailSender
from tests.test_admin import login, make_member
from tests.test_registration import as_admin
from tests.turn_helpers import events, new_id, start


def last_start(upstream) -> dict:
    return upstream.turns.bodies("POST", "")[-1]


def force(client: TestClient, on: bool = True) -> None:
    assert client.put("/api/armory-tool-approval", json={"value": on}).status_code == 200


def action_log(client: TestClient) -> str:
    return client.get("/api/logs/action", params={"actor": client.get("/api/auth/me").json()["id"]}).text


# --- starting --------------------------------------------------------------------------


def test_the_start_is_answered_in_the_browsers_shape(client: TestClient, upstream) -> None:
    as_admin(client)
    chat_id = new_id()
    response = start(client, chat_id, "What is up?", title="My chat")
    assert response.status_code == 202
    body = response.json()
    assert body["sequence"] == 3
    assert (body["chat"]["id"], body["chat"]["title"], body["chat"]["running"]) == (chat_id, "My chat", True)
    sent = last_start(upstream)
    assert sent["question"] == "What is up?" and "agent_id" not in sent


def test_the_trusted_block_is_added_for_an_admin(client: TestClient, upstream) -> None:
    as_admin(client)
    start(client, new_id())
    assert last_start(upstream)["trusted"] == {"forced_approval": False, "tools_execute": True}


def test_a_trusted_key_from_the_browser_never_reaches_stronghold(client: TestClient, upstream) -> None:
    as_admin(client)
    start(client, new_id(), trusted={"forced_approval": False, "tools_execute": True, "extension_ids": ["evil"]},
          enabled_extensions=["../etc"])
    sent = last_start(upstream)
    assert "extension_ids" not in sent["trusted"] and "enabled_extensions" not in sent


def test_the_administrators_forced_approval_is_sent(client: TestClient, upstream) -> None:
    as_admin(client)
    force(client)
    start(client, new_id(), ask_before_tools=False)
    assert last_start(upstream)["trusted"]["forced_approval"] is True


def test_extensions_are_empty_when_mcp_server_cannot_list_them(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(503, json={"error": "down"})
    assert start(client, new_id()).status_code == 202
    assert "extension_ids" not in last_start(upstream)["trusted"]


def test_a_refusal_from_stronghold_comes_back_unchanged(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.turns.start_status = 409
    assert start(client, new_id()).status_code == 409


def test_a_stronghold_that_is_down_is_a_bad_gateway(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.unreachable = True
    assert start(client, new_id()).status_code == 502


def test_the_request_is_validated_before_it_goes_on(client: TestClient, upstream) -> None:
    as_admin(client)
    assert start(client, new_id(), allowed_tools=["has space"]).status_code == 422
    assert start(client, new_id(), allowed_tools=[f"t{i}" for i in range(201)]).status_code == 422
    assert start(client, "x").status_code == 422  # not a chat id
    assert upstream.turns.bodies("POST", "") == []


def test_a_turn_needs_login_and_chat_use(client: TestClient, email: FakeEmailSender, upstream) -> None:
    assert start(client, new_id()).status_code == 401
    make_member(client, email, verify=False)
    login(client, "alice")
    assert start(client, new_id()).status_code == 403
    assert upstream.turns.calls == []


# --- watching ---------------------------------------------------------------------------


def test_events_are_relayed_as_a_stream(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.turns.events_body = (
        b"id: 1\ndata: {\"type\": \"token\", \"text\": \"Hi\", \"sequence\": 1}\n\n: ping\n\n"
        b"id: 2\ndata: {\"type\": \"final\", \"sequence\": 2}\n\n"
    )
    with client.stream("GET", f"/api/chats/{new_id()}/events") as response:
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        text = b"".join(response.iter_bytes())
    assert text == upstream.turns.events_body


def test_the_replay_position_reaches_stronghold(client: TestClient, upstream) -> None:
    as_admin(client)
    chat_id = new_id()
    events(client, chat_id, after=4)
    with client.stream("GET", f"/api/chats/{chat_id}/events", headers={"Last-Event-ID": "9"}) as response:
        response.read()
    afters = [r.url.params["after"] for r in upstream.requests if r.url.path.endswith("/events")]
    assert afters == ["4", "9"]


def test_no_turn_to_watch_is_404(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.turns.events_status = 404
    assert client.get(f"/api/chats/{new_id()}/events").status_code == 404


def test_events_need_login(client: TestClient) -> None:
    assert client.get(f"/api/chats/{new_id()}/events").status_code == 401


# --- approvals, questions, cancel -------------------------------------------------------------


def approve(client: TestClient, chat_id: str, **extra):
    return client.post(f"/api/chats/{chat_id}/approvals", json={"step_id": "step0", "decision": "allow", **extra})


def test_an_approval_goes_on_with_the_forced_flag_and_is_logged(client: TestClient, upstream) -> None:
    as_admin(client)
    force(client)
    response = approve(client, new_id(), decision="always")
    assert (response.status_code, response.json()) == (200, {"decided": True})
    assert upstream.turns.bodies("POST", "/approvals")[-1] == {
        "step_id": "step0", "decision": "always", "trusted": {"forced_approval": True}}
    log = action_log(client)
    assert "tool.approval" in log and "send_mail" in log


@pytest.mark.parametrize("code", [404, 409, 502])
def test_a_refused_approval_comes_back_unchanged_and_is_not_logged(client: TestClient, upstream, code: int) -> None:
    as_admin(client)
    upstream.turns.approval_status = code
    upstream.turns.approval = {"detail": "no"}
    assert approve(client, new_id()).status_code == code
    assert "tool.approval" not in action_log(client)


@pytest.mark.parametrize("body", [{"step_id": "s", "decision": "yes"}, {"decision": "allow"}, {"step_id": "", "decision": "allow"}])
def test_an_approval_is_validated(client: TestClient, upstream, body: dict) -> None:
    as_admin(client)
    assert client.post(f"/api/chats/{new_id()}/approvals", json=body).status_code == 422
    assert upstream.turns.bodies("POST", "/approvals") == []


def test_a_browser_cannot_set_the_forced_flag_of_an_approval(client: TestClient, upstream) -> None:
    as_admin(client)
    approve(client, new_id(), trusted={"forced_approval": True})  # the switch is off: Portcullis's value wins
    assert upstream.turns.bodies("POST", "/approvals")[-1]["trusted"] == {"forced_approval": False}


def test_a_question_answer_is_passed_on(client: TestClient, upstream) -> None:
    as_admin(client)
    chat_id = new_id()
    response = client.post(f"/api/chats/{chat_id}/questions", json={"step_id": "q1", "answers": [{"selected": ["CSV"]}]})
    assert (response.status_code, response.json()) == (200, {"answered": True})
    assert upstream.turns.bodies("POST", "/questions")[-1]["answers"] == [{"selected": ["CSV"], "other": None}]
    too_many = client.post(f"/api/chats/{chat_id}/questions", json={"step_id": "q1", "answers": [{"selected": list("abcde")}]})
    assert too_many.status_code == 422


def test_an_elicitation_answer_is_passed_on(client: TestClient, upstream) -> None:
    chat_id = new_id()
    body = {"id": "e1", "action": "accept", "content": {"count": 2, "yes": False, "many": ["a"]}}
    assert client.post(f"/api/chats/{chat_id}/elicitations", json=body).status_code == 401
    as_admin(client)
    response = client.post(f"/api/chats/{chat_id}/elicitations", json=body)
    assert (response.status_code, response.json()) == (200, {"answered": True})
    assert upstream.turns.bodies("POST", "/elicitations")[-1] == body
    assert client.post(f"/api/chats/{chat_id}/elicitations", json={"id": "e1", "action": "maybe"}).status_code == 422


def test_can_elicit_reaches_stronghold(client: TestClient, upstream) -> None:
    as_admin(client)
    start(client, new_id(), can_elicit=True)
    assert last_start(upstream)["can_elicit"] is True


def test_cancel_is_passed_on(client: TestClient, upstream) -> None:
    as_admin(client)
    assert client.post(f"/api/chats/{new_id()}/cancel", json={}).json() == {"cancelled": True}


def test_answering_needs_login_and_chat_use(client: TestClient, email: FakeEmailSender, upstream) -> None:
    assert approve(client, new_id()).status_code == 401
    make_member(client, email, verify=False)
    login(client, "alice")
    assert approve(client, new_id()).status_code == 403
    assert client.post(f"/api/chats/{new_id()}/cancel", json={}).status_code == 403
    assert upstream.turns.calls == []


# --- running flags, discard, suggestion, summarize --------------------------------------------


def test_running_flags_come_from_stronghold(client: TestClient, upstream) -> None:
    as_admin(client)
    busy, idle = new_id(), new_id()
    for chat_id in (busy, idle):
        assert client.put(f"/api/chats/{chat_id}", json={"title": "t", "messages": []}).status_code == 200
    upstream.turns.running = {busy}
    flags = {c["id"]: c["running"] for c in client.get("/api/chats").json()}
    assert flags == {busy: True, idle: False}
    assert client.get(f"/api/chats/{busy}").json()["running"] is True
    assert client.put(f"/api/chats/{busy}", json={"title": "t", "messages": []}).status_code == 409
    appended = client.post(f"/api/chats/{busy}/messages", json={"title": "t", "messages": [{"role": "user", "content": "x"}]})
    assert appended.status_code == 409
    assert client.put(f"/api/chats/{idle}", json={"title": "t2", "messages": []}).status_code == 200


def test_a_stronghold_that_cannot_say_what_runs_blocks_the_write(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.turns = None  # the handler below answers /turns/running with something unreadable
    upstream.handler = lambda request: httpx.Response(200, json={"unexpected": True})
    assert client.put(f"/api/chats/{new_id()}", json={"title": "t", "messages": []}).status_code == 502


def test_deleting_a_chat_stops_its_turn_and_deleting_all_stops_every_turn(client: TestClient, upstream) -> None:
    as_admin(client)
    chat_id = new_id()
    client.put(f"/api/chats/{chat_id}", json={"title": "t", "messages": []})
    assert client.delete(f"/api/chats/{chat_id}").status_code == 204
    assert ("DELETE", f"/turns/{chat_id}", None) in upstream.turns.calls
    assert client.delete("/api/chats").status_code == 204
    assert ("DELETE", "/turns", None) in upstream.turns.calls


def test_a_folder_delete_tells_stronghold_which_chats_run(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.turns.running = {"aaaaaaaa-1", "bbbbbbbb-2"}
    folder = client.post("/api/chat-folders", json={"name": "Work"}).json()["id"]
    client.delete(f"/api/chat-folders/{folder}")
    sent = [r for r in upstream.requests if r.method == "DELETE" and r.url.path == f"/chat-folders/{folder}"]
    assert b"aaaaaaaa-1" in sent[-1].content and b"bbbbbbbb-2" in sent[-1].content


def test_the_suggestion_is_passed_on(client: TestClient, upstream) -> None:
    as_admin(client)
    assert client.get(f"/api/chats/{new_id()}/suggestion").json() == {"text": "And then?"}


def test_summarize_and_clear_answer_in_the_browsers_shape(client: TestClient, upstream) -> None:
    as_admin(client)
    chat_id = new_id()
    for action in ("summarize", "clear"):
        response = client.post(f"/api/chats/{chat_id}/{action}", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == chat_id and body["running"] is False
        assert body["messages"] == [{"role": "assistant", "content": "SUMMARY"}]
    upstream.turns.refuse = (409, "An answer is still being written for this chat")
    assert client.post(f"/api/chats/{chat_id}/summarize", json={}).status_code == 409


def test_a_folder_with_an_answering_chat_cannot_be_deleted(client: TestClient, upstream) -> None:
    as_admin(client)
    folder = client.post("/api/chat-folders", json={"name": "Work"}).json()["id"]
    chat_id = new_id()
    assert client.put(f"/api/chats/{chat_id}", json={"title": "t", "messages": []}).status_code == 200
    assert client.patch(f"/api/chats/{chat_id}", json={"folder_id": folder}).status_code == 200
    upstream.turns.running = {chat_id}
    response = client.delete(f"/api/chat-folders/{folder}")
    assert response.status_code == 409 and "answer" in response.json()["detail"]
    assert client.get(f"/api/chats/{chat_id}").status_code == 200  # nothing was deleted
    upstream.turns.running = set()
    assert client.delete(f"/api/chat-folders/{folder}").status_code == 204


def test_a_chat_can_be_branched_while_it_is_answering(client: TestClient, upstream) -> None:
    as_admin(client)
    source = new_id()
    messages = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}, {"role": "user", "content": "q2"}]
    assert client.put(f"/api/chats/{source}", json={"title": "t", "messages": messages}).status_code == 200
    upstream.turns.running = {source}
    response = client.post(f"/api/chats/{source}/branch", json={"upto": 1})
    assert response.status_code == 201
    assert [m["content"] for m in response.json()["messages"]] == ["q1", "a1"]
    assert client.get(f"/api/chats/{source}").json()["running"] is True and response.json()["running"] is False
