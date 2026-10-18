from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import load_config
from src.providers.base import Provider
from src.run import main


class FakeProvider(Provider):
    def __init__(self, name: str, logged_in: bool = True, plan: str | None = "Max") -> None:
        self.name, self._logged_in, self._plan = name, logged_in, plan

    async def detect_plan(self):
        return self._plan

    async def is_logged_in(self):
        return self._logged_in

    def run_turn(self, request, gate):  # pragma: no cover - not used here
        raise NotImplementedError

    async def cancel(self, turn_id):  # pragma: no cover
        pass


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "config_worker.json.example").write_text(
        json.dumps({"url": "http://127.0.0.1:8030", "heartbeat_seconds": 20, "plan_override": {}}), encoding="utf-8"
    )
    return tmp_path


def factory(**providers):
    return lambda name: providers[name]


def test_pair_saves_the_address_and_token_after_checking_the_login(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main(
        ["pair", "https://ember.example.com/", "ft_secret", "--provider", "claude"],
        root=root, provider_factory=factory(claude=FakeProvider("claude", plan="max")),
    )

    out = capsys.readouterr().out
    assert code == 0
    config = load_config(root)
    assert (config.url, config.tokens) == ("https://ember.example.com", {"claude": "ft_secret"})
    assert "max" in out and "ft_secret" not in out


def test_pair_refuses_when_the_cli_is_not_logged_in(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main(
        ["pair", "http://127.0.0.1:8030", "ft_secret", "--provider", "codex"],
        root=root, provider_factory=factory(codex=FakeProvider("codex", logged_in=False)),
    )

    err = capsys.readouterr().err
    assert code == 1 and "not logged in" in err
    assert load_config(root).tokens == {}  # nothing was saved


def test_pair_with_an_undetectable_plan_suggests_the_plan_option(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main(
        ["pair", "http://127.0.0.1:8030", "ft_t", "--provider", "claude"],
        root=root, provider_factory=factory(claude=FakeProvider("claude", plan=None)),
    )

    assert code == 0 and "--plan" in capsys.readouterr().out


def test_pair_can_record_the_plan_by_hand(tmp_path: Path) -> None:
    root = make_root(tmp_path)

    main(
        ["pair", "http://127.0.0.1:8030", "ft_t", "--provider", "claude", "--plan", "Max 20x"],
        root=root, provider_factory=factory(claude=FakeProvider("claude", plan=None)),
    )

    assert load_config(root).plan_override == {"claude": "Max 20x"}


def test_status_reports_without_revealing_tokens(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)
    main(
        ["pair", "http://127.0.0.1:8030", "ft_hidden", "--provider", "claude"],
        root=root, provider_factory=factory(claude=FakeProvider("claude")),
    )
    capsys.readouterr()

    code = main(
        ["status"],
        root=root,
        provider_factory=factory(claude=FakeProvider("claude", plan="max"), codex=FakeProvider("codex", logged_in=False, plan=None)),
    )

    out = capsys.readouterr().out
    assert code == 0 and "ft_hidden" not in out
    assert "http://127.0.0.1:8030" in out
    claude_block, codex_block = out.split("codex")
    assert "logged in: yes" in claude_block and "plan: max" in claude_block and "paired: yes" in claude_block
    assert "logged in: no" in codex_block and "plan: unknown" in codex_block and "paired: no" in codex_block


def test_run_without_a_paired_worker_explains_how_to_pair(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main([], root=root, provider_factory=factory())

    assert code == 1 and "pair" in capsys.readouterr().err


def test_a_config_problem_is_a_clear_message_not_a_traceback(tmp_path: Path, capsys) -> None:
    code = main(["status"], root=tmp_path, provider_factory=factory())  # no configs folder at all

    assert code == 1 and "config_worker.json" in capsys.readouterr().err


def test_unknown_provider_is_refused_by_the_parser() -> None:
    with pytest.raises(SystemExit):
        main(["pair", "u", "t", "--provider", "gemini"])
