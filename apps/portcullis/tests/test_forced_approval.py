"""Requiring approval for everyone: Armory owns the switch; Portcullis proxies it for the admin and relays it to
accounts and to every turn (what it does to a turn is tested with the pass-through routes and in Stronghold)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.models import AppSetting, LogEntry
from tests.conftest import FakeEmailSender, FakeUpstream
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/armory-tool-approval"
KEY = "force_tool_approval"


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

        assert client.get("/api/settings").json() == {KEY: False}
        assert client.get(URL).json()[KEY] is False

    def test_reading_needs_a_login(self, client: TestClient) -> None:
        assert client.get("/api/settings").status_code == 401

    def test_an_admin_turns_it_on_and_off_and_armory_keeps_it(self, client: TestClient, upstream: FakeUpstream) -> None:
        as_admin(client)

        force(client, True)
        assert upstream.force_tool_approval is True
        assert client.get("/api/settings").json() == {KEY: True}
        force(client, False)
        assert upstream.force_tool_approval is False
        assert client.get("/api/settings").json() == {KEY: False}

    def test_any_logged_in_account_can_read_it(self, client: TestClient, email: FakeEmailSender) -> None:
        as_admin(client)
        force(client)
        make_member(client, email)
        login(client, "alice")

        assert client.get("/api/settings").json() == {KEY: True}

    def test_only_an_admin_can_change_it(self, client: TestClient, email: FakeEmailSender, upstream: FakeUpstream) -> None:
        as_admin(client)
        make_member(client, email)
        login(client, "alice")

        assert client.put(URL, json={"value": True}).status_code == 403
        assert client.get(URL).status_code == 403
        assert upstream.force_tool_approval is False

    def test_a_logged_out_visitor_cannot_change_it(self, client: TestClient) -> None:
        assert client.put(URL, json={"value": True}).status_code == 401

    def test_the_old_settings_route_is_gone(self, client: TestClient) -> None:
        as_admin(client)

        assert client.put("/api/admin/settings/force_tool_approval", json={"value": True}).status_code in (404, 405)

    @pytest.mark.parametrize("value", ["yes", 1, None, [True]])
    def test_the_value_must_be_true_or_false(self, client: TestClient, value) -> None:
        as_admin(client)

        assert client.put(URL, json={"value": value}).status_code == 422

    def test_a_change_is_written_to_the_activity_log_with_the_old_value(self, client: TestClient) -> None:
        as_admin(client)

        force(client, True)
        force(client, False)

        assert log_messages(client, "admin.setting") == [f"{KEY}: off -> on", f"{KEY}: on -> off"]


class TestWhenArmoryCannotAnswer:
    def test_accounts_are_told_approval_is_required(self, client: TestClient, upstream: FakeUpstream) -> None:
        as_admin(client)
        upstream.armory_switch_status = 503

        assert client.get("/api/settings").json() == {KEY: True}

    def test_the_admin_sees_the_failure_instead_of_a_guess(self, client: TestClient, upstream: FakeUpstream) -> None:
        as_admin(client)
        upstream.armory_switch_status = 503

        assert client.get(URL).status_code == 502
        assert client.put(URL, json={"value": False}).status_code == 502


class TestCarryOverFromThePortcullisRow:
    """A switch stored here before Armory took the rule over is sent to Armory once, then dropped."""

    @staticmethod
    def leave_row(client: TestClient, value: str) -> None:
        async def go() -> None:
            async with client.app.state.database.sessions() as session:
                session.add(AppSetting(name=KEY, value=value))
                await session.commit()

        asyncio.run(go())

    @staticmethod
    def rows(client: TestClient) -> list[str]:
        async def go() -> list[str]:
            async with client.app.state.database.sessions() as session:
                return [row.name for row in await session.scalars(select(AppSetting))]

        return asyncio.run(go())

    def test_an_old_on_row_is_sent_to_armory_and_dropped(self, client: TestClient, upstream: FakeUpstream) -> None:
        as_admin(client)
        self.leave_row(client, "1")

        assert client.get("/api/settings").json() == {KEY: True}
        assert upstream.force_tool_approval is True
        assert self.rows(client) == []
        assert client.get("/api/settings").json() == {KEY: True}

    def test_an_old_off_row_is_just_dropped(self, client: TestClient, upstream: FakeUpstream) -> None:
        as_admin(client)
        self.leave_row(client, "0")

        assert client.get("/api/settings").json() == {KEY: False}
        assert upstream.force_tool_approval is False and upstream.armory_switch_stored is False
        assert self.rows(client) == []

    def test_a_switch_armory_already_holds_wins_over_an_old_row(self, client: TestClient, upstream: FakeUpstream) -> None:
        as_admin(client)
        force(client, False)
        self.leave_row(client, "1")

        assert client.get("/api/settings").json() == {KEY: False}
        assert self.rows(client) == [KEY]
