from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.services.chat_service import ChatService
from tests.conftest import AGENTS, FakeAgent, FakeEmailSender
from tests.test_admin import login, make_member, role_by_name
from tests.test_registration import as_admin
from tests.test_turns import events


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


def test_chat_turns_are_traced_and_agent_failures_logged(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    root = my_id(client)
    chat_id = str(uuid.uuid4())
    body = {"question": "What is up?", "agent_id": AGENTS[0]["id"], "enabled_extensions": ["notes"]}
    assert client.post(f"/api/chats/{chat_id}/turns", json=body).status_code == 202
    events(client, chat_id)

    traces = client.get("/api/logs/chat_trace", params={"actor": root}).json()
    assert len(traces) == 1
    assert traces[0]["message"].startswith(f"What is up? → {AGENTS[0]['id']}/claude-test, ")
    assert '"enabled_extensions": [\n    "notes"\n  ]' in traces[0]["details"]
    assert '"response": "Hello!"' in traces[0]["details"]

    agent.fail = "provider rate limited"
    other = str(uuid.uuid4())
    client.post(f"/api/chats/{other}/turns", json={**body, "enabled_extensions": []})
    events(client, other)
    assert messages(client, "error", root) == [f"{AGENTS[0]['id']}: provider rate limited"]


TRACE_ROWS = [
    {
        "agent_id": "claude-agent", "agent_label": "Ember", "provider_id": "anthropic", "gateway": "openrouter",
        "model": "claude-test", "input_tokens": 70, "output_tokens": 30, "total_tokens": 100,
        "started_at": "2026-10-04T09:12:03.512Z", "finished_at": "2026-10-04T09:12:07.044Z", "delegated_by": None,
        "model_tier": "heavy", "reasoning_effort": "low",
        "prompt": [{"role": "user", "content": "earlier"}, {"role": "user", "content": "add 2 and 3"}],
    },
    {
        "agent_id": "calc", "agent_label": "Calculator", "provider_id": "openai", "gateway": None,
        "model": "gpt-x", "input_tokens": 20, "output_tokens": 5, "total_tokens": 25,
        "started_at": "2026-10-04T09:12:04.000Z", "finished_at": "2026-10-04T09:12:05.250Z", "delegated_by": "claude-agent",
        "prompt": [{"role": "user", "content": "2 + 3"}],
    },
]


def test_chat_trace_lists_each_agent_and_hides_prompts_without_the_permission(
    client: TestClient, agent: FakeAgent, email: FakeEmailSender
) -> None:
    agent.result_extra = {"agent_usage": TRACE_ROWS}
    agent.tool_calls = ["notes"]
    as_admin(client)
    root = my_id(client)
    chat_id = str(uuid.uuid4())
    body = {"question": "add 2 and 3", "agent_id": AGENTS[0]["id"], "enabled_extensions": []}
    assert client.post(f"/api/chats/{chat_id}/turns", json=body).status_code == 202
    events(client, chat_id)

    trace = client.get("/api/logs/chat_trace", params={"actor": root}).json()[0]
    # Admin holds every permission, so the prompts come back too.
    import json

    details = json.loads(trace["details"])
    assert [a["agent_id"] for a in details["agents"]] == ["claude-agent", "calc"]
    first, second = details["agents"]
    assert (first["model_tier"], first["reasoning_effort"], first.get("delegated_by")) == ("heavy", "low", None)
    assert second["delegated_by"] == "claude-agent"
    assert first["tools"] == ["notes"] and second["tools"] == []
    assert "prompt" not in first and "earlier" not in trace["details"]
    prompts = json.loads(trace["prompts"])
    assert [p["messages"][-1]["content"] for p in prompts] == ["add 2 and 3", "2 + 3"]
    assert prompts[0]["truncated"] is False

    # A role with only logs.chat.view reads the entry but never the prompts.
    member_role = role_by_name(client, "Member")["id"]
    assert client.put(f"/api/admin/roles/{member_role}/permissions/logs.chat.view").status_code == 200
    make_member(client, email)
    client.post("/api/auth/logout", json={})
    login(client, "alice")
    seen = client.get("/api/logs/chat_trace", params={"actor": root}).json()[0]
    assert seen["prompts"] is None and "earlier" not in str(seen)
    assert json.loads(seen["details"])["agents"][0]["agent_id"] == "claude-agent"


def test_chat_trace_prompts_are_clipped_to_a_budget_keeping_the_newest(client: TestClient, agent: FakeAgent) -> None:
    import json

    big = [{"role": "user", "content": "old " * 5000}, {"role": "user", "content": "the question"}]
    agent.result_extra = {"agent_usage": [{**TRACE_ROWS[0], "prompt": big}]}
    as_admin(client)
    root = my_id(client)
    chat_id = str(uuid.uuid4())
    client.post(f"/api/chats/{chat_id}/turns", json={"question": "x", "agent_id": AGENTS[0]["id"], "enabled_extensions": []})
    events(client, chat_id)

    prompt = json.loads(client.get("/api/logs/chat_trace", params={"actor": root}).json()[0]["prompts"])[0]
    assert prompt["truncated"] is True
    assert prompt["messages"][-1]["content"] == "the question"
    assert sum(len(m["content"]) for m in prompt["messages"]) <= 12_000


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
