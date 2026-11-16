"""Per-chat auto-save preference, capability gating and the agent's save instruction."""
import httpx
import pytest

from tests.test_admin import login, make_member
from tests.test_registration import as_admin
from tests.turn_helpers import new_id


@pytest.fixture
def obsidian(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(200, json=[{
        "name": "obsidian", "enabled": True, "tools": ["tool_obsidian_write"],
    }])
    return client


def test_unsubscribed_and_offline_capability_cannot_enable(obsidian, upstream):
    assert obsidian.get("/api/chats/second-brain").json() == {"available": True}
    upstream.handler = lambda request: httpx.Response(200, json=[{"name": "obsidian", "enabled": False, "tools": []}])
    assert obsidian.get("/api/chats/second-brain").json() == {"available": False}
    chat_id = new_id()
    assert obsidian.put(f"/api/chats/{chat_id}", json={"title": "t", "messages": []}).status_code == 200
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": True}).status_code == 409
    upstream.handler = lambda request: httpx.Response(200, json=[{"name": "obsidian", "enabled": True, "tools": ["tool_obsidian_write"]}])
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": True}).status_code == 200


def test_second_brain_requires_login(client):
    assert client.get("/api/chats/second-brain").status_code == 401


def test_another_account_cannot_read_or_change_the_chat_preference(obsidian, email):
    chat_id = new_id()
    assert obsidian.put(f"/api/chats/{chat_id}", json={"title": "t", "messages": []}).status_code == 200
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": True}).status_code == 200
    make_member(obsidian, email)
    login(obsidian, "alice")
    assert obsidian.get(f"/api/chats/{chat_id}").status_code == 404
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": False}).status_code == 404


def test_capability_check_failure_refuses_enable_but_allows_turning_off(obsidian, upstream):
    chat_id = new_id()
    assert obsidian.put(f"/api/chats/{chat_id}", json={"title": "t", "messages": []}).status_code == 200
    upstream.handler = lambda request: httpx.Response(503, json={"error": "unavailable"})
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": True}).status_code == 503
    assert obsidian.patch(f"/api/chats/{chat_id}", json={"save_to_second_brain": False}).status_code == 200
