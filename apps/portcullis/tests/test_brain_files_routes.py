import json

import httpx
import pytest

from tests.auth_helpers import assertion, requester
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

JSON = {"Content-Type": "application/json"}
ID = "a" * 32

CASES = [
    ("GET", "/api/brain/files?folder=drinks", "/brain/files"),
    ("POST", "/api/brain/files", "/brain/files"),
    ("GET", f"/api/brain/files/{ID}", f"/brain/files/{ID}"),
    ("PUT", f"/api/brain/files/{ID}", f"/brain/files/{ID}"),
    ("DELETE", f"/api/brain/files/{ID}", f"/brain/files/{ID}"),
    ("POST", f"/api/brain/files/{ID}/revert", f"/brain/files/{ID}/revert"),
    ("GET", "/api/brain/search?q=tea&limit=3", "/brain/search"),
    ("GET", "/api/brain/summary", "/brain/summary"),
]


@pytest.mark.parametrize("method, url, target", CASES)
def test_a_route_forwards_to_stronghold_for_a_logged_in_account(client, upstream, method, url, target):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(200, json={"forwarded": True})
    upstream.requests.clear()
    body = {"title": "t", "body": "b"} if method in ("POST", "PUT") and not url.endswith("revert") else None
    answer = client.request(method, url, json=body, headers=JSON)
    assert answer.status_code == 200 and answer.json() == {"forwarded": True}
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path) == (method, target)
    assert (json.loads(sent.content) if sent.content else None) == body
    assert dict(sent.url.params) == dict(httpx.URL(url).params)
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
        assert client.request(method, url, headers=JSON).status_code in (401, 403)
    assert not upstream.requests


def test_a_file_id_that_is_not_32_hex_never_reaches_stronghold(client, upstream):
    as_admin(client)
    upstream.requests.clear()
    for bad in ("accounts", "..", "a" * 31, "A" * 32, "x" * 32):
        assert client.get(f"/api/brain/files/{bad}").status_code in (404, 422)
        assert client.delete(f"/api/brain/files/{bad}").status_code in (404, 405, 422)
    assert not upstream.requests


def test_the_purge_route_is_out_of_reach(client, upstream):
    as_admin(client)
    upstream.requests.clear()
    assert client.delete("/api/brain/accounts/u-1").status_code in (404, 405)
    assert not upstream.requests


def test_deleting_an_account_purges_its_long_term_memory(client, email, upstream):
    account_id = make_member(client, email)
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()

    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
    purges = [sent for sent in upstream.requests
              if sent.method == "DELETE" and sent.url.path == f"/brain/accounts/{uid}"]
    assert len(purges) == 1
    assert assertion(purges[0], "stronghold")["iss"] == "portcullis"


def test_brain_routes_keep_stronghold_storage_errors(client, upstream):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(503, json={"detail": "Storage is unavailable"})
    answer = client.get("/api/brain/files")
    assert (answer.status_code, answer.json()) == (503, {"detail": "Storage is unavailable"})
    upstream.handler = lambda _: httpx.Response(409, json={"detail": "You have reached the limit of 500 files."})
    answer = client.post("/api/brain/files", json={"title": "t"}, headers=JSON)
    assert answer.status_code == 409

def test_brain_query_text_is_removed_from_proxy_request_logs(client):
    import logging

    logger = logging.getLogger("httpx")
    record = logger.makeRecord(
        logger.name, logging.INFO, __file__, 1, "%s %s",
        ("GET", httpx.URL("http://stronghold/brain/files?folder=private-folder")), None,
    )
    for log_filter in logger.filters:
        log_filter.filter(record)
    assert record.getMessage() == "GET http://stronghold/brain/files?[redacted]"
