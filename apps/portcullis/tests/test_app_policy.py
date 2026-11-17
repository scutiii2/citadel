"""/api/admin/app-config: the policy settings are saved in Portcullis's settings database and used from the next start."""

from __future__ import annotations

from src.config import load_settings
from src.services import app_policy

from tests.test_admin import login, make_member
from tests.test_registration import as_admin


def test_the_defaults_are_listed_and_a_change_is_saved_for_the_next_start(client_factory) -> None:
    admin = as_admin(client_factory())

    first = admin.get("/api/admin/app-config").json()
    assert (first["session_hours"], first["default_role"], first["require_email_verification"]) == (12, "Member", True)
    assert first["rate_limit"]["max_attempts"] == 5 and (first["backup"]["keep"], first["backup"]["every_hours"]) == (14, 24)
    assert first["stored"] == []

    saved = admin.put("/api/admin/app-config", json={"session_hours": 4, "rate_limit": {"max_attempts": 3}})

    assert saved.status_code == 200 and saved.json()["applies"] == "next start"
    assert saved.json()["session_hours"] == 4 and saved.json()["stored"] == ["rate_limit", "session_hours"]
    assert saved.json()["rate_limit"] == {**first["rate_limit"], "max_attempts": 3}  # the rest of the group is kept
    assert admin.app.state.settings.session_hours == 12  # in use until Portcullis restarts
    uid = admin.get("/api/auth/me").json()["id"]
    logged = " ".join(entry["message"] for entry in admin.get("/api/logs/action", params={"actor": uid}).json())
    assert "Changed Portcullis settings (rate_limit, session_hours)" in logged


def test_what_was_saved_is_what_the_next_start_loads(client_factory, monkeypatch) -> None:
    admin = as_admin(client_factory())
    admin.put("/api/admin/app-config", json={
        "default_role": " Guest ", "ip_filter": {"deny_list": ["10.0.0.0/8"]}, "backup": {"keep": 3},
        "fingerprint": {"signals": ["user_agent"]}, "headers": {"hsts_max_age": 60},
    })
    settings = admin.app.state.settings
    path = admin.app.state.tool_tokens_db

    reloaded = app_policy.overlay({"security": {"trusted_proxies": ["127.0.0.1"]}}, path)

    assert reloaded["default_role"] == "Guest" and reloaded["backup"]["keep"] == 3
    assert reloaded["security"]["trusted_proxies"] == ["127.0.0.1"]
    assert reloaded["security"]["ip_filter"] == {"allow_list": [], "deny_list": ["10.0.0.0/8"]}
    assert reloaded["security"]["fingerprint"] == {"enabled": True, "signals": ["user_agent"]}
    assert reloaded["security"]["headers"] == {"enabled": True, "hsts_max_age": 60}
    assert settings.default_role == "Member"


def test_null_puts_a_setting_back_to_the_default(client_factory) -> None:
    admin = as_admin(client_factory())
    admin.put("/api/admin/app-config", json={"session_hours": 4})

    reset = admin.put("/api/admin/app-config", json={"session_hours": None})

    assert reset.json()["stored"] == [] and reset.json()["session_hours"] == 12


def test_a_bad_change_is_refused_and_saves_nothing(client_factory) -> None:
    admin = as_admin(client_factory())

    for bad in (
        {}, {"made_up": 1}, {"session_hours": 0}, {"session_hours": "12"}, {"session_hours": True},
        {"default_role": " "}, {"require_email_verification": "yes"},
        {"rate_limit": {"scope": "everyone"}}, {"rate_limit": {"max_attempts": 0}}, {"rate_limit": {"nope": 1}}, {"rate_limit": []},
        {"ip_filter": {"deny_list": ["not-an-address"]}}, {"ip_filter": {"allow_list": "10.0.0.1"}},
        {"headers": {"hsts_max_age": -1}}, {"fingerprint": {"signals": []}}, {"fingerprint": {"signals": ["cookie"]}},
        {"backup": {"keep": 0}}, {"backup": {"every_hours": 1.5}},
    ):
        refused = admin.put("/api/admin/app-config", json=bad)
        assert refused.status_code == 400 and refused.json()["detail"], bad
    mixed = admin.put("/api/admin/app-config", json={"session_hours": 6, "backup": {"keep": 0}})
    assert mixed.status_code == 400
    assert admin.get("/api/admin/app-config").json()["stored"] == []


def test_the_policy_routes_need_settings_manage(client_factory, email) -> None:
    assert client_factory().get("/api/admin/app-config").status_code == 401
    member = client_factory()
    make_member(member, email)
    login(member, "alice")

    assert member.get("/api/admin/app-config").status_code == 403
    assert member.put("/api/admin/app-config", json={"session_hours": 1}).status_code == 403
