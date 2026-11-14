import httpx
import pytest

from tests.test_registration import as_admin
from tests.test_admin import login, make_member
from tests.test_account_uid import uids

URL = "/api/memory"


def test_memory_requires_login(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"text": "coffee"}).status_code == 401
    assert client.put(f"{URL}/1", json={"text": "tea", "expected_text": "coffee"}).status_code == 401
    assert client.delete(f"{URL}/1").status_code == 401


def test_memory_requires_verified_chat_permission(client, email):
    make_member(client, email, "alice", verify=False)
    login(client, "alice")
    assert client.get(URL).status_code == 403


def test_memory_requires_chat_permission_on_every_action(client, email, upstream):
    alice = make_member(client, email, "alice")
    as_admin(client)
    member = next(role for role in client.get("/api/admin/roles").json() if role["name"] == "Member")
    assert client.delete(f"/api/admin/accounts/{alice}/roles/{member['id']}").status_code == 200
    client.post("/api/auth/logout", json={})
    login(client, "alice")
    upstream.requests.clear()
    assert client.get(URL).status_code == 403
    assert client.post(URL, json={"text": "coffee"}).status_code == 403
    assert client.put(f"{URL}/1", json={"text": "tea", "expected_text": "coffee"}).status_code == 403
    assert client.delete(f"{URL}/1").status_code == 403
    assert not upstream.requests


def test_memory_uses_authenticated_uid_and_internal_token(client_factory, upstream):
    client = client_factory(internal_token="shared-test-token")
    as_admin(client)
    uid = uids(client)["root"]
    note = {"id": 1, "text": "coffee", "created_at": "2026-10-18T00:00:00+00:00"}
    def respond(request):
        assert request.url.path.startswith(f"/memory/owners/{uid}/notes")
        assert request.headers["X-Internal-Token"] == "shared-test-token"
        return httpx.Response(204) if request.method == "DELETE" else httpx.Response(200, json=[note] if request.method == "GET" else note)
    upstream.handler = respond
    assert client.get(URL, params={"uid": "b" * 32}).json() == [note]
    assert client.post(URL, json={"text": "coffee", "uid": "b" * 32}).status_code == 201
    assert client.put(f"{URL}/1", json={"text": "coffee", "expected_text": "coffee"}).json() == note
    assert client.delete(f"{URL}/1").status_code == 204


@pytest.mark.parametrize("body", [{"text": " "}, {"text": "x" * 501}, {}])
def test_memory_validates_before_upstream(client, upstream, body):
    as_admin(client)
    upstream.requests.clear()
    assert client.post(URL, json=body).status_code == 422
    assert not upstream.requests


@pytest.mark.parametrize("code, expected", [(404, 404), (409, 409), (401, 503), (500, 503), (307, 503)])
def test_memory_upstream_failures_are_safe(client, upstream, code, expected):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(code, json={"error": "Memory is not enabled"}, headers={"location": "http://other.invalid"})
    assert client.get(URL).status_code == expected


def test_memory_network_failure_is_503(client, upstream):
    as_admin(client)
    def fail(request):
        raise httpx.ConnectError("offline")
    upstream.handler = fail
    assert client.get(URL).status_code == 503


def test_memory_audit_and_request_logs_never_include_text_or_uid(client, upstream, caplog):
    import logging
    as_admin(client)
    uid = uids(client)["root"]
    text = "A private memory for audit testing"
    note = {"id": 1, "text": text, "created_at": "2026-10-18T00:00:00Z"}
    upstream.handler = lambda request: httpx.Response(204) if request.method == "DELETE" else httpx.Response(200, json=note)
    caplog.set_level(logging.INFO)
    assert client.post(URL, json={"text": text}).status_code == 201
    assert client.put(f"{URL}/1", json={"text": text, "expected_text": text}).status_code == 200
    assert client.delete(f"{URL}/1").status_code == 204
    assert uid not in caplog.text
    assert text not in caplog.text
    account_id = client.get("/api/auth/me").json()["id"]
    entries = client.get("/api/logs/action", params={"actor": str(account_id)}).json()
    actions = {entry["source"] for entry in entries}
    assert {"memory.create", "memory.update", "memory.delete"} <= actions
    assert text not in str(entries)


def test_memory_rejects_invalid_upstream_shape(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(200, json={"unexpected": "shape"})
    assert client.get(URL).status_code == 503
