from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import FakeEmailSender
from tests.test_admin import login, make_member, role_by_name
from tests.test_registration import as_admin


def forge_role_id(client: TestClient) -> int:
    """The id of a role holding only forge.use (made on first use). Call while logged in as admin."""
    existing = [r for r in client.get("/api/admin/roles").json() if r["name"] == "Forgers"]
    if existing:
        return existing[0]["id"]
    role = client.post("/api/admin/roles", json={"name": "Forgers"}).json()
    assert client.put(f"/api/admin/roles/{role['id']}/permissions/forge.use").status_code == 200
    return role["id"]


def make_forger(client: TestClient, email: FakeEmailSender, username: str = "alice") -> int:
    """A member who also holds forge.use (not settings.manage). Leaves the client logged out."""
    account_id = make_member(client, email, username)
    as_admin(client)
    assert client.put(f"/api/admin/accounts/{account_id}/roles/{forge_role_id(client)}").status_code == 200
    client.post("/api/auth/logout", json={})
    return account_id


def new_worker(client: TestClient, label: str = "claude", provider: str = "claude") -> dict:
    response = client.post("/api/forge/workers", json={"provider": provider, "label": label})
    assert response.status_code == 201, response.text
    return response.json()


def new_group(client: TestClient, title: str = "Build") -> dict:
    response = client.post("/api/forge/groups", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


# --- access --------------------------------------------------------------------------


def test_forge_routes_need_login_and_the_forge_permission(client: TestClient, email: FakeEmailSender) -> None:
    paths = [
        ("get", "/api/forge/workers"),
        ("get", "/api/forge/groups"),
        ("get", "/api/forge/plans"),
        ("post", "/api/forge/groups"),
        ("delete", "/api/forge/workers/1"),
    ]
    def call(method: str, path: str) -> int:
        return client.request(method.upper(), path, json={} if method == "post" else None).status_code

    for method, path in paths:
        assert call(method, path) == 401, path

    make_member(client, email)
    login(client, "alice")  # a plain member does not hold forge.use
    for method, path in paths:
        assert call(method, path) == 403, path


# --- workers -------------------------------------------------------------------------


def test_create_list_and_delete_a_worker(client: TestClient) -> None:
    as_admin(client)

    created = new_worker(client, "Claude")
    assert created["label"] == "claude" and created["token"].startswith("ft_")
    assert created["online"] is False and created["eligible"] is False
    assert created["problem"] == "Plan not eligible: not reported yet"

    listed = client.get("/api/forge/workers").json()
    assert [w["label"] for w in listed] == ["claude"]
    assert "token" not in listed[0]  # shown once only

    assert client.delete(f"/api/forge/workers/{created['id']}").status_code == 204
    assert client.get("/api/forge/workers").json() == []
    assert client.delete(f"/api/forge/workers/{created['id']}").status_code == 404


def test_worker_validation_and_conflicts(client: TestClient) -> None:
    as_admin(client)
    new_worker(client, "claude")

    assert client.post("/api/forge/workers", json={"provider": "claude", "label": "CLAUDE"}).status_code == 409
    assert client.post("/api/forge/workers", json={"provider": "claude", "label": "bad label"}).status_code == 422
    assert client.post("/api/forge/workers", json={"provider": "gemini", "label": "g"}).status_code == 422


def test_workers_are_private_to_their_account(client: TestClient, email: FakeEmailSender) -> None:
    make_forger(client, email, "alice")
    as_admin(client)
    theirs = new_worker(client, "root-worker")
    client.post("/api/auth/logout", json={})
    login(client, "alice")

    assert client.get("/api/forge/workers").json() == []
    assert client.delete(f"/api/forge/workers/{theirs['id']}").status_code == 404


# --- plans ---------------------------------------------------------------------------


def test_plan_allowlists_need_settings_manage_to_change(client: TestClient, email: FakeEmailSender) -> None:
    make_forger(client, email, "alice")
    login(client, "alice")
    assert client.get("/api/forge/plans").json() == {"claude": [], "codex": []}
    assert client.put("/api/forge/plans/claude", json={"plans": ["max"]}).status_code == 403

    client.post("/api/auth/logout", json={})
    as_admin(client)
    response = client.put("/api/forge/plans/claude", json={"plans": [" Max ", "pro", "max"]})
    assert response.status_code == 200 and response.json() == {"plans": ["max", "pro"]}
    assert client.get("/api/forge/plans").json() == {"claude": ["max", "pro"], "codex": []}
    assert client.put("/api/forge/plans/gemini", json={"plans": []}).status_code == 404
    assert client.put("/api/forge/plans/claude", json={"plans": ["x"] * 13}).status_code == 422


# --- groups --------------------------------------------------------------------------


def test_create_update_and_delete_a_group(client: TestClient) -> None:
    as_admin(client)

    group = new_group(client, "  Build   site ")
    assert (group["title"], group["mode"], group["relay"], group["running"], group["members"]) == (
        "Build site", "ask", False, False, [],
    )
    gid = group["id"]
    assert [g["id"] for g in client.get("/api/forge/groups").json()] == [gid]
    assert client.get(f"/api/forge/groups/{gid}").json()["title"] == "Build site"

    updated = client.patch(f"/api/forge/groups/{gid}", json={"title": "Site", "mode": "plan", "relay": True})
    assert updated.status_code == 200
    assert (updated.json()["title"], updated.json()["mode"], updated.json()["relay"]) == ("Site", "plan", True)

    assert client.delete(f"/api/forge/groups/{gid}").status_code == 204
    assert client.get(f"/api/forge/groups/{gid}").status_code == 404


def test_group_validation(client: TestClient) -> None:
    as_admin(client)

    assert client.post("/api/forge/groups", json={"title": "   "}).status_code == 422
    assert client.post("/api/forge/groups", json={"title": "ok", "mode": "full_auto"}).status_code == 422
    gid = new_group(client)["id"]
    assert client.patch(f"/api/forge/groups/{gid}", json={}).status_code == 422
    assert client.patch(f"/api/forge/groups/{gid}", json={"mode": "yolo"}).status_code == 422


def test_full_auto_needs_explicit_confirmation_and_is_announced(client: TestClient) -> None:
    as_admin(client)
    gid = new_group(client)["id"]

    assert client.patch(f"/api/forge/groups/{gid}", json={"mode": "full_auto"}).status_code == 422
    ok = client.patch(f"/api/forge/groups/{gid}", json={"mode": "full_auto", "confirm_full_auto": True})
    assert ok.status_code == 200 and ok.json()["mode"] == "full_auto"
    messages = client.get(f"/api/forge/groups/{gid}/messages").json()
    assert [(m["kind"], m["sender"]) for m in messages] == [("system", "system")]
    assert "Full auto" in messages[0]["body"]["text"]


def test_groups_are_private_to_their_account(client: TestClient, email: FakeEmailSender) -> None:
    make_forger(client, email, "alice")
    as_admin(client)
    gid = new_group(client)["id"]
    client.post("/api/auth/logout", json={})
    login(client, "alice")

    assert client.get("/api/forge/groups").json() == []
    assert client.get(f"/api/forge/groups/{gid}").status_code == 404
    assert client.patch(f"/api/forge/groups/{gid}", json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/forge/groups/{gid}").status_code == 404
    assert client.post(f"/api/forge/groups/{gid}/workers", json={"worker_id": 1, "folder": "C:/x"}).status_code == 404


def test_inviting_needs_an_eligible_worker_of_your_own(client: TestClient) -> None:
    as_admin(client)
    gid = new_group(client)["id"]
    worker = new_worker(client)  # no plan reported yet, and no plan is allowed

    refused = client.post(f"/api/forge/groups/{gid}/workers", json={"worker_id": worker["id"], "folder": "C:/x"})
    assert refused.status_code == 409 and "Plan not eligible" in refused.json()["detail"]
    assert client.post(f"/api/forge/groups/{gid}/workers", json={"worker_id": 9999, "folder": "C:/x"}).status_code == 404


def test_removing_a_worker_that_is_not_a_member_is_a_404(client: TestClient) -> None:
    as_admin(client)
    gid = new_group(client)["id"]
    worker = new_worker(client)

    assert client.delete(f"/api/forge/groups/{gid}/workers/{worker['id']}").status_code == 404
