"""/api/admin/outside-clients: staff-only management of outside clients."""

from __future__ import annotations

import pytest

from tests.test_admin import login, make_member
from tests.test_logs import messages, my_id
from tests.test_outside_routes import ENTRY, FakeDirectory, auth, fake_legion, login_admin  # noqa: F401 - fixture reuse

BASE = "/api/admin/outside-clients"


def call_outside(client, key, question="q"):
    return client.post("/api/outside/legion/ask", json={"question": question}, headers=auth(key))


def test_only_staff_with_settings_manage_may_use_the_admin_routes(client, email):
    assert client.get(BASE).status_code in (401, 403)
    make_member(client, email)
    login(client, "alice")
    assert client.get(BASE).status_code == 403
    assert client.post(BASE, json={"name": "x", "budget_tokens": 10}).status_code == 403


def test_create_shows_the_key_once_and_never_the_hash(client):
    login_admin(client)
    created = client.post(BASE, json={"name": "Docs bot", "budget_tokens": 5000})
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("ock_") and body["client"]["name"] == "Docs bot" and body["client"]["services"] == ["legion"]
    listed = client.get(BASE).json()["clients"]
    assert len(listed) == 1 and "key" not in listed[0] and "key_hash" not in listed[0]
    assert listed[0]["key_prefix"] == body["key"][:8] and listed[0]["budget"]["used"] == 0 and listed[0]["budget"]["remaining"] == 5000


def test_a_response_that_shows_a_key_is_never_cached(client):
    login_admin(client)
    created = client.post(BASE, json={"name": "Docs bot", "budget_tokens": 5000})
    assert created.headers["cache-control"] == "no-store"
    rotated = client.post(f"{BASE}/{created.json()['client']['id']}/rotate-key", json={})
    assert rotated.status_code == 200 and rotated.headers["cache-control"] == "no-store"


def test_bad_input_is_400_in_words_or_422(client):
    login_admin(client)
    assert client.post(BASE, json={"name": "x"}).status_code == 422  # budget is required
    refused = client.post(BASE, json={"name": "x", "budget_tokens": 0})
    assert refused.status_code == 400 and "budget" in refused.json()["detail"]
    assert client.post(BASE, json={"name": "x", "budget_tokens": 5, "services": ["other"]}).status_code == 400
    assert client.post(BASE, json={"name": "x", "budget_tokens": 5, "key": "ock_mine"}).status_code == 422
    assert client.get(f"{BASE}/999").status_code == 404
    assert client.patch(f"{BASE}/999", json={"enabled": False}).status_code == 404
    assert client.delete(f"{BASE}/999").status_code == 404


def test_patch_disable_rotate_and_delete(client, fake_legion):  # noqa: F811
    login_admin(client)
    created = client.post(BASE, json={"name": "Docs bot", "budget_tokens": 5000}).json()
    client_id, key = created["client"]["id"], created["key"]
    assert client.patch(f"{BASE}/{client_id}", json={"enabled": False}).json()["enabled"] is False
    fake_legion.next = {"text": "a", "tokens": 1}
    assert call_outside(client, key).status_code == 401
    client.patch(f"{BASE}/{client_id}", json={"enabled": True})
    assert call_outside(client, key).status_code == 200
    rotated = client.post(f"{BASE}/{client_id}/rotate-key", json={}).json()
    assert rotated["key"] != key and call_outside(client, key).status_code == 401
    assert call_outside(client, rotated["key"]).status_code == 200
    assert client.delete(f"{BASE}/{client_id}").status_code == 204
    assert client.get(f"{BASE}/{client_id}").status_code == 404
    assert call_outside(client, rotated["key"]).status_code == 401


def test_the_detail_shows_the_audit_events_and_no_text(client_factory, fake_legion):  # noqa: F811
    client = client_factory(address="127.0.0.1")  # a trusted proxy, so X-Forwarded-For sets the client address
    client.app.state.legion_ask, client.app.state.agent_directory = fake_legion, FakeDirectory(ENTRY)
    login_admin(client)
    created = client.post(BASE, json={"name": "Docs bot", "budget_tokens": 5000, "ip_allow": ["203.0.113.0/24"]}).json()
    fake_legion.next = {"text": "SECRET ANSWER", "tokens": 9}

    def at(ip, question="q"):
        return client.post("/api/outside/legion/ask", json={"question": question},
                           headers={**auth(created["key"]), "X-Forwarded-For": ip})

    assert at("203.0.113.7", "SECRET QUESTION").status_code == 200
    assert at("198.51.100.1").status_code == 403  # outside the client's own list
    detail = client.get(f"{BASE}/{created['client']['id']}").json()
    assert [(e["action"], e["reason"], e["status"]) for e in detail["events"]] == [("refused", "ip_not_allowed", 403), ("call", "", 200)]
    assert "SECRET" not in str(detail) and detail["budget"]["used"] == 9
    assert len(client.get(f"{BASE}/{created['client']['id']}", params={"limit": 1}).json()["events"]) == 1


def test_admin_changes_are_logged_without_a_key(client):
    login_admin(client)
    created = client.post(BASE, json={"name": "Docs bot", "budget_tokens": 5000}).json()
    client.patch(f"{BASE}/{created['client']['id']}", json={"rate_per_minute": 5})
    logged = messages(client, "action", my_id(client))
    text = " ".join(logged)
    assert any("Docs bot" in m for m in logged) and "rate_per_minute" in text
    assert created["key"] not in text and created["key"][:8] not in text
