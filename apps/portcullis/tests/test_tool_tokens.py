"""/api/admin/tool-tokens and /api/admin/stronghold-tool-tokens: needs settings.manage; a token is saved, used and never shown."""

from __future__ import annotations

import json

import httpx

from tests.test_admin import login, make_member
from tests.test_registration import as_admin


def test_own_tokens_are_saved_used_at_once_logged_without_the_value_and_never_returned(client_factory) -> None:
    root = client_factory()
    admin = as_admin(root)

    first = admin.get("/api/admin/tool-tokens").json()["services"]
    assert [row["name"] for row in first] == ["bard", "scribe"]

    saved = admin.put("/api/admin/tool-tokens", json={"bard": "bd-secret"})

    assert saved.status_code == 200 and "bd-secret" not in saved.text and "bd-secret" not in admin.get("/api/admin/tool-tokens").text
    assert {row["name"]: row["stored"] for row in saved.json()["services"]} == {"bard": True, "scribe": False}
    assert admin.app.state.bard_token == "bd-secret"
    uid = admin.get("/api/auth/me").json()["id"]
    logged = " ".join(entry["message"] for entry in admin.get("/api/logs/action", params={"actor": uid}).json())
    assert "Changed Portcullis tool service tokens (bard)" in logged and "bd-secret" not in logged

    removed = admin.put("/api/admin/tool-tokens", json={"bard": None})
    assert removed.json()["services"][0]["stored"] is False and admin.app.state.bard_token is None


def test_a_bad_token_change_is_refused(client_factory) -> None:
    admin = as_admin(client_factory())

    assert admin.put("/api/admin/tool-tokens", json={"made_up": "x"}).json()["detail"] == "Unknown tool service: made_up."
    assert admin.put("/api/admin/tool-tokens", json={"bard": "  "}).status_code == 400
    assert admin.put("/api/admin/tool-tokens", json={}).status_code == 400


def test_stronghold_tokens_pass_through_and_the_log_names_only_the_services(client_factory, upstream) -> None:
    def stronghold(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path": request.url.path, "method": request.method})

    upstream.handler = stronghold
    admin = as_admin(client_factory())

    assert admin.get("/api/admin/stronghold-tool-tokens").json()["path"] == "/admin/tool-tokens"
    changed = admin.put("/api/admin/stronghold-tool-tokens", json={"reader": "rd-secret"})
    assert changed.status_code == 200 and json.loads(upstream.requests[-1].content) == {"reader": "rd-secret"}
    uid = admin.get("/api/auth/me").json()["id"]
    logged = " ".join(entry["message"] for entry in admin.get("/api/logs/action", params={"actor": uid}).json())
    assert "Changed Stronghold tool service tokens (reader)" in logged and "rd-secret" not in logged


def test_every_tool_token_route_needs_settings_manage(client_factory, email, upstream) -> None:
    upstream.handler = lambda request: httpx.Response(200, json={})
    assert client_factory().get("/api/admin/tool-tokens").status_code == 401
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    served = len(upstream.requests)

    for method, path in [("get", "/api/admin/tool-tokens"), ("get", "/api/admin/stronghold-tool-tokens")]:
        assert getattr(member, method)(path).status_code == 403
    assert member.put("/api/admin/tool-tokens", json={"bard": "x"}).status_code == 403
    assert member.put("/api/admin/stronghold-tool-tokens", json={"bard": "x"}).status_code == 403
    assert len(upstream.requests) == served


def test_stronghold_usage_settings_pass_through_log_the_sections_and_need_settings_manage(client_factory, email, upstream) -> None:
    def stronghold(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path": request.url.path, "method": request.method})

    upstream.handler = stronghold
    admin = as_admin(client_factory())

    assert admin.get("/api/admin/stronghold-usage-settings").json()["path"] == "/admin/usage-settings"
    assert admin.put("/api/admin/stronghold-usage-settings", json={"usage": {"weekly_token_limit": 9}}).status_code == 200
    assert json.loads(upstream.requests[-1].content) == {"usage": {"weekly_token_limit": 9}}
    uid = admin.get("/api/auth/me").json()["id"]
    logged = " ".join(entry["message"] for entry in admin.get("/api/logs/action", params={"actor": uid}).json())
    assert "Changed Stronghold usage settings (usage)" in logged

    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.get("/api/admin/stronghold-usage-settings").status_code == 403
    assert member.put("/api/admin/stronghold-usage-settings", json={"usage": {}}).status_code == 403
