"""/tickets and /ticket-admin: Armory keeps the tickets; Stronghold scopes them to the requester and tracks what was read."""

from __future__ import annotations

from tests.auth_helpers import identity, caller, requester

import asyncio
import json
import re
from datetime import timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from src.clock import utcnow
from src.tickets.client import ArmoryTickets
from src.tickets.unread import TicketUnread
from tests.conftest import IDENTITY, FakeArmory, FakeDbGateway
from tests.helpers import action_messages, as_admin, login, uid_of

UID = IDENTITY["uid"]
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
    """Armory's ticket routes with canned answers; tests read armory.requests."""
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
        ticket_id = int(match.group(2))
        if ticket_id == 404:
            return httpx.Response(404, json={"error": "No ticket 404."})
        if match.group(1) and method in ("POST", "PATCH"):
            STAFF_ACTIVITY[ticket_id] = utcnow().replace(tzinfo=timezone.utc).isoformat()
        return httpx.Response(200, json={"ticket": {**upstream_ticket(ticket_id), "comments": []}})
    match = re.fullmatch(r"/ticket-admin/groups/(\d+)", path)
    if match and method == "PATCH":
        return httpx.Response(200, json={"group": {**GROUP, **body_of(request)}})
    return httpx.Response(404, json={"error": "no route"})


@pytest.fixture(autouse=True)
def armory_tickets(armory: FakeArmory) -> FakeArmory:
    armory.handler = tickets_server
    return armory


def as_member(client: TestClient, name: str = "alice") -> None:
    login(client, name)


def as_staff(client: TestClient) -> None:
    as_admin(client)


def test_the_client_drops_empty_filters_and_flags_possible(armory: FakeArmory) -> None:
    from src.requester import Requester

    http = httpx.AsyncClient(base_url="http://armory.test", transport=httpx.MockTransport(armory))
    tickets = ArmoryTickets(http)

    from src.citadel_auth import Caller, requester_context
    from tests import auth_helpers
    async def run():
        token = identity("u-9", "root", "root@example.com")["X-Citadel-Requester"]
        async with requester_context(auth_helpers.stack["stronghold"], Caller("portcullis"), token, "stronghold"):
            return await tickets.list_all(Requester("u-9", "root", "root@example.com"),
                                          {"status": "open", "tag": None, "possible": True, "group_id": 3})
    result = asyncio.run(run())

    assert result == {"tickets": [TICKET]}
    request = armory.requests[-1]
    assert dict(request.url.params) == {"status": "open", "possible": "1", "group_id": "3"}
    assert (requester(request)["username"], requester(request)["sub"]) == ("root", "u-9")
    assert caller(request, "armory") == "stronghold"


# ---- reporter routes -------------------------------------------------------

def test_tickets_need_the_requester_identity(client: TestClient, armory: FakeArmory) -> None:
    assert client.get("/tickets", headers=identity(uid="")).status_code == 400
    assert client.get("/ticket-admin/stats", headers=identity(uid="")).status_code == 400
    assert not armory.requests


def test_reporter_reopen_is_scoped_logged_and_keeps_staff_fields_private(client: TestClient, armory, platform) -> None:
    as_member(client)

    response = client.post("/tickets/7/reopen", json={})

    assert response.status_code == 200
    assert response.json()["ticket"]["id"] == 7 and "priority" not in response.json()["ticket"]
    assert armory.requests[-1].url.path == "/tickets/7/reopen"
    assert requester(armory.requests[-1])["username"] == "alice"
    assert platform.actions == [(uid_of("alice"), "tickets.reopen", "Reopened ticket 7")]
    assert client.post("/tickets/404/reopen", json={}).status_code == 404


def test_member_files_and_follows_own_tickets(client: TestClient, armory) -> None:
    as_member(client)

    created = client.post("/tickets", json={"type": "bug", "title": "Email fails", "description": "It does not send"})
    assert created.status_code == 201, created.text
    assert created.json() == {"ticket": REPORTER_TICKET, "duplicate": False, "group_size": 1}
    sent = armory.requests[-1]
    assert (sent.method, sent.url.path) == ("POST", "/tickets")
    assert requester(sent)["username"] == "alice"
    assert body_of(sent) == {
        "type": "bug", "title": "Email fails", "description": "It does not send", "source": "user",
        "verified_context": {"via": "portcullis", "account_id": uid_of("alice")},
    }

    assert client.get("/tickets", params={"status": "open"}).json() == {"tickets": [{**REPORTER_TICKET, "has_unread": False}]}
    assert dict(armory.requests[-1].url.params) == {"status": "open", "all": "1"}
    assert client.get("/tickets/7").json()["ticket"]["id"] == 7
    assert client.post("/tickets/7/comments", json={"body": "log attached"}).status_code == 200
    assert body_of(armory.requests[-1]) == {"body": "log attached"}
    assert client.post("/tickets/7/close", json={}).status_code == 200
    assert armory.requests[-1].url.path == "/tickets/7/close"


def test_a_repeated_report_answers_200(client: TestClient) -> None:
    as_member(client)

    response = client.post("/tickets", json={"type": "bug", "title": "dup", "description": "again"})

    assert response.status_code == 200 and response.json()["duplicate"] is True


def test_staff_replies_and_updates_are_unread_until_opened(client: TestClient) -> None:
    as_member(client)
    assert client.get("/tickets/unread-count").json() == {"count": 0}
    as_staff(client)
    assert client.post("/ticket-admin/tickets/7/comments", json={"body": "Please retry"}).status_code == 200
    as_member(client)
    assert client.get("/tickets").json()["tickets"][0]["has_unread"] is True
    assert client.get("/tickets/unread-count").json() == {"count": 1}
    assert client.get("/tickets/7").status_code == 200
    assert client.get("/tickets/unread-count").json() == {"count": 0}
    as_staff(client)
    assert client.patch("/ticket-admin/tickets/7", json={"status": "resolved"}).status_code == 200
    as_member(client)
    assert client.get("/tickets").json()["tickets"][0]["has_unread"] is True
    # Reporter replies and closing do not acknowledge an unopened staff update.
    assert client.post("/tickets/7/comments", json={"body": "Thanks"}).status_code == 200
    assert client.post("/tickets/7/close", json={}).status_code == 200
    assert client.get("/tickets/unread-count").json() == {"count": 1}
    assert client.get("/tickets/7").status_code == 200
    assert client.get("/tickets/unread-count").json() == {"count": 0}


def test_foreign_reads_do_not_mark_seen(client: TestClient, armory, db_gateway: FakeDbGateway) -> None:
    as_staff(client)
    client.post("/ticket-admin/tickets/7/comments", json={"body": "Your update"})
    client.post("/ticket-admin/tickets/8/comments", json={"body": "Foreign update"})
    as_member(client)

    def ownership_server(request):
        if request.url.path == "/tickets/8":
            return httpx.Response(404, json={"error": "No ticket 8."})
        return tickets_server(request)

    armory.handler = ownership_server
    assert client.get("/tickets/unread-count").json() == {"count": 1}
    assert client.get("/tickets/8").status_code == 404
    assert client.get("/tickets/404").status_code == 404

    assert db_gateway.records == {}
    assert client.get("/tickets/unread-count").json() == {"count": 1}


def test_seen_receipts_are_per_account(client: TestClient) -> None:
    as_staff(client)
    client.post("/ticket-admin/tickets/7/comments", json={"body": "Update"})
    # The fake Armory deliberately returns the same ticket for both accounts.
    assert client.get("/tickets/7").status_code == 200
    assert client.get("/tickets/unread-count").json() == {"count": 0}
    as_member(client)
    assert client.get("/tickets/unread-count").json() == {"count": 1}


def test_staff_reply_arriving_during_detail_fetch_remains_unread(client: TestClient, monkeypatch) -> None:
    as_member(client)
    original = ArmoryTickets.get_own

    async def get_with_concurrent_reply(tickets, who, ticket_id):
        result = await original(tickets, who, ticket_id)
        STAFF_ACTIVITY[ticket_id] = utcnow().replace(tzinfo=timezone.utc).isoformat()
        result["ticket"]["last_staff_activity_at"] = STAFF_ACTIVITY[ticket_id]
        return result

    monkeypatch.setattr(ArmoryTickets, "get_own", get_with_concurrent_reply)
    detail = client.get("/tickets/7")
    assert detail.status_code == 200
    assert detail.json()["ticket"]["has_unread"] is True
    assert client.get("/tickets/unread-count").json() == {"count": 1}
    monkeypatch.setattr(ArmoryTickets, "get_own", original)
    assert client.get("/tickets/7").status_code == 200
    assert client.get("/tickets/unread-count").json() == {"count": 0}


def test_seen_receipts_never_move_backwards(db_gateway: FakeDbGateway) -> None:
    async def reverse_order():
        unread = TicketUnread(db_gateway)
        earlier = utcnow() - timedelta(seconds=1)
        activity = {7: utcnow().isoformat()}
        await unread.mark_seen("u-1", 7, utcnow() + timedelta(seconds=1))
        await unread.mark_seen("u-1", 7, earlier)
        return await unread.unread_ids("u-1", activity)

    assert asyncio.run(reverse_order()) == set()


def test_direct_upstream_activity_is_unread_without_any_staff_request(client: TestClient) -> None:
    as_member(client)
    assert client.get("/tickets/7").status_code == 200
    # Changes through the MCP tool or another client still reach list/count (here: a time with an offset).
    STAFF_ACTIVITY[7] = utcnow().replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).isoformat()
    assert client.get("/tickets/unread-count").json() == {"count": 1}
    assert client.get("/tickets").json()["tickets"][0]["has_unread"] is True
    assert "last_staff_activity_at" not in client.get("/tickets").json()["tickets"][0]
    assert client.get("/tickets/7").json()["ticket"]["has_unread"] is False
    assert client.get("/tickets/unread-count").json() == {"count": 0}


def test_reporter_lists_and_badges_request_all_owned_tickets(client: TestClient, armory) -> None:
    as_member(client)
    timestamp = utcnow().replace(tzinfo=timezone.utc).isoformat()

    def many_tickets(request):
        if request.method == "GET" and request.url.path == "/tickets":
            tickets = [{**TICKET, "id": index, "last_staff_activity_at": timestamp} for index in range(1, 122)]
            return httpx.Response(200, json={"tickets": tickets if request.url.params.get("all") == "1" else tickets[:100]})
        return tickets_server(request)

    armory.handler = many_tickets
    assert len(client.get("/tickets").json()["tickets"]) == 121
    assert client.get("/tickets/unread-count").json() == {"count": 121}


@pytest.mark.parametrize("method,path,payload", [
    ("post", "/tickets", {"type": "bug", "title": "test", "description": "details"}),
    ("get", "/tickets/7", None),
    ("post", "/tickets/7/comments", {"body": "More info"}),
    ("post", "/tickets/7/close", {}),
])
def test_reporter_responses_strip_private_ticket_and_comment_fields(client: TestClient, armory, method, path, payload) -> None:
    as_member(client)
    comment = {"id": 1, "ticket_id": 7, "author": "support", "author_role": "staff", "body": "Reply",
               "created_at": TICKET["created_at"]}

    def private_server(request):
        result = {"ticket": {**TICKET, "comments": [{**comment, "private_context": "hidden"}]}, "staff_secret": "hidden"}
        if request.url.path == "/tickets":
            result.update(duplicate=False, group_size=2)
        return httpx.Response(200, json=result)

    armory.handler = private_server
    response = getattr(client, method)(path, **({"json": payload} if payload is not None else {}))
    assert response.status_code in (200, 201)
    result = response.json()
    expected = {**REPORTER_TICKET, "comments": [comment]}
    if method == "get":
        expected["has_unread"] = False
    assert result["ticket"] == expected
    assert "staff_secret" not in result


@pytest.mark.parametrize("payload", [
    {"type": "bug", "title": "t", "description": "d", "reporter": "mallory"},
    {"type": "bug", "title": "t", "description": "d", "tags": ["email"]},
    {"type": "bug", "title": "t", "description": "d", "source": "ai_auto"},
    {"type": "complaint", "title": "t", "description": "d"},
    {"type": "bug", "title": "", "description": "d"},
    {"type": "bug", "title": "x" * 121, "description": "d"},
    {"type": "bug", "title": "t", "description": "x" * 4001},
    {"type": "bug", "title": "t"},
])
def test_invalid_reports_never_reach_armory(client: TestClient, armory, payload) -> None:
    assert client.post("/tickets", json=payload).status_code == 422
    assert armory.requests == []


def test_comment_and_id_validation(client: TestClient, armory) -> None:
    assert client.post("/tickets/7/comments", json={"body": ""}).status_code == 422
    assert client.post("/tickets/7/comments", json={"body": "x" * 2001}).status_code == 422
    assert client.post("/tickets/7/comments", json={"body": "hi", "role": "staff"}).status_code == 422
    assert client.get("/tickets/abc").status_code == 422
    assert client.get("/tickets/0").status_code == 422
    assert client.get("/tickets", params={"status": "done"}).status_code == 422
    assert armory.requests == []


def test_armory_answers_map_to_http_errors(client: TestClient, armory) -> None:
    as_member(client)

    refused = client.post("/tickets", json={"type": "bug", "title": "bad", "description": "d"})
    assert (refused.status_code, refused.json()["detail"]) == (400, "The title is not acceptable.")
    missing = client.get("/tickets/404")
    assert (missing.status_code, missing.json()["detail"]) == (404, "No ticket 404.")

    def unreachable(request):
        raise httpx.ConnectError("offline")

    armory.handler = unreachable
    down = client.get("/tickets")
    assert (down.status_code, down.json()["detail"]) == (502, "armory is unreachable")
    armory.handler = lambda request: httpx.Response(500, json={"error": "boom"})
    assert client.get("/tickets").status_code == 502


# ---- staff routes ----------------------------------------------------------

def test_staff_list_forwards_filters_and_reads_everything(client: TestClient, armory) -> None:
    as_staff(client)

    listing = client.get("/ticket-admin/tickets", params={
        "status": "open", "type": "bug", "tag": "email", "priority": "high", "assignee": "root",
        "group_id": 3, "possible": "true", "limit": 20})

    assert listing.json() == {"tickets": [TICKET]}
    request = armory.requests[-1]
    assert request.url.path == "/ticket-admin/tickets"
    assert dict(request.url.params) == {
        "status": "open", "type": "bug", "tag": "email", "priority": "high", "assignee": "root",
        "group_id": "3", "possible": "1", "limit": "20",
    }
    assert requester(request)["username"] == "root"
    assert client.get("/ticket-admin/tickets", params={"status": "done"}).status_code == 422
    assert client.get("/ticket-admin/tickets", params={"limit": 501}).status_code == 422


def test_staff_stats_is_not_read_as_a_ticket_id(client: TestClient, armory) -> None:
    assert client.get("/ticket-admin/stats").json() == {"open": 1, "urgent": 0, "groups": 1}
    assert armory.requests[-1].url.path == "/ticket-admin/stats"
    assert client.get("/ticket-admin/tickets/7").json()["ticket"]["id"] == 7
    assert armory.requests[-1].url.path == "/ticket-admin/tickets/7"


def test_staff_groups_list_and_priority(client: TestClient, armory) -> None:
    assert client.get("/ticket-admin/groups", params={"tag": "email"}).json() == {"groups": [GROUP]}
    assert dict(armory.requests[-1].url.params) == {"tag": "email", "limit": "100"}

    pinned = client.patch("/ticket-admin/groups/3", json={"priority": "urgent"})
    assert pinned.status_code == 200 and pinned.json()["group"]["priority"] == "urgent"
    assert body_of(armory.requests[-1]) == {"priority": "urgent"}
    assert client.patch("/ticket-admin/groups/3", json={"pinned": False}).status_code == 200
    assert body_of(armory.requests[-1]) == {"pinned": False}
    assert client.patch("/ticket-admin/groups/3", json={"priority": "critical"}).status_code == 422
    assert client.patch("/ticket-admin/groups/3", json={}).status_code == 422


def test_staff_ticket_changes_are_proxied_and_logged_without_text(client: TestClient, armory, platform) -> None:
    as_staff(client)

    patched = client.patch("/ticket-admin/tickets/7", json={"status": "in_progress", "assignee": "root", "tags": ["config"]})
    assert patched.status_code == 200
    assert body_of(armory.requests[-1]) == {"status": "in_progress", "assignee": "root", "tags": ["config"]}
    assert client.post("/ticket-admin/tickets/7/comments", json={"body": "secret log text"}).status_code == 200
    assert client.post("/ticket-admin/tickets/7/move", json={"group_id": 3}).status_code == 200
    assert body_of(armory.requests[-1]) == {"group_id": 3}
    assert client.post("/ticket-admin/tickets/7/move", json={"group_id": None}).status_code == 200
    assert client.patch("/ticket-admin/groups/3", json={"priority": "urgent"}).status_code == 200
    assert client.patch("/ticket-admin/groups/3", json={"pinned": False}).status_code == 200

    assert action_messages(client) == [
        "Updated ticket 7 (assignee, status, tags)",
        "Commented on ticket 7",
        "Moved ticket 7 to group 3",
        "Moved ticket 7 to a new group",
        "Set ticket group 3 priority to urgent (pinned)",
        "Changed ticket group 3 pin to off",
    ]
    assert {uid for uid, _action, _message in platform.actions} == {uid_of("root")}


def test_staff_request_validation(client: TestClient, armory) -> None:
    assert client.patch("/ticket-admin/tickets/7", json={"status": "done"}).status_code == 422
    assert client.patch("/ticket-admin/tickets/7", json={"priority": "critical"}).status_code == 422
    assert client.patch("/ticket-admin/tickets/7", json={"reporter": "x"}).status_code == 422
    assert client.patch("/ticket-admin/tickets/7", json={"tags": ["a", "b", "c", "d", "e", "f"]}).status_code == 422
    assert client.patch("/ticket-admin/tickets/7", json={}).status_code == 422
    assert client.post("/ticket-admin/tickets/7/move", json={}).status_code == 422
    assert client.post("/ticket-admin/tickets/7/move", json={"group_id": 0}).status_code == 422
    assert client.post("/ticket-admin/tickets/7/comments", json={"body": ""}).status_code == 422
    assert armory.requests == []


def test_failed_staff_change_is_not_logged(client: TestClient, armory, platform) -> None:
    assert client.patch("/ticket-admin/tickets/404", json={"status": "closed"}).status_code == 404
    assert armory.requests[-1].url.path == "/ticket-admin/tickets/404"
    assert client.post("/ticket-admin/tickets/404/comments", json={"body": "retry"}).status_code == 404

    assert platform.actions == []


# ---- account deletion -------------------------------------------------------

def test_purging_an_account_removes_only_its_read_receipts(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_member(client, "alice")
    client.get("/tickets/7")
    as_member(client, "bob")
    client.get("/tickets/7")

    assert client.delete(f"/tickets/accounts/{uid_of('alice')}").status_code == 204

    assert [doc["owner"] for doc in db_gateway.records.values()] == [uid_of("bob")]
    assert client.delete("/tickets/accounts/has%20space").status_code == 422
