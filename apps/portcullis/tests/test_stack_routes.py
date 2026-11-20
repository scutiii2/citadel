import json

import httpx
import pytest

from tests.auth_helpers import assertion, requester
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

JSON = {"Content-Type": "application/json"}

CASES = [
    ("GET", "/api/chats/c1/stack", "/stack/c1"),
    ("POST", "/api/chats/c1/stack/items", "/stack/c1/items"),
    ("PUT", "/api/chats/c1/stack/items/3", "/stack/c1/items/3"),
    ("DELETE", "/api/chats/c1/stack/items/3", "/stack/c1/items/3"),
    ("POST", "/api/chats/c1/stack/compact", "/stack/c1/compact"),
]



@pytest.mark.parametrize("method, url, target", CASES)
def test_a_route_forwards_to_stronghold_for_a_logged_in_account(client, upstream, method, url, target):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(200, json={"forwarded": True})
    upstream.requests.clear()
    body = {"text": "x"} if url.endswith("/items") else {"pinned": True} if method == "PUT" else None
    answer = client.request(method, url, json=body, headers=JSON)
    assert answer.status_code == 200
    assert answer.json() == {"forwarded": True}
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path) == (method, target)
    assert (json.loads(sent.content) if sent.content else None) == body
    assert assertion(sent, "stronghold")["iss"] == "portcullis"
    assert requester(sent)["username"] == "root"


def test_no_login_means_no_forward(client, upstream):
    upstream.requests.clear()
    for method, url, _ in CASES:
        assert client.request(method, url, headers=JSON).status_code == 401
    assert not upstream.requests


def test_an_account_without_chat_use_is_refused(client, email, upstream):
    make_member(client, email, verify=False)
    login(client, "alice")
    upstream.requests.clear()
    for method, url, _ in CASES:
        assert client.request(method, url, headers=JSON).status_code == 403
    assert not upstream.requests


@pytest.mark.parametrize("chat_id", ["bad.id", "a%2F%2E%2E%2Fb"])
def test_malformed_chat_ids_never_forward(client, upstream, chat_id):
    as_admin(client)
    upstream.requests.clear()
    for method, url, _ in CASES:
        assert client.request(method, url.replace("/c1/", f"/{chat_id}/"), headers=JSON).status_code in (404, 422)
    assert not upstream.requests


def test_stack_proxies_keep_safe_upstream_error_statuses(client, upstream):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(503, json={"detail": "Storage is unavailable"})
    answer = client.get("/api/chats/c1/stack")
    assert (answer.status_code, answer.json()) == (503, {"detail": "Storage is unavailable"})
    upstream.handler = lambda _: httpx.Response(502, json={"detail": "The context summarizer did not answer."})
    answer = client.post("/api/chats/c1/stack/compact", headers=JSON)
    assert (answer.status_code, answer.json()) == (502, {"detail": "The context summarizer did not answer."})


def test_deleting_an_account_purges_its_stacks(client, email, upstream):
    account_id = make_member(client, email)
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()

    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
    purges = [sent for sent in upstream.requests
              if sent.method == "DELETE" and sent.url.path == f"/stack/accounts/{uid}"]
    assert len(purges) == 1
    assert assertion(purges[0], "stronghold")["iss"] == "portcullis"
