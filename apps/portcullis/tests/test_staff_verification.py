"""Protected routes always require a verified email."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from src.models.account import Account
from src.models.role import Permission, Role
from src.routes.internal import _is_usable
from src.services import otp_service
from src.services.permissions import STAFF_PERMISSIONS
from tests.conftest import FakeEmailSender
from tests.test_admin import login, make_member, role_by_name
from tests.test_registration import as_admin


def _account(*permissions: str, verified: bool) -> Account:
    role = Role(name="r", permissions=[Permission(name=p, description="") for p in permissions])
    return Account(username="u", email="u@example.com", password_hash="x", email_verified=verified, roles=[role])


def test_unverified_accounts_lose_only_the_staff_permissions() -> None:
    assert _account("chat.use", "invites.manage", verified=False).permission_names == {"chat.use"}
    assert _account("chat.use", "invites.manage", verified=True).permission_names == {"chat.use", "invites.manage"}


def test_every_staff_permission_is_a_known_permission() -> None:
    from src.services.permissions import ALL_PERMISSIONS

    assert STAFF_PERMISSIONS <= set(ALL_PERMISSIONS)
    assert not {"chat.use", "tools.execute", "tickets.create", "files.upload"} & STAFF_PERMISSIONS


def test_an_unverified_account_cannot_be_given_a_staff_role(client: TestClient, email: FakeEmailSender) -> None:
    account_id = make_member(client, email, verify=False)
    as_admin(client)

    refused = client.put(f"/api/admin/accounts/{account_id}/roles/{role_by_name(client, 'Administrator')['id']}")

    assert refused.status_code == 409
    assert "verified its email" in refused.json()["detail"]


def test_a_verified_account_can_be_given_a_staff_role(client: TestClient, email: FakeEmailSender) -> None:
    account_id = make_member(client, email, verify=True)
    as_admin(client)

    granted = client.put(f"/api/admin/accounts/{account_id}/roles/{role_by_name(client, 'Administrator')['id']}")

    assert granted.status_code == 200


def test_only_an_active_verified_account_is_usable_internally() -> None:
    assert not _is_usable(None)
    unverified = _account("chat.use", verified=False)
    unverified.is_active = True
    assert not _is_usable(unverified)
    account = _account("chat.use", verified=True)
    account.is_active = True
    assert _is_usable(account)
    account.is_active = False
    assert not _is_usable(account)


def test_unverified_member_can_request_and_use_a_code(client, email, monkeypatch) -> None:
    make_member(client, email, verify=False, send_verification=False)
    login(client, "alice")
    monkeypatch.setattr(otp_service, "VERIFICATION_COOLDOWN", timedelta(seconds=30))
    assert [kind for kind, _, _ in email.sent] == ["invite"]

    forbidden = client.get("/api/admin/invites")
    assert forbidden.status_code == 403 and forbidden.json()["detail"] == "Email not verified"
    resent = client.post("/api/auth/verify-email/resend", json={})
    assert resent.status_code == 200 and resent.json() == {"sent": True}
    assert email.sent[-1][:2] == ("verify", "alice@example.com")
    cooldown = client.post("/api/auth/verify-email/resend", json={})
    assert cooldown.status_code == 429
    assert 1 <= int(cooldown.headers["retry-after"]) <= 30

    verified = client.post("/api/auth/verify-email", json={"code": email.last_code("verify")})
    assert verified.status_code == 200 and verified.json()["email_verified"] is True
    assert client.get("/api/admin/invites").json()["detail"] == "Missing permission: invites.manage"
