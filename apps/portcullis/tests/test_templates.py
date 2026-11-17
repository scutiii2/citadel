"""/api/templates: Portcullis checks the login and chat.use; Stronghold answers."""

from __future__ import annotations

from tests.auth_helpers import requester, assertion

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeEmailSender, FakeUpstream
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/templates"
TEMPLATE_ID = "a" * 32
BODY = {"name": "Review", "body": "Please review this:"}


def stronghold(request: httpx.Request) -> httpx.Response:
    if request.method == "DELETE":
        return httpx.Response(204)
    return httpx.Response(201 if request.method == "POST" else 200, json={"path": request.url.path})


def test_templates_need_login_and_chat_use(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    assert client.get(URL).status_code == 401
    assert client.post(URL, json=BODY).status_code == 401
    assert client.put(f"{URL}/{TEMPLATE_ID}", json=BODY).status_code == 401
    assert client.delete(f"{URL}/{TEMPLATE_ID}").status_code == 401

    make_member(client, email, verify=False)
    login(client, "alice")
    upstream.requests.clear()
    assert client.get(URL).status_code == 403  # unverified: no permissions
    assert client.post(URL, json=BODY).status_code == 403
    assert not upstream.requests


def test_every_template_route_goes_to_stronghold_as_the_signed_in_account(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    as_admin(client)
    uid = uids(client)["root"]
    upstream.requests.clear()

    assert client.get(URL).json() == {"path": "/templates"}
    assert client.post(URL, json=BODY).status_code == 201
    assert client.put(f"{URL}/{TEMPLATE_ID}", json=BODY).json() == {"path": f"/templates/{TEMPLATE_ID}"}
    assert client.delete(f"{URL}/{TEMPLATE_ID}").status_code == 204

    assert all(requester(request)["sub"] == uid for request in upstream.requests)
    assert json.loads(upstream.requests[1].content) == BODY
    assert len(upstream.requests) == 4


def test_a_refusal_from_stronghold_passes_through(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: httpx.Response(409, json={"detail": 'You already have a template named "Review"'})
    as_admin(client)

    refused = client.post(URL, json=BODY)

    assert (refused.status_code, refused.json()["detail"]) == (409, 'You already have a template named "Review"')


@pytest.mark.parametrize("segment", ["0", "not-a-number", "A" * 32, "a" * 33, "accounts"])
def test_malformed_ids_and_the_purge_route_do_not_reach_stronghold(client: TestClient, upstream: FakeUpstream, segment: str) -> None:
    upstream.handler = stronghold
    as_admin(client)
    upstream.requests.clear()

    assert client.put(f"{URL}/{segment}", json=BODY).status_code == 422
    assert client.delete(f"{URL}/{segment}").status_code == 422
    assert client.delete(f"{URL}/accounts/someone").status_code in (404, 405)
    assert not upstream.requests


def test_posts_must_be_json(client: TestClient) -> None:
    as_admin(client)

    response = client.post(URL, content="name=x&body=y", headers={"Content-Type": "text/plain"})

    assert response.status_code == 415


def test_deleting_an_account_purges_its_templates_in_stronghold(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [r.method for r in upstream.requests if r.url.path == f"/templates/accounts/{uid}"] == ["DELETE"]


def test_failed_purge_never_blocks_account_deletion(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(503, json={"detail": "Storage is unavailable"})

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204
    assert "alice" not in uids(client)
    root = client.get("/api/auth/me").json()["id"]
    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.templates_purge" for entry in errors)
