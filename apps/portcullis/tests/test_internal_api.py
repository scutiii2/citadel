"""/internal: what Stronghold may ask Portcullis, and only with the internal token."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.models import Account
from tests.conftest import FakeEmailSender
from tests.test_admin import make_member
from tests.test_registration import as_admin

TOKEN = {"X-Internal-Token": "internal-secret"}


def uid_of(client: TestClient, username: str) -> str:
    async def read() -> str:
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(Account.uid).where(Account.username == username))

    return client.portal.call(read)


def test_refused_without_the_token_and_when_none_is_configured(client_factory) -> None:
    locked = client_factory(internal_token="internal-secret")
    assert locked.get("/internal/switches").status_code == 401
    assert locked.get("/internal/switches", headers={"X-Internal-Token": "wrong"}).status_code == 401
    as_admin(locked)  # a browser session is not the token
    assert locked.get("/internal/switches").status_code == 401
    assert locked.get("/internal/switches", headers=TOKEN).status_code == 200
    unconfigured = client_factory()
    assert unconfigured.get("/internal/switches", headers={"X-Internal-Token": ""}).status_code == 401


def test_recipient_only_for_a_usable_account_that_holds_the_permission(client_factory, email: FakeEmailSender) -> None:
    client = client_factory(internal_token="internal-secret")
    make_member(client, email, "carol")
    admin_uid = uid_of(client, "root")
    found = client.get(f"/internal/accounts/{admin_uid}/recipient", params={"permission": "calendar.use"}, headers=TOKEN)
    assert found.status_code == 200 and found.json()["uid"] == admin_uid and "@" in found.json()["email"]
    for uid, permission in ((uid_of(client, "carol"), "calendar.use"), ("0" * 32, "calendar.use"), (admin_uid, "no.such")):
        refused = client.get(f"/internal/accounts/{uid}/recipient", params={"permission": permission}, headers=TOKEN)
        assert refused.status_code == 404


def test_switches_notify_and_error_log(client_factory, email: FakeEmailSender) -> None:
    client = client_factory(internal_token="internal-secret")
    admin_uid = uid_of(client, "root")
    assert client.get("/internal/switches", headers=TOKEN).json()["calendar_email"] is True

    sent = client.post(f"/internal/accounts/{admin_uid}/notify", json={"subject": "Starting\nsoon", "body": "At 9"}, headers=TOKEN)
    assert sent.status_code == 204
    kind, to, text = email.sent[-1]
    assert kind == "notification" and "@" in to and "Starting soon" in text
    assert client.post(f"/internal/accounts/{'0' * 32}/notify", json={"subject": "s", "body": "b"}, headers=TOKEN).status_code == 404
    assert client.post(f"/internal/accounts/{admin_uid}/notify", json={"subject": "s", "to": "x@evil.test", "body": ""}, headers=TOKEN).status_code == 422

    assert client.post("/internal/errors", json={"source": "calendar", "message": "alerts could not run"}, headers=TOKEN).status_code == 204
    assert client.post("/internal/errors", json={"source": "Bad Source", "message": "x"}, headers=TOKEN).status_code == 422
    as_admin(client)
    logged = client.get("/api/logs/error").text
    assert "stronghold.calendar" in logged and "alerts could not run" in logged


def test_an_action_is_logged_for_the_named_account(client_factory, email: FakeEmailSender) -> None:
    client = client_factory(internal_token="internal-secret")
    admin_uid = uid_of(client, "root")
    url = f"/internal/accounts/{admin_uid}/actions"
    assert client.post(url, json={"action": "memory.create", "message": "Saved a memory"}, headers=TOKEN).status_code == 204
    assert client.post(url, json={"action": "Bad Action", "message": "x"}, headers=TOKEN).status_code == 422
    assert client.post(f"/internal/accounts/{'0' * 32}/actions", json={"action": "memory.create", "message": "x"}, headers=TOKEN).status_code == 404
    assert client.post(url, json={"action": "memory.create", "message": "x"}).status_code == 401
    as_admin(client)
    account_id = client.get("/api/auth/me").json()["id"]
    entries = client.get("/api/logs/action", params={"actor": str(account_id)}).json()
    assert [e["message"] for e in entries if e["source"] == "memory.create"] == ["Saved a memory"]


def test_a_turn_log_line_lands_in_the_accounts_logs(client_factory) -> None:
    client = client_factory(internal_token="internal-secret")
    admin_uid = uid_of(client, "root")
    line = {"kind": "chat_trace", "uid": admin_uid, "source": "chat.turn", "message": "hi → agent/model, 1.0s", "details": "{}", "prompts": None}
    assert client.post("/internal/logs", json=line, headers=TOKEN).status_code == 204
    assert client.post("/internal/logs", json={**line, "kind": "error", "source": "chat.answer", "message": "boom"}, headers=TOKEN).status_code == 204
    assert client.post("/internal/logs", json={**line, "uid": "0" * 32}, headers=TOKEN).status_code == 404
    assert client.post("/internal/logs", json={**line, "kind": "action"}, headers=TOKEN).status_code == 422
    assert client.post("/internal/logs", json=line).status_code == 401
    as_admin(client)
    account_id = client.get("/api/auth/me").json()["id"]
    assert "boom" in client.get("/api/logs/error", params={"actor": account_id}).text
    assert "agent/model" in client.get("/api/logs/chat_trace", params={"actor": account_id}).text
