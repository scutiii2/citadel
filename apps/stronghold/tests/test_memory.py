"""/memory: Armory keeps the notes; Stronghold scopes every call to the requester."""

import logging

import httpx
import pytest

from tests.conftest import IDENTITY

URL = "/memory"
UID = IDENTITY["X-Requester-Uid"]
NOTE = {"id": 1, "text": "coffee", "created_at": "2026-10-18T00:00:00+00:00"}


def answer_notes(request: httpx.Request) -> httpx.Response:
    if request.method == "DELETE":
        return httpx.Response(204)
    return httpx.Response(200, json=[NOTE] if request.method == "GET" else NOTE)


def test_memory_needs_the_requester_identity(client, armory):
    assert client.get(URL, headers={"X-Requester-Uid": ""}).status_code == 400
    assert not armory.requests


def test_memory_uses_the_requester_uid_and_the_internal_token(client, armory):
    armory.handler = answer_notes
    assert client.get(URL, params={"uid": "b" * 32}).json() == [NOTE]
    assert client.post(URL, json={"text": "coffee", "uid": "b" * 32}).status_code == 201
    assert client.put(f"{URL}/1", json={"text": "coffee", "expected_text": "coffee"}).json() == NOTE
    assert client.delete(f"{URL}/1").status_code == 204
    for request in armory.requests:
        assert request.url.path.startswith(f"/memory/owners/{UID}/notes")
        assert request.headers["X-Internal-Token"] == "shared-test-token"


@pytest.mark.parametrize("body", [{"text": " "}, {"text": "x" * 501}, {}])
def test_memory_validates_before_upstream(client, armory, body):
    assert client.post(URL, json=body).status_code == 422
    assert not armory.requests


@pytest.mark.parametrize("code, expected", [(404, 404), (409, 409), (401, 503), (500, 503), (307, 503)])
def test_memory_upstream_failures_are_safe(client, armory, code, expected):
    armory.handler = lambda request: httpx.Response(
        code, json={"error": "Memory is not enabled"}, headers={"location": "http://other.invalid"})
    assert client.get(URL).status_code == expected


def test_memory_network_failure_is_503(client, armory):
    def fail(request):
        raise httpx.ConnectError("offline")

    armory.handler = fail
    assert client.get(URL).status_code == 503


def test_actions_are_logged_through_portcullis_and_logs_never_include_text_or_uid(client, armory, platform, caplog):
    text = "A private memory for audit testing"
    note = {"id": 1, "text": text, "created_at": "2026-10-18T00:00:00Z"}
    armory.handler = lambda request: httpx.Response(204) if request.method == "DELETE" else httpx.Response(200, json=note)
    caplog.set_level(logging.INFO)
    assert client.post(URL, json={"text": text}).status_code == 201
    assert client.put(f"{URL}/1", json={"text": text, "expected_text": text}).status_code == 200
    assert client.delete(f"{URL}/1").status_code == 204
    assert UID not in caplog.text and "/memory/owners/[redacted]" in caplog.text
    assert text not in caplog.text
    assert [(uid, action) for uid, action, _ in platform.actions] == [
        (UID, "memory.create"), (UID, "memory.update"), (UID, "memory.delete")]
    assert text not in str(platform.actions)


def test_a_failed_action_is_not_logged(client, armory, platform):
    armory.handler = lambda request: httpx.Response(409)
    assert client.post(URL, json={"text": "coffee"}).status_code == 409
    assert platform.actions == []


def test_memory_rejects_invalid_upstream_shape(client, armory):
    armory.handler = lambda request: httpx.Response(200, json={"unexpected": "shape"})
    assert client.get(URL).status_code == 503


def test_purge_deletes_the_owner_once_and_reports_a_refusal(client, armory):
    armory.handler = answer_notes
    assert client.delete(f"{URL}/accounts/carol-uid").status_code == 204
    assert [(r.method, r.url.path) for r in armory.requests] == [("DELETE", "/memory/owners/carol-uid")]
    armory.handler = lambda request: httpx.Response(500)
    assert client.delete(f"{URL}/accounts/carol-uid").status_code == 502
