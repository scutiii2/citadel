"""/shares: links to frozen chat snapshots, kept in Treasury, readable by anyone who holds the link."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.clock import utcnow
from src.shares import store as share_store
from tests.conftest import FakeDbGateway
from tests.helpers import as_admin, login, uid_of

CHAT = "chat-0001-aaaa"
OTHER_CHAT = "chat-0002-bbbb"
MESSAGES = [
    {"role": "user", "content": "please summarize\n\n📎 report.txt"},
    {"role": "assistant", "content": "Here you go."},
]


def share(client: TestClient, chat_id: str = CHAT, **body):
    payload = {"chat_id": chat_id, "title": "Quarterly report", "messages": MESSAGES, **body}
    return client.post("/shares", json=payload)


def read(client: TestClient, token: str):
    return client.get(f"/shares/public/{token}")


def expire(db: FakeDbGateway, share_id: int) -> None:
    for doc in db.records.values():
        if doc.get("id") == share_id:
            doc["expires_at"] = (utcnow() - timedelta(minutes=1)).isoformat()


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text)


# --- access ---------------------------------------------------------------------------------


def test_managing_links_needs_the_requester_identity(client: TestClient) -> None:
    anonymous = {"X-Requester-Uid": ""}
    assert client.post("/shares", json={"chat_id": CHAT, "title": "t", "messages": MESSAGES}, headers=anonymous).status_code == 400
    assert client.get("/shares", headers=anonymous).status_code == 400
    assert client.delete("/shares/1", headers=anonymous).status_code == 400
    assert client.post("/shares/revoke", json={"chat_ids": "all"}, headers=anonymous).status_code == 400


def test_reading_a_link_needs_no_requester(client: TestClient) -> None:
    token = share(client).json()["token"]

    assert read(client, token).status_code == 200
    assert client.get(f"/shares/public/{token}", headers={"X-Requester-Uid": ""}).status_code == 200


# --- creating -------------------------------------------------------------------------------


def test_creating_a_link_returns_the_token_once(client: TestClient) -> None:
    response = share(client)

    assert response.status_code == 201
    body = response.json()
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", body["token"])
    assert (body["chat_id"], body["title"], body["message_count"]) == (CHAT, "Quarterly report", 2)
    assert _parse(body["expires_at"]) - _parse(body["created_at"]) == timedelta(days=7)  # the default


@pytest.mark.parametrize("days", [1, 7, 30])
def test_expiry_choices(client: TestClient, days: int) -> None:
    body = share(client, expires_in_days=days).json()

    assert _parse(body["expires_at"]) - _parse(body["created_at"]) == timedelta(days=days)


def test_a_link_can_be_made_without_expiry(client: TestClient) -> None:
    body = share(client, expires_in_days=None).json()

    assert body["expires_at"] is None
    assert read(client, body["token"]).json()["expires_at"] is None


@pytest.mark.parametrize("days", [0, 2, 365, -1, "7", 7.5, "forever"])
def test_other_expiries_are_refused(client: TestClient, days) -> None:
    assert share(client, expires_in_days=days).status_code == 422
    assert client.get("/shares").json() == []


@pytest.mark.parametrize("body", [
    {"chat_id": "x", "title": "t", "messages": MESSAGES},
    {"chat_id": CHAT, "title": "t" * 121, "messages": MESSAGES},
    {"chat_id": CHAT, "title": "t", "messages": []},
    {"chat_id": CHAT, "title": "t", "messages": [{"role": "system", "content": "x"}]},
    {"chat_id": CHAT, "title": "t", "messages": [{"role": "user", "content": ""}]},
    {"chat_id": CHAT, "messages": MESSAGES},
])
def test_bad_requests_are_refused(client: TestClient, body: dict) -> None:
    assert client.post("/shares", json=body).status_code == 422
    assert client.get("/shares").json() == []


def test_every_link_gets_its_own_token(client: TestClient) -> None:
    assert len({share(client).json()["token"] for _ in range(5)}) == 5


# --- what is stored -------------------------------------------------------------------------


def test_the_token_is_not_stored_only_its_hash(client: TestClient, db_gateway: FakeDbGateway) -> None:
    body = share(client).json()

    ((collection, key), doc), = db_gateway.records.items()

    assert collection == "shared_chats" and key == hashlib.sha256(body["token"].encode()).hexdigest()
    assert body["token"] not in str(doc)


def test_lists_never_contain_a_token(client: TestClient) -> None:
    share(client)

    listed = client.get("/shares").json()

    assert len(listed) == 1 and "token" not in listed[0]
    assert set(listed[0]) == {"id", "chat_id", "title", "message_count", "created_at", "expires_at"}


# --- reading --------------------------------------------------------------------------------


def test_a_link_shows_the_snapshot_and_nothing_else(client: TestClient) -> None:
    token = share(client).json()["token"]

    shared = read(client, token).json()

    assert shared["title"] == "Quarterly report" and shared["messages"] == MESSAGES
    assert set(shared) == {"title", "messages", "created_at", "expires_at"}


def test_unknown_malformed_expired_and_revoked_links_all_look_the_same(client: TestClient, db_gateway) -> None:
    expired, revoked = share(client).json(), share(client).json()
    expire(db_gateway, expired["id"])
    assert client.delete(f"/shares/{revoked['id']}").status_code == 204

    attempts = ["A" * 43, "short", "x" * 200, "has spaces and !!", expired["token"], revoked["token"]]
    answers = [read(client, t) for t in attempts]

    assert {r.status_code for r in answers} == {404}
    assert len({r.text for r in answers}) == 1  # nothing tells the cases apart


def test_reading_an_expired_link_removes_it(client: TestClient, db_gateway: FakeDbGateway) -> None:
    made = share(client).json()
    expire(db_gateway, made["id"])

    assert read(client, made["token"]).status_code == 404

    assert db_gateway.records == {}


def test_a_link_with_no_expiry_or_a_future_one_keeps_working(client: TestClient) -> None:
    forever = share(client, expires_in_days=None).json()["token"]
    week = share(client, expires_in_days=7).json()["token"]

    assert read(client, forever).status_code == 200
    assert read(client, week).status_code == 200


# --- listing and revoking -------------------------------------------------------------------


def test_listing_is_newest_first_and_can_be_narrowed_to_one_chat(client: TestClient, monkeypatch) -> None:
    clock = [utcnow()]
    monkeypatch.setattr(share_store, "utcnow", lambda: clock[0])

    def later(seconds: int):
        clock[0] += timedelta(seconds=seconds)

    a = share(client, CHAT).json()
    later(1)
    b = share(client, OTHER_CHAT).json()
    later(1)
    c = share(client, CHAT).json()

    assert [s["id"] for s in client.get("/shares").json()] == [c["id"], b["id"], a["id"]]
    assert [s["id"] for s in client.get("/shares", params={"chat_id": CHAT}).json()] == [c["id"], a["id"]]
    assert client.get("/shares", params={"chat_id": "no way"}).status_code == 422


def test_expired_links_drop_out_of_the_list(client: TestClient, db_gateway: FakeDbGateway) -> None:
    old, kept = share(client).json(), share(client).json()

    expire(db_gateway, old["id"])

    assert [s["id"] for s in client.get("/shares").json()] == [kept["id"]]


def test_links_are_private_per_account(client: TestClient) -> None:
    login(client, "alice")
    mine = share(client).json()
    login(client, "bob")

    assert client.get("/shares").json() == []
    assert client.delete(f"/shares/{mine['id']}").status_code == 404
    assert read(client, mine["token"]).status_code == 200  # a link is readable by anyone who has it
    login(client, "alice")
    assert len(client.get("/shares").json()) == 1  # ... but only its owner can revoke it


def test_revoking_kills_the_link_at_once(client: TestClient, platform) -> None:
    made = share(client, expires_in_days=30).json()
    assert read(client, made["token"]).status_code == 200

    assert client.delete(f"/shares/{made['id']}").status_code == 204

    assert read(client, made["token"]).status_code == 404
    assert client.get("/shares").json() == []
    assert client.delete(f"/shares/{made['id']}").status_code == 404
    assert [(action, message) for _uid, action, message in platform.actions] == [
        ("share.create", f'Shared chat "Quarterly report" (link {made["id"]}, 30 days)'),
        ("share.revoke", f'Revoked the link {made["id"]} to chat "Quarterly report"'),
    ]
    assert made["token"] not in str(platform.actions)


def test_share_ids_are_validated(client: TestClient) -> None:
    assert client.delete("/shares/0").status_code == 422
    assert client.delete("/shares/abc").status_code == 422
    assert client.delete("/shares/99999").status_code == 404


# --- limits ---------------------------------------------------------------------------------


def test_active_link_limit(client: TestClient, db_gateway: FakeDbGateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(share_store, "MAX_ACTIVE_SHARES_PER_ACCOUNT", 2)
    first, second = share(client).json(), share(client).json()

    refused = share(client)

    assert refused.status_code == 409 and "At most 2" in refused.json()["detail"]
    # Revoking frees a slot, and so does a link expiring.
    client.delete(f"/shares/{first['id']}")
    assert share(client).status_code == 201
    expire(db_gateway, second["id"])
    assert share(client).status_code == 201


def test_making_a_link_removes_the_accounts_expired_ones(client: TestClient, db_gateway: FakeDbGateway) -> None:
    old = share(client).json()
    expire(db_gateway, old["id"])

    kept = share(client).json()

    assert [doc["id"] for doc in db_gateway.records.values()] == [kept["id"]]


# --- what removes links ----------------------------------------------------------------------


def test_revoking_chats_removes_their_links_and_only_theirs(client: TestClient) -> None:
    doomed = share(client, CHAT).json()["token"]
    stays = share(client, OTHER_CHAT).json()["token"]

    assert client.post("/shares/revoke", json={"chat_ids": [CHAT]}).status_code == 204

    assert read(client, doomed).status_code == 404 and read(client, stays).status_code == 200


def test_revoking_all_removes_every_link_of_the_account_and_no_one_elses(client: TestClient) -> None:
    login(client, "alice")
    mine = [share(client).json()["token"] for _ in range(3)]
    login(client, "bob")
    bobs = share(client).json()["token"]

    login(client, "alice")
    assert client.post("/shares/revoke", json={"chat_ids": "all"}).status_code == 204

    assert all(read(client, t).status_code == 404 for t in mine)
    assert read(client, bobs).status_code == 200


@pytest.mark.parametrize("body", [{}, {"chat_ids": "some"}, {"chat_ids": ["x"]}, {"chat_ids": None}, {"all": True}])
def test_revoke_needs_chat_ids_or_all(client: TestClient, body: dict) -> None:
    token = share(client).json()["token"]

    assert client.post("/shares/revoke", json=body).status_code == 422
    assert read(client, token).status_code == 200


def test_purging_an_account_removes_only_its_links(client: TestClient) -> None:
    login(client, "alice")
    gone = share(client).json()["token"]
    login(client, "bob")
    stays = share(client).json()["token"]

    assert client.delete(f"/shares/accounts/{uid_of('alice')}").status_code == 204

    assert read(client, gone).status_code == 404 and read(client, stays).status_code == 200
    assert client.delete("/shares/accounts/has%20space").status_code == 422


def test_token_hash_is_a_stable_sha256_hex() -> None:
    assert share_store.hash_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
