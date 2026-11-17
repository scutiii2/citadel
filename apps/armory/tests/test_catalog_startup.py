import runpy
from pathlib import Path

from src import config, environment_settings
from src.citadel_auth import settings_store


def test_treasury_bootstrap_uses_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TREASURY_URL", "http://treasury.test:29602")
    monkeypatch.setenv("MCP_SETTINGS_DB_PATH", str(tmp_path / "settings.db"))
    loaded = runpy.run_path(config.__file__)
    assert loaded["settings"].treasury_url == "http://treasury.test:29602"


def test_peer_addresses_are_not_editable_and_stale_rows_are_deleted(tmp_path):
    db = tmp_path / "settings.db"
    settings_store.put(db, "environment", "stronghold_url", "http://old:1")
    settings_store.put(db, "environment", "db_gateway_url", "http://old:2")
    current = environment_settings.overlay(config.Settings(), db)
    fields = {row["field"] for row in environment_settings.view(current, db)["settings"]}
    assert not fields & {"stronghold_url", "db_gateway_url"}
    assert settings_store.read_all(db, "environment") == {}
