import httpx
import pytest

from tests.auth_helpers import assertion, requester
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_internal_api import internal_headers, uid_of
from tests.test_registration import as_admin

JSON = {"Content-Type": "application/json"}
ID = "a" * 32

USER_CASES = [
    ("POST", "/api/brain/shares", "/brain/shares"),
    ("GET", "/api/brain/shares/sent", "/brain/shares/sent"),
    ("GET", "/api/brain/shares/inbox", "/brain/shares/inbox"),
    ("GET", f"/api/brain/shares/{ID}", f"/brain/shares/{ID}"),
    ("DELETE", f"/api/brain/shares/{ID}", f"/brain/shares/{ID}"),
    ("POST", f"/api/brain/shares/{ID}/accept", f"/brain/shares/{ID}/accept"),
    ("POST", f"/api/brain/shares/{ID}/decline", f"/brain/shares/{ID}/decline"),
    ("GET", "/api/brain/blocks", "/brain/blocks"),
    ("PUT", "/api/brain/blocks", "/brain/blocks"),
    ("DELETE", "/api/brain/blocks/u-2", "/brain/blocks/u-2"),
    ("GET", "/api/brain/global/files", "/brain/global/files"),
    ("GET", f"/api/brain/global/files/{ID}", f"/brain/global/files/{ID}"),
    ("GET", "/api/brain/global/search?q=tea", "/brain/global/search"),
    ("GET", "/api/brain/global/summary", "/brain/global/summary"),
    ("GET", "/api/brain/global/skills", "/brain/global/skills"),
]
WRITER_CASES = [
    ("POST", "/api/brain/global/files", "/brain/global/files"),
    ("PUT", f"/api/brain/global/files/{ID}", f"/brain/global/files/{ID}"),
    ("DELETE", f"/api/brain/global/files/{ID}", f"/brain/global/files/{ID}"),
    ("GET", "/api/brain/global/skills/all", "/brain/global/skills/all"),
    ("PUT", "/api/brain/global/skills/3/status", "/brain/global/skills/3/status"),
    ("PUT", "/api/brain/global/skills/3", "/brain/global/skills/3"),
    ("DELETE", "/api/brain/global/skills/3", "/brain/global/skills/3"),
    ("GET", "/api/brain/global/shares", "/brain/global/shares"),
    ("GET", f"/api/brain/global/shares/{ID}", f"/brain/global/shares/{ID}"),
    ("POST", f"/api/brain/global/shares/{ID}/approve", f"/brain/global/shares/{ID}/approve"),
    ("POST", f"/api/brain/global/shares/{ID}/reject", f"/brain/global/shares/{ID}/reject"),
]


@pytest.mark.parametrize("method, url, target", USER_CASES + WRITER_CASES)
def test_an_administrator_reaches_every_route(client, upstream, method, url, target):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(200, json={"forwarded": True})
    upstream.requests.clear()
    answer = client.request(method, url, json={"x": 1} if method in ("POST", "PUT") else None, headers=JSON)
    assert answer.status_code == 200 and answer.json() == {"forwarded": True}
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path) == (method, target)
    assert assertion(sent, "stronghold")["iss"] == "portcullis"
    assert requester(sent)["username"] == "root"


def test_a_query_string_is_forwarded_on_a_read(client, upstream):
    as_admin(client)
    upstream.requests.clear()
    client.get("/api/brain/global/search?q=tea&limit=3")
    assert dict(upstream.requests[-1].url.params) == {"q": "tea", "limit": "3"}


@pytest.mark.parametrize("method, url, _target", USER_CASES + WRITER_CASES)
def test_no_login_means_no_forward(client, upstream, method, url, _target):
    upstream.requests.clear()
    assert client.request(method, url, headers=JSON).status_code == 401
    assert not upstream.requests


@pytest.mark.parametrize("method, url, _target", USER_CASES + WRITER_CASES)
def test_an_account_without_chat_use_is_refused(client, email, upstream, method, url, _target):
    make_member(client, email, verify=False)
    login(client, "alice")
    upstream.requests.clear()
    assert client.request(method, url, headers=JSON).status_code == 403
    assert not upstream.requests


@pytest.mark.parametrize("method, url, _target", WRITER_CASES)
def test_a_member_without_the_global_permission_cannot_use_a_writer_route(client, email, upstream, method, url, _target):
    make_member(client, email)  # a normal member: chat.use, no brain.global.write
    login(client, "alice")
    upstream.requests.clear()
    assert client.request(method, url, json={"x": 1}, headers=JSON).status_code == 403
    assert not upstream.requests


@pytest.mark.parametrize("bad", ["bad.id", "a%2F%2E%2Fb"])
def test_malformed_ids_never_forward(client, upstream, bad):
    as_admin(client)
    upstream.requests.clear()
    for method, path in (
        ("GET", f"/api/brain/shares/{bad}"),
        ("POST", f"/api/brain/shares/{bad}/accept"),
        ("POST", f"/api/brain/global/shares/{bad}/approve"),
    ):
        assert client.request(method, path, headers=JSON).status_code in (404, 422)
    assert not upstream.requests


def test_safe_upstream_errors_pass_through(client, upstream):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(503, json={"detail": "Storage is unavailable"})
    answer = client.get("/api/brain/shares/inbox")
    assert (answer.status_code, answer.json()) == (503, {"detail": "Storage is unavailable"})


def test_deleting_an_account_purges_its_shares(client, email, upstream):
    account_id = make_member(client, email)
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()
    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
    purges = [s for s in upstream.requests if s.method == "DELETE" and s.url.path == f"/brain/shares/accounts/{uid}"]
    assert len(purges) == 1 and assertion(purges[0], "stronghold")["iss"] == "portcullis"


def test_username_lookup_requires_signed_stronghold_and_returns_a_usable_account(client, email):
    disabled = make_member(client, email, username="disabled")
    make_member(client, email, username="pending", verify=False)
    as_admin(client)
    assert client.patch(f"/api/admin/accounts/{disabled}", json={"is_active": False}, headers=JSON).status_code == 200

    prefix = "/internal/accounts/by-username"
    assert client.get(f"{prefix}/root").status_code == 401
    answer = client.get(f"{prefix}/root", headers=internal_headers(client))
    assert answer.status_code == 200
    assert answer.json() == {"uid": uid_of(client, "root"), "username": "root"}

    for unavailable in ("ROOT", "missing", "disabled", "pending"):
        answer = client.get(f"{prefix}/{unavailable}", headers=internal_headers(client))
        assert (answer.status_code, answer.json()) == (404, {"detail": "No such recipient"})
