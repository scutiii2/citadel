import json

import pytest

from src.config import ConfigError, load_config, parse_config
from tests.conftest import EXAMPLE_CONFIG


def test_example_config_loads(config):
    assert config.port == 8060
    assert config.situation_source == "heuristic"
    assert config.emblem_prompt_seconds == 5.0
    assert config.database_path.name == "ascension.sqlite3"


@pytest.fixture
def raw():
    return json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))


def test_unknown_situation_source_is_rejected(raw):
    raw["situation_source"] = "magic"
    with pytest.raises(ConfigError, match="situation_source"):
        parse_config(raw)


def test_bool_is_not_a_number(raw):
    raw["port"] = True
    with pytest.raises(ConfigError, match="port"):
        parse_config(raw)


def test_confidence_above_one_is_rejected(raw):
    raw["laya_min_confidence"] = 1.5
    with pytest.raises(ConfigError, match="at most"):
        parse_config(raw)


def test_missing_field_is_rejected(raw):
    del raw["host"]
    with pytest.raises(ConfigError, match="host"):
        parse_config(raw)


def test_unreadable_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.json")



def host_values():
    return {"ember_api_url": "http://127.0.0.1:8030", "ember_origin": "http://127.0.0.1:5173", "session_hours": 8, "game_id": "ascension", "dev_fake_owner": ""}


def test_game_host_settings_are_typed_and_dev_owner_is_off(raw):
    raw.update(host_values())
    config = parse_config(raw)
    assert config.ember_api_url == "http://127.0.0.1:8030"
    assert config.ember_origin == "http://127.0.0.1:5173"
    assert config.session_hours == 8
    assert config.game_id == "ascension" and config.dev_fake_owner == ""


@pytest.mark.parametrize("key", list(host_values()))
def test_game_host_settings_are_required(raw, key):
    raw.update(host_values())
    del raw[key]
    with pytest.raises(ConfigError, match=key):
        parse_config(raw)


@pytest.mark.parametrize("key,value", [("session_hours", 0), ("session_hours", True), ("session_hours", float("inf")), ("dev_fake_owner", 42), ("ember_origin", "http://host/path"), ("ember_origin", "http://user:password@host"), ("ember_origin", "http://host; frame-ancestors *"), ("ember_api_url", "ftp://host"), ("game_id", "Bad_ID")])
def test_game_host_settings_reject_unsafe_values(raw, key, value):
    raw.update(host_values())
    raw[key] = value
    with pytest.raises(ConfigError, match=key):
        parse_config(raw)


def test_shop_settings_are_typed(raw):
    raw.update(host_values())
    config = parse_config(raw)
    assert config.shop_rotation_seconds == 21600.0 and config.shop_offers == 5


@pytest.mark.parametrize("key", ["shop_rotation_seconds", "shop_offers"])
def test_shop_settings_are_required(raw, key):
    raw.update(host_values())
    del raw[key]
    with pytest.raises(ConfigError, match=key):
        parse_config(raw)


@pytest.mark.parametrize("key,value", [("shop_offers", 0), ("shop_offers", 13), ("shop_offers", 2.5), ("shop_offers", True), ("shop_rotation_seconds", 10)])
def test_shop_settings_reject_bad_values(raw, key, value):
    raw.update(host_values())
    raw[key] = value
    with pytest.raises(ConfigError, match=key):
        parse_config(raw)
