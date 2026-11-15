"""/api/skills: Portcullis checks the login and chat.use; Stronghold answers."""

import json
import logging

import httpx
import pytest

from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/skills"
EDIT = {"title": "Reboot an app", "when_to_use": "an app freezes", "steps": "kill it, then launch it", "tools": "tool_srv_restartApp"}


def stronghold(request: httpx.Request) -> httpx.Response:
    if request.method == "DELETE":
        return httpx.Response(204)
    return httpx.Response(200, json={"path": request.url.path})


def test_skills_require_login(client):
    assert client.get(URL).status_code == 401
    assert client.put(f"{URL}/1/status", json={"status": "active"}).status_code == 401
    assert client.put(f"{URL}/1", json=EDIT).status_code == 401
    assert client.delete(f"{URL}/1").status_code == 401


def test_skills_require_a_verified_account(client, email):
    make_member(client, email, "alice", verify=False)
    login(client, "alice")
    assert client.get(URL).status_code == 403


def test_skills_require_chat_permission_on_every_action(client, email, upstream):
    alice = make_member(client, email, "alice")
    as_admin(client)
    member = next(role for role in client.get("/api/admin/roles").json() if role["name"] == "Member")
    assert client.delete(f"/api/admin/accounts/{alice}/roles/{member['id']}").status_code == 200
    client.post("/api/auth/logout", json={})
    login(client, "alice")
    upstream.requests.clear()
    assert client.get(URL).status_code == 403
    assert client.put(f"{URL}/1/status", json={"status": "active"}).status_code == 403
    assert client.put(f"{URL}/1", json=EDIT).status_code == 403
    assert client.delete(f"{URL}/1").status_code == 403
    assert not upstream.requests


def test_every_skills_route_goes_to_stronghold_as_the_signed_in_account(client, upstream):
    upstream.handler = stronghold
    as_admin(client)
    uid = uids(client)["root"]
    upstream.requests.clear()

    assert client.get(URL).json() == {"path": "/skills"}
    assert client.put(f"{URL}/1/status", json={"status": "active"}).json() == {"path": "/skills/1/status"}
    assert client.put(f"{URL}/1", json=EDIT).json() == {"path": "/skills/1"}
    assert client.delete(f"{URL}/1").status_code == 204

    assert all(request.headers["x-requester-uid"] == uid for request in upstream.requests)
    assert json.loads(upstream.requests[2].content) == EDIT
    assert len(upstream.requests) == 4


def test_a_refusal_from_stronghold_passes_through(client, upstream):
    upstream.handler = lambda request: httpx.Response(409, json={"detail": "Another skill already has that title."})
    as_admin(client)

    refused = client.put(f"{URL}/1", json=EDIT)

    assert (refused.status_code, refused.json()["detail"]) == (409, "Another skill already has that title.")


@pytest.mark.parametrize("path", ["0", "-1", "abc", "accounts", "0/status"])
def test_malformed_ids_and_the_purge_route_do_not_reach_stronghold(client, upstream, path):
    upstream.handler = stronghold
    as_admin(client)
    upstream.requests.clear()

    assert client.put(f"{URL}/{path}", json=EDIT).status_code == 422
    assert client.delete(f"{URL}/accounts/someone").status_code in (404, 405)
    assert not upstream.requests


def test_deleting_an_account_purges_its_skills_once(client, email, upstream, caplog):
    upstream.handler = stronghold
    alice = make_member(client, email, "alice")
    as_admin(client)
    uid = uids(client)["alice"]
    upstream.requests.clear()
    caplog.set_level(logging.INFO)

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    assert [r.method for r in upstream.requests if r.url.path == f"/skills/accounts/{uid}"] == ["DELETE"]
    assert uid not in caplog.text


def test_a_failing_skills_purge_never_blocks_the_deletion(client, email, upstream):
    alice = make_member(client, email, "alice")
    uid = uids(client)["alice"]
    as_admin(client)
    root = client.get("/api/auth/me").json()["id"]
    upstream.handler = lambda request: httpx.Response(502, json={"detail": "Skills were not purged"})

    assert client.delete(f"/api/admin/accounts/{alice}").status_code == 204

    errors = client.get("/api/logs/error", params={"actor": root}).json()
    assert any(entry["source"] == "admin.skills_purge" and "'alice'" in entry["message"] for entry in errors)
    assert uid not in str(errors)
