"""/skills: Armory keeps the skills; Stronghold scopes every call to the requester."""

from tests.auth_helpers import identity, caller, requester

import json
import logging

import httpx
import pytest

from tests.conftest import IDENTITY

URL = "/skills"
UID = IDENTITY["uid"]
SKILL = {
    "id": 1, "title": "Restart an app", "when_to_use": "an app is hung", "steps": "stop it, then start it",
    "tools": "tool_srv_stopApp", "status": "proposed", "successes": 0, "failures": 0,
    "created_at": "2026-10-25T00:00:00+00:00", "failing": False,
}
EDIT = {"title": "Reboot an app", "when_to_use": "an app freezes", "steps": "kill it, then launch it", "tools": "tool_srv_restartApp"}


def test_skills_need_the_requester_identity(client, armory):
    assert client.get(URL, headers=identity(uid="")).status_code == 400
    assert not armory.requests


def test_skills_use_the_requester_uid_and_the_internal_token(client, armory):
    approved = {**SKILL, "status": "active"}

    def respond(request):
        assert request.url.path.startswith(f"/skills/owners/{UID}/skills")
        assert caller(request, "armory") == "stronghold"
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=[SKILL] if request.method == "GET" else approved)

    armory.handler = respond
    assert client.get(URL, params={"uid": "b" * 32}).json() == [SKILL]
    assert client.put(f"{URL}/1/status", json={"status": "active", "uid": "b" * 32}).json() == approved
    assert client.delete(f"{URL}/1").status_code == 204
    assert len(armory.requests) == 3


@pytest.mark.parametrize("body", [{"status": "banana"}, {}, {"status": 5}])
def test_status_is_validated_before_upstream(client, armory, body):
    assert client.put(f"{URL}/1/status", json=body).status_code == 422
    assert not armory.requests


@pytest.mark.parametrize("code, expected", [(404, 404), (409, 409), (422, 422), (401, 503), (500, 503), (307, 503)])
def test_upstream_failures_are_safe(client, armory, code, expected):
    armory.handler = lambda request: httpx.Response(
        code, json={"error": "Skills is not enabled"}, headers={"location": "http://other.invalid"})
    assert client.get(URL).status_code == expected


def test_a_malformed_upstream_answer_is_503(client, armory):
    armory.handler = lambda request: httpx.Response(200, json=[{"id": 1}])
    assert client.get(URL).status_code == 503


def test_network_failure_is_503(client, armory):
    def fail(request):
        raise httpx.ConnectError("offline")

    armory.handler = fail
    assert client.get(URL).status_code == 503


def test_actions_are_logged_through_portcullis_and_logs_never_include_text_or_uid(client, armory, platform, caplog):
    armory.handler = lambda request: httpx.Response(204) if request.method == "DELETE" else httpx.Response(200, json=SKILL)
    caplog.set_level(logging.INFO)
    assert client.put(f"{URL}/1/status", json={"status": "active"}).status_code == 200
    assert client.put(f"{URL}/1", json=EDIT).status_code == 200
    assert client.delete(f"{URL}/1").status_code == 204
    assert UID not in caplog.text and "/skills/owners/[redacted]" in caplog.text
    assert "stop it, then start it" not in caplog.text
    assert platform.actions == [(UID, "skills.status", "Set a skill to active"), (UID, "skills.edit", "Edited a skill"),
                                (UID, "skills.delete", "Deleted a skill")]


def test_editing_sends_the_cleaned_fields_for_the_requester(client, armory):
    edited = {**SKILL, **EDIT, "status": "active", "failing": False}
    armory.handler = lambda request: httpx.Response(200, json=edited)

    response = client.put(f"{URL}/1", json={**EDIT, "title": "  Reboot   an app ", "uid": "b" * 32})

    assert response.status_code == 200 and response.json()["title"] == "Reboot an app"
    sent = armory.requests[-1]
    assert (sent.method, sent.url.path) == ("PUT", f"/skills/owners/{UID}/skills/1")
    assert json.loads(sent.content) == EDIT


@pytest.mark.parametrize("body", [
    {**EDIT, "title": " "}, {**EDIT, "title": "x" * 81}, {**EDIT, "when_to_use": ""}, {**EDIT, "steps": "x" * 1201},
    {**EDIT, "tools": "x" * 201}, {"title": "only"}, {},
])
def test_editing_is_validated_before_upstream(client, armory, body):
    assert client.put(f"{URL}/1", json=body).status_code == 422
    assert not armory.requests


def test_editing_shows_the_reason_for_a_clash_but_other_failures_stay_generic(client, armory):
    armory.handler = lambda request: httpx.Response(409, json={"error": "Another skill already has that title."})
    response = client.put(f"{URL}/1", json=EDIT)
    assert response.status_code == 409 and "already has that title" in response.json()["detail"]

    armory.handler = lambda request: httpx.Response(500, json={"error": "stack trace with secrets"})
    response = client.put(f"{URL}/1", json=EDIT)
    assert response.status_code == 503 and "secrets" not in response.text

    armory.handler = lambda request: httpx.Response(404, json={"error": "Skill not found"})
    assert client.put(f"{URL}/1", json=EDIT).status_code == 404


def test_the_failing_flag_is_passed_through(client, armory):
    armory.handler = lambda request: httpx.Response(200, json=[{**SKILL, "status": "active", "failures": 3, "failing": True}])
    assert client.get(URL).json()[0]["failing"] is True


def test_purging_an_account_asks_armory_once_and_keeps_the_uid_out_of_logs(client, armory, caplog):
    armory.handler = lambda request: httpx.Response(204)
    caplog.set_level(logging.INFO)

    assert client.delete(f"{URL}/accounts/{'c' * 32}").status_code == 204

    assert [(r.method, r.url.path) for r in armory.requests] == [("DELETE", f"/skills/owners/{'c' * 32}")]
    assert "c" * 32 not in caplog.text and "/skills/owners/[redacted]" in caplog.text


def test_a_purge_armory_did_not_confirm_is_502(client, armory):
    armory.handler = lambda request: httpx.Response(500, json={"error": "boom"})
    assert client.delete(f"{URL}/accounts/{'c' * 32}").status_code == 502
