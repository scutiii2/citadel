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
    assert set(note) == {"id", "title", "body", "tags", "agent_readable", "last_editor", "created_at", "updated_at"}
    assert (note["title"], note["body"]) == ("Groceries", "milk")
    assert (note["tags"], note["agent_readable"], note["last_editor"]) == ([], False, "user")
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


def test_tags_are_cleaned_and_stored(client: TestClient) -> None:
    as_admin(client)

    note = client.post(URL, json={"title": "t", "tags": [" Work ", "home", "work", "to-do_1"]}).json()

    assert note["tags"] == ["work", "home", "to-do_1"]
    assert client.get(f"{URL}/{note['id']}").json()["tags"] == ["work", "home", "to-do_1"]
    changed = client.put(f"{URL}/{note['id']}", json={"title": "t", "tags": ["home"]}).json()
    assert changed["tags"] == ["home"]
    assert client.put(f"{URL}/{note['id']}", json={"title": "t"}).json()["tags"] == []  # PUT replaces


@pytest.mark.parametrize(
    "tags",
    [[""], ["   "], ["two words"], ["x" * 31], ["-lead"], ["ünï"], ["a/b"], [f"t{i}" for i in range(11)], [1], "work"],
)
def test_bad_tags_are_refused(client: TestClient, tags) -> None:
    as_admin(client)

    assert client.post(URL, json={"title": "t", "tags": tags}).status_code == 422


def test_tag_limits_are_allowed_at_the_edge(client: TestClient) -> None:
    as_admin(client)

    tags = ["x" * 30] + [f"t{i}" for i in range(9)]

    assert client.post(URL, json={"title": "t", "tags": tags}).status_code == 201


def test_tag_list_counts_only_the_accounts_own_notes(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email, "alice")
    make_member(client, email, "bob")
    login(client, "alice")
    assert client.get(f"{URL}/tags").json() == []
    client.post(URL, json={"title": "1", "tags": ["work", "home"]})
    client.post(URL, json={"title": "2", "tags": ["work"]})
    client.post(URL, json={"title": "3"})
    client.post("/api/auth/logout", json={})
    login(client, "bob")
    client.post(URL, json={"title": "b", "tags": ["secret"]})
    client.post("/api/auth/logout", json={})

    login(client, "alice")

    assert client.get(f"{URL}/tags").json() == [{"tag": "work", "count": 2}, {"tag": "home", "count": 1}]


def test_agent_flag_defaults_off_and_is_set_and_cleared(client: TestClient) -> None:
    as_admin(client)

    note = add(client)
    assert note["agent_readable"] is False
    on = client.put(f"{URL}/{note['id']}", json={"title": "t", "agent_readable": True}).json()
    assert on["agent_readable"] is True
    assert client.get(f"{URL}/{note['id']}").json()["agent_readable"] is True
    off = client.put(f"{URL}/{note['id']}", json={"title": "t", "agent_readable": False}).json()
    assert off["agent_readable"] is False
    assert client.post(URL, json={"title": "t", "agent_readable": "yes please"}).status_code == 422


def test_a_note_saved_before_tags_existed_reads_as_untagged_and_locked(
    client: TestClient, db_gateway: FakeDbGateway
) -> None:
    as_admin(client)
    owner = uids(client)["root"]
    key = "1" * 32
    db_gateway.records[("notes", key)] = {
        "id": key, "owner": owner, "title": "old", "body": "b",
        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
    }

    old = client.get(f"{URL}/{key}").json()

    assert (old["tags"], old["agent_readable"]) == ([], False)
    assert client.get(f"{URL}/tags").json() == []


def put_agent_note(db_gateway: FakeDbGateway, client: TestClient, key: str = "a" * 32, **extra) -> str:
    """A note as mcp_server's notes tools store it: shared, last edited by an agent."""
    db_gateway.records[("notes", key)] = {
        "id": key, "owner": uids(client)["root"], "title": "From an agent", "body": "Arrival", "tags": ["movies"],
        "agent_readable": True, "last_editor": "agent", "created_at": "2026-02-01T10:00:00",
        "updated_at": "2026-02-01T10:00:00", **extra,
    }
    return key


def test_a_note_written_by_an_agent_says_so_and_a_page_save_takes_it_back(
    client: TestClient, db_gateway: FakeDbGateway
) -> None:
    as_admin(client)
    key = put_agent_note(db_gateway, client)

    assert client.get(f"{URL}/{key}").json()["last_editor"] == "agent"
    assert [n["last_editor"] for n in client.get(URL).json()] == ["agent"]

    saved = client.put(f"{URL}/{key}", json={"title": "Mine now", "body": "Arrival, Primer", "tags": ["movies"], "agent_readable": True})

    assert saved.status_code == 200
    assert saved.json()["last_editor"] == "user"
    assert client.get(f"{URL}/{key}").json()["last_editor"] == "user"
    assert db_gateway.records[("notes", key)]["last_editor"] == "user"


def test_notes_made_on_the_page_and_older_notes_read_as_written_by_the_user(
    client: TestClient, db_gateway: FakeDbGateway
) -> None:
    as_admin(client)
    made = add(client)
    old_key = "b" * 32
    db_gateway.records[("notes", old_key)] = {
        "id": old_key, "owner": uids(client)["root"], "title": "old", "body": "", "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",  # no tags, no flag, no last_editor
    }

    assert made["last_editor"] == "user"
    assert db_gateway.records[("notes", made["id"])]["last_editor"] == "user"
    assert client.get(f"{URL}/{old_key}").json()["last_editor"] == "user"


def save(client: TestClient, key: str, **fields):
    return client.put(f"{URL}/{key}", json={"title": "t", "body": "mine", **fields})


def test_a_save_with_the_version_it_opened_goes_through(client: TestClient) -> None:
    as_admin(client)
    note = add(client)

    saved = save(client, note["id"], expected_updated_at=note["updated_at"])

    assert saved.status_code == 200 and saved.json()["body"] == "mine"
    # The next save must name the new version, not the old one.
    again = save(client, note["id"], body="again", expected_updated_at=saved.json()["updated_at"])
    assert again.status_code == 200 and again.json()["body"] == "again"


def test_a_save_after_an_agent_changed_the_note_is_refused_and_changes_nothing(
    client: TestClient, db_gateway: FakeDbGateway
) -> None:
    as_admin(client)
    key = put_agent_note(db_gateway, client)  # opened at updated_at 2026-02-01T10:00:00 ...
    opened = client.get(f"{URL}/{key}").json()
    db_gateway.records[("notes", key)].update(body="Arrival, Primer", updated_at="2026-02-01T10:05:00")  # ... then an agent writes

    refused = save(client, key, expected_updated_at=opened["updated_at"])

    assert refused.status_code == 412
    assert refused.json()["detail"] == "This note changed since you opened it"
    stored = db_gateway.records[("notes", key)]
    assert (stored["body"], stored["updated_at"], stored["last_editor"]) == ("Arrival, Primer", "2026-02-01T10:05:00", "agent")


def test_the_refused_save_can_be_repeated_with_the_newer_version_to_overwrite(
    client: TestClient, db_gateway: FakeDbGateway
) -> None:
    as_admin(client)
    key = put_agent_note(db_gateway, client)
    db_gateway.records[("notes", key)]["updated_at"] = "2026-02-01T10:05:00"

    assert save(client, key, expected_updated_at="2026-02-01T10:00:00").status_code == 412
    current = client.get(f"{URL}/{key}").json()
    forced = save(client, key, expected_updated_at=current["updated_at"])

    assert forced.status_code == 200 and forced.json()["body"] == "mine" and forced.json()["last_editor"] == "user"


def test_a_save_that_names_no_version_always_goes_through(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_admin(client)
    key = put_agent_note(db_gateway, client)

    assert save(client, key).status_code == 200


def test_a_refused_save_is_not_audited_as_an_edit(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_admin(client)
    key = put_agent_note(db_gateway, client)
    save(client, key, expected_updated_at="1999-01-01T00:00:00")

    root = client.get("/api/auth/me").json()["id"]
    messages = [e["message"] for e in client.get("/api/logs/action", params={"actor": str(root)}).json()]

    assert "Edited a note" not in messages


def test_the_version_check_does_not_reveal_another_accounts_note(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email, "alice")
    make_member(client, email, "bob")
    login(client, "alice")
    note = add(client)
    client.post("/api/auth/logout", json={})
    login(client, "bob")

    assert save(client, note["id"], expected_updated_at=note["updated_at"]).status_code == 404
    assert save(client, note["id"], expected_updated_at="wrong").status_code == 404


@pytest.mark.parametrize("value", [5, "x" * 65, ["a"]])
def test_a_malformed_version_is_a_validation_error(client: TestClient, value) -> None:
    as_admin(client)
    note = add(client)

    assert save(client, note["id"], expected_updated_at=value).status_code == 422


def test_creating_ignores_a_version(client: TestClient) -> None:
    as_admin(client)

    assert client.post(URL, json={"title": "t", "expected_updated_at": "whatever"}).status_code == 201


def test_an_unknown_last_editor_value_reads_as_the_user(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_admin(client)
    key = put_agent_note(db_gateway, client, last_editor="somebody else")

    assert client.get(f"{URL}/{key}").json()["last_editor"] == "user"


def test_the_page_cannot_claim_an_agent_edit(client: TestClient) -> None:
    as_admin(client)
    note = client.post(URL, json={"title": "t", "last_editor": "agent"}).json()

    assert note["last_editor"] == "user"
    assert client.put(f"{URL}/{note['id']}", json={"title": "t", "last_editor": "agent"}).json()["last_editor"] == "user"


def test_agent_access_changes_are_audited_only_when_the_switch_flips(client: TestClient) -> None:
    as_admin(client)
    note = add(client, "very private title", "very private body")
    client.put(f"{URL}/{note['id']}", json={"title": "t", "agent_readable": False})  # no change
    client.put(f"{URL}/{note['id']}", json={"title": "t", "agent_readable": True})
    client.put(f"{URL}/{note['id']}", json={"title": "t", "agent_readable": True})  # no change
    client.put(f"{URL}/{note['id']}", json={"title": "t", "agent_readable": False})
    client.post(URL, json={"title": "shared from the start", "agent_readable": True})

    root = client.get("/api/auth/me").json()["id"]
    entries = client.get("/api/logs/action", params={"actor": str(root)}).json()
    messages = [e["message"] for e in entries]

    assert messages.count("Let agents read a note") == 2
    assert messages.count("Stopped agents reading a note") == 1
    assert "very private" not in str(entries)


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
