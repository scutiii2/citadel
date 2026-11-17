"""/api/tickets and /api/admin/tickets: Portcullis checks the login and the permission; Stronghold answers."""

from __future__ import annotations

from tests.auth_helpers import requester, assertion

import json

import httpx
import pytest

from tests.test_account_uid import uids
from tests.test_admin import login, make_member, role_by_name
from tests.test_permission_split import limited_account
from tests.test_registration import as_admin

NEW = {"type": "bug", "title": "Email fails", "description": "It does not send"}


def stronghold(request: httpx.Request) -> httpx.Response:
    if request.method == "DELETE":
        return httpx.Response(204)
    return httpx.Response(201 if request.method == "POST" and request.url.path == "/tickets" else 200,
                          json={"path": request.url.path, "query": dict(request.url.params)})


@pytest.fixture
def served(upstream):
    upstream.handler = stronghold
    return upstream


def member_client(client_factory, email):
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    return member


def test_logged_out_visitors_get_401(client, served) -> None:
    for method, path in [("get", "/api/tickets"), ("get", "/api/tickets/unread-count"), ("get", "/api/tickets/7"),
                         ("get", "/api/admin/tickets"),
                         ("get", "/api/admin/tickets/stats"), ("get", "/api/admin/ticket-groups")]:
        assert getattr(client, method)(path).status_code == 401
    assert client.post("/api/tickets", json=NEW).status_code == 401
    assert client.post("/api/tickets/7/reopen", json={}).status_code == 401
    assert served.requests == []


def test_every_reporter_route_goes_to_stronghold_as_the_signed_in_account(client_factory, email, served) -> None:
    member = member_client(client_factory, email)
    uid = uids(member)["alice"]
    served.requests.clear()

    assert member.post("/api/tickets", json=NEW).status_code == 201
    assert member.get("/api/tickets", params={"status": "open"}).json() == {"path": "/tickets", "query": {"status": "open"}}
    assert member.get("/api/tickets/unread-count").json()["path"] == "/tickets/unread-count"
    assert member.get("/api/tickets/7").json()["path"] == "/tickets/7"
    assert member.post("/api/tickets/7/comments", json={"body": "log attached"}).json()["path"] == "/tickets/7/comments"
    assert member.post("/api/tickets/7/close", json={}).json()["path"] == "/tickets/7/close"
    assert member.post("/api/tickets/7/reopen", json={}).json()["path"] == "/tickets/7/reopen"

    assert all(requester(request)["sub"] == uid for request in served.requests)
    assert json.loads(served.requests[0].content) == NEW
    assert len(served.requests) == 7


def test_every_staff_route_goes_to_stronghold_as_the_staff_account(client, served) -> None:
    admin = as_admin(client)
    uid = uids(admin)["root"]
    served.requests.clear()

    assert admin.get("/api/admin/tickets", params={"status": "open", "limit": 20}).json() == {
        "path": "/ticket-admin/tickets", "query": {"status": "open", "limit": "20"}}
    assert admin.get("/api/admin/tickets/stats").json()["path"] == "/ticket-admin/stats"
    assert admin.get("/api/admin/tickets/7").json()["path"] == "/ticket-admin/tickets/7"
    assert admin.patch("/api/admin/tickets/7", json={"status": "closed"}).json()["path"] == "/ticket-admin/tickets/7"
    assert admin.post("/api/admin/tickets/7/comments", json={"body": "hi"}).json()["path"] == "/ticket-admin/tickets/7/comments"
    assert admin.post("/api/admin/tickets/7/move", json={"group_id": 3}).json()["path"] == "/ticket-admin/tickets/7/move"
    assert admin.get("/api/admin/ticket-groups").json()["path"] == "/ticket-admin/groups"
    assert admin.patch("/api/admin/ticket-groups/3", json={"pinned": False}).json()["path"] == "/ticket-admin/groups/3"

    assert all(requester(request)["sub"] == uid for request in served.requests)
    assert json.loads(served.requests[3].content) == {"status": "closed"}
    assert len(served.requests) == 8


def test_a_refusal_from_stronghold_passes_through(client_factory, email, upstream) -> None:
    upstream.handler = lambda request: httpx.Response(400, json={"detail": "The title is not acceptable."})
    member = member_client(client_factory, email)

    refused = member.post("/api/tickets", json={**NEW, "title": "bad"})

    assert (refused.status_code, refused.json()["detail"]) == (400, "The title is not acceptable.")


def test_ids_are_checked_before_stronghold(client_factory, email, served) -> None:
    member = member_client(client_factory, email)
    served.requests.clear()

    assert member.get("/api/tickets/abc").status_code == 422
    assert member.get("/api/tickets/0").status_code == 422
    assert member.post("/api/tickets/0/close", json={}).status_code == 422
    assert member.delete("/api/tickets/accounts/someone").status_code in (404, 405)
    assert served.requests == []


def test_stronghold_down_gives_502(client_factory, email, upstream) -> None:
    member = member_client(client_factory, email)
    upstream.unreachable = True

    down = member.get("/api/tickets")

    assert (down.status_code, down.json()["detail"]) == (502, "Stronghold is unavailable")


def test_ticket_routes_need_tickets_create(client_factory, email, served) -> None:
    member = client_factory()
    make_member(member, email)
    admin = as_admin(client_factory())
    role = role_by_name(admin, "Member")
    assert admin.delete(f"/api/admin/roles/{role['id']}/permissions/tickets.create").status_code == 200
    login(member, "alice")
    served.requests.clear()

    refused = member.get("/api/tickets")

    assert (refused.status_code, refused.json()["detail"]) == (403, "Missing permission: tickets.create")
    assert member.post("/api/tickets", json=NEW).status_code == 403
    assert member.get("/api/tickets/unread-count").status_code == 403
    assert served.requests == []


def test_staff_routes_need_tickets_manage(client_factory, email, served) -> None:
    member = member_client(client_factory, email)
    served.requests.clear()

    for method, path in [("get", "/api/admin/tickets"), ("get", "/api/admin/tickets/stats"),
                         ("get", "/api/admin/tickets/7"), ("get", "/api/admin/ticket-groups")]:
        refused = getattr(member, method)(path)
        assert (refused.status_code, refused.json()["detail"]) == (403, "Missing permission: tickets.manage")
    assert member.patch("/api/admin/tickets/7", json={"status": "closed"}).status_code == 403
    assert member.patch("/api/admin/ticket-groups/3", json={"priority": "low"}).status_code == 403
    assert served.requests == []


def test_manage_without_create_can_triage_but_not_file(client_factory, email, served) -> None:
    client = client_factory()
    limited_account(client, email, "tickets.manage")

    assert client.get("/api/admin/tickets").status_code == 200
    assert client.get("/api/tickets").status_code == 403
    assert client.post("/api/tickets", json=NEW).status_code == 403


def test_deleting_an_account_purges_its_read_receipts_in_stronghold(client, email, served) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    served.requests.clear()

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [r.method for r in served.requests if r.url.path == f"/tickets/accounts/{uid}"] == ["DELETE"]


def test_failed_receipt_purge_never_blocks_account_deletion(client, email, upstream) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    root = client.get("/api/auth/me").json()["id"]
    upstream.handler = lambda request: httpx.Response(503, json={"detail": "Storage is unavailable"})

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.tickets_purge" for entry in errors)
