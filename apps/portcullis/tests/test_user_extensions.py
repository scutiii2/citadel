"""/api/user-extensions: Portcullis checks the login and the permission, passes the call to Stronghold
(which stores, probes and encrypts) and writes the account log."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.test_registration import as_admin

URL = "/api/user-extensions"
EXT_URL = "https://notes.example.com/mcp?token=abc123"
SAVED = {"id": "notes", "label": "Notes", "description": "", "url": EXT_URL, "header_names": ["X-Key"], "enabled": True,
         "status": "connected", "error": None, "tools": []}


def answer(status_code: int, body):
    return lambda request: httpx.Response(status_code, json=body)


def test_needs_login(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"label": "x", "url": EXT_URL}).status_code == 401
    assert client.patch(f"{URL}/notes", json={"enabled": False}).status_code == 401
    assert client.delete(f"{URL}/notes").status_code == 401


def test_the_calls_go_to_stronghold_with_their_body(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(
        201 if request.method == "POST" else 200,
        json={**SAVED, "seen": [request.method, request.url.path, json.loads(request.content or b"null")]})

    listed = client.get(URL).json()
    added = client.post(URL, json={"label": "Notes", "url": EXT_URL, "headers": {"X-Key": "s3cret"}})
    patched = client.patch(f"{URL}/notes", json={"enabled": False}).json()

    assert listed["seen"] == ["GET", "/user-extensions", None]
    assert added.status_code == 201
    assert added.json()["seen"] == ["POST", "/user-extensions", {"label": "Notes", "url": EXT_URL, "headers": {"X-Key": "s3cret"}}]
    assert patched["seen"] == ["PATCH", "/user-extensions/notes", {"enabled": False}]


def test_stronghold_refusals_pass_through_unchanged(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.handler = answer(422, {"detail": "Enter an http or https address"})

    response = client.post(URL, json={"label": "x", "url": "ftp://x.com/m"})

    assert (response.status_code, response.json()) == (422, {"detail": "Enter an http or https address"})


def test_the_slug_must_look_like_one(client: TestClient, upstream) -> None:
    as_admin(client)
    seen = len(upstream.requests)

    assert client.patch(f"{URL}/Bad_Slug", json={"enabled": False}).status_code == 422
    assert client.delete(f"{URL}/{'x' * 41}").status_code == 422
    assert len(upstream.requests) == seen


def test_the_for_turn_route_is_not_reachable_from_a_browser(client: TestClient, upstream) -> None:
    as_admin(client)
    seen = len(upstream.requests)

    assert client.get(f"{URL}/for-turn").status_code in (404, 405)
    assert len(upstream.requests) == seen


def test_changes_are_logged_without_secrets_or_the_query_string(client: TestClient, upstream) -> None:
    as_admin(client)
    me = client.get("/api/auth/me").json()["id"]
    upstream.handler = answer(201, SAVED)
    client.post(URL, json={"label": "Notes", "url": EXT_URL, "headers": {"X-Key": "s3cret-value"}})
    upstream.handler = answer(200, {**SAVED, "enabled": False})
    client.patch(f"{URL}/notes", json={"enabled": False})
    client.patch(f"{URL}/notes", json={"enabled": True})
    upstream.handler = answer(200, {**SAVED, "label": "Renamed"})
    client.patch(f"{URL}/notes", json={"label": "Renamed"})
    upstream.handler = answer(204, None)
    client.delete(f"{URL}/notes")

    logged = [e["message"] for e in client.get("/api/logs/action", params={"actor": me}).json()]

    assert logged[:5] == [
        "Removed private extension 'notes'",
        "Edited private extension 'Renamed' (notes.example.com)",
        "Enabled private extension 'Notes'",
        "Disabled private extension 'Notes'",
        "Added private extension 'Notes' (notes.example.com)",
    ]
    assert not any("abc123" in m or "s3cret-value" in m for m in logged)


def test_a_refused_change_is_not_logged(client: TestClient, upstream) -> None:
    as_admin(client)
    me = client.get("/api/auth/me").json()["id"]
    upstream.handler = answer(404, {"detail": "No such extension"})
    client.patch(f"{URL}/notes", json={"enabled": False})
    client.delete(f"{URL}/notes")

    logged = [e["message"] for e in client.get("/api/logs/action", params={"actor": me}).json()]

    assert not [m for m in logged if "private extension" in m]


def test_stronghold_down_is_a_502(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.unreachable = True

    assert client.get(URL).status_code == 502


def test_deleting_an_account_purges_its_agents_and_extensions_in_stronghold(client: TestClient, email, upstream) -> None:
    from sqlalchemy import select

    from src.models import Account
    from tests.test_admin import make_member

    account_id = make_member(client, email, "carol")
    as_admin(client)

    async def uid_of(username: str) -> str:
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(Account.uid).where(Account.username == username))

    uid = client.portal.call(uid_of, "carol")
    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204

    purged = {r.url.path for r in upstream.requests if r.method == "DELETE"}
    assert {f"/account-agents/accounts/{uid}", f"/user-extensions/accounts/{uid}"} <= purged
