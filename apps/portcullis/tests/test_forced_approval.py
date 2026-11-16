"""Requiring approval for everyone: the admin switch (what it does to a turn is tested with the pass-through
routes and in Stronghold)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.models import AppSetting, LogEntry
from src.services.settings_service import FORCE_TOOL_APPROVAL, SettingsService, UnknownSetting
from tests.conftest import FakeEmailSender
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = f"/api/admin/settings/{FORCE_TOOL_APPROVAL}"


def force(client: TestClient, on: bool = True) -> None:
    assert client.put(URL, json={"value": on}).status_code == 200


def log_messages(client: TestClient, source: str) -> list[str]:
    async def read() -> list[str]:
        async with client.app.state.database.sessions() as session:
            return [row.message for row in await session.scalars(select(LogEntry).where(LogEntry.source == source))]

    return asyncio.run(read())


class TestTheSwitch:
    def test_it_is_off_by_default(self, client: TestClient) -> None:
        as_admin(client)

        assert client.get("/api/settings").json() == {FORCE_TOOL_APPROVAL: False, "calendar_inapp": True, "calendar_email": True, "calendar_push": True}

    def test_reading_needs_a_login(self, client: TestClient) -> None:
        assert client.get("/api/settings").status_code == 401

    def test_an_admin_turns_it_on_and_off(self, client: TestClient) -> None:
        as_admin(client)

        force(client, True)
        assert client.get("/api/settings").json() == {FORCE_TOOL_APPROVAL: True, "calendar_inapp": True, "calendar_email": True, "calendar_push": True}
        force(client, False)
        assert client.get("/api/settings").json() == {FORCE_TOOL_APPROVAL: False, "calendar_inapp": True, "calendar_email": True, "calendar_push": True}

    def test_any_logged_in_account_can_read_it(self, client: TestClient, email: FakeEmailSender) -> None:
        as_admin(client)
        force(client)
        make_member(client, email)
        login(client, "alice")

        assert client.get("/api/settings").json() == {FORCE_TOOL_APPROVAL: True, "calendar_inapp": True, "calendar_email": True, "calendar_push": True}

    def test_only_an_admin_can_change_it(self, client: TestClient, email: FakeEmailSender) -> None:
        as_admin(client)
        make_member(client, email)
        login(client, "alice")

        assert client.put(URL, json={"value": True}).status_code == 403
        assert client.get("/api/settings").json() == {FORCE_TOOL_APPROVAL: False, "calendar_inapp": True, "calendar_email": True, "calendar_push": True}

    def test_a_logged_out_visitor_cannot_change_it(self, client: TestClient) -> None:
        assert client.put(URL, json={"value": True}).status_code == 401

    def test_an_unknown_setting_is_not_found(self, client: TestClient) -> None:
        as_admin(client)

        assert client.put("/api/admin/settings/nonsense", json={"value": True}).status_code == 404

    @pytest.mark.parametrize("value", ["yes", 1, None, [True]])
    def test_the_value_must_be_true_or_false(self, client: TestClient, value) -> None:
        as_admin(client)

        assert client.put(URL, json={"value": value}).status_code == 422

    def test_a_change_is_written_to_the_activity_log_with_the_old_value(self, client: TestClient) -> None:
        as_admin(client)

        force(client, True)
        force(client, False)

        assert log_messages(client, "admin.setting") == [
            f"{FORCE_TOOL_APPROVAL}: off -> on",
            f"{FORCE_TOOL_APPROVAL}: on -> off",
        ]

    def test_it_is_stored_in_the_database(self, client: TestClient) -> None:
        as_admin(client)
        force(client)

        async def read() -> list[tuple[str, str]]:
            async with client.app.state.database.sessions() as session:
                return [(r.name, r.value) for r in await session.scalars(select(AppSetting))]

        assert asyncio.run(read()) == [(FORCE_TOOL_APPROVAL, "1")]


class TestSettingsService:
    def test_set_returns_the_value_it_replaced(self, client: TestClient) -> None:
        async def go() -> list[bool]:
            async with client.app.state.database.sessions() as session:
                service = SettingsService(session)
                return [
                    await service.set_bool(FORCE_TOOL_APPROVAL, True),
                    await service.set_bool(FORCE_TOOL_APPROVAL, True),
                    await service.set_bool(FORCE_TOOL_APPROVAL, False),
                ]

        assert asyncio.run(go()) == [False, True, True]

    def test_an_unknown_name_is_refused(self, client: TestClient) -> None:
        async def go() -> None:
            async with client.app.state.database.sessions() as session:
                await SettingsService(session).get_bool("nonsense")

        with pytest.raises(UnknownSetting):
            asyncio.run(go())
