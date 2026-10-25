"""The admin overlay (.data/tuning_overrides.json): one key for now, the Triage Assistant's default strategy."""

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


def test_a_write_creates_the_missing_data_folder(tmp_path):
    path = tmp_path / ".data" / "o.json"
    tuning_overrides.set_triage_strategy("auto", path)
    assert tuning_overrides.triage_strategy(path) == "auto"


def test_the_default_path_is_in_the_data_folder():
    assert tuning_overrides.OVERRIDES_PATH.parent.name == ".data"


# apps/garrison/tests/test_tuning_overrides.py
"""The admin overlay over config_tuning.json."""

import json
from pathlib import Path

import pytest

from src.core import config_files, tuning_overrides
from src.core.tuning_overrides import TuningError


@pytest.fixture
def tuning(tmp_path):
    path = tmp_path / "config_tuning.json"
    examples = Path(config_files.__file__).resolve().parents[2] / "configs"
    path.with_suffix(".json.example").write_bytes((examples / "config_tuning.json.example").read_bytes())
    return path, tmp_path / tuning_overrides.OVERLAY_NAME


def test_apply_sets_nested_value_and_leaves_base_alone(tuning):
    _, overlay = tuning
    overlay.write_text(json.dumps({"token_limits.default.max_tool_rounds": 20}), encoding="utf-8")
    base = {"token_limits": {"default": {"max_tool_rounds": 15}}}
    merged = tuning_overrides.apply(base, overlay)
    assert merged["token_limits"]["default"]["max_tool_rounds"] == 20
    assert base["token_limits"]["default"]["max_tool_rounds"] == 15


def test_save_none_resets_a_path(tuning):
    _, overlay = tuning
    tuning_overrides.save({"gateway_failover.quota_cooldown_seconds": 60}, overlay)
    assert tuning_overrides.load(overlay) == {"gateway_failover.quota_cooldown_seconds": 60.0}
    tuning_overrides.save({"gateway_failover.quota_cooldown_seconds": None}, overlay)
    assert tuning_overrides.load(overlay) == {}


@pytest.mark.parametrize("path, value", [
    ("classifier.typesafe.url", "https://x"),              # file-only
    ("token_limits.default.max_tool_rounds", 0),           # below range
    ("token_limits.default.max_tool_rounds", 101),         # above range
    ("token_limits.default.max_tool_rounds", True),        # bool is not a number
    ("token_limits.default.max_tool_rounds", 2.5),         # int field
    ("classifier.timeout_seconds", 0),                     # open lower bound
    ("classifier.triage_thresholds.4.jev", 0.5),           # unknown count
    ("classifier.triage_enabled.jev.choice", "yes"),       # bool field
    ("nonsense", 1),
])
def test_save_rejects_bad_changes(tuning, path, value):
    _, overlay = tuning
    with pytest.raises(TuningError):
        tuning_overrides.save({path: value}, overlay)
    assert not overlay.exists()


def test_save_rejects_unknown_path_on_reset(tuning):
    _, overlay = tuning
    with pytest.raises(TuningError):
        tuning_overrides.save({"classifier.chains.triage": None}, overlay)


def test_invalid_entry_in_the_file_is_ignored(tuning):
    _, overlay = tuning
    overlay.write_text(json.dumps({"token_limits.default.max_tool_rounds": 999, "classifier.triage_trace": True}), encoding="utf-8")
    assert tuning_overrides.load(overlay) == {"classifier.triage_trace": True}


def test_unreadable_overlay_is_empty(tuning):
    _, overlay = tuning
    overlay.write_text("{not json", encoding="utf-8")
    assert tuning_overrides.load(overlay) == {}


def test_read_section_merges_the_overlay_next_to_the_tuning_file(tuning):
    path, overlay = tuning
    tuning_overrides.save({"token_limits.default.max_tool_rounds": 20}, overlay)
    limits = config_files.read_section(path, "token_limits")
    assert limits["default"]["max_tool_rounds"] == 20
    assert limits["default"]["max_output_tokens"] == 2048


def test_tuning_view_hides_file_only_keys(tuning):
    path, overlay = tuning
    tuning_overrides.save({"classifier.timeout_seconds": 5}, overlay)
    view = config_files.tuning_view(path)
    assert view["overrides"] == {"classifier.timeout_seconds": 5.0}
    assert view["defaults"]["classifier"]["timeout_seconds"] == 3.0
    assert view["effective"]["classifier"]["timeout_seconds"] == 5.0
    for section in (view["defaults"], view["effective"]):
        assert not {"typesafe", "vercel", "chains", "triage_order"} & set(section["classifier"])


def test_every_allowed_extreme_is_accepted_by_the_real_loaders(tuning, monkeypatch):
    """The allowlist must never admit a value token_limits or decision would refuse."""
    from src.llm import decision, token_limits

    path, overlay = tuning
    extremes = {
        "token_limits.default.max_output_tokens": 200_000, "token_limits.default.max_context_tokens": 1_000,
        "token_limits.default.max_tool_rounds": 100, "token_limits.openai.gateways.ollama.max_context_tokens": 2_000_000,
        "gateway_failover.unavailable_cooldown_seconds": 0, "classifier.timeout_seconds": 60,
        "classifier.max_input_chars": 1, "classifier.triage_fallback": True, "classifier.triage_trace": True,
        "classifier.triage_window": 512, "classifier.triage_prune_ratio": 0, "classifier.triage_pair_ratio": 1,
        "classifier.triage_thresholds.3+.laya-typed": 1, "classifier.triage_enabled.jev.score": False,
    }
    tuning_overrides.save(extremes, overlay)
    monkeypatch.setattr(token_limits, "_CONFIG_PATH", path)
    monkeypatch.setattr(decision, "TUNING_PATH", path)
    monkeypatch.setattr(decision, "read_section", config_files.read_section)
    token_limits.reset_cache()
    decision.reset_cache()
    try:
        assert token_limits.limits_for("openai", "ollama")["max_context_tokens"] == 2_000_000
        assert decision.settings().triage_window == 512
    finally:
        token_limits.reset_cache()
        decision.reset_cache()


def test_poll_clears_registered_caches_once_per_change(tuning, monkeypatch):
    _, overlay = tuning
    calls = []
    monkeypatch.setattr(tuning_overrides, "_resets", [lambda: calls.append(1)])
    monkeypatch.setattr(tuning_overrides, "_seen", None)

    tuning_overrides.poll(overlay)                      # no file: nothing changed
    assert calls == []
    tuning_overrides.save({"classifier.triage_trace": True}, overlay)
    tuning_overrides.poll(overlay)
    tuning_overrides.poll(overlay)                      # same file: no second reset
    assert calls == [1]


def test_a_failing_reset_does_not_stop_the_others_or_the_turn(tuning, monkeypatch):
    _, overlay = tuning
    calls = []

    def boom():
        raise ValueError("bad file")

    monkeypatch.setattr(tuning_overrides, "_resets", [boom, lambda: calls.append(1)])
    monkeypatch.setattr(tuning_overrides, "_seen", None)
    tuning_overrides.save({"classifier.triage_trace": True}, overlay)
    tuning_overrides.poll(overlay)
    assert calls == [1]


def test_an_admin_edit_reaches_token_limits_after_poll(tuning, monkeypatch):
    from src.llm import token_limits

    path, overlay = tuning
    monkeypatch.setattr(token_limits, "_CONFIG_PATH", path)
    monkeypatch.setattr(tuning_overrides, "_seen", None)
    token_limits.reset_cache()
    assert token_limits.max_tool_rounds("anthropic") == 15
    tuning_overrides.save({"token_limits.default.max_tool_rounds": 30}, overlay)
    assert token_limits.max_tool_rounds("anthropic") == 15      # cached until the poll
    tuning_overrides.poll(overlay)
    assert token_limits.max_tool_rounds("anthropic") == 30
    token_limits.reset_cache()


def test_save_rejects_disabling_the_last_voter_in_the_file_order(tuning):
    path, overlay = tuning
    tuning_overrides.save({"classifier.triage_enabled.laya-typed.noul": False}, overlay)
    before = overlay.read_bytes()
    with pytest.raises(TuningError, match="classifier.triage_enabled"):
        tuning_overrides.save({"classifier.triage_enabled.jev.noul": False}, overlay)
    assert overlay.read_bytes() == before


def test_invalid_voter_combination_on_disk_falls_back_to_the_file(tuning, monkeypatch):
    from src.llm import decision
    path, overlay = tuning
    overlay.write_text(json.dumps({
        "classifier.triage_enabled.laya-typed.noul": False,
        "classifier.triage_enabled.jev.noul": False,
        "classifier.triage_trace": True,
    }), encoding="utf-8")
    monkeypatch.setattr(decision, "read_section", config_files.read_section)
    monkeypatch.setattr(decision, "TUNING_PATH", path)
    decision.reset_cache()
    try:
        assert decision.settings().triage_enabled["jev"]["noul"] is True
        assert decision.settings().triage_trace is True
    finally:
        decision.reset_cache()


def test_save_preserves_a_persistent_overlay_symlink(tuning, tmp_path):
    _, overlay = tuning
    target = tmp_path / ".data" / "admin_tuning_overrides.json"
    target.parent.mkdir()
    overlay.symlink_to(target)
    tuning_overrides.save({"classifier.triage_trace": True}, overlay)
    assert overlay.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8")) == {"classifier.triage_trace": True}
    # Another container's configs link can read the same retained volume file.
    recreated = tmp_path / "recreated" / tuning_overrides.OVERLAY_NAME
    recreated.parent.mkdir()
    recreated.symlink_to(target)
    assert tuning_overrides.load(recreated) == {"classifier.triage_trace": True}


@pytest.mark.parametrize("body", ["{not json", "[]"])
def test_malformed_overlay_is_logged_and_ignored(tuning, caplog, body):
    _, overlay = tuning
    overlay.write_text(body, encoding="utf-8")
    assert tuning_overrides.load(overlay) == {}
    assert any(record.name == tuning_overrides.__name__ and "ignored" in record.getMessage() for record in caplog.records)
