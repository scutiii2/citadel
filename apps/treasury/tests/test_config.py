from pathlib import Path

import pytest

from src.cache import CacheSettings
from src.config import ConfigError, load_config, parse_connections

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def test_example_configs_parse():
    config = load_config(CONFIGS / "config_app.json.example")
    import json

    raw = json.loads((CONFIGS / "config_connections.json.example").read_text(encoding="utf-8"))
    parsed = parse_connections(raw, config.default_cache)
    assert parsed.instances["default"] == ("main", "scratch")
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
    assert load_config(CONFIGS / "config_app.json.example").port == 9999
    monkeypatch.setenv("DB_GATEWAY_PORT", "abc")
    with pytest.raises(ConfigError):
        load_config(CONFIGS / "config_app.json.example")
