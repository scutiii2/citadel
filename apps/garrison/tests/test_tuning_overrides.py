"""The admin overlay (configs/config_tuning_overrides.json): one key for now, the Triage Assistant's default strategy."""

from __future__ import annotations

import json

from src.core import tuning_overrides


def test_nothing_is_set_without_a_file(tmp_path):
    assert tuning_overrides.triage_strategy(tmp_path / "o.json") is None


def test_a_saved_strategy_is_read_back(tmp_path):
    path = tmp_path / "o.json"
    tuning_overrides.set_triage_strategy("typed-only", path)
    assert tuning_overrides.triage_strategy(path) == "typed-only"
    assert json.loads(path.read_text(encoding="utf-8")) == {"classifier": {"triage_strategy": "typed-only"}}


def test_none_clears_the_key_and_leaves_the_other_keys(tmp_path):
    path = tmp_path / "o.json"
    path.write_text(json.dumps({"classifier": {"triage_strategy": "average", "other": 1}, "x": 2}), encoding="utf-8")
    tuning_overrides.set_triage_strategy(None, path)
    assert tuning_overrides.triage_strategy(path) is None
    assert json.loads(path.read_text(encoding="utf-8")) == {"classifier": {"other": 1}, "x": 2}


def test_a_broken_file_reads_as_unset_and_is_replaced_by_a_write(tmp_path, caplog):
    path = tmp_path / "o.json"
    for bad in ("{not json", "[]", json.dumps({"classifier": []}), json.dumps({"classifier": {"triage_strategy": 5}})):
        path.write_text(bad, encoding="utf-8")
        assert tuning_overrides.triage_strategy(path) is None
    tuning_overrides.set_triage_strategy("consensus", path)
    assert tuning_overrides.triage_strategy(path) == "consensus"


def test_a_write_leaves_no_temporary_file(tmp_path):
    tuning_overrides.set_triage_strategy("auto", tmp_path / "o.json")
    assert [p.name for p in tmp_path.iterdir()] == ["o.json"]
