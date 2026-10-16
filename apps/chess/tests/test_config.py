import json

import pytest

from src.config import ConfigError, load_config, parse_config
from tests.conftest import EXAMPLE_CONFIG


def test_example_config_loads(config):
    assert config.port == 8070
    assert config.difficulties["medium"].depth == 2
    assert config.default_picker == {"chess": "laya", "tetris": "laya"}


@pytest.fixture
def raw():
    return json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))


def test_unknown_picker_is_rejected(raw):
    raw["default_picker"]["chess"] = "magic"
    with pytest.raises(ConfigError, match="default_picker"):
        parse_config(raw)


def test_k_above_ten_is_rejected(raw):
    raw["difficulties"]["easy"]["k"] = 11
    with pytest.raises(ConfigError, match="at most 10"):
        parse_config(raw)


def test_bool_is_not_a_number(raw):
    raw["port"] = True
    with pytest.raises(ConfigError, match="port"):
        parse_config(raw)


def test_missing_difficulties_is_rejected(raw):
    raw["difficulties"] = {}
    with pytest.raises(ConfigError, match="difficulties"):
        parse_config(raw)


def test_chess_port_env_overrides_the_file(monkeypatch):
    monkeypatch.setenv("CHESS_PORT", "9123")
    assert load_config(EXAMPLE_CONFIG).port == 9123


@pytest.mark.parametrize("value", ["abc", "0", "70000"])
def test_bad_chess_port_env_is_rejected(monkeypatch, value):
    monkeypatch.setenv("CHESS_PORT", value)
    with pytest.raises(ConfigError, match="CHESS_PORT"):
        load_config(EXAMPLE_CONFIG)


def test_unreadable_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.json")
