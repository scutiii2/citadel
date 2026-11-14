from tests.test_registration import as_admin
from tests.test_admin import make_member, login
import json


def test_connections_require_login_and_sanitize_saved_key(client):
    url = "/api/brains/connections/personal"
    assert client.get(url).status_code == 401
    as_admin(client)
    response = client.put(url, json={"label": "Mine", "endpoint": "https://vault.lan", "api_key": "private-brain-key"})
    assert response.status_code == 200, response.text
    assert "private-brain-key" not in response.text
    assert response.json()["credential_configured"]
    assert client.get(url).json()["revision"] == 1
    stale = client.put(url, json={"label": "Stale", "endpoint": "https://vault.lan", "api_key": "private-brain-key"})
    assert stale.status_code == 409
    invalid = client.put(url, json={"label": "Mine", "endpoint": "http://bad", "api_key": "private-brain-key"})
    assert invalid.status_code == 422 and "private-brain-key" not in invalid.text


def test_members_own_personal_settings_but_cannot_manage_shared(client, email):
    make_member(client, email, "alice")
    login(client, "alice")
    assert client.get("/api/brains/connections/personal").status_code == 200
    assert client.get("/api/brains/connections/instance").status_code == 403
    assert client.get("/api/brains/destinations").status_code == 200
    assert client.post("/api/brains/internal/resolve", json={"scope": "instance", "operation": "read"}).status_code == 401


def test_internal_resolution_requires_real_uid_and_checks_publish(client):
    as_admin(client)
    client.app.state.internal_token = "internal-brain-token"
    headers = {"X-Internal-Token": "internal-brain-token", "X-Requester-Uid": "invented"}
    response = client.post("/api/brains/internal/resolve", headers=headers,
                           json={"scope": "personal", "operation": "read"})
    assert response.status_code == 403


def test_ai_review_consent_and_usage_even_for_invalid_output(client, agent):
    as_admin(client)
    client.put("/api/brains/connections/personal", json={"label": "Mine", "endpoint": "https://vault.lan",
        "api_key": "not-for-the-model", "allow_write": True})
    note = client.post("/api/notes", json={"title": "Private procedure", "body": "Durable private instructions"}).json()
    payload = {"note_ids": [note["id"]]}
    assert client.post("/api/brains/suggestions/review", json=payload).status_code == 400
    assert not agent.interprets
    payload["explicit_private"] = [note["id"]]
    agent.summary = json.dumps({"suggestions": [{"note_id": note["id"], "reason": "Reusable procedure", "title": "Procedure",
        "folder": "Inbox", "tags": [], "scope": "personal", "draft": "# Procedure\nInstructions"}]})
    response = client.post("/api/brains/suggestions/review", json=payload)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert "not-for-the-model" not in agent.interprets[0]
    assert "Durable private instructions" in agent.interprets[0]
    assert client.get(f"/api/notes/{note['id']}").json()["agent_readable"] is False
    suggestion_id = response.json()[0]["id"]
    assert client.post(f"/api/brains/suggestions/{suggestion_id}/dismiss", json={}).status_code == 200
    assert client.get("/api/brains/suggestions").json() == []
    agent.summary = '{"suggestions":[{"note_id":"foreign"}]}'
    assert client.post("/api/brains/suggestions/review", json=payload).status_code == 502
    assert client.get("/api/usage").json()["six_hour"]["used"] == 20
