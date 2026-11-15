"""/api/usage and /api/admin/usage: Portcullis checks the login and the permission; Stronghold keeps the usage.

Admin inspection is independent of chat and account-management access.
"""
import json

import httpx
import pytest
from sqlalchemy import select

from src.models import Account, Permission, Role
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin


def grant(client, permissions, *, verified=True):
    async def run():
        async with client.app.state.database.sessions() as session:
            root = (await session.execute(select(Account).where(Account.username == "root"))).scalar_one()
            selected = list((await session.execute(select(Permission).where(Permission.name.in_(permissions)))).scalars())
            role = Role(name="Usage test role", permissions=selected)
            root.roles = [role]
            root.email_verified = verified
            await session.commit()
    client.portal.call(run)


def spend(upstream, uid, tokens, turn="t1", kind="chat"):
    upstream.usage.rows.append({"owner": uid, "total_tokens": tokens, "turn_id": turn, "kind": kind, "chat_id": None,
                                "agent": "main", "model": "m", "created_at": "2026-10-10T12:00:00", "id": len(upstream.usage.rows) + 1})


@pytest.fixture
def accounts(client, email):
    ids = {name: make_member(client, email, name) for name in ("alice", "bob", "empty")}
    as_admin(client)
    return ids


def test_usage_routes_need_login(client):
    for url in ("/api/usage", "/api/usage/records", "/api/admin/usage", "/api/admin/usage/1", "/api/admin/usage/1/records"):
        assert client.get(url).status_code == 401


def test_my_usage_goes_to_stronghold_as_the_signed_in_account_whatever_the_browser_says(client, upstream):
    as_admin(client)
    uid = uids(client)["root"]
    spend(upstream, uid, 40)
    spend(upstream, "someone-else", 900)
    upstream.requests.clear()

    usage = client.get("/api/usage", params={"days": 7, "account_id": 5, "uid": "someone-else"}).json()
    records = client.get("/api/usage/records", params={"limit": 5}).json()

    assert usage["six_hour"]["used"] == 40 and [r["total_tokens"] for r in records] == [40]
    assert [r.url.path for r in upstream.requests] == ["/usage", "/usage/records"]
    assert upstream.requests[0].url.params["days"] == "7"
    assert all(r.headers["x-requester-uid"] == uid for r in upstream.requests)


def test_a_refusal_from_stronghold_passes_through(client, upstream):
    upstream.usage = None
    upstream.handler = lambda request: httpx.Response(422, json={"detail": "since must not be in the future"})
    as_admin(client)

    refused = client.get("/api/usage", params={"since": "2999-01-01"})

    assert (refused.status_code, refused.json()["detail"]) == (422, "since must not be in the future")


def test_stronghold_down_gives_502(client, upstream):
    as_admin(client)
    upstream.usage.down = True

    assert client.get("/api/usage").status_code == 502
    assert client.get("/api/admin/usage").status_code == 502


def test_summary_lists_every_account_with_zero_for_those_that_used_nothing(client, accounts, upstream):
    spend(upstream, uids(client)["alice"], 100, "a1")
    spend(upstream, uids(client)["alice"], 25, "a1")
    spend(upstream, uids(client)["alice"], 10, "s1", kind="summary")
    spend(upstream, uids(client)["bob"], 200, "b1")
    spend(upstream, "deleted-account", 999, "x")

    rows = client.get("/api/admin/usage", params={"days": 30}).json()

    assert [r["username"] for r in rows] == ["bob", "alice", "empty", "root"]
    assert [(r["tokens"], r["turns"]) for r in rows[:2]] == [(200, 1), (135, 1)]
    assert all(r["tokens"] == r["turns"] == 0 and r["last_used_at"] is None for r in rows[2:])
    assert rows[0]["account_id"] == accounts["bob"]


def test_target_report_and_records_are_that_accounts_not_the_admins(client, accounts, upstream):
    spend(upstream, uids(client)["alice"], 135)
    spend(upstream, uids(client)["root"], 7)
    upstream.requests.clear()

    report = client.get(f"/api/admin/usage/{accounts['alice']}", params={"group_by": "model"}).json()
    records = client.get(f"/api/admin/usage/{accounts['alice']}/records", params={"limit": 1}).json()

    assert report["report"]["total_tokens"] == 135 and [r["total_tokens"] for r in records] == [135]
    assert all(r.headers["x-requester-uid"] == uids(client)["alice"] for r in upstream.requests)
    assert upstream.requests[0].url.params["group_by"] == "model"
    assert client.get(f"/api/admin/usage/{accounts['empty']}").json()["report"]["total_tokens"] == 0


@pytest.mark.parametrize("suffix", ["", "/records"])
def test_admin_permission_is_required_before_lookup(client, accounts, suffix):
    url = "/api/admin/usage/999999" + suffix
    client.post("/api/auth/logout", json={})
    assert client.get(url).status_code == 401
    as_admin(client)
    grant(client, ["chat.use"])
    assert client.get(url).status_code == 403


def test_usage_only_role_can_inspect_without_chat_or_accounts_access(client, accounts):
    grant(client, ["usage.all.view"])
    assert client.get("/api/usage").status_code == 403
    assert client.get("/api/admin/usage").status_code == 200
    assert client.get(f"/api/admin/usage/{accounts['alice']}").status_code == 200
    assert client.get(f"/api/admin/usage/{accounts['alice']}/records").status_code == 200
    assert client.get("/api/admin/usage/999999").status_code == 404
    assert client.get("/api/admin/usage/999999/records").status_code == 404


def test_unverified_observer_is_denied(client, accounts):
    grant(client, ["usage.all.view"], verified=False)
    assert client.get(f"/api/admin/usage/{accounts['alice']}").status_code == 403
    assert client.get(f"/api/admin/usage/{accounts['alice']}/records").status_code == 403


def test_invalid_account_id(client, accounts):
    assert client.get("/api/admin/usage/nope").status_code == 422


def test_deleting_an_account_purges_its_usage_in_stronghold(client, accounts, upstream):
    uid = uids(client)["alice"]
    spend(upstream, uid, 50)
    spend(upstream, uids(client)["bob"], 60)

    assert client.delete(f"/api/admin/accounts/{accounts['alice']}").status_code == 204

    assert [row["owner"] for row in upstream.usage.rows] == [uids(client)["bob"]]


def test_failed_usage_purge_never_blocks_account_deletion(client, accounts, upstream):
    upstream.usage.down = True
    root = client.get("/api/auth/me").json()["id"]

    assert client.delete(f"/api/admin/accounts/{accounts['alice']}").status_code == 204

    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.usage_purge" for entry in errors)
