"""Deleting an account tells Stronghold to delete its long-term Brain files (best effort)."""

from __future__ import annotations

from tests.auth_helpers import requester, assertion

import logging

import httpx
from fastapi.testclient import TestClient

from tests.conftest import ADMIN_USERNAME, FakeEmailSender, FakeUpstream
from tests.test_account_uid import uids
from tests.test_admin import make_member
from tests.test_registration import as_admin


def purges(upstream: FakeUpstream) -> list[httpx.Request]:
    return [r for r in upstream.requests if r.method == "DELETE" and r.url.path.startswith("/brain/accounts/")]


def test_deleting_an_account_purges_its_brain_files_once(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream, caplog) -> None:
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()
    caplog.set_level(logging.INFO)

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    sent = purges(upstream)
    assert [r.url.path for r in sent] == [f"/brain/accounts/{uid}"]
    assert not any(r.method == "DELETE" and r.url.path.startswith(("/notes/accounts/", "/brains/accounts/"))
                   for r in upstream.requests)
    assert assertion(sent[0])["iss"] == "portcullis"
    assert uid not in caplog.text
    assert "/brain/accounts/[redacted]" in caplog.text


def test_the_internal_token_is_sent_when_configured(client_factory, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    client = client_factory()
    alice = make_member(client, email, "alice")
    as_admin(client)
    upstream.requests.clear()

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert assertion(purges(upstream)[0])["iss"] == "portcullis"


def test_a_failing_purge_never_blocks_the_deletion(client: TestClient, email: FakeEmailSender, upstream: FakeUpstream, caplog) -> None:
    accounts = {name: make_member(client, email, name) for name in ("alice", "bob", "charlie")}
    identities = uids(client)
    as_admin(client)
    root = client.get("/api/auth/me").json()["id"]
    caplog.set_level(logging.INFO)

    def broken(request):
        raise httpx.ConnectError(f"transport failed for {request.url}", request=request)

    handlers = [
        lambda request: httpx.Response(502, json={"detail": "Long-term memory was not purged"}),
        lambda request: httpx.Response(307, headers={"location": "http://third-party.invalid" + request.url.path}),
        broken,
    ]
    for (name, account_id), handler in zip(accounts.items(), handlers):
        upstream.handler = handler
        upstream.requests.clear()
        # A caller's client setting must not let the uid follow a redirect.
        if name == "bob":
            client.app.state.upstream.follow_redirects = True
        assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
        assert name not in uids(client)
        sent = purges(upstream)
        assert len(sent) == 1 and sent[0].url.port == 29650
        errors = client.get("/api/logs/error", params={"actor": root}).json()
        if name != "bob":  # a redirect is not followed and is not an error status
            brain_error = next(entry for entry in errors if entry["source"] == "admin.brain_purge")
            assert f"deleted account '{name}'" in brain_error["message"]
        assert identities[name] not in str(errors)
        assert identities[name] not in caplog.text


def test_a_refused_deletion_does_not_purge(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    root_id = next(a["id"] for a in client.get("/api/admin/accounts").json() if a["username"] == ADMIN_USERNAME)
    upstream.requests.clear()

    assert client.delete(f"/api/admin/accounts/{root_id}").status_code == 409  # protected and your own account
    assert purges(upstream) == []
