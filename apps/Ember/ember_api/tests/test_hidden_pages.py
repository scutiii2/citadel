"""Hiding sidebar pages for everyone: GET /api/settings/pages, PUT /api/admin/settings/pages."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeEmailSender
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

READ = "/api/settings/pages"
WRITE = "/api/admin/settings/pages"


def hide(client: TestClient, pages: list[str]):
    return client.put(WRITE, json={"hidden": pages})


def test_nothing_is_hidden_by_default(client: TestClient) -> None:
    as_admin(client)

    assert client.get(READ).json() == {"hidden": []}


def test_reading_needs_a_login(client: TestClient) -> None:
    assert client.get(READ).status_code == 401


def test_an_admin_saves_and_every_account_reads(client: TestClient, email: FakeEmailSender) -> None:
    as_admin(client)
    saved = hide(client, ["/usage", "/agents", "/usage"])
    make_member(client, email)
    login(client, "alice")

    assert saved.status_code == 200 and saved.json() == {"hidden": ["/usage", "/agents"]}
    assert client.get(READ).json() == {"hidden": ["/usage", "/agents"]}


def test_saving_an_empty_list_shows_everything_again(client: TestClient) -> None:
    as_admin(client)
    hide(client, ["/usage"])

    assert hide(client, []).json() == {"hidden": []}
    assert client.get(READ).json() == {"hidden": []}


def test_only_an_admin_can_change_it(client: TestClient, email: FakeEmailSender) -> None:
    as_admin(client)
    make_member(client, email)
    login(client, "alice")

    assert hide(client, ["/usage"]).status_code == 403
    assert client.get(READ).json() == {"hidden": []}


def test_a_logged_out_visitor_cannot_change_it(client: TestClient) -> None:
    assert hide(client, ["/usage"]).status_code == 401


@pytest.mark.parametrize(
    "pages",
    [["/"], ["/settings"], ["usage"], ["/Bad"], ["/a/b"], ["/" + "a" * 40], [f"/p{i}" for i in range(21)], ["/usage", "/"]],
)
def test_bad_lists_are_refused_and_nothing_changes(client: TestClient, pages: list[str]) -> None:
    as_admin(client)
    hide(client, ["/tickets"])

    assert hide(client, pages).status_code in (400, 422)
    assert client.get(READ).json() == {"hidden": ["/tickets"]}


@pytest.mark.parametrize("body", [{}, {"hidden": "/usage"}, {"hidden": [1]}, {"hidden": [], "extra": 1}])
def test_the_body_must_be_a_list_of_page_ids(client: TestClient, body: dict) -> None:
    as_admin(client)

    assert client.put(WRITE, json=body).status_code == 422


def test_a_list_too_long_to_store_is_refused(client: TestClient) -> None:
    as_admin(client)
    long_ids = [f"/{'a' * 20}{i:02d}" for i in range(20)]

    assert hide(client, long_ids).status_code == 400


def test_the_change_is_logged(client: TestClient) -> None:
    as_admin(client)
    hide(client, ["/usage"])
    me = client.get("/api/auth/me").json()["id"]
    lines = [e["message"] for e in client.get("/api/logs/action", params={"actor": str(me)}).json()]

    assert any(line.startswith("Hidden sidebar pages") and "/usage" in line for line in lines)


def test_the_boolean_settings_list_is_unchanged(client: TestClient) -> None:
    as_admin(client)
    hide(client, ["/usage"])

    assert client.get("/api/settings").json() == {
        "force_tool_approval": False, "calendar_inapp": True, "calendar_email": True, "calendar_push": True,
    }
