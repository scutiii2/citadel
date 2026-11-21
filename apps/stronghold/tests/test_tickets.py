"""Ticket HTTP contracts, ownership, staff activity and read receipts."""

import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient

from src.clock import utcnow
from src.tickets.unread import TicketUnread
from tests.auth_helpers import identity
from tests.conftest import FakeDbGateway
from tests.helpers import action_messages, as_admin, login, uid_of


def as_member(client: TestClient, name: str = "alice") -> None:
    login(client, name)


def as_staff(client: TestClient) -> None:
    as_admin(client)


def file_ticket(client: TestClient, title="Email fails", **extra):
    body = {"type": "bug", "title": title, "description": "It does not send", **extra}
    return client.post("/tickets", json=body)


def test_a_member_files_and_follows_only_their_own_tickets(client: TestClient) -> None:
    as_member(client, "alice")
    created = file_ticket(client)
    assert created.status_code == 201
    ticket = created.json()["ticket"]
    assert ticket["title"] == "Email fails" and "owner" not in ticket and "tags" not in ticket and "effective_priority" not in ticket
    assert [t["id"] for t in client.get("/tickets").json()["tickets"]] == [ticket["id"]]
    as_member(client, "bob")
    assert client.get("/tickets").json()["tickets"] == []
    assert client.get(f"/tickets/{ticket['id']}").status_code == 404
    assert client.post(f"/tickets/{ticket['id']}/comments", json={"body": "hi"}).status_code == 404


def test_a_member_cannot_name_the_reporter_the_source_or_the_tags(client: TestClient) -> None:
    as_member(client)
    for extra in ({"source": "ai_auto"}, {"tags": ["x"]}, {"reporter": "root"}):
        assert file_ticket(client, **extra).status_code == 422


def test_a_bad_report_is_a_400_in_words_and_a_malformed_one_a_422(client: TestClient) -> None:
    as_member(client)
    blank = file_ticket(client, title=" ")
    assert blank.status_code == 400 and "title is required" in blank.json()["detail"]
    too_long = client.post("/tickets", json={"type": "bug", "title": "t", "description": "x" * 4001})
    assert too_long.status_code == 422


def test_reporter_comments_close_and_reopen(client: TestClient, platform) -> None:
    as_member(client)
    ticket_id = file_ticket(client).json()["ticket"]["id"]
    commented = client.post(f"/tickets/{ticket_id}/comments", json={"body": "more info"})
    assert commented.json()["ticket"]["comments"][0]["body"] == "more info"
    assert client.post(f"/tickets/{ticket_id}/reopen").status_code == 400
    assert client.post(f"/tickets/{ticket_id}/close").json()["ticket"]["status"] == "closed"
    assert client.post(f"/tickets/{ticket_id}/reopen").json()["ticket"]["status"] == "open"
    assert any("Reopened ticket" in message for message in action_messages(client))


def test_staff_see_everything_change_it_and_the_log_names_no_text(client: TestClient) -> None:
    as_member(client, "alice")
    ticket_id = file_ticket(client, title="Secret title").json()["ticket"]["id"]
    as_staff(client)
    listed = client.get("/ticket-admin/tickets").json()["tickets"]
    assert listed[0]["owner"] == uid_of("alice") and listed[0]["effective_priority"] == "normal"
    patched = client.patch(f"/ticket-admin/tickets/{ticket_id}", json={"status": "in_progress", "priority": "high", "tags": ["email"]})
    assert patched.json()["ticket"]["status"] == "in_progress"
    assert client.post(f"/ticket-admin/tickets/{ticket_id}/comments", json={"body": "On it"}).status_code == 200
    assert client.patch(f"/ticket-admin/tickets/{ticket_id}", json={}).status_code == 422
    assert client.get("/ticket-admin/tickets/404").status_code == 404
    assert client.get("/ticket-admin/stats").json()["open"] == 1
    assert [g["id"] for g in client.get("/ticket-admin/groups").json()["groups"]] == [1]
    messages = " ".join(action_messages(client))
    assert "Secret title" not in messages and "On it" not in messages and f"ticket {ticket_id}" in messages


def test_a_staff_reply_is_unread_for_the_reporter_until_it_is_opened(client: TestClient) -> None:
    as_member(client, "alice")
    ticket_id = file_ticket(client).json()["ticket"]["id"]
    assert client.get("/tickets/unread-count").json() == {"count": 0}
    as_staff(client)
    client.post(f"/ticket-admin/tickets/{ticket_id}/comments", json={"body": "Hello"})
    as_member(client, "alice")
    assert client.get("/tickets/unread-count").json() == {"count": 1}
    assert client.get("/tickets").json()["tickets"][0]["has_unread"] is True
    assert client.get(f"/tickets/{ticket_id}").json()["ticket"]["has_unread"] is False
    assert client.get("/tickets/unread-count").json() == {"count": 0}


def test_staff_move_and_group_priority_use_the_service(client: TestClient) -> None:
    as_member(client)
    first = file_ticket(client).json()["ticket"]
    second = file_ticket(client, title="Other").json()["ticket"]
    as_staff(client)
    first = client.get(f"/ticket-admin/tickets/{first['id']}").json()["ticket"]
    moved = client.post(f"/ticket-admin/tickets/{second['id']}/move", json={"group_id": first["group_id"]})
    assert moved.json()["ticket"]["group_id"] == first["group_id"]
    assert client.post(f"/ticket-admin/tickets/{second['id']}/move", json={"group_id": 77}).status_code == 404
    group = client.patch(f"/ticket-admin/groups/{first['group_id']}", json={"priority": "urgent"})
    assert group.json()["group"]["priority"] == "urgent" and group.json()["group"]["priority_pinned"] is True
    assert client.patch(f"/ticket-admin/groups/{first['group_id']}", json={}).status_code == 422


def test_staff_ticket_settings_are_read_validated_and_saved(client: TestClient) -> None:
    as_staff(client)
    document = client.get("/ticket-admin/settings").json()
    assert "tags" in document and document["auto_hourly_cap"] == 5
    assert client.patch("/ticket-admin/settings", json={"tags": {}}).status_code == 400
    saved = client.patch("/ticket-admin/settings", json={"auto_hourly_cap": 9})
    assert saved.json()["auto_hourly_cap"] == 9
    assert client.get("/ticket-admin/settings").json()["auto_hourly_cap"] == 9


def test_purging_an_account_removes_its_tickets_and_read_receipts(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_member(client, "alice")
    alice_ticket = file_ticket(client).json()["ticket"]["id"]
    assert client.get(f"/tickets/{alice_ticket}").status_code == 200
    as_member(client, "bob")
    bob_ticket = file_ticket(client, title="Bob's").json()["ticket"]["id"]
    assert client.delete(f"/tickets/accounts/{uid_of('alice')}").status_code == 204
    assert ("ticket_seen", f"{uid_of('alice')}:{alice_ticket}") not in db_gateway.records
    as_staff(client)
    assert [t["id"] for t in client.get("/ticket-admin/tickets").json()["tickets"]] == [bob_ticket]



def test_tickets_need_the_requester_identity(client):
    assert client.get("/tickets", headers=identity(uid="")).status_code == 400
    assert client.get("/ticket-admin/stats", headers=identity(uid="")).status_code == 400


def test_comment_and_id_validation(client):
    as_member(client)
    ticket_id = file_ticket(client).json()["ticket"]["id"]
    assert client.post(f"/tickets/{ticket_id}/comments", json={"body": ""}).status_code == 422
    assert client.post(f"/tickets/{ticket_id}/comments", json={"body": " "}).status_code == 400
    assert client.get("/tickets/0").status_code == 422
    assert client.get("/tickets/nope").status_code == 422


def test_staff_request_validation(client):
    as_staff(client)
    assert client.get("/ticket-admin/tickets", params={"status": "done"}).status_code == 422
    assert client.post("/ticket-admin/tickets/1/move", json={"group_id": 0}).status_code == 422
    assert client.patch("/ticket-admin/groups/1", json={"priority": "invalid"}).status_code == 422
    assert client.patch("/ticket-admin/tickets/1", json={"assignee": 123}).status_code == 422


def test_reporter_responses_strip_private_ticket_and_comment_fields(client):
    as_member(client)
    ticket_id = file_ticket(client).json()["ticket"]["id"]
    as_staff(client)
    staff = client.post(f"/ticket-admin/tickets/{ticket_id}/comments", json={"body": "staff reply"}).json()["ticket"]
    as_member(client)
    detail = client.get(f"/tickets/{ticket_id}").json()["ticket"]
    assert set(detail) == {"id", "type", "title", "description", "status", "created_at",
                           "updated_at", "closed_at", "comments", "has_unread"}
    assert set(detail["comments"][0]) == {"id", "ticket_id", "author", "author_role", "body", "created_at"}
    assert "context" in staff and staff["owner"] == uid_of("alice")


def test_foreign_reads_do_not_mark_seen(client, db_gateway):
    as_member(client, "alice")
    first = file_ticket(client).json()["ticket"]["id"]
    as_member(client, "bob")
    second = file_ticket(client).json()["ticket"]["id"]
    as_staff(client)
    client.post(f"/ticket-admin/tickets/{first}/comments", json={"body": "Update"})
    as_member(client, "alice")
    assert client.get(f"/tickets/{second}").status_code == 404
    assert client.get("/tickets/999").status_code == 404
    assert not any(collection == "ticket_seen" for collection, _ in db_gateway.records)
    assert client.get("/tickets/unread-count").json() == {"count": 1}


def test_seen_receipts_are_per_account(db_gateway):
    async def check():
        unread = TicketUnread(db_gateway)
        activity = {7: utcnow().isoformat()}
        await unread.mark_seen("u-1", 7, utcnow() + timedelta(seconds=1))
        assert await unread.unread_ids("u-1", activity) == set()
        assert await unread.unread_ids("u-2", activity) == {7}

    asyncio.run(check())


def test_staff_reply_arriving_during_detail_fetch_remains_unread(client, monkeypatch):
    as_member(client)
    ticket_id = file_ticket(client).json()["ticket"]["id"]
    service = client.app.state.tickets
    original = type(service).get_ticket

    async def get_with_concurrent_reply(tickets, number, *, owner=None):
        await tickets.add_comment(number, author="root", role="staff", body="Concurrent reply")
        return await original(tickets, number, owner=owner)

    with monkeypatch.context() as patch:
        patch.setattr(type(service), "get_ticket", get_with_concurrent_reply)
        assert client.get(f"/tickets/{ticket_id}").json()["ticket"]["has_unread"] is True
    assert client.get("/tickets/unread-count").json() == {"count": 1}
    assert client.get(f"/tickets/{ticket_id}").json()["ticket"]["has_unread"] is False
    assert client.get("/tickets/unread-count").json() == {"count": 0}


def test_staff_filters_and_failures_keep_the_http_contract(client, platform):
    as_member(client)
    first = file_ticket(client).json()["ticket"]["id"]
    file_ticket(client, title="Second")
    as_staff(client)
    assert client.patch(f"/ticket-admin/tickets/{first}", json={"tags": ["email"], "status": "in_progress"}).status_code == 200
    response = client.get("/ticket-admin/tickets", params={"tag": "email", "status": "in_progress", "limit": 1})
    assert [ticket["id"] for ticket in response.json()["tickets"]] == [first]
    assert client.get("/ticket-admin/tickets", params={"possible": True}).json() == {"tickets": []}
    before = list(platform.actions)
    missing = client.patch("/ticket-admin/tickets/999", json={"status": "closed"})
    assert missing.status_code == 404 and missing.json() == {"detail": "No ticket 999."}
    assert platform.actions == before


def test_treasury_unavailable_is_a_503(client, db_gateway, monkeypatch):
    from src.document_store import DbGatewayUnavailable

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("storage unreachable")

    as_member(client)
    monkeypatch.setattr(db_gateway, "query", down)
    result = client.get("/tickets")
    assert result.status_code == 503 and result.json() == {"detail": "Storage is unavailable"}


def test_seen_receipts_never_move_backwards(db_gateway: FakeDbGateway) -> None:
    async def reverse_order():
        unread = TicketUnread(db_gateway)
        earlier = utcnow() - timedelta(seconds=1)
        activity = {7: utcnow().isoformat()}
        await unread.mark_seen("u-1", 7, utcnow() + timedelta(seconds=1))
        await unread.mark_seen("u-1", 7, earlier)
        return await unread.unread_ids("u-1", activity)

    assert asyncio.run(reverse_order()) == set()
