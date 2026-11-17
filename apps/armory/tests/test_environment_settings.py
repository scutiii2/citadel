"""Deployment values edited at run time: stored in settings.db, used at once, secrets never shown."""

from __future__ import annotations

import dataclasses
import warnings
from pathlib import Path

import pytest
from starlette.applications import Starlette

warnings.filterwarnings("ignore", category=DeprecationWarning)
from starlette.testclient import TestClient  # noqa: E402

from src import config, environment_settings  # noqa: E402
from src.citadel_auth import settings_store  # noqa: E402
from src.environment_routes import install_environment_routes  # noqa: E402


@pytest.fixture
def live(tmp_path, monkeypatch):
    """A private Settings object, as the routes see it, with its own settings.db."""
    current = dataclasses.replace(config.Settings(), settings_db_path=tmp_path / "settings.db")
    monkeypatch.setattr(config, "settings", current)
    return current


@pytest.fixture
def client(live):
    app = Starlette()
    install_environment_routes(app)
    with TestClient(app) as test_client:
        yield test_client


def row(body: dict, field: str) -> dict:
    return next(item for item in body["settings"] if item["field"] == field)


def test_stored_values_win_over_the_defaults_and_bad_ones_are_skipped(tmp_path):
    path = tmp_path / "settings.db"
    settings_store.put(path, "environment", "firecrawl_api_url", "http://firecrawl:3002")
    settings_store.put(path, "environment", "vault_dir", "/data/vault")
    settings_store.put(path, "environment", "obsidian_timeout", -1)
    settings_store.put(path, "environment", "no_such_setting", "x")

    result = environment_settings.overlay(config.Settings(), path)

    assert result.firecrawl_api_url == "http://firecrawl:3002"
    assert result.vault_dir == Path("/data/vault")
    assert result.obsidian_timeout == config.Settings().obsidian_timeout


def test_a_change_is_saved_used_at_once_and_reset_puts_the_default_back(client, live):
    default = config.Settings().firecrawl_api_url

    saved = client.put("/admin/environment", json={"firecrawl_api_url": " http://firecrawl:3002 ", "obsidian_allow_write": True})

    assert saved.status_code == 200 and saved.json()["restart"] == []
    assert live.firecrawl_api_url == "http://firecrawl:3002" and live.obsidian_allow_write is True
    assert row(saved.json(), "firecrawl_api_url")["stored"] is True
    assert environment_settings.stored(live.settings_db_path)["firecrawl_api_url"] == "http://firecrawl:3002"

    reset = client.put("/admin/environment", json={"firecrawl_api_url": None})

    assert live.firecrawl_api_url == default and row(reset.json(), "firecrawl_api_url")["stored"] is False


def test_a_setting_read_once_is_reported_as_needing_a_restart(client):
    answer = client.put("/admin/environment", json={"laya_url": "http://legion:29611/mcp", "firecrawl_api_url": "http://s:1"})

    assert answer.json()["restart"] == ["laya_url"]


def test_secrets_are_never_returned(client, live):
    answer = client.put("/admin/environment", json={"media_signing_key": "s3cret-key", "obsidian_api_key": "k"})

    assert "s3cret-key" not in answer.text and "s3cret-key" not in client.get("/admin/environment").text
    assert row(answer.json(), "media_signing_key") == {
        **row(answer.json(), "media_signing_key"), "secret": True, "has_value": True, "stored": True}
    assert "value" not in row(answer.json(), "media_signing_key")
    assert live.media_signing_key == "s3cret-key"


@pytest.mark.parametrize("changes", [
    {"firecrawl_api_url": "ftp://x"},
    {"firecrawl_api_url": "http://user:pw@host"},
    {"obsidian_timeout": 0},
    {"obsidian_verify_tls": "yes"},
    {"vault_dir": "  "},
    {"made_up": "x"},
    {},
])
def test_a_refused_change_saves_nothing(client, live, changes):
    before = live.firecrawl_api_url

    answer = client.put("/admin/environment", json={"laya_url": "http://ok:1/mcp", **changes} if changes else changes)

    assert answer.status_code == 400 and answer.json()["error"]
    assert live.firecrawl_api_url == before and live.laya_url == config.Settings().laya_url
    assert environment_settings.stored(live.settings_db_path) == {}


def test_the_body_must_be_an_object(client):
    assert client.put("/admin/environment", json=["a"]).status_code == 400
    assert client.put("/admin/environment", content=b"nope").status_code == 400


def test_email_settings_are_saved_checked_and_the_password_is_never_returned(client, live):
    assert client.get("/admin/email").json() == {"configured": False}

    saved = client.put("/admin/email", json={"smtp_server": "smtp.example.com", "smtp_port": 587,
                                             "from": "a@example.com", "password": "p4ss", "to": ["b@example.com"]})

    assert saved.status_code == 200 and "p4ss" not in saved.text
    assert saved.json() == {"configured": True, "smtp_server": "smtp.example.com", "smtp_port": 587, "security": "",
                            "from": "a@example.com", "to": ["b@example.com"], "allowed_recipient_domains": [],
                            "has_password": True}
    assert "p4ss" not in client.get("/admin/email").text
    changed = client.put("/admin/email", json={"password": None, "smtp_port": 465})
    assert changed.json()["has_password"] is False and changed.json()["smtp_port"] == 465


def test_a_bad_email_change_is_refused_with_the_reason_and_saves_nothing(client, live):
    client.put("/admin/email", json={"smtp_server": "smtp.example.com", "smtp_port": 587, "from": "a@example.com"})

    for bad in ({"smtp_port": "abc"}, {"security": "tls"}, {"from": None}, {"made_up": 1}):
        refused = client.put("/admin/email", json=bad)
        assert refused.status_code == 400 and refused.json()["error"]
    assert client.get("/admin/email").json()["smtp_port"] == 587
    assert client.put("/admin/email", json=[]).status_code == 400


def test_web_research_keys_are_editable_secrets_used_at_once(client, live):
    answer = client.put("/admin/environment", json={"tavily_api_key": "tvly-1", "firecrawl_api_key": "fc-1",
                                                    "firecrawl_api_url": "http://firecrawl:3002"})

    assert answer.json()["restart"] == [] and "tvly-1" not in answer.text and "fc-1" not in answer.text
    assert row(answer.json(), "tavily_api_key")["has_value"] is True
    assert row(answer.json(), "firecrawl_api_url")["value"] == "http://firecrawl:3002"
    assert (live.tavily_api_key, live.firecrawl_api_key) == ("tvly-1", "fc-1")


def test_limits_start_at_the_defaults_and_a_change_keeps_the_rest(client, live):
    first = client.get("/admin/tuning").json()
    assert first["pdf_merger"]["limits"]["max_file_mb"] == 100 and first["pdf_merger"]["stored"] is False
    assert first["media_downloader"]["limits"]["max_caller_downloads"] == 2

    saved = client.put("/admin/tuning/pdf_merger", json={"file_ttl_hours": 12, "limits": {"max_file_mb": 250}})

    assert saved.status_code == 200 and saved.json()["applies"] == "next start"
    pdf = saved.json()["pdf_merger"]
    assert (pdf["file_ttl_hours"], pdf["limits"]["max_file_mb"], pdf["limits"]["max_segments"], pdf["stored"]) == (12, 250, 50, True)
    assert saved.json()["media_downloader"]["stored"] is False

    again = client.put("/admin/tuning/pdf_merger", json={"limits": {"max_segments": 10}}).json()["pdf_merger"]
    assert (again["file_ttl_hours"], again["limits"]["max_file_mb"], again["limits"]["max_segments"]) == (12, 250, 10)


def test_unusable_limits_are_refused_and_save_nothing(client, live):
    for name, bad in [
        ("pdf_merger", {"mcp_wait_seconds": 121}), ("pdf_merger", {"file_ttl_hours": 0}),
        ("pdf_merger", {"limits": {"max_concurrent_merges": 0}}), ("pdf_merger", {"made_up": 1}),
        ("pdf_merger", {"limits": {"nope": 1}}), ("pdf_merger", {"file_ttl_hours": "6"}), ("pdf_merger", {}),
        ("media_downloader", {"limits": {"max_caller_downloads": 0}}), ("media_downloader", {"limits": {"max_caller_downloads": 1.5}}),
        ("media_downloader", {"mcp_wait_seconds": 5}), ("nothing", {"file_ttl_hours": 1}),
    ]:
        refused = client.put(f"/admin/tuning/{name}", json=bad)
        assert refused.status_code == 400 and refused.json()["error"], (name, bad)
    assert client.get("/admin/tuning").json()["pdf_merger"]["stored"] is False
    assert client.put("/admin/tuning/pdf_merger", json=[1]).status_code == 400


def test_reset_puts_the_defaults_back(client, live):
    client.put("/admin/tuning/media_downloader", json={"limits": {"max_file_mb": 50}})

    reset = client.delete("/admin/tuning/media_downloader")

    assert reset.status_code == 200
    media = reset.json()["media_downloader"]
    assert media["limits"]["max_file_mb"] == 500 and media["stored"] is False
    assert client.delete("/admin/tuning/nothing").status_code == 400
