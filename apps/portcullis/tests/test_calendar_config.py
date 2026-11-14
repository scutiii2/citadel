"""Calendar config block, permission and admin channel switches."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import CalendarSettings
from src.services.permissions import CALENDAR_USE, is_known_permission
from tests.test_registration import as_admin


def test_defaults_match_the_spec() -> None:
    s = CalendarSettings.from_config({})
    assert (s.enabled, s.tick_seconds, s.feed_refresh_minutes, s.lookahead_hours) == (True, 30, 10, 48)
    assert (s.late_grace_minutes, s.max_feeds_per_account, s.max_alarm_rules) == (5, 10, 10)
    assert (s.max_ics_bytes, s.fetch_timeout_s, s.allow_private_urls) == (5242880, 15, False)


def test_values_are_read_and_validated() -> None:
    assert CalendarSettings.from_config({"tick_seconds": 5, "enabled": False}).tick_seconds == 5
    for bad in ({"tick_seconds": 0}, {"max_ics_bytes": -1}, {"push_contact": "nobody"}):
        with pytest.raises(ValueError):
            CalendarSettings.from_config(bad)


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


def test_push_over_plain_http_on_a_reachable_host_is_a_warning(tmp_path) -> None:
    import dataclasses

    from src.services.config_validation import _check_deployment
    from tests.conftest import make_settings

    reachable = dataclasses.replace(make_settings(tmp_path), host="0.0.0.0")
    assert any(key == "calendar.enabled" for key, _ in _check_deployment(reachable))
    assert not any(key == "calendar.enabled" for key, _ in _check_deployment(make_settings(tmp_path)))
