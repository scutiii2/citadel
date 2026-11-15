"""What Portcullis still owns of the calendar: the permission and the admin channel switches."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.services.permissions import CALENDAR_USE, is_known_permission
from tests.test_registration import as_admin


def test_permission_is_known() -> None:
    assert is_known_permission(CALENDAR_USE) and CALENDAR_USE == "calendar.use"


def test_administrator_holds_calendar_use(client: TestClient) -> None:
    as_admin(client)
    assert CALENDAR_USE in client.get("/api/auth/me").json()["permissions"]


def test_channel_switches_default_on_and_admin_can_flip(client: TestClient) -> None:
    as_admin(client)
    body = client.get("/api/settings").json()
    assert [body[n] for n in ("calendar_inapp", "calendar_email", "calendar_push")] == [True, True, True]
    assert client.put("/api/admin/settings/calendar_push", json={"value": False}).json() == {"calendar_push": False}
    assert client.get("/api/settings").json()["calendar_push"] is False
