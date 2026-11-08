"""The signed-in account's learned skills: a thin authenticated proxy to mcp_server."""

import json
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
    "created_at": "2026-10-25T00:00:00+00:00", "failing": False,
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


EDIT = {"title": "Reboot an app", "when_to_use": "an app freezes", "steps": "kill it, then launch it", "tools": "tool_srv_restartApp"}


def test_editing_sends_the_cleaned_fields_for_the_authenticated_uid(client_factory, upstream):
    client = client_factory(internal_token="shared-test-token")
    as_admin(client)
    uid = uids(client)["root"]
    edited = {**SKILL, **EDIT, "status": "active", "failing": False}
    seen = {}

    def respond(request):
        seen["path"], seen["method"], seen["token"] = request.url.path, request.method, request.headers["X-Internal-Token"]
        seen["body"] = request.read()
        return httpx.Response(200, json=edited)

    upstream.handler = respond
    response = client.put(f"{URL}/1", json={**EDIT, "title": "  Reboot   an app ", "uid": "b" * 32})

    assert response.status_code == 200 and response.json()["title"] == "Reboot an app"
    assert (seen["method"], seen["path"], seen["token"]) == ("PUT", f"/skills/owners/{uid}/skills/1", "shared-test-token")
    assert json.loads(seen["body"]) == EDIT


@pytest.mark.parametrize("body", [
    {**EDIT, "title": " "}, {**EDIT, "title": "x" * 81}, {**EDIT, "when_to_use": ""}, {**EDIT, "steps": "x" * 1201},
    {**EDIT, "tools": "x" * 201}, {"title": "only"}, {},
])
def test_editing_is_validated_before_upstream(client, upstream, body):
    as_admin(client)
    upstream.requests.clear()
    assert client.put(f"{URL}/1", json=body).status_code == 422
    assert not upstream.requests


def test_editing_shows_the_reason_for_a_clash_but_other_failures_stay_generic(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(409, json={"error": "Another skill already has that title."})
    response = client.put(f"{URL}/1", json=EDIT)
    assert response.status_code == 409 and "already has that title" in response.json()["detail"]

    upstream.handler = lambda request: httpx.Response(500, json={"error": "stack trace with secrets"})
    response = client.put(f"{URL}/1", json=EDIT)
    assert response.status_code == 503 and "secrets" not in response.text

    upstream.handler = lambda request: httpx.Response(404, json={"error": "Skill not found"})
    assert client.put(f"{URL}/1", json=EDIT).status_code == 404


def test_editing_requires_login_and_permission(client):
    assert client.put(f"{URL}/1", json=EDIT).status_code == 401


def test_the_failing_flag_is_passed_through(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(200, json=[{**SKILL, "status": "active", "failures": 3, "failing": True}])
    assert client.get(URL).json()[0]["failing"] is True


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
