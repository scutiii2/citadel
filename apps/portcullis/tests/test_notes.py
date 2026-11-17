"""/api/notes: Portcullis checks the login and chat.use; Stronghold answers."""

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

URL = "/api/notes"
NOTE_ID = "a" * 32


def stronghold(request: httpx.Request) -> httpx.Response:
    if request.method == "DELETE":
        return httpx.Response(204)
    return httpx.Response(201 if request.method == "POST" else 200, json={"path": request.url.path})


def test_needs_login(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"title": "x"}).status_code == 401
    assert client.get(f"{URL}/{NOTE_ID}").status_code == 401
    assert client.put(f"{URL}/{NOTE_ID}", json={"title": "x"}).status_code == 401
    assert client.delete(f"{URL}/{NOTE_ID}").status_code == 401
    assert client.post(f"{URL}/suggest-tags", json={"title": "x"}).status_code == 401
    assert client.post(f"{URL}/generate-tag", json={"title": "x"}).status_code == 401


def test_unverified_account_is_refused(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    make_member(client, email, "alice", verify=False)
    login(client, "alice")
    upstream.requests.clear()

    assert client.get(URL).status_code == 403
    assert client.post(f"{URL}/suggest-tags", json={"title": "x"}).status_code == 403
    assert not upstream.requests


def test_every_notes_route_goes_to_stronghold_as_the_signed_in_account(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    as_admin(client)
    uid = uids(client)["root"]
    upstream.requests.clear()

    assert client.get(URL).json() == {"path": "/notes"}
    assert client.post(URL, json={"title": "t", "tags": ["work"]}).status_code == 201
    assert client.get(f"{URL}/tags").json() == {"path": "/notes/tags"}
    assert client.post(f"{URL}/suggest-tags", json={"title": "t"}).json() == {"path": "/notes/suggest-tags"}
    assert client.post(f"{URL}/generate-tag", json={"title": "t"}).json() == {"path": "/notes/generate-tag"}
    assert client.get(f"{URL}/{NOTE_ID}").json() == {"path": f"/notes/{NOTE_ID}"}
    assert client.put(f"{URL}/{NOTE_ID}", json={"title": "u"}).json() == {"path": f"/notes/{NOTE_ID}"}
    assert client.delete(f"{URL}/{NOTE_ID}").status_code == 204

    assert all(requester(request)["sub"] == uid for request in upstream.requests)
    assert json.loads(upstream.requests[1].content) == {"title": "t", "tags": ["work"]}
    assert len(upstream.requests) == 8


def test_a_refusal_from_stronghold_passes_through(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: httpx.Response(412, json={"detail": "This note changed since you opened it"})
    as_admin(client)

    refused = client.put(f"{URL}/{NOTE_ID}", json={"title": "x", "expected_updated_at": "old"})

    assert (refused.status_code, refused.json()["detail"]) == (412, "This note changed since you opened it")


@pytest.mark.parametrize("segment", ["../etc", "nope", "A" * 32, "a" * 31, "a" * 33, "accounts", "accounts/someone"])
def test_malformed_ids_and_the_purge_route_are_not_found(client: TestClient, upstream: FakeUpstream, segment: str) -> None:
    upstream.handler = stronghold
    as_admin(client)
    upstream.requests.clear()

    assert client.get(f"{URL}/{segment}").status_code == 404
    assert client.delete(f"{URL}/{segment}").status_code in (404, 405)
    assert not upstream.requests


def test_deleting_an_account_purges_its_notes_in_stronghold(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [r.method for r in upstream.requests if r.url.path == f"/notes/accounts/{uid}"] == ["DELETE"]


def test_failed_purge_never_blocks_account_deletion(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(503, json={"detail": "Notes storage is unavailable"})

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204
    assert "alice" not in uids(client)
    root = client.get("/api/auth/me").json()["id"]
    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.notes_purge" for entry in errors)
