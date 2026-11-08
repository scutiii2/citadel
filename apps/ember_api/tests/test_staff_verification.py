"""Staff permissions need a verified email, even when require_email_verification is off."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.models.account import Account
from src.models.role import Permission, Role
from src.services.permissions import STAFF_PERMISSIONS
from tests.conftest import FakeEmailSender
from tests.test_admin import make_member, role_by_name
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
