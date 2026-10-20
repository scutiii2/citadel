"""Per-chat auto-save preference, capability gating and the agent's save instruction."""
import httpx
import pytest

from tests.test_admin import login, make_member
from tests.test_registration import as_admin
from tests.test_turns import events, new_id, start


@pytest.fixture
def obsidian(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(200, json=[{
        "name": "obsidian", "enabled": True, "tools": ["tool_obsidian_write"],
    }])
    assert client.put("/api/account-capabilities/capability/obsidian", json={"enabled": True}).status_code == 200
    return client


def test_default_off_sends_original_question_and_does_not_request_save(obsidian, agent):
    chat_id = new_id()
    assert start(obsidian, chat_id, "Explain cats").status_code == 202
    events(obsidian, chat_id)
    assert agent.asks[-1]["question"] == "Explain cats"
    assert obsidian.get(f"/api/chats/{chat_id}").json()["save_to_second_brain"] is False


def test_flag_persists_per_chat_and_requests_safe_summary_write(obsidian, agent):
    chat_id = new_id()
    response = start(obsidian, chat_id, "Explain cats", save_to_second_brain=True, ask_before_tools=True)
    assert response.status_code == 202
    events(obsidian, chat_id)
    asked = agent.asks[-1]
    assert "Conversations/" in asked["question"]
    assert "tool_obsidian_write" in asked["question"]
    assert "overwrite=false" in asked["question"]
    assert chat_id in asked["question"] and "tags:" in asked["question"] and "date:" in asked["question"]
    assert asked["approval_mode"] == "ask"
    saved = obsidian.get(f"/api/chats/{chat_id}").json()
    assert saved["save_to_second_brain"] is True
    assert saved["messages"][0]["content"] == "Explain cats"
    assert start(obsidian, chat_id, "And food?").status_code == 202
    events(obsidian, chat_id)
    assert "tool_obsidian_write" in agent.asks[-1]["question"]
    another = new_id()
    assert start(obsidian, another, "no save").status_code == 202
    events(obsidian, another)
    assert agent.asks[-1]["question"] == "no save"
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": False}).status_code == 200
    assert start(obsidian, chat_id, "now off").status_code == 202
    events(obsidian, chat_id)
    assert agent.asks[-1]["question"] == "now off"


def test_unsubscribed_and_offline_capability_cannot_enable(obsidian, upstream):
    assert obsidian.get("/api/chats/second-brain").json() == {"available": True}
    upstream.handler = lambda request: httpx.Response(200, json=[{"name": "obsidian", "enabled": False, "tools": []}])
    assert obsidian.get("/api/chats/second-brain").json() == {"available": False}
    chat_id = new_id()
    assert start(obsidian, chat_id, save_to_second_brain=True).status_code == 409
    assert obsidian.get(f"/api/chats/{chat_id}").status_code == 404
    upstream.handler = lambda request: httpx.Response(200, json=[{"name": "obsidian", "enabled": True, "tools": ["tool_obsidian_write"]}])
    obsidian.put("/api/account-capabilities/capability/obsidian", json={"enabled": False})
    assert start(obsidian, new_id(), save_to_second_brain=True).status_code == 409


def test_disabling_write_tool_does_not_silently_auto_save(obsidian, agent):
    chat_id = new_id()
    assert start(obsidian, chat_id, save_to_second_brain=True, disabled_tools=["tool_obsidian_write"]).status_code == 409
    assert not agent.asks


def test_second_brain_requires_login(client):
    assert client.get("/api/chats/second-brain").status_code == 401


def test_another_account_cannot_read_or_change_the_chat_preference(obsidian, email):
    chat_id = new_id()
    assert start(obsidian, chat_id, save_to_second_brain=True).status_code == 202
    events(obsidian, chat_id)
    make_member(obsidian, email)
    login(obsidian, "alice")
    assert obsidian.get(f"/api/chats/{chat_id}").status_code == 404
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": False}).status_code == 404


def test_capability_check_failure_refuses_enable_but_allows_turning_off(obsidian, upstream):
    chat_id = new_id()
    assert start(obsidian, chat_id).status_code == 202
    events(obsidian, chat_id)
    upstream.handler = lambda request: httpx.Response(503, json={"error": "unavailable"})
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": True}).status_code == 503
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": False}).status_code == 200
