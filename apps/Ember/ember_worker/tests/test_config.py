from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import ConfigError, EnvFile, WorkerConfig, load_config, save_pairing, token_key

EXAMPLE = {"url": "http://127.0.0.1:8030", "heartbeat_seconds": 20, "plan_override": {}}


def make_root(tmp_path: Path, config: dict | None = EXAMPLE, env: str | None = None) -> Path:
    (tmp_path / "configs").mkdir()
    if config is not None:
        (tmp_path / "configs" / "config_worker.json.example").write_text(json.dumps(config), encoding="utf-8")
    if env is not None:
        (tmp_path / ".env").write_text(env, encoding="utf-8")
    return tmp_path


def test_a_missing_config_is_made_from_its_example_twin(tmp_path: Path) -> None:
    root = make_root(tmp_path)

    config = load_config(root)

    assert (root / "configs" / "config_worker.json").exists()
    assert (config.url, config.heartbeat_seconds, config.plan_override, config.tokens) == (
        "http://127.0.0.1:8030", 20.0, {}, {},
    )


def test_no_config_and_no_example_is_a_clear_error(tmp_path: Path) -> None:
    root = make_root(tmp_path, config=None)

    with pytest.raises(ConfigError, match="config_worker.json"):
        load_config(root)


@pytest.mark.parametrize(
    "url, socket",
    [
        ("http://127.0.0.1:8030", "ws://127.0.0.1:8030/api/forge/worker"),
        ("https://ember.example.com", "wss://ember.example.com/api/forge/worker"),
    ],
)
def test_the_socket_address_follows_the_http_address(url: str, socket: str) -> None:
    assert WorkerConfig(url, 20, {}, {}).socket_url == socket


def test_a_bad_address_is_refused() -> None:
    with pytest.raises(ConfigError, match="http"):
        WorkerConfig("ember.example.com", 20, {}, {}).socket_url


def test_a_trailing_slash_is_dropped_and_bad_values_are_refused(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"url": "https://e.example.com/", "heartbeat_seconds": 5, "plan_override": {"claude": "Max", "bogus": "x", "codex": " "}})

    config = load_config(root)

    assert config.url == "https://e.example.com"
    assert config.plan_override == {"claude": "Max"}  # unknown providers and blanks are dropped

    other = tmp_path / "bad"
    other.mkdir()
    bad = make_root(other, {"url": "", "heartbeat_seconds": 5})
    with pytest.raises(ConfigError, match="url"):
        load_config(bad)


def test_tokens_come_from_dot_env_and_the_environment_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_root(tmp_path, env="# comment\nEMBER_WORKER_TOKEN_CLAUDE=ft_one\nEMBER_WORKER_TOKEN_CODEX=\n")
    config = load_config(root)
    assert config.tokens == {"claude": "ft_one"} and config.paired_providers() == ["claude"]

    monkeypatch.setenv("EMBER_WORKER_TOKEN_CODEX", "ft_two")
    config = load_config(root)
    assert config.paired_providers() == ["claude", "codex"]


def test_env_file_set_keeps_other_lines(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# keep me\nOTHER=1\nEMBER_WORKER_TOKEN_CLAUDE=old\n", encoding="utf-8")

    env = EnvFile(path)
    env.set("EMBER_WORKER_TOKEN_CLAUDE", "new")
    env.set("EMBER_WORKER_TOKEN_CODEX", "added")

    assert path.read_text(encoding="utf-8") == "# keep me\nOTHER=1\nEMBER_WORKER_TOKEN_CLAUDE=new\nEMBER_WORKER_TOKEN_CODEX=added\n"
    assert env.read()["OTHER"] == "1"


def test_save_pairing_writes_the_address_the_plan_and_the_token(tmp_path: Path) -> None:
    root = make_root(tmp_path)

    save_pairing(root, "claude", "https://ember.example.com/", "ft_secret", plan="Max")
    save_pairing(root, "codex", "https://ember.example.com", "ft_other")

    config = load_config(root)
    assert config.url == "https://ember.example.com"
    assert config.plan_override == {"claude": "Max"}
    assert config.tokens == {"claude": "ft_secret", "codex": "ft_other"}
    assert token_key("claude") == "EMBER_WORKER_TOKEN_CLAUDE"
    assert "ft_secret" not in (root / "configs" / "config_worker.json").read_text(encoding="utf-8")
