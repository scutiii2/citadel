from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from src.db import utcnow
from src.models import EmailVerificationCode, InviteCode
from src.services.otp_service import OtpService
from src.services.permissions import DEFAULT_ROLE_PERMISSIONS
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, FakeEmailSender


def as_admin(client: TestClient) -> TestClient:
    assert client.post(
        "/api/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    ).status_code == 200
    return client


def new_invite(client: TestClient, email: str = "alice@example.com") -> str:
    """Creates an invite as admin and returns its code; leaves the client logged out."""
    as_admin(client)
    response = client.post("/api/admin/invites", json={"invitee_email": email})
    assert response.status_code == 201, response.text
    client.post("/api/auth/logout", json={})
    return client.app.state.email_sender.last_code("invite")


def register(client: TestClient, code: str, username: str = "alice", email: str = "alice@example.com"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "long enough pw", "invite_code": code},
    )


def expire_all_invites(client: TestClient) -> None:
    async def run() -> None:
        async with client.app.state.database.sessions() as session:
            await session.execute(update(InviteCode).values(expires_at=utcnow() - timedelta(minutes=1)))
            await session.commit()

    client.portal.call(run)


# --- registration ------------------------------------------------------------


def test_registration_verifies_the_invited_email_without_a_second_code(client: TestClient, email: FakeEmailSender) -> None:
    response = register(client, new_invite(client), email="ALICE@Example.com")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"account"}
    assert body["account"]["email_verified"] is True
    assert body["account"]["roles"] == ["Member"]
    assert body["account"]["permissions"] == sorted(DEFAULT_ROLE_PERMISSIONS)
    assert client.get("/api/auth/me").json()["username"] == "alice"
    assert [kind for kind, _, _ in email.sent] == ["invite"]

    async def count_codes():
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(func.count()).select_from(EmailVerificationCode))

    assert client.portal.call(count_codes) == 0


def test_an_invite_refuses_a_different_email_and_remains_unused(client: TestClient) -> None:
    code = new_invite(client)
    refused = register(client, code, email="other@example.com")

    assert refused.status_code == 409
    assert refused.json() == {"detail": "This invite was sent to a different email address"}
    assert register(client, code).status_code == 201


def test_bad_invite_is_rejected(client: TestClient) -> None:
    assert register(client, "not-a-real-code").status_code == 400


def test_expired_invite_is_rejected(client: TestClient) -> None:
    code = new_invite(client)
    expire_all_invites(client)

    assert register(client, code).status_code == 400


def test_invite_lasts_a_week_but_verification_code_fifteen_minutes(client: TestClient) -> None:
    from datetime import datetime

    as_admin(client)
    invite = client.post("/api/admin/invites", json={"invitee_email": "alice@example.com"}).json()
    lifetime = datetime.fromisoformat(invite["expires_at"]) - datetime.fromisoformat(invite["created_at"])

    assert abs(lifetime - timedelta(days=7)) < timedelta(seconds=5)

    from src.services import otp_service

    assert otp_service.CODE_EXPIRY == timedelta(minutes=15)


def test_invite_works_only_once(client: TestClient) -> None:
    code = new_invite(client)
    assert register(client, code).status_code == 201
    client.post("/api/auth/logout", json={})

    assert register(client, code, username="bob", email="bob@example.com").status_code == 400


def test_a_stale_registration_cannot_claim_a_consumed_invite(client: TestClient) -> None:
    code = new_invite(client)

    async def claim_from_two_sessions():
        async with client.app.state.database.sessions() as first, client.app.state.database.sessions() as stale:
            first_otp, stale_otp = OtpService(first), OtpService(stale)
            invite = await first_otp.find_valid_invite(code)
            stale_invite = await stale_otp.find_valid_invite(code)
            assert invite is not None and stale_invite is not None
            assert await first_otp.claim_invite(invite)
            await first.commit()
            assert not await stale_otp.claim_invite(stale_invite)

    client.portal.call(claim_from_two_sessions)


def test_duplicate_username_and_email_keep_the_invite_unused(client: TestClient) -> None:
    assert register(client, new_invite(client)).status_code == 201
    client.post("/api/auth/logout", json={})
    other_invite = new_invite(client, "other@example.com")
    taken_name = register(client, other_invite, username="alice", email="other@example.com")
    assert taken_name.status_code == 409
    assert taken_name.json()["detail"] == "Username is already taken"
    assert register(client, other_invite, username="other", email="other@example.com").status_code == 201
    client.post("/api/auth/logout", json={})

    taken_email = register(client, new_invite(client), username="carol")
    assert taken_email.status_code == 409
    assert taken_email.json()["detail"] == "Email is already registered"


def test_invalid_registration_fields_are_rejected(client: TestClient) -> None:
    code = new_invite(client)

    assert register(client, code, username="a b").status_code == 422  # bad characters
    assert register(client, code, email="not-an-email").status_code == 422
    short = client.post(
        "/api/auth/register",
        json={"username": "dave", "email": "d@example.com", "password": "short", "invite_code": code},
    )
    assert short.status_code == 422


def test_registration_validation_does_not_echo_invite_codes(client: TestClient) -> None:
    code = new_invite(client)
    response = client.post("/api/auth/register", json={"invite_code": code})

    assert response.status_code == 422
    if code in response.text:
        pytest.fail("Validation errors exposed the invite code")


# --- email verification --------------------------------------------------------


def test_resend_when_already_verified_is_409(client: TestClient) -> None:
    as_admin(client)  # bootstrap admin is verified from the start

    assert client.post("/api/auth/verify-email/resend", json={}).status_code == 409


def test_invites_require_login(client: TestClient) -> None:
    assert client.get("/api/admin/invites").status_code == 401
    assert client.post("/api/admin/invites", json={}).status_code == 401
