"""Share links: Portcullis cuts the chat down, checks login and permission and rate-limits the public read;
Stronghold keeps the links (its own tests cover expiry, limits and tokens)."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from src.services.public_rate_limiter import PublicReadLimiter
from tests.conftest import FakeEmailSender, FakeUpstream
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

FILE = '[[ATTACHMENT filename="report.txt" chars="9" truncated="false"]]\nsecretword\n[[/ATTACHMENT]]'

CONVERSATION = [
    {"role": "assistant", "kind": "summary", "content": "SUMMARY-SECRET"},
    {"role": "user", "content": f"please summarize\n\n{FILE}"},
    {
        "role": "assistant",
        "content": "Here you go.\n[[DOWNLOAD filename=\"out.csv\" bytes=\"1\" url=\"/internal/f\"]]",
        "model": "claude-test",
        "total_tokens": 100,
        "steps": [{"tool": "tool_x", "label": "X", "arguments": {"key": "TOOL-ARG"}, "ok": True, "result": "TOOL-RESULT"}],
    },
    {"role": "user", "kind": "command", "content": "/apps start"},
    {"role": "assistant", "kind": "command", "content": "COMMAND-RESULT"},
    {"role": "user", "content": "and again?"},
    {"role": "assistant", "content": "error: provider blew up at 10.0.0.5"},
]
TOKEN = "T" * 43


def new_id() -> str:
    return str(uuid.uuid4())


def make_chat(client: TestClient, messages=None, title: str = "Quarterly report") -> str:
    chat_id = new_id()
    response = client.put(
        f"/api/chats/{chat_id}",
        json={"title": title, "agent_id": "claude-agent", "messages": messages if messages is not None else CONVERSATION},
    )
    assert response.status_code == 200
    return chat_id


def share(client: TestClient, chat_id: str, **body):
    return client.post(f"/api/chats/{chat_id}/shares", json=body)


def stronghold(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/shares" and request.method == "POST":
        return httpx.Response(201, json={"id": 5, "token": TOKEN})
    if request.url.path.startswith("/shares/public/"):
        return httpx.Response(200, json={"title": "Quarterly report", "messages": [], "created_at": "x", "expires_at": None})
    return httpx.Response(204 if request.method in ("DELETE", "POST") else 200, json=[])


@pytest.fixture
def served(upstream: FakeUpstream) -> FakeUpstream:
    upstream.handler = stronghold
    return upstream


def sent_to(upstream: FakeUpstream, path: str) -> list[httpx.Request]:
    return [r for r in upstream.requests if r.url.path == path]


# --- access -------------------------------------------------------------------


def test_managing_links_needs_login_and_chat_use(client: TestClient, email: FakeEmailSender, served) -> None:
    assert share(client, new_id()).status_code == 401
    assert client.get("/api/shares").status_code == 401
    assert client.delete("/api/shares/1").status_code == 401

    make_member(client, email, verify=False)
    login(client, "alice")
    assert share(client, new_id()).status_code == 403  # unverified: no permissions
    assert client.get("/api/shares").status_code == 403
    assert client.delete("/api/shares/1").status_code == 403
    assert sent_to(served, "/shares") == []


def test_reading_a_link_needs_no_login_and_sends_no_identity(client_factory, served) -> None:
    stranger = client_factory()  # a browser that never logged in

    response = stranger.get(f"/api/shared/{TOKEN}")

    assert response.status_code == 200
    (call,) = sent_to(served, f"/shares/public/{TOKEN}")
    assert "x-requester-uid" not in call.headers and "x-requester-username" not in call.headers


# --- creating -----------------------------------------------------------------


def test_creating_sends_only_the_sanitized_conversation(client: TestClient, served) -> None:
    as_admin(client)
    chat_id = make_chat(client)

    response = share(client, chat_id, expires_in_days=30)

    assert (response.status_code, response.json()) == (201, {"id": 5, "token": TOKEN})
    (call,) = sent_to(served, "/shares")
    assert call.headers["x-requester-uid"] == uids(client)["root"]
    body = json.loads(call.content)
    assert body == {
        "chat_id": chat_id, "title": "Quarterly report", "expires_in_days": 30,
        "messages": [
            {"role": "user", "content": "please summarize\n\n📎 report.txt"},
            {"role": "assistant", "content": "Here you go."},
            {"role": "user", "content": "and again?"},
        ],
    }
    for secret in ("SUMMARY-SECRET", "secretword", "TOOL-ARG", "TOOL-RESULT", "COMMAND-RESULT", "10.0.0.5", "/internal/f", "claude-test"):
        assert secret not in call.content.decode()


def test_the_default_expiry_is_a_week(client: TestClient, served) -> None:
    as_admin(client)

    share(client, make_chat(client))

    assert json.loads(sent_to(served, "/shares")[0].content)["expires_in_days"] == 7


@pytest.mark.parametrize("days", [0, 2, 365, -1, "7", 7.5, "forever"])
def test_other_expiries_are_refused_before_stronghold(client: TestClient, served, days) -> None:
    as_admin(client)
    chat_id = make_chat(client)

    assert share(client, chat_id, expires_in_days=days).status_code == 422
    assert sent_to(served, "/shares") == []


def test_unknown_and_foreign_chats_are_404(client_factory, email: FakeEmailSender, served) -> None:
    alice = client_factory()
    make_member(alice, email)
    make_member(alice, email, "bob")
    login(alice, "alice")
    chat_id = make_chat(alice)
    bob = client_factory()
    login(bob, "bob")

    assert share(alice, new_id()).status_code == 404
    assert share(bob, chat_id).status_code == 404
    assert share(alice, "x").status_code == 422  # not even an id
    assert sent_to(served, "/shares") == []


def test_a_chat_with_nothing_shareable_is_refused(client: TestClient, served) -> None:
    as_admin(client)
    only_private_parts = [
        {"role": "assistant", "kind": "summary", "content": "S"},
        {"role": "assistant", "kind": "log_attachment", "content": "raw"},
        {"role": "user", "kind": "command", "content": "/x y"},
        {"role": "assistant", "kind": "command", "content": "result"},
        {"role": "assistant", "content": "error: down"},
    ]

    assert share(client, make_chat(client, only_private_parts)).status_code == 422
    assert share(client, make_chat(client, [])).status_code == 422
    assert sent_to(served, "/shares") == []


def test_a_refusal_from_stronghold_passes_through(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: httpx.Response(409, json={"detail": "At most 50 active shared links per account - revoke some first"})
    as_admin(client)

    refused = share(client, make_chat(client))

    assert (refused.status_code, refused.json()["detail"]) == (409, "At most 50 active shared links per account - revoke some first")


def test_shares_are_posted_as_json_only(client: TestClient, served) -> None:
    as_admin(client)
    chat_id = make_chat(client)

    response = client.post(f"/api/chats/{chat_id}/shares", content="expires_in_days=7", headers={"Content-Type": "text/plain"})

    assert response.status_code == 415


# --- listing and revoking --------------------------------------------------------

def test_list_and_revoke_go_to_stronghold_as_the_signed_in_account(client: TestClient, served) -> None:
    as_admin(client)
    uid = uids(client)["root"]
    served.requests.clear()

    assert client.get("/api/shares", params={"chat_id": "abcdefgh"}).json() == []
    assert client.delete("/api/shares/12").status_code == 204

    listed, revoked = served.requests
    assert (listed.url.path, dict(listed.url.params)) == ("/shares", {"chat_id": "abcdefgh"})
    assert (revoked.method, revoked.url.path) == ("DELETE", "/shares/12")
    assert listed.headers["x-requester-uid"] == revoked.headers["x-requester-uid"] == uid


def test_share_ids_are_validated(client: TestClient, served) -> None:
    as_admin(client)
    served.requests.clear()

    assert client.delete("/api/shares/0").status_code == 422
    assert client.delete("/api/shares/abc").status_code == 422
    assert client.delete("/api/shares/accounts/someone").status_code in (404, 405)
    assert served.requests == []


# --- the public read ---------------------------------------------------------------


def test_the_public_response_is_never_cached_or_indexed(client_factory, served) -> None:
    response = client_factory().get(f"/api/shared/{TOKEN}")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_only_reading_is_possible_without_login(client_factory) -> None:
    anon = client_factory()

    for method in ("post", "put", "patch", "delete"):
        assert getattr(anon, method)("/api/shared/" + "a" * 43).status_code in (401, 403, 405, 415, 422)


def test_malformed_tokens_never_reach_stronghold_and_look_like_unknown_ones(client_factory, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: httpx.Response(404, json={"detail": "Shared chat not found"})
    anon = client_factory()

    answers = [anon.get(f"/api/shared/{t}") for t in ("short", "x" * 200, "has spaces and !!", "A" * 43)]

    assert {r.status_code for r in answers} == {404}
    assert len({r.text for r in answers}) == 1  # nothing tells the cases apart
    assert [r.url.path for r in upstream.requests] == ["/shares/public/" + "A" * 43]
    assert "cache-control" not in answers[-1].headers


def test_reading_is_rate_limited_per_address(client_factory, served) -> None:
    anon = client_factory()
    anon.app.state.share_limiter = PublicReadLimiter(max_requests=3, window_seconds=60)

    codes = [anon.get(f"/api/shared/{TOKEN}").status_code for _ in range(3)]
    refused = anon.get("/api/shared/" + "A" * 43)  # guesses count too

    assert codes == [200, 200, 200]
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) >= 1
    assert anon.get(f"/api/shared/{TOKEN}").status_code == 429


def test_stronghold_down_gives_502_for_managing_and_reading(client_factory, upstream: FakeUpstream) -> None:
    owner = client_factory()
    as_admin(owner)
    upstream.unreachable = True

    assert owner.get("/api/shares").status_code == 502
    assert client_factory().get(f"/api/shared/{TOKEN}").status_code == 502


# --- what removes links -------------------------------------------------------------------


# Stronghold revokes a chat's links in the same call that deletes the chat (its own tests prove it).


def test_nothing_is_deleted_when_the_links_cannot_be_revoked(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    chat_id = make_chat(client)
    folder = client.post("/api/chat-folders", json={"name": "Work"}).json()["id"]
    client.patch(f"/api/chats/{chat_id}", json={"folder_id": folder})
    other = make_chat(client)
    upstream.unreachable = True

    assert client.delete(f"/api/chats/{other}").status_code == 502
    assert client.delete("/api/chats").status_code == 502
    assert client.delete(f"/api/chat-folders/{folder}").status_code == 502

    upstream.unreachable = False
    assert client.get(f"/api/chats/{other}").status_code == 200
    assert client.get(f"/api/chats/{chat_id}").status_code == 200
    assert client.get("/api/chat-folders").json()[0]["chat_count"] == 1


def test_deleting_an_account_purges_its_links_in_stronghold(client: TestClient, email: FakeEmailSender, served) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    served.requests.clear()

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [r.method for r in sent_to(served, f"/shares/accounts/{uid}")] == ["DELETE"]


def test_failed_link_purge_never_blocks_account_deletion(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    root = client.get("/api/auth/me").json()["id"]
    upstream.handler = lambda request: httpx.Response(503, json={"detail": "Storage is unavailable"})

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.shares_purge" for entry in errors)
