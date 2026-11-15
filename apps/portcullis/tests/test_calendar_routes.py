"""/api/calendar: Portcullis checks the login and the permission, Stronghold answers."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.models import Account
from tests.conftest import FakeUpstream
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/calendar"


def stronghold(request: httpx.Request) -> httpx.Response:
    if request.method == "DELETE":
        return httpx.Response(204)
    if request.url.path == "/calendar/feeds/nope":
        return httpx.Response(404, json={"detail": "No such calendar"})
    return httpx.Response(200, json={"path": request.url.path})


def test_every_route_needs_login_and_the_permission(client: TestClient, email, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    assert client.get(f"{URL}/feeds").status_code == 401
    make_member(client, email)
    login(client, "alice")
    for method, path in (("get", "/feeds"), ("get", "/alarms"), ("delete", "/feeds/abc")):
        assert getattr(client, method)(URL + path).status_code == 403
    assert upstream.requests == []


def test_the_request_goes_to_stronghold_with_identity_query_and_body(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    as_admin(client)
    listed = client.get(f"{URL}/events", params={"from": "2026-10-26T00:00:00Z", "to": "2026-10-27T00:00:00Z"})
    assert listed.json() == {"path": "/calendar/events"}
    sent = upstream.requests[-1]
    assert sent.url.params["from"] == "2026-10-26T00:00:00Z" and len(sent.headers["x-requester-uid"]) == 32
    assert "cookie" not in sent.headers

    client.patch(f"{URL}/feeds/abc", json={"name": "Job"})
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path, json.loads(sent.content)) == ("PATCH", "/calendar/feeds/abc", {"name": "Job"})

    refused = client.patch(f"{URL}/feeds/nope", json={"name": "x"})
    assert (refused.status_code, refused.json()) == (404, {"detail": "No such calendar"})
    assert client.delete(f"{URL}/feeds/abc").status_code == 204


def test_paths_that_could_leave_the_calendar_are_refused(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    as_admin(client)
    before = len(upstream.requests)
    for path in ("/accounts/someone", "/accounts", "/feeds/A.B", "/%2e%2e/whoami", "/feeds//x"):
        assert client.delete(URL + path).status_code in (404, 422), path
    assert client.post(f"{URL}/feeds", content=b"{not json", headers={"content-type": "application/json"}).status_code == 422
    assert len(upstream.requests) == before


def test_deleting_an_account_purges_its_calendar_in_stronghold(client: TestClient, email, upstream: FakeUpstream) -> None:
    upstream.handler = stronghold
    account_id = make_member(client, email, "carol")
    as_admin(client)

    async def uid_of(username: str) -> str:
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(Account.uid).where(Account.username == username))

    uid = client.portal.call(uid_of, "carol")  # runs on the app's own event loop
    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
    purge = [r for r in upstream.requests if r.url.path == f"/calendar/accounts/{uid}"]
    assert [r.method for r in purge] == ["DELETE"]


def test_a_stronghold_outage_does_not_stop_the_account_delete(client: TestClient, email, upstream: FakeUpstream) -> None:
    account_id = make_member(client, email, "dave")
    as_admin(client)
    upstream.unreachable = True
    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
