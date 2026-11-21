"""Account deletion asks Stronghold to purge legacy notes."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from tests.conftest import FakeEmailSender, FakeUpstream
from tests.test_account_uid import uids
from tests.test_admin import make_member
from tests.test_registration import as_admin


def test_deleting_an_account_purges_its_notes_in_stronghold(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: httpx.Response(204)
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [r.method for r in upstream.requests if r.url.path == f"/notes/accounts/{uid}"] == ["DELETE"]


def test_failed_purge_never_blocks_account_deletion(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(503, json={"detail": "Notes storage is unavailable"})

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204
    assert "alice" not in uids(client)
    root = client.get("/api/auth/me").json()["id"]
    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.notes_purge" for entry in errors)
