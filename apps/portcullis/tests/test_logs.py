from __future__ import annotations

import uuid

import httpx

import pytest
from fastapi.testclient import TestClient

from src.services.chat_service import ChatService
from tests.conftest import AGENTS, FakeEmailSender
from tests.test_admin import login, make_member, role_by_name
from tests.test_registration import as_admin
from tests.turn_helpers import events


def my_id(client: TestClient) -> int:
    return client.get("/api/auth/me").json()["id"]


def messages(client: TestClient, kind: str, actor: str | int) -> list[str]:
    response = client.get(f"/api/logs/{kind}", params={"actor": str(actor)})
    assert response.status_code == 200, response.text
    return [e["message"] for e in response.json()]


def test_account_and_admin_actions_are_logged(client: TestClient, email: FakeEmailSender) -> None:
    alice = make_member(client, email)
    as_admin(client)
    client.post("/api/admin/roles", json={"name": "Ops"})
    root = my_id(client)

    assert messages(client, "action", alice) == [
        "Logged out",
        "Verified email alice@example.com",
        "Registered with an invite code",
    ]
    admin_lines = messages(client, "action", root)
    assert admin_lines[0] == "Created role 'Ops'"
    assert admin_lines[1].startswith("Logged in from ")
    assert any(line.startswith("Created invite #") for line in admin_lines)
    # Nothing the server did on its own yet.
    assert messages(client, "action", "server") == []


def test_logs_page_needs_a_logs_permission_per_kind(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email)
    login(client, "alice")
    assert client.get("/api/logs").status_code == 403
    assert client.get("/api/logs/action").status_code == 403

    client.post("/api/auth/logout", json={})
    as_admin(client)
    everything = client.get("/api/logs").json()
    assert everything["kinds"] == ["action", "error", "chat_trace"]
    assert [a["username"] for a in everything["accounts"]] == ["alice", "root"]
    member_role = role_by_name(client, "Member")["id"]
    assert client.put(f"/api/admin/roles/{member_role}/permissions/logs.view").status_code == 200
    client.post("/api/auth/logout", json={})

    login(client, "alice")
    assert client.get("/api/logs").json()["kinds"] == ["action"]
    assert client.get("/api/logs/action", params={"actor": "server"}).status_code == 200
    assert client.get("/api/logs/error").status_code == 403
    assert client.get("/api/logs/chat_trace").status_code == 403
    assert client.get("/api/logs/action", params={"actor": "everyone"}).status_code == 422
    assert client.get("/api/logs/secrets").status_code == 422


def test_chat_trace_prompts_are_hidden_without_the_permission(client: TestClient, email: FakeEmailSender) -> None:
    """Stronghold writes the trace through /internal/logs; only the readers of prompts see them."""
    import json

    as_admin(client)
    root = my_id(client)
    details = json.dumps({"agents": [{"agent_id": "claude-agent"}]})
    prompts = json.dumps([{"messages": [{"role": "user", "content": "add 2 and 3"}], "truncated": False}])
    client.portal.call(client.app.state.logs.chat_trace, root, "add 2 and 3 -> claude-agent", details, prompts)
    trace = client.get("/api/logs/chat_trace", params={"actor": root}).json()[0]
    assert json.loads(trace["prompts"])[0]["messages"][-1]["content"] == "add 2 and 3"  # an admin holds every permission

    member_role = role_by_name(client, "Member")["id"]
    assert client.put(f"/api/admin/roles/{member_role}/permissions/logs.chat.view").status_code == 200
    make_member(client, email)
    client.post("/api/auth/logout", json={})
    login(client, "alice")
    seen = client.get("/api/logs/chat_trace", params={"actor": root}).json()[0]
    assert seen["prompts"] is None
    assert json.loads(seen["details"])["agents"][0]["agent_id"] == "claude-agent"


def test_unexpected_errors_are_logged_under_the_account(client: TestClient, monkeypatch) -> None:
    as_admin(client)
    root = my_id(client)

    async def broken(self):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(ChatService, "list", broken)
    with pytest.raises(RuntimeError):  # TestClient re-raises what the app didn't handle
        client.get("/api/chats")

    entries = client.get("/api/logs/error", params={"actor": root}).json()
    assert entries[0]["message"] == "RuntimeError: disk on fire"
    assert entries[0]["source"] == "http GET /api/chats"
    assert "Traceback" in entries[0]["details"]
