"""Ticket routes and gateway: ember_api only proxies to mcp_server and decides who may call what."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from src.db import utcnow
from src.models import Account, AccountTicketSeen, TicketStaffActivity
from src.services.mcp_server_info import McpServerInfo
from src.services.ticket_gateway import TicketGateway
from src.services.ticket_unread import TicketUnreadService
from tests.conftest import FakeUpstream
from tests.test_admin import login, make_member, role_by_name
from tests.test_permission_split import limited_account
from tests.test_registration import as_admin

TICKET = {
    "id": 7, "group_id": 3, "type": "bug", "title": "Email fails", "description": "It does not send",
    "status": "open", "priority": "normal", "effective_priority": "normal", "assignee": None, "reporter": "alice",
    "source": "user", "tags": ["email"], "context": {}, "possible_group_id": None,
    "created_at": "2026-10-10T10:00:00+00:00", "updated_at": "2026-10-10T10:00:00+00:00", "closed_at": None,
}
GROUP = {"id": 3, "title": "Email fails", "priority": "normal", "priority_pinned": False, "ticket_count": 1,
         "recent_count": 1, "open_count": 1, "tags": ["email"]}
REPORTER_TICKET = {key: TICKET[key] for key in (
    "id", "type", "title", "description", "status", "created_at", "updated_at", "closed_at",
)}
STAFF_ACTIVITY: dict[int, str] = {}


@pytest.fixture(autouse=True)
def reset_staff_activity():
    STAFF_ACTIVITY.clear()


def upstream_ticket(ticket_id=7):
    return {**TICKET, "id": ticket_id, "last_staff_activity_at": STAFF_ACTIVITY.get(ticket_id)}


def body_of(request: httpx.Request):
    return json.loads(request.content) if request.content else None


def tickets_server(request: httpx.Request) -> httpx.Response:
    """mcp_server's ticket routes with canned answers; tests read upstream.requests."""
    path, method = request.url.path, request.method
    if path == "/tickets" and method == "POST":
        title = body_of(request)["title"]
        if title == "bad":
            return httpx.Response(400, json={"error": "The title is not acceptable."})
        if title == "dup":
            return httpx.Response(200, json={"ticket": TICKET, "duplicate": True, "group_size": 1})
        return httpx.Response(201, json={"ticket": TICKET, "duplicate": False, "group_size": 1})
    if path == "/tickets" and method == "GET":
        return httpx.Response(200, json={"tickets": [upstream_ticket()]})
    if path == "/ticket-admin/tickets" and method == "GET":
        return httpx.Response(200, json={"tickets": [TICKET]})
    if path == "/ticket-admin/groups" and method == "GET":
        return httpx.Response(200, json={"groups": [GROUP]})
    if path == "/ticket-admin/stats":
        return httpx.Response(200, json={"open": 1, "urgent": 0, "groups": 1})
    match = re.fullmatch(r"/(ticket-admin/)?tickets/(\d+)(?:/(comments|close|reopen|move))?", path)
    if match:
        ticket_id, action = int(match.group(2)), match.group(3)
        if ticket_id == 404:
            return httpx.Response(404, json={"error": "No ticket 404."})
        if match.group(1) and method in ("POST", "PATCH"):
            STAFF_ACTIVITY[ticket_id] = utcnow().replace(tzinfo=timezone.utc).isoformat()
        return httpx.Response(200, json={"ticket": {**upstream_ticket(ticket_id), "comments": []}})
    match = re.fullmatch(r"/ticket-admin/groups/(\d+)", path)
    if match and method == "PATCH":
        return httpx.Response(200, json={"group": {**GROUP, **body_of(request)}})
    return httpx.Response(404, json={"error": "no route"})


def test_gateway_drops_empty_filters_and_flags_possible(upstream: FakeUpstream) -> None:
    upstream.handler = tickets_server
    account = Account(id=1, username="root", email="root@example.com")
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    gateway = TicketGateway(McpServerInfo(client, "http://mcp-server.internal/mcp", "tok", None))

    result = asyncio.run(gateway.list_all(account, {"status": "open", "tag": None, "possible": True, "group_id": 3}))

    assert result == {"tickets": [TICKET]}
    request = upstream.requests[-1]
    assert dict(request.url.params) == {"status": "open", "possible": "1", "group_id": "3"}
    assert request.headers["x-requester-username"] == "root"
    assert request.headers["x-internal-token"] == "tok"


# ---- reporter routes -------------------------------------------------------

def test_reporter_reopen_is_scoped_and_keeps_staff_fields_private(client_factory, email, upstream) -> None:
    member, _ = member_client(client_factory, email, upstream)
    response = member.post("/api/tickets/7/reopen", json={})
    assert response.status_code == 200
    assert response.json()["ticket"]["id"] == 7
    assert "priority" not in response.json()["ticket"]
    assert upstream.requests[-1].url.path == "/tickets/7/reopen"
    assert upstream.requests[-1].headers["x-requester-username"] == "alice"
    assert member.post("/api/tickets/404/reopen", json={}).status_code == 404


def test_reopen_requires_login(client) -> None:
    assert client.post("/api/tickets/7/reopen", json={}).status_code == 401

def member_client(client_factory, email, upstream):
    upstream.handler = tickets_server
    member = client_factory()
    member_id = make_member(member, email)
    login(member, "alice")
    return member, member_id


def test_member_files_and_follows_own_tickets(client_factory, email, upstream) -> None:
    member, member_id = member_client(client_factory, email, upstream)

    created = member.post("/api/tickets", json={"type": "bug", "title": "Email fails", "description": "It does not send"})
    assert created.status_code == 201, created.text
    assert created.json() == {"ticket": REPORTER_TICKET, "duplicate": False, "group_size": 1}
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path) == ("POST", "/tickets")
    assert sent.headers["x-requester-username"] == "alice"
    assert body_of(sent) == {
        "type": "bug", "title": "Email fails", "description": "It does not send", "source": "user",
        "verified_context": {"via": "ember_api", "account_id": str(member_id)},
    }

    assert member.get("/api/tickets", params={"status": "open"}).json() == {
        "tickets": [{**REPORTER_TICKET, "has_unread": False}],
    }
    assert dict(upstream.requests[-1].url.params) == {"status": "open", "all": "1"}
    assert member.get("/api/tickets/7").json()["ticket"]["id"] == 7
    assert member.post("/api/tickets/7/comments", json={"body": "log attached"}).status_code == 200
    assert body_of(upstream.requests[-1]) == {"body": "log attached"}
    assert member.post("/api/tickets/7/close", json={}).status_code == 200
    assert upstream.requests[-1].url.path == "/tickets/7/close"


def test_a_repeated_report_answers_200(client_factory, email, upstream) -> None:
    member, _ = member_client(client_factory, email, upstream)

    response = member.post("/api/tickets", json={"type": "bug", "title": "dup", "description": "again"})

    assert response.status_code == 200 and response.json()["duplicate"] is True


def test_staff_replies_and_updates_are_unread_until_opened(client_factory, email, upstream) -> None:
    member, _ = member_client(client_factory, email, upstream)
    admin = as_admin(client_factory())
    assert member.get("/api/tickets/unread-count").json() == {"count": 0}
    assert admin.post("/api/admin/tickets/7/comments", json={"body": "Please retry"}).status_code == 200
    assert member.get("/api/tickets").json()["tickets"][0]["has_unread"] is True
    assert member.get("/api/tickets/unread-count").json() == {"count": 1}
    assert member.get("/api/tickets/7").status_code == 200
    assert member.get("/api/tickets/unread-count").json() == {"count": 0}
    assert admin.patch("/api/admin/tickets/7", json={"status": "resolved"}).status_code == 200
    assert member.get("/api/tickets").json()["tickets"][0]["has_unread"] is True
    # Reporter replies and closing do not acknowledge an unopened staff update.
    assert member.post("/api/tickets/7/comments", json={"body": "Thanks"}).status_code == 200
    assert member.post("/api/tickets/7/close", json={}).status_code == 200
    assert member.get("/api/tickets/unread-count").json() == {"count": 1}
    assert member.get("/api/tickets/7").status_code == 200
    assert member.get("/api/tickets/unread-count").json() == {"count": 0}


def test_unread_count_is_ownership_scoped_and_foreign_reads_do_not_mark_seen(client_factory, email, upstream) -> None:
    member, member_id = member_client(client_factory, email, upstream)
    admin = as_admin(client_factory())
    assert admin.post("/api/admin/tickets/7/comments", json={"body": "Your update"}).status_code == 200
    assert admin.post("/api/admin/tickets/8/comments", json={"body": "Foreign update"}).status_code == 200

    def ownership_server(request):
        if request.url.path == "/tickets/8":
            return httpx.Response(404, json={"error": "No ticket 8."})
        return tickets_server(request)

    upstream.handler = ownership_server
    assert member.get("/api/tickets/unread-count").json() == {"count": 1}
    assert member.get("/api/tickets/8").status_code == 404
    assert member.get("/api/tickets/404").status_code == 404

    async def read_receipts():
        async with member.app.state.database.sessions() as session:
            return list((await session.scalars(select(AccountTicketSeen).where(
                AccountTicketSeen.account_id == member_id,
            ))).all())

    assert asyncio.run(read_receipts()) == []
    assert member.get("/api/tickets/unread-count").json() == {"count": 1}


def test_seen_receipts_are_per_account(client_factory, email, upstream) -> None:
    member, _ = member_client(client_factory, email, upstream)
    admin = as_admin(client_factory())
    assert admin.post("/api/admin/tickets/7/comments", json={"body": "Update"}).status_code == 200
    # The fake upstream deliberately returns the same ticket for both accounts.
    assert admin.get("/api/tickets/7").status_code == 200
    assert admin.get("/api/tickets/unread-count").json() == {"count": 0}
    assert member.get("/api/tickets/unread-count").json() == {"count": 1}


def test_staff_reply_arriving_during_detail_fetch_remains_unread(client_factory, email, upstream, monkeypatch) -> None:
    member, _ = member_client(client_factory, email, upstream)
    original = TicketGateway.get_own

    async def get_with_concurrent_reply(gateway, account, ticket_id):
        result = await original(gateway, account, ticket_id)
        STAFF_ACTIVITY[ticket_id] = utcnow().replace(tzinfo=timezone.utc).isoformat()
        result["ticket"]["last_staff_activity_at"] = STAFF_ACTIVITY[ticket_id]
        return result

    monkeypatch.setattr(TicketGateway, "get_own", get_with_concurrent_reply)
    detail = member.get("/api/tickets/7")
    assert detail.status_code == 200
    assert detail.json()["ticket"]["has_unread"] is True
    assert member.get("/api/tickets/unread-count").json() == {"count": 1}
    monkeypatch.setattr(TicketGateway, "get_own", original)
    assert member.get("/api/tickets/7").status_code == 200
    assert member.get("/api/tickets/unread-count").json() == {"count": 0}


def test_seen_receipts_never_move_backwards(client_factory, email, upstream) -> None:
    member, member_id = member_client(client_factory, email, upstream)

    async def reverse_order():
        async with member.app.state.database.sessions() as session:
            service = TicketUnreadService(session)
            earlier = utcnow() - timedelta(seconds=1)
            await service.reconcile({7: utcnow().isoformat()})
            await service.mark_seen(member_id, 7, utcnow())
            await service.mark_seen(member_id, 7, earlier)
            return await service.unread_ids(member_id, [7])

    assert asyncio.run(reverse_order()) == set()


def test_direct_upstream_activity_is_unread_without_any_ember_staff_request(client_factory, email, upstream):
    member, _ = member_client(client_factory, email, upstream)
    assert member.get("/api/tickets/7").status_code == 200
    # Changes through the MCP tool or another client still reach list/count.
    STAFF_ACTIVITY[7] = utcnow().replace(tzinfo=timezone.utc).astimezone(
        timezone(timedelta(hours=8)),
    ).isoformat()
    assert member.get("/api/tickets/unread-count").json() == {"count": 1}
    assert member.get("/api/tickets").json()["tickets"][0]["has_unread"] is True
    assert "last_staff_activity_at" not in member.get("/api/tickets").json()["tickets"][0]
    assert member.get("/api/tickets/7").json()["ticket"]["has_unread"] is False
    assert member.get("/api/tickets/unread-count").json() == {"count": 0}


def test_reporter_lists_and_badges_request_all_owned_tickets(client_factory, email, upstream):
    member, _ = member_client(client_factory, email, upstream)
    timestamp = utcnow().replace(tzinfo=timezone.utc).isoformat()

    def many_tickets(request):
        if request.method == "GET" and request.url.path == "/tickets":
            tickets = [{**TICKET, "id": index, "last_staff_activity_at": timestamp} for index in range(1, 122)]
            return httpx.Response(200, json={"tickets": tickets if request.url.params.get("all") == "1" else tickets[:100]})
        return tickets_server(request)

    upstream.handler = many_tickets
    assert len(member.get("/api/tickets").json()["tickets"]) == 121
    assert member.get("/api/tickets/unread-count").json() == {"count": 121}


@pytest.mark.parametrize("method,path,payload", [
    ("post", "/api/tickets", {"type": "bug", "title": "test", "description": "details"}),
    ("get", "/api/tickets/7", None),
    ("post", "/api/tickets/7/comments", {"body": "More info"}),
    ("post", "/api/tickets/7/close", {}),
])
def test_reporter_responses_strip_private_ticket_and_comment_fields(
    client_factory, email, upstream, method, path, payload,
) -> None:
    member, _ = member_client(client_factory, email, upstream)
    comment = {"id": 1, "ticket_id": 7, "author": "support", "author_role": "staff", "body": "Reply",
               "created_at": TICKET["created_at"]}

    def private_server(request):
        result = {"ticket": {**TICKET, "comments": [{**comment, "private_context": "hidden"}]}, "staff_secret": "hidden"}
        if request.url.path == "/tickets":
            result.update(duplicate=False, group_size=2)
        return httpx.Response(200, json=result)

    upstream.handler = private_server
    response = getattr(member, method)(path, **({"json": payload} if payload is not None else {}))
    assert response.status_code in (200, 201)
    result = response.json()
    expected = {**REPORTER_TICKET, "comments": [comment]}
    if method == "get":
        expected["has_unread"] = False
    assert result["ticket"] == expected
    assert "staff_secret" not in result


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "bug", "title": "t", "description": "d", "reporter": "mallory"},
        {"type": "bug", "title": "t", "description": "d", "tags": ["email"]},
        {"type": "bug", "title": "t", "description": "d", "source": "ai_auto"},
        {"type": "complaint", "title": "t", "description": "d"},
        {"type": "bug", "title": "", "description": "d"},
        {"type": "bug", "title": "x" * 121, "description": "d"},
        {"type": "bug", "title": "t", "description": "x" * 4001},
        {"type": "bug", "title": "t"},
    ],
)
def test_invalid_reports_never_reach_mcp_server(client_factory, email, upstream, payload) -> None:
    member, _ = member_client(client_factory, email, upstream)

    assert member.post("/api/tickets", json=payload).status_code == 422
    assert len(upstream.requests) == 0


def test_comment_and_id_validation(client_factory, email, upstream) -> None:
    member, _ = member_client(client_factory, email, upstream)

    assert member.post("/api/tickets/7/comments", json={"body": ""}).status_code == 422
    assert member.post("/api/tickets/7/comments", json={"body": "x" * 2001}).status_code == 422
    assert member.post("/api/tickets/7/comments", json={"body": "hi", "role": "staff"}).status_code == 422
    assert member.get("/api/tickets/abc").status_code == 422
    assert member.get("/api/tickets/0").status_code == 422
    assert member.get("/api/tickets", params={"status": "done"}).status_code == 422
    assert len(upstream.requests) == 0


def test_ticket_routes_need_tickets_create(client_factory, email, upstream) -> None:
    upstream.handler = tickets_server
    member = client_factory()
    make_member(member, email)
    admin = as_admin(client_factory())
    role = role_by_name(admin, "Member")
    assert admin.delete(f"/api/admin/roles/{role['id']}/permissions/tickets.create").status_code == 200
    login(member, "alice")

    refused = member.get("/api/tickets")

    assert (refused.status_code, refused.json()["detail"]) == (403, "Missing permission: tickets.create")
    assert member.post("/api/tickets", json={"type": "bug", "title": "t", "description": "d"}).status_code == 403
    assert member.get("/api/tickets/unread-count").status_code == 403
    assert len(upstream.requests) == 0


def test_logged_out_visitors_get_401(client, upstream) -> None:
    upstream.handler = tickets_server
    assert client.get("/api/tickets").status_code == 401
    assert client.get("/api/tickets/unread-count").status_code == 401
    assert client.post("/api/tickets", json={"type": "bug", "title": "t", "description": "d"}).status_code == 401
    assert len(upstream.requests) == 0


def test_mcp_server_answers_map_to_http_errors(client_factory, email, upstream) -> None:
    member, _ = member_client(client_factory, email, upstream)

    refused = member.post("/api/tickets", json={"type": "bug", "title": "bad", "description": "d"})
    assert (refused.status_code, refused.json()["detail"]) == (400, "The title is not acceptable.")
    missing = member.get("/api/tickets/404")
    assert (missing.status_code, missing.json()["detail"]) == (404, "No ticket 404.")

    upstream.unreachable = True
    down = member.get("/api/tickets")
    assert (down.status_code, down.json()["detail"]) == (502, "mcp_server is unreachable")


# ---- staff routes ----------------------------------------------------------

def test_staff_list_forwards_filters_and_reads_everything(client, upstream) -> None:
    upstream.handler = tickets_server
    admin = as_admin(client)

    listing = admin.get(
        "/api/admin/tickets",
        params={"status": "open", "type": "bug", "tag": "email", "priority": "high", "assignee": "root",
                "group_id": 3, "possible": "true", "limit": 20},
    )

    assert listing.json() == {"tickets": [TICKET]}
    request = upstream.requests[-1]
    assert request.url.path == "/ticket-admin/tickets"
    assert dict(request.url.params) == {
        "status": "open", "type": "bug", "tag": "email", "priority": "high", "assignee": "root",
        "group_id": "3", "possible": "1", "limit": "20",
    }
    assert request.headers["x-requester-username"] == "root"
    assert admin.get("/api/admin/tickets", params={"status": "done"}).status_code == 422
    assert admin.get("/api/admin/tickets", params={"limit": 501}).status_code == 422


def test_staff_stats_is_not_read_as_a_ticket_id(client, upstream) -> None:
    upstream.handler = tickets_server
    admin = as_admin(client)

    assert admin.get("/api/admin/tickets/stats").json() == {"open": 1, "urgent": 0, "groups": 1}
    assert upstream.requests[-1].url.path == "/ticket-admin/stats"
    assert admin.get("/api/admin/tickets/7").json()["ticket"]["id"] == 7
    assert upstream.requests[-1].url.path == "/ticket-admin/tickets/7"


def test_staff_groups_list_and_priority(client, upstream) -> None:
    upstream.handler = tickets_server
    admin = as_admin(client)

    assert admin.get("/api/admin/ticket-groups", params={"tag": "email"}).json() == {"groups": [GROUP]}
    assert dict(upstream.requests[-1].url.params) == {"tag": "email", "limit": "100"}

    pinned = admin.patch("/api/admin/ticket-groups/3", json={"priority": "urgent"})
    assert pinned.status_code == 200 and pinned.json()["group"]["priority"] == "urgent"
    assert body_of(upstream.requests[-1]) == {"priority": "urgent"}
    assert admin.patch("/api/admin/ticket-groups/3", json={"pinned": False}).status_code == 200
    assert body_of(upstream.requests[-1]) == {"pinned": False}
    assert admin.patch("/api/admin/ticket-groups/3", json={"priority": "critical"}).status_code == 422
    assert admin.patch("/api/admin/ticket-groups/3", json={}).status_code == 422


def test_staff_ticket_changes_are_proxied_and_logged_without_text(client, upstream) -> None:
    upstream.handler = tickets_server
    admin = as_admin(client)

    patched = admin.patch("/api/admin/tickets/7", json={"status": "in_progress", "assignee": "root", "tags": ["config"]})
    assert patched.status_code == 200
    assert body_of(upstream.requests[-1]) == {"status": "in_progress", "assignee": "root", "tags": ["config"]}
    assert admin.post("/api/admin/tickets/7/comments", json={"body": "secret log text"}).status_code == 200
    assert admin.post("/api/admin/tickets/7/move", json={"group_id": 3}).status_code == 200
    assert body_of(upstream.requests[-1]) == {"group_id": 3}
    assert admin.post("/api/admin/tickets/7/move", json={"group_id": None}).status_code == 200
    assert admin.patch("/api/admin/ticket-groups/3", json={"priority": "urgent"}).status_code == 200
    assert admin.patch("/api/admin/ticket-groups/3", json={"pinned": False}).status_code == 200

    messages = [entry["message"] for entry in admin.get("/api/logs/action", params={"actor": admin.get("/api/auth/me").json()["id"]}).json()]
    assert messages[:6] == [
        "Changed ticket group 3 pin to off",
        "Set ticket group 3 priority to urgent (pinned)",
        "Moved ticket 7 to a new group",
        "Moved ticket 7 to group 3",
        "Commented on ticket 7",
        "Updated ticket 7 (assignee, status, tags)",
    ]
    assert not any("secret log text" in message for message in messages)


def test_staff_request_validation(client, upstream) -> None:
    upstream.handler = tickets_server
    admin = as_admin(client)

    assert admin.patch("/api/admin/tickets/7", json={"status": "done"}).status_code == 422
    assert admin.patch("/api/admin/tickets/7", json={"priority": "critical"}).status_code == 422
    assert admin.patch("/api/admin/tickets/7", json={"reporter": "x"}).status_code == 422
    assert admin.patch("/api/admin/tickets/7", json={"tags": ["a", "b", "c", "d", "e", "f"]}).status_code == 422
    assert admin.patch("/api/admin/tickets/7", json={}).status_code == 422
    assert admin.post("/api/admin/tickets/7/move", json={}).status_code == 422
    assert admin.post("/api/admin/tickets/7/move", json={"group_id": 0}).status_code == 422
    assert admin.post("/api/admin/tickets/7/comments", json={"body": ""}).status_code == 422
    assert len(upstream.requests) == 0


def test_failed_staff_change_is_not_logged(client, upstream) -> None:
    upstream.handler = tickets_server
    admin = as_admin(client)

    assert admin.patch("/api/admin/tickets/404", json={"status": "closed"}).status_code == 404
    assert upstream.requests[-1].url.path == "/ticket-admin/tickets/404"
    assert admin.post("/api/admin/tickets/404/comments", json={"body": "retry"}).status_code == 404

    async def activities():
        async with client.app.state.database.sessions() as session:
            return list((await session.scalars(select(TicketStaffActivity))).all())

    assert asyncio.run(activities()) == []
    messages = [entry["message"] for entry in admin.get("/api/logs/action", params={"actor": admin.get("/api/auth/me").json()["id"]}).json()]
    assert not any("ticket 404" in message for message in messages)


def test_staff_routes_need_tickets_manage_and_own_routes_need_create(client_factory, email, upstream) -> None:
    upstream.handler = tickets_server
    member, _ = member_client(client_factory, email, upstream)
    for method, path in [("get", "/api/admin/tickets"), ("get", "/api/admin/tickets/stats"),
                         ("get", "/api/admin/tickets/7"), ("get", "/api/admin/ticket-groups")]:
        refused = getattr(member, method)(path)
        assert (refused.status_code, refused.json()["detail"]) == (403, "Missing permission: tickets.manage")
    assert member.patch("/api/admin/tickets/7", json={"status": "closed"}).status_code == 403
    assert member.patch("/api/admin/ticket-groups/3", json={"priority": "low"}).status_code == 403
    assert len(upstream.requests) == 0


def test_manage_without_create_can_triage_but_not_file(client_factory, email, upstream) -> None:
    upstream.handler = tickets_server
    client = client_factory()
    limited_account(client, email, "tickets.manage")

    assert client.get("/api/admin/tickets").status_code == 200
    assert client.get("/api/tickets").status_code == 403
    assert client.post("/api/tickets", json={"type": "bug", "title": "t", "description": "d"}).status_code == 403


def test_staff_routes_report_an_unreachable_mcp_server(client, upstream) -> None:
    admin = as_admin(client)
    upstream.unreachable = True

    down = admin.get("/api/admin/tickets")

    assert (down.status_code, down.json()["detail"]) == (502, "mcp_server is unreachable")
