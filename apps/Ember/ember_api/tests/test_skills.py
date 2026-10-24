"""The signed-in account's learned skills: a thin authenticated proxy to mcp_server."""

import logging

import httpx
import pytest

from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/skills"
SKILL = {
    "id": 1, "title": "Restart an app", "when_to_use": "an app is hung", "steps": "stop it, then start it",
    "tools": "tool_srv_stopApp", "status": "proposed", "successes": 0, "failures": 0,
    "created_at": "2026-10-25T00:00:00+00:00",
}


def test_skills_require_login(client):
    assert client.get(URL).status_code == 401
    assert client.put(f"{URL}/1/status", json={"status": "active"}).status_code == 401
    assert client.delete(f"{URL}/1").status_code == 401


def test_skills_require_a_verified_account(client, email):
    make_member(client, email, "alice", verify=False)
    login(client, "alice")
    assert client.get(URL).status_code == 403


def test_skills_require_chat_permission_on_every_action(client, email, upstream):
    alice = make_member(client, email, "alice")
    as_admin(client)
    member = next(role for role in client.get("/api/admin/roles").json() if role["name"] == "Member")
    assert client.delete(f"/api/admin/accounts/{alice}/roles/{member['id']}").status_code == 200
    client.post("/api/auth/logout", json={})
    login(client, "alice")
    upstream.requests.clear()
    assert client.get(URL).status_code == 403
    assert client.put(f"{URL}/1/status", json={"status": "active"}).status_code == 403
    assert client.delete(f"{URL}/1").status_code == 403
    assert not upstream.requests


def test_skills_use_the_authenticated_uid_and_internal_token(client_factory, upstream):
    client = client_factory(internal_token="shared-test-token")
    as_admin(client)
    uid = uids(client)["root"]
    approved = {**SKILL, "status": "active"}

    def respond(request):
        assert request.url.path.startswith(f"/skills/owners/{uid}/skills")
        assert request.headers["X-Internal-Token"] == "shared-test-token"
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=[SKILL] if request.method == "GET" else approved)

    upstream.handler = respond
    assert client.get(URL, params={"uid": "b" * 32}).json() == [SKILL]
    assert client.put(f"{URL}/1/status", json={"status": "active", "uid": "b" * 32}).json() == approved
    assert client.delete(f"{URL}/1").status_code == 204


@pytest.mark.parametrize("body", [{"status": "banana"}, {}, {"status": 5}])
def test_status_is_validated_before_upstream(client, upstream, body):
    as_admin(client)
    upstream.requests.clear()
    assert client.put(f"{URL}/1/status", json=body).status_code == 422
    assert not upstream.requests


@pytest.mark.parametrize("code, expected", [(404, 404), (409, 409), (422, 422), (401, 503), (500, 503), (307, 503)])
def test_upstream_failures_are_safe(client, upstream, code, expected):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(code, json={"error": "Skills is not enabled"}, headers={"location": "http://other.invalid"})
    assert client.get(URL).status_code == expected


def test_a_malformed_upstream_answer_is_503(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(200, json=[{"id": 1}])
    assert client.get(URL).status_code == 503


def test_network_failure_is_503(client, upstream):
    as_admin(client)

    def fail(request):
        raise httpx.ConnectError("offline")

    upstream.handler = fail
    assert client.get(URL).status_code == 503


def test_logs_never_include_skill_text_or_uid(client, upstream, caplog):
    as_admin(client)
    uid = uids(client)["root"]
    upstream.handler = lambda request: httpx.Response(204) if request.method == "DELETE" else httpx.Response(200, json=SKILL)
    caplog.set_level(logging.INFO)
    assert client.put(f"{URL}/1/status", json={"status": "active"}).status_code == 200
    assert client.delete(f"{URL}/1").status_code == 204
    assert uid not in caplog.text
    assert "stop it, then start it" not in caplog.text


def purges(upstream):
    return [r for r in upstream.requests if r.method == "DELETE" and r.url.path.startswith("/skills/owners/")]


def test_deleting_an_account_purges_its_skills_once(client, email, upstream, caplog):
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()
    caplog.set_level(logging.INFO)

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [r.url.path for r in purges(upstream)] == [f"/skills/owners/{uid}"]
    assert uid not in caplog.text
    assert "/skills/owners/[redacted]" in caplog.text


def test_a_failing_skills_purge_never_blocks_the_deletion(client, email, upstream):
    alice = make_member(client, email, "alice")
    uid = uids(client)["alice"]
    as_admin(client)
    root = client.get("/api/auth/me").json()["id"]
    upstream.handler = lambda request: httpx.Response(500, json={"error": "boom"})

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.skills_purge" and "'alice'" in entry["message"] for entry in errors)
    assert uid not in str(errors)
