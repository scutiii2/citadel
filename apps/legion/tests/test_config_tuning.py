"""Shared consumers of the tuning config."""

import json
from pathlib import Path

import pytest

from src.runtime import config_files
from src.providers import token_limits


@pytest.fixture
def tuning_path(tmp_path):
    path = tmp_path / "config_tuning.json"
    examples = Path(config_files.__file__).resolve().parents[2] / "configs"
    path.write_bytes((examples / "config_tuning.json").read_bytes())
    return path


def test_token_limits_read_the_shared_tuning_file(tuning_path, monkeypatch):
    assert token_limits._CONFIG_PATH == config_files.TUNING_PATH
    data = {"token_limits": {"default": {"max_output_tokens": 101, "max_context_tokens": 202,
                                        "max_tool_rounds": 3}}}
    tuning_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(token_limits, "_CONFIG_PATH", tuning_path)
    token_limits.reset_cache()
    try:
        assert token_limits.max_output_tokens("anthropic") == 101
    finally:
        token_limits.reset_cache()
