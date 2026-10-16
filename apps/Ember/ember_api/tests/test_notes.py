"""/api/notes: private per-account notes kept in db_gateway (FakeDbGateway here)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.services.db_gateway import DbGatewayUnavailable
from src.services.notes import MAX_NOTES
from tests.conftest import FakeDbGateway, FakeEmailSender
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/notes"


def add(client: TestClient, title: str = "Groceries", body: str = "milk") -> dict:
    response = client.post(URL, json={"title": title, "body": body})
    assert response.status_code == 201, response.text
    return response.json()


def test_needs_login(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"title": "x"}).status_code == 401
    assert client.get(f"{URL}/{'a' * 32}").status_code == 401
    assert client.put(f"{URL}/{'a' * 32}", json={"title": "x"}).status_code == 401
    assert client.delete(f"{URL}/{'a' * 32}").status_code == 401


def test_unverified_account_is_refused(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email, "alice", verify=False)
    login(client, "alice")

    assert client.get(URL).status_code == 403


def test_create_read_update_delete(client: TestClient) -> None:
    as_admin(client)
    assert client.get(URL).json() == []

    note = add(client)
    assert set(note) == {"id", "title", "body", "created_at", "updated_at"}
    assert (note["title"], note["body"]) == ("Groceries", "milk")
    assert client.get(f"{URL}/{note['id']}").json() == note

    changed = client.put(f"{URL}/{note['id']}", json={"title": "Shopping", "body": "milk, eggs"})
    assert changed.status_code == 200
    assert (changed.json()["title"], changed.json()["body"]) == ("Shopping", "milk, eggs")
    assert changed.json()["created_at"] == note["created_at"]
    assert client.get(URL).json() == [changed.json()]

    assert client.delete(f"{URL}/{note['id']}").status_code == 204
    assert client.get(f"{URL}/{note['id']}").status_code == 404
    assert client.delete(f"{URL}/{note['id']}").status_code == 404
    assert client.get(URL).json() == []


def test_list_is_newest_updated_first(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_admin(client)
    first, second = add(client, "first"), add(client, "second")
    # Same-second timestamps: set them apart in the store.
    for note, stamp in ((first, "2026-01-02T00:00:00"), (second, "2026-01-01T00:00:00")):
        db_gateway.records[("notes", note["id"])]["updated_at"] = stamp

    assert [n["title"] for n in client.get(URL).json()] == ["first", "second"]


def test_title_is_trimmed_and_required_and_limits(client: TestClient) -> None:
    as_admin(client)

    assert add(client, "  padded  ")["title"] == "padded"
    assert client.post(URL, json={"title": "   "}).status_code == 422
    assert client.post(URL, json={}).status_code == 422
    assert client.post(URL, json={"title": "x" * 201}).status_code == 422
    assert client.post(URL, json={"title": "ok", "body": "x" * 20_001}).status_code == 422
    assert client.post(URL, json={"title": "ok", "body": "x" * 20_000}).status_code == 201
    assert client.post(URL, json={"title": "ok"}).json()["body"] == ""


def test_another_account_cannot_see_or_touch_a_note(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email, "alice")
    make_member(client, email, "bob")
    login(client, "alice")
    note = add(client, "alice's secret")
    client.post("/api/auth/logout", json={})

    login(client, "bob")
    assert client.get(URL).json() == []
    assert client.get(f"{URL}/{note['id']}").status_code == 404
    assert client.put(f"{URL}/{note['id']}", json={"title": "mine now"}).status_code == 404
    assert client.delete(f"{URL}/{note['id']}").status_code == 404
    client.post("/api/auth/logout", json={})

    login(client, "alice")
    assert client.get(f"{URL}/{note['id']}").json()["title"] == "alice's secret"


@pytest.mark.parametrize("note_id", ["../etc", "nope", "A" * 32, "a" * 31, "a" * 33])
def test_malformed_ids_are_not_found(client: TestClient, note_id: str) -> None:
    as_admin(client)

    assert client.get(f"{URL}/{note_id}").status_code == 404


def test_per_account_cap(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_admin(client)
    owner = uids(client)["root"]
    for i in range(MAX_NOTES):
        key = f"{i:032x}"
        db_gateway.records[("notes", key)] = {
            "id": key, "owner": owner, "title": "t", "body": "", "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

    full = client.post(URL, json={"title": "one too many"})

    assert full.status_code == 409
    assert str(MAX_NOTES) in full.json()["detail"]


def test_storage_down_gives_503_and_core_still_works(client: TestClient, db_gateway: FakeDbGateway, monkeypatch) -> None:
    as_admin(client)

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("db_gateway is not reachable")

    for method in ("get", "put", "delete", "query"):
        monkeypatch.setattr(db_gateway, method, down)

    for response in (
        client.get(URL),
        client.post(URL, json={"title": "x"}),
        client.get(f"{URL}/{'a' * 32}"),
        client.put(f"{URL}/{'a' * 32}", json={"title": "x"}),
        client.delete(f"{URL}/{'a' * 32}"),
    ):
        assert response.status_code == 503
        assert response.json()["detail"] == "Notes storage is unavailable"
    assert client.get("/api/auth/me").status_code == 200  # the rest of ember_api is unaffected


def test_changes_are_audited_without_note_text(client: TestClient) -> None:
    as_admin(client)
    note = add(client, "very private title", "very private body")
    client.put(f"{URL}/{note['id']}", json={"title": "t2"})
    client.delete(f"{URL}/{note['id']}")

    root = client.get("/api/auth/me").json()["id"]
    entries = client.get("/api/logs/action", params={"actor": str(root)}).json()
    messages = [e["message"] for e in entries]
    for line in ("Created a note", "Edited a note", "Deleted a note"):
        assert line in messages
    assert "very private" not in str(entries)


def test_deleting_an_account_removes_only_its_notes(
    client: TestClient, email: FakeEmailSender, db_gateway: FakeDbGateway
) -> None:
    alice = make_member(client, email, "alice")
    make_member(client, email, "bob")
    login(client, "alice")
    add(client, "a1"), add(client, "a2")
    client.post("/api/auth/logout", json={})
    login(client, "bob")
    add(client, "b1")
    client.post("/api/auth/logout", json={})
    assert len(db_gateway.records) == 3

    as_admin(client)
    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [d["title"] for d in db_gateway.records.values()] == ["b1"]


def test_failed_purge_never_blocks_account_deletion(
    client: TestClient, email: FakeEmailSender, db_gateway: FakeDbGateway, monkeypatch
) -> None:
    alice = make_member(client, email, "alice")
    login(client, "alice")
    add(client)
    client.post("/api/auth/logout", json={})

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("db_gateway is not reachable")

    monkeypatch.setattr(db_gateway, "query", down)
    as_admin(client)

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204
    assert "alice" not in uids(client)
