"""Signed browser forwarding and service-only requester renewal."""
import asyncio

from tests.auth_helpers import requester, assertion
import json

from src.citadel_auth import verify_requester
from src.citadel_auth.testing import signed
from src.services import service_auth
from tests.test_registration import as_admin
from tests.test_internal_api import uid_of


def test_requester_cache_and_audience(auth_stack):
    first = service_auth.identity_headers("alice", "alice@example.test", "alice")
    second = service_auth.identity_headers("alice", "alice@example.test", "alice")
    assert first == second
    raw = first["X-Citadel-Requester"]
    for audience in ("stronghold", "legion", "armory"):
        who = asyncio.run(verify_requester(auth_stack[audience], raw, audience))
        assert who.uid == "alice"


def test_refresh_requires_stronghold_active_account_and_running_turn(client, upstream, auth_stack):
    as_admin(client)
    uid = uid_of(client, "root")
    path = "/internal/requester-token"
    assert client.post(path, json={"uid": uid}).status_code == 401
    assert client.post(path, json={"uid": uid}, headers=signed(auth_stack["armory"], "portcullis")).status_code == 403
    def stronghold():
        return signed(auth_stack["stronghold"], "portcullis")
    assert client.post(path, json={"uid": "unknown"}, headers=stronghold()).status_code == 404
    upstream.turns.running.clear()
    assert client.post(path, json={"uid": uid}, headers=stronghold()).status_code == 409
    upstream.turns.running.add("chat-1234")
    response = client.post(path, json={"uid": uid}, headers=stronghold())
    assert response.status_code == 200
    who = asyncio.run(verify_requester(auth_stack["legion"], response.json()["token"], "legion"))
    assert who.uid == uid
    async def disable():
        from sqlalchemy import update
        from src.models import Account
        async with client.app.state.database.sessions() as session:
            await session.execute(update(Account).where(Account.uid == uid).values(is_active=False))
            await session.commit()
    client.portal.call(disable)
    assert client.post(path, json={"uid": uid}, headers=stronghold()).status_code == 404

