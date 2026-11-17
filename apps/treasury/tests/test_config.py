from pathlib import Path

import pytest

from src.cache import CacheSettings
from src.config import ConfigError, load_config, parse_connections

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def test_the_tracked_file_holds_only_where_treasury_listens_and_the_builtin_connections_parse():
    from src.config import DEFAULT_CONNECTIONS

    config = load_config(CONFIGS / "config_app.json")
    assert (config.host, config.port) == ("127.0.0.1", 29602)
    parsed = parse_connections({"connections": DEFAULT_CONNECTIONS}, config.default_cache)
    assert sorted(parsed.connections) == ["data", "main", "scratch", "stronghold"]
    assert parsed.connections["scratch"].cache.ttl_seconds == 0 and parsed.connections["scratch"].allow_raw_sql
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

    monkeypatch.setattr(config, "SETTINGS_DB", tmp_path / "settings.db")
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    settings_store.put(tmp_path / "settings.db", "connections", "other", {"type": "sqlite", "path": "o.db"})

    assert config.load_connections(CacheSettings()).instances == {}
    settings_store.put(tmp_path / "settings.db", "instances", "reports", ["other"])
    assert config.load_connections(CacheSettings()).instances == {"reports": ("other",)}


def test_saved_connections_and_cache_defaults_win_over_the_builtin_ones(tmp_path, monkeypatch):
    from src import config
    from src.citadel_auth import settings_store

    db = tmp_path / "settings.db"
    monkeypatch.setattr(config, "SETTINGS_DB", db)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    settings_store.put(db, "connections", "data", {"type": "sqlite", "path": "mine.db"})
    settings_store.put(db, "connections", "extra", {"type": "sqlite", "path": "x.db", "allow_raw_sql": True})
    settings_store.put(db, "settings", "default_cache", {"ttl_seconds": 7, "max_entries": 10, "negative_ttl_seconds": 1})

    loaded = config.load_connections(config.load_config().default_cache)

    assert sorted(loaded.connections) == ["data", "extra", "main", "scratch", "stronghold"]
    assert loaded.connections["data"].options["path"].endswith("mine.db")
    assert loaded.connections["extra"].allow_raw_sql and loaded.connections["main"].cache.ttl_seconds == 7
