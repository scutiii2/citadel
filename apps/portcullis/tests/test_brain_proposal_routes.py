import httpx
import pytest

from tests.auth_helpers import assertion, requester
from tests.test_account_uid import uids
from tests.test_admin import make_member
from tests.test_registration import as_admin

JSON = {"Content-Type": "application/json"}
ID = "a" * 32

CASES = [
    ("GET", "/api/brain/proposals", "/brain/proposals"),
    ("GET", f"/api/brain/proposals/{ID}", f"/brain/proposals/{ID}"),
    ("POST", f"/api/brain/proposals/{ID}/accept", f"/brain/proposals/{ID}/accept"),
    ("POST", f"/api/brain/proposals/{ID}/decline", f"/brain/proposals/{ID}/decline"),
]


@pytest.mark.parametrize("method, url, target", CASES)
def test_a_signed_in_person_reaches_every_route(client, upstream, method, url, target):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(200, json={"forwarded": True})
    upstream.requests.clear()
    answer = client.request(method, url, json={"x": 1} if method == "POST" else None, headers=JSON)
    assert answer.status_code == 200 and answer.json() == {"forwarded": True}
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path) == (method, target)
    assert assertion(sent, "stronghold")["iss"] == "portcullis"
    assert requester(sent)["username"] == "root"


@pytest.mark.parametrize("method, url, _target", CASES)
def test_no_login_means_no_forward(client, upstream, method, url, _target):
    upstream.requests.clear()
    assert client.request(method, url, headers=JSON).status_code == 401
    assert not upstream.requests


def test_a_bad_id_is_refused_before_it_is_forwarded(client, upstream):
    as_admin(client)
    upstream.requests.clear()
    assert client.get("/api/brain/proposals/not-hex").status_code == 422
    assert not upstream.requests


def test_deleting_an_account_purges_its_suggestions(client, email, upstream):
    account_id = make_member(client, email)
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()
    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
    purges = [request for request in upstream.requests
              if request.method == "DELETE" and request.url.path == f"/brain/proposals/accounts/{uid}"]
    assert len(purges) == 1 and assertion(purges[0], "stronghold")["iss"] == "portcullis"
