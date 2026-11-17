"""/internal: what Stronghold may ask Portcullis, and only with the internal token."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.models import Account
from tests.conftest import FakeEmailSender
from tests.test_admin import make_member
from tests.test_registration import as_admin

from src.citadel_auth.testing import signed
from src.services import service_auth
from src.citadel_auth.keyring import Keyring


def internal_headers(client):
    own = client.app.state.keyring
    caller = Keyring("stronghold", own.trust_dir, own.identity_dir.parent / "stronghold")
    import asyncio
    asyncio.run(caller.ensure_identity())
    return signed(caller, "portcullis")


def uid_of(client: TestClient, username: str) -> str:
    async def read() -> str:
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(Account.uid).where(Account.username == username))

    return client.portal.call(read)


def test_browser_session_cannot_authenticate_internal_routes(client_factory) -> None:
    locked = client_factory()
    assert locked.get("/internal/accounts/0/permissions").status_code == 401
    assert locked.get("/internal/accounts/0/permissions", headers={"Authorization": "wrong"}).status_code == 401
    as_admin(locked)  # a browser session is not the token
    assert locked.get("/internal/accounts/0/permissions").status_code == 401
    assert locked.get(f"/internal/accounts/{uid_of(locked, 'root')}/permissions", headers=internal_headers(locked)).status_code == 200
    unconfigured = client_factory()
    assert unconfigured.get("/internal/accounts/0/permissions", headers={"Authorization": ""}).status_code == 401


def test_error_log(client_factory) -> None:
    client = client_factory()
    assert client.post("/internal/errors", json={"source": "tickets", "message": "alerts could not run"}, headers=internal_headers(client)).status_code == 204
    assert client.post("/internal/errors", json={"source": "Bad Source", "message": "x"}, headers=internal_headers(client)).status_code == 422
    as_admin(client)
    logged = client.get("/api/logs/error").text
    assert "stronghold.tickets" in logged and "alerts could not run" in logged


def test_an_action_is_logged_for_the_named_account(client_factory, email: FakeEmailSender) -> None:
    client = client_factory()
    admin_uid = uid_of(client, "root")
    url = f"/internal/accounts/{admin_uid}/actions"
    assert client.post(url, json={"action": "memory.create", "message": "Saved a memory"}, headers=internal_headers(client)).status_code == 204
    assert client.post(url, json={"action": "Bad Action", "message": "x"}, headers=internal_headers(client)).status_code == 422
    assert client.post(f"/internal/accounts/{'0' * 32}/actions", json={"action": "memory.create", "message": "x"}, headers=internal_headers(client)).status_code == 404
    assert client.post(url, json={"action": "memory.create", "message": "x"}).status_code == 401
    as_admin(client)
    account_id = client.get("/api/auth/me").json()["id"]
    entries = client.get("/api/logs/action", params={"actor": str(account_id)}).json()
    assert [e["message"] for e in entries if e["source"] == "memory.create"] == ["Saved a memory"]


def test_a_turn_log_line_lands_in_the_accounts_logs(client_factory) -> None:
    client = client_factory()
    admin_uid = uid_of(client, "root")
    line = {"kind": "chat_trace", "uid": admin_uid, "source": "chat.turn", "message": "hi → agent/model, 1.0s", "details": "{}", "prompts": None}
    assert client.post("/internal/logs", json=line, headers=internal_headers(client)).status_code == 204
    assert client.post("/internal/logs", json={**line, "kind": "error", "source": "chat.answer", "message": "boom"}, headers=internal_headers(client)).status_code == 204
    assert client.post("/internal/logs", json={**line, "uid": "0" * 32}, headers=internal_headers(client)).status_code == 404
    assert client.post("/internal/logs", json={**line, "kind": "action"}, headers=internal_headers(client)).status_code == 422
    assert client.post("/internal/logs", json=line).status_code == 401
    as_admin(client)
    account_id = client.get("/api/auth/me").json()["id"]
    assert "boom" in client.get("/api/logs/error", params={"actor": account_id}).text
    assert "agent/model" in client.get("/api/logs/chat_trace", params={"actor": account_id}).text
