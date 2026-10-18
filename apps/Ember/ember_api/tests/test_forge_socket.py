from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import FakeEmailSender
from tests.test_admin import login
from tests.test_forge_routes import make_forger, new_group, new_worker
from tests.test_registration import as_admin


def eventually(check, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.02)


def wait_for(client: TestClient, group_id: int, predicate, timeout: float = 5.0) -> list[dict]:
    """Polls the stored messages until predicate(messages) is true."""
    deadline = time.monotonic() + timeout
    while True:
        messages = client.get(f"/api/forge/groups/{group_id}/messages").json()
        if predicate(messages):
            return messages
        assert time.monotonic() < deadline, f"not reached: {messages}"
        time.sleep(0.02)


def connect(client: TestClient, token: str, plan: str | None = "Max"):
    """An open worker socket that has said hello and received `ready`."""
    ws = client.websocket_connect("/api/forge/worker", headers={"Authorization": f"Bearer {token}"})
    session = ws.__enter__()
    session.send_json({"type": "hello", "plan": plan, "version": "test"})
    ready = session.receive_json()
    assert ready["type"] == "ready"
    return ws, session, ready


def invite(client: TestClient, group_id: int, worker_id: int, folder: str = "C:/work") -> dict:
    response = client.post(f"/api/forge/groups/{group_id}/workers", json={"worker_id": worker_id, "folder": folder})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_bad_token_cannot_connect(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Bearer ft_nope"}, {"Authorization": "Basic abc"}):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/forge/worker", headers=headers):
                pass


def test_hello_must_come_first(client: TestClient) -> None:
    as_admin(client)
    token = new_worker(client)["token"]

    with client.websocket_connect("/api/forge/worker", headers={"Authorization": f"Bearer {token}"}) as ws:
        ws.send_json({"type": "heartbeat"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_hello_reports_the_plan_and_marks_the_worker_online(client: TestClient) -> None:
    as_admin(client)
    assert client.put("/api/forge/plans/claude", json={"plans": ["max"]}).status_code == 200
    worker = new_worker(client)

    ws, session, ready = connect(client, worker["token"], plan="Max")
    try:
        assert ready["worker_id"] == worker["id"]
        listed = client.get("/api/forge/workers").json()[0]
        assert (listed["online"], listed["reported_plan"], listed["eligible"], listed["problem"]) == (True, "Max", True, None)
        session.send_json({"type": "heartbeat"})
        time.sleep(0.3)  # let the server finish writing it before the socket closes
    finally:
        ws.__exit__(None, None, None)
    eventually(lambda: client.get("/api/forge/workers").json()[0]["online"] is False)


def test_a_turn_from_message_to_stored_reply(client: TestClient) -> None:
    as_admin(client)
    client.put("/api/forge/plans/claude", json={"plans": ["max"]})
    worker = new_worker(client)
    group = new_group(client)
    ws, session, _ready = connect(client, worker["token"])
    try:
        members = invite(client, group["id"], worker["id"])["members"]
        assert [(m["label"], m["online"], m["folder"]) for m in members] == [("claude", True, "C:/work")]

        sent = client.post(f"/api/forge/groups/{group['id']}/messages", json={"text": "@claude fix the bug"})
        assert sent.status_code == 201 and sent.json()["seq"] == 1

        turn = session.receive_json()
        assert (turn["type"], turn["prompt"], turn["folder"], turn["mode"]) == ("turn", "@claude fix the bug", "C:/work", "ask")
        assert client.get(f"/api/forge/groups/{group['id']}").json()["running"] is True
        assert client.post(f"/api/forge/groups/{group['id']}/messages", json={"text": "@claude again"}).status_code == 409

        session.send_json({"type": "delta", "turn_id": turn["turn_id"], "text": "Looking"})
        session.send_json({"type": "tool", "turn_id": turn["turn_id"], "name": "Edit", "summary": "app.py"})
        session.send_json({"type": "turn_done", "turn_id": turn["turn_id"], "text": "Fixed it."})

        messages = wait_for(client, group["id"], lambda m: m and m[-1]["kind"] == "text" and m[-1]["sender"] != "user")
        assert [(m["kind"], m["sender"]) for m in messages] == [
            ("text", "user"), ("tool", str(worker["id"])), ("text", str(worker["id"])),
        ]
        assert messages[-1]["body"]["text"] == "Fixed it." and messages[-1]["body"]["label"] == "claude"
        wait_for(client, group["id"], lambda _m: client.get(f"/api/forge/groups/{group['id']}").json()["running"] is False)
        assert client.get(f"/api/forge/groups/{group['id']}/messages", params={"after": 2}).json()[0]["seq"] == 3
    finally:
        ws.__exit__(None, None, None)


def test_permission_requests_are_relayed_to_the_page_and_back(client: TestClient) -> None:
    as_admin(client)
    client.put("/api/forge/plans/claude", json={"plans": ["max"]})
    worker, group = new_worker(client), new_group(client)
    ws, session, _ready = connect(client, worker["token"])
    try:
        invite(client, group["id"], worker["id"])
        client.post(f"/api/forge/groups/{group['id']}/messages", json={"text": "@claude go"})
        turn = session.receive_json()
        session.send_json(
            {"type": "permission_request", "turn_id": turn["turn_id"], "request_id": "r1", "tool": "Bash", "summary": "npm test"}
        )
        wait_for(client, group["id"], lambda m: any(x["kind"] == "permission_request" for x in m))

        answered = client.post(f"/api/forge/groups/{group['id']}/permissions/r1", json={"allow": True})
        assert answered.status_code == 200 and answered.json() == {"answered": True}
        assert session.receive_json() == {"type": "permission_reply", "request_id": "r1", "allow": True}
        assert client.post(f"/api/forge/groups/{group['id']}/permissions/r1", json={"allow": True}).status_code == 404

        session.send_json({"type": "turn_done", "turn_id": turn["turn_id"], "text": "ok"})
        wait_for(client, group["id"], lambda m: m[-1]["kind"] == "text" and m[-1]["sender"] != "user")
    finally:
        ws.__exit__(None, None, None)


def test_stop_reaches_the_worker(client: TestClient) -> None:
    as_admin(client)
    client.put("/api/forge/plans/claude", json={"plans": ["max"]})
    worker, group = new_worker(client), new_group(client)
    ws, session, _ready = connect(client, worker["token"])
    try:
        invite(client, group["id"], worker["id"])
        assert client.post(f"/api/forge/groups/{group['id']}/cancel", json={}).json() == {"stopping": False}
        client.post(f"/api/forge/groups/{group['id']}/messages", json={"text": "@claude go"})
        turn = session.receive_json()

        assert client.post(f"/api/forge/groups/{group['id']}/cancel", json={}).json() == {"stopping": True}
        assert session.receive_json() == {"type": "cancel", "turn_id": turn["turn_id"]}
        session.send_json({"type": "turn_error", "turn_id": turn["turn_id"], "message": "cancelled"})
        messages = wait_for(client, group["id"], lambda m: m[-1]["kind"] == "system")
        assert messages[-1]["body"]["text"] == "@claude stopped."
    finally:
        ws.__exit__(None, None, None)


def test_removing_a_worker_closes_its_socket(client: TestClient) -> None:
    as_admin(client)
    worker = new_worker(client)
    ws, session, _ready = connect(client, worker["token"])
    try:
        assert client.delete(f"/api/forge/workers/{worker['id']}").status_code == 204
        with pytest.raises(WebSocketDisconnect) as closed:
            session.receive_json()
        assert closed.value.code == 4401
    finally:
        ws.__exit__(None, None, None)
    with pytest.raises(WebSocketDisconnect):  # the token no longer works
        with client.websocket_connect("/api/forge/worker", headers={"Authorization": f"Bearer {worker['token']}"}):
            pass


def test_a_second_connection_replaces_the_first(client: TestClient) -> None:
    as_admin(client)
    worker = new_worker(client)
    first_ws, first, _ = connect(client, worker["token"])
    second_ws, second, _ = connect(client, worker["token"])
    try:
        with pytest.raises(WebSocketDisconnect):
            first.receive_json()
        assert client.get("/api/forge/workers").json()[0]["online"] is True
    finally:
        second_ws.__exit__(None, None, None)
        first_ws.__exit__(None, None, None)


def test_members_can_be_removed_and_a_deleted_worker_leaves_its_groups(client: TestClient) -> None:
    as_admin(client)
    client.put("/api/forge/plans/claude", json={"plans": ["max"]})
    worker, group = new_worker(client), new_group(client)
    ws, _session, _ready = connect(client, worker["token"])
    try:
        invite(client, group["id"], worker["id"])
        assert client.post(
            f"/api/forge/groups/{group['id']}/workers", json={"worker_id": worker["id"], "folder": "C:/x"}
        ).status_code == 409  # already in

        removed = client.delete(f"/api/forge/groups/{group['id']}/workers/{worker['id']}")
        assert removed.status_code == 200 and removed.json()["members"] == []

        invite(client, group["id"], worker["id"], folder="D:/other")
        assert client.get(f"/api/forge/groups/{group['id']}").json()["members"][0]["folder"] == "D:/other"
        assert client.delete(f"/api/forge/workers/{worker['id']}").status_code == 204
        assert client.get(f"/api/forge/groups/{group['id']}").json()["members"] == []
    finally:
        ws.__exit__(None, None, None)


def test_chat_routes_are_private_to_the_owner(client: TestClient, email: FakeEmailSender) -> None:
    make_forger(client, email, "alice")
    as_admin(client)
    group = new_group(client)
    client.post("/api/auth/logout", json={})
    login(client, "alice")
    gid = group["id"]

    assert client.get(f"/api/forge/groups/{gid}/messages").status_code == 404
    assert client.post(f"/api/forge/groups/{gid}/messages", json={"text": "hi"}).status_code == 404
    assert client.get(f"/api/forge/groups/{gid}/events").status_code == 404
    assert client.post(f"/api/forge/groups/{gid}/permissions/r1", json={"allow": True}).status_code == 404
    assert client.post(f"/api/forge/groups/{gid}/cancel", json={}).status_code == 404


def test_message_text_is_validated(client: TestClient) -> None:
    as_admin(client)
    gid = new_group(client)["id"]

    assert client.post(f"/api/forge/groups/{gid}/messages", json={"text": "   "}).status_code == 422
    assert client.post(f"/api/forge/groups/{gid}/messages", json={"text": "x" * 8001}).status_code == 422
