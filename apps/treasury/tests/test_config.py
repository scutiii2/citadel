from pathlib import Path

import pytest

from src.cache import CacheSettings
from src.config import ConfigError, load_config, parse_connections

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def test_tracked_configs_parse():
    config = load_config(CONFIGS / "config_app.json")
    import json

    raw = json.loads((CONFIGS / "config_connections.json").read_text(encoding="utf-8"))
    parsed = parse_connections(raw, config.default_cache)
    assert parsed.instances == {}
    assert parsed.connections["scratch"].cache.ttl_seconds == 0
    assert parsed.connections["main"].cache == config.default_cache


def test_instance_with_unknown_connection_is_rejected():
    raw = {"connections": {"a": {"type": "sqlite", "path": "x.db"}}, "instances": {"i": ["a", "zzz"]}}
    with pytest.raises(ConfigError, match="zzz"):
        parse_connections(raw, CacheSettings())


def test_placeholders_resolve_from_env():
    raw = {"connections": {"a": {"type": "sqlite", "path": "${DB_PATH}"}}}
    parsed = parse_connections(raw, CacheSettings(), {"DB_PATH": "real.db"})
    assert parsed.connections["a"].options["path"] == "real.db"
    with pytest.raises(ConfigError, match="MISSING"):
        parse_connections({"connections": {"a": {"type": "sqlite", "path": "${MISSING}"}}}, CacheSettings(), {})


def test_port_override(monkeypatch):
    monkeypatch.setenv("DB_GATEWAY_PORT", "9999")
    assert load_config(CONFIGS / "config_app.json").port == 9999
    monkeypatch.setenv("DB_GATEWAY_PORT", "abc")
    with pytest.raises(ConfigError):
        load_config(CONFIGS / "config_app.json")


def test_registered_instances_come_from_the_settings_database(tmp_path, monkeypatch):
    from src import config
    from src.citadel_auth import settings_store

    connections = tmp_path / "connections.json"
    connections.write_text('{"connections": {"main": {"type": "sqlite", "path": "m.db"}, "other": {"type": "sqlite", "path": "o.db"}}}', encoding="utf-8")
    monkeypatch.setattr(config, "SETTINGS_DB", tmp_path / "settings.db")
    monkeypatch.setattr(config, "CONNECTIONS_PATH", connections)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")

    assert config.load_connections(CacheSettings()).instances == {}
    settings_store.put(tmp_path / "settings.db", "instances", "reports", ["other"])
    assert config.load_connections(CacheSettings()).instances == {"reports": ("other",)}
