from src.services.permissions import ALL_PERMISSIONS, BARD_ADMIN, BARD_DELETE, STAFF_PERMISSIONS
from tests.conftest import ADMIN_USERNAME
from tests.test_permission_split import limited_account
from tests.test_registration import as_admin

TOKEN = "bard-internal"
HEADERS = {"X-Internal-Token": TOKEN}


def check(client, username, headers=HEADERS):
    return client.post("/api/bard/internal/admin-check", headers=headers, json={"username": username})


def test_bard_admin_is_a_known_staff_permission():
    assert BARD_ADMIN == "bard.admin"
    assert BARD_ADMIN in ALL_PERMISSIONS
    assert BARD_ADMIN in STAFF_PERMISSIONS


def test_admin_check_needs_the_internal_token(client):
    client.app.state.internal_token = TOKEN
    assert check(client, ADMIN_USERNAME, headers={}).status_code == 401
    assert check(client, ADMIN_USERNAME, headers={"X-Internal-Token": "wrong"}).status_code == 401


def test_admin_check_refuses_everything_when_no_token_is_configured(client):
    client.app.state.internal_token = ""
    assert check(client, ADMIN_USERNAME, headers={"X-Internal-Token": ""}).status_code == 401


def test_the_administrator_role_holds_bard_admin(client):
    client.app.state.internal_token = TOKEN
    assert check(client, ADMIN_USERNAME).json() == {"admin": True}


def test_unknown_usernames_answer_like_non_admins(client):
    client.app.state.internal_token = TOKEN
    assert check(client, "nobody-here").json() == {"admin": False}
    assert check(client, "").status_code == 422


def test_a_member_becomes_admin_when_the_permission_is_granted_and_stops_when_it_is_revoked(client, email):
    client.app.state.internal_token = TOKEN
    _, role_id = limited_account(client, email, "tools.execute")
    assert check(client, "alice").json() == {"admin": False}
    as_admin(client)
    assert client.put(f"/api/admin/roles/{role_id}/permissions/{BARD_ADMIN}").status_code == 200
    assert check(client, "alice").json() == {"admin": True}
    assert client.delete(f"/api/admin/roles/{role_id}/permissions/{BARD_ADMIN}").status_code == 200
    assert check(client, "alice").json() == {"admin": False}


def test_bard_delete_is_its_own_staff_permission_and_admin_does_not_imply_it(client, email):
    assert BARD_DELETE == "bard.delete"
    assert BARD_DELETE in ALL_PERMISSIONS and BARD_DELETE in STAFF_PERMISSIONS
    client.app.state.internal_token = TOKEN
    limited_account(client, email, BARD_ADMIN)

    def can_delete(username):
        body = {"username": username, "permission": BARD_DELETE}
        return client.post("/api/bard/internal/admin-check", headers=HEADERS, json=body).json()

    assert check(client, "alice").json() == {"admin": True}
    assert can_delete("alice") == {"admin": False}
    assert can_delete(ADMIN_USERNAME) == {"admin": True}


def test_admin_check_refuses_other_permissions(client):
    client.app.state.internal_token = TOKEN
    body = {"username": ADMIN_USERNAME, "permission": "accounts.manage"}
    assert client.post("/api/bard/internal/admin-check", headers=HEADERS, json=body).status_code == 422


def test_a_disabled_account_is_not_admin(client, email):
    client.app.state.internal_token = TOKEN
    account_id, role_id = limited_account(client, email, BARD_ADMIN)
    assert check(client, "alice").json() == {"admin": True}
    as_admin(client)
    assert client.patch(f"/api/admin/accounts/{account_id}", json={"is_active": False}).status_code == 200
    assert check(client, "alice").json() == {"admin": False}
