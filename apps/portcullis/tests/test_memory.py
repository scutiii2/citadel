"""/api/memory: Portcullis checks the login and chat.use; Stronghold answers."""

import json

import httpx

from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/memory"
NOTE = {"id": 1, "text": "coffee", "created_at": "2026-10-18T00:00:00+00:00"}


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


def test_memory_goes_to_stronghold_as_the_signed_in_account(client_factory, upstream):
    client = client_factory(internal_token="shared-test-token")
    as_admin(client)
    uid = uids(client)["root"]

    def respond(request):
        assert request.url.host == "127.0.0.1" and request.url.port == 29650
        assert request.headers["X-Requester-Uid"] == uid
        assert request.headers["X-Internal-Token"] == "shared-test-token"
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(201 if request.method == "POST" else 200, json=[NOTE] if request.method == "GET" else NOTE)

    upstream.handler = respond
    upstream.requests.clear()
    assert client.get(URL).json() == [NOTE]
    assert client.post(URL, json={"text": "coffee"}).status_code == 201
    assert client.put(f"{URL}/1", json={"text": "coffee", "expected_text": "coffee"}).json() == NOTE
    assert client.delete(f"{URL}/1").status_code == 204
    assert [(r.method, r.url.path) for r in upstream.requests] == [
        ("GET", "/memory"), ("POST", "/memory"), ("PUT", "/memory/1"), ("DELETE", "/memory/1")]
    assert json.loads(upstream.requests[1].content) == {"text": "coffee"}


def test_refusals_pass_through_and_odd_paths_never_reach_stronghold(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(409, json={"detail": "This memory changed"})
    refused = client.put(f"{URL}/1", json={"text": "a", "expected_text": "b"})
    assert (refused.status_code, refused.json()) == (409, {"detail": "This memory changed"})
    upstream.requests.clear()
    for method, path in (("delete", "/accounts/someone"), ("delete", "/0"), ("put", "/1/x"), ("delete", "")):
        assert getattr(client, method)(URL + path).status_code in (404, 405, 422), path
    assert not upstream.requests


def test_a_stronghold_outage_is_502(client, upstream):
    as_admin(client)
    upstream.unreachable = True
    assert client.get(URL).status_code == 502
