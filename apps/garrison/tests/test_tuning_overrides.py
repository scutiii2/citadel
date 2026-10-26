# apps/garrison/tests/test_tuning_overrides.py
"""The admin overlay over config_tuning.json."""

import json
from pathlib import Path

import pytest

from src.runtime import config_files, tuning_overrides
from src.runtime.tuning_overrides import TuningError


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
    ("classifier.auto_tier.min_confidence", 101),          # confidence range
    ("classifier.auto_route.min_confidence", True),        # bool is not confidence
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
    overlay.write_text(json.dumps({"token_limits.default.max_tool_rounds": 999, "classifier.auto_tier.strategy": "both"}), encoding="utf-8")
    assert tuning_overrides.load(overlay) == {"classifier.auto_tier.strategy": "both"}


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
        assert not {"typesafe", "vercel", "chains", "triage_" + "order"} & set(section["classifier"])


def test_every_allowed_extreme_is_accepted_by_the_real_loaders(tuning, monkeypatch):
    """The allowlist must never admit a value token_limits or settings would refuse."""
    from src.providers.decision import settings
    from src.providers import token_limits

    path, overlay = tuning
    extremes = {
        "token_limits.default.max_output_tokens": 200_000, "token_limits.default.max_context_tokens": 1_000,
        "token_limits.default.max_tool_rounds": 100, "token_limits.openai.gateways.ollama.max_context_tokens": 2_000_000,
        "gateway_failover.unavailable_cooldown_seconds": 0, "classifier.timeout_seconds": 60,
        "classifier.max_input_chars": 1, "classifier.auto_tier.strategy": "laya-only",
        "classifier.auto_tier.min_confidence": 100, "classifier.auto_route.strategy": "jev-only",
        "classifier.auto_route.min_confidence": 0,
    }
    tuning_overrides.save(extremes, overlay)
    monkeypatch.setattr(token_limits, "_CONFIG_PATH", path)
    monkeypatch.setattr(settings, "TUNING_PATH", path)
    monkeypatch.setattr(settings, "read_section", config_files.read_section)
    token_limits.reset_cache()
    settings.reset_cache()
    try:
        assert token_limits.limits_for("openai", "ollama")["max_context_tokens"] == 2_000_000
        assert settings.settings().auto_tier.strategy == "laya-only"
        assert settings.settings().auto_route.min_confidence == 0
    finally:
        token_limits.reset_cache()
        settings.reset_cache()


def test_poll_clears_registered_caches_once_per_change(tuning, monkeypatch):
    _, overlay = tuning
    calls = []
    monkeypatch.setattr(tuning_overrides, "_resets", [lambda: calls.append(1)])
    monkeypatch.setattr(tuning_overrides, "_seen", None)

    tuning_overrides.poll(overlay)                      # no file: nothing changed
    assert calls == []
    tuning_overrides.save({"classifier.auto_tier.strategy": "both"}, overlay)
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
    tuning_overrides.save({"classifier.auto_tier.strategy": "both"}, overlay)
    tuning_overrides.poll(overlay)
    assert calls == [1]


def test_an_admin_edit_reaches_token_limits_after_poll(tuning, monkeypatch):
    from src.providers import token_limits

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






def test_save_preserves_a_persistent_overlay_symlink(tuning, tmp_path):
    _, overlay = tuning
    target = tmp_path / ".data" / "admin_tuning_overrides.json"
    target.parent.mkdir()
    overlay.symlink_to(target)
    tuning_overrides.save({"classifier.auto_tier.strategy": "both"}, overlay)
    assert overlay.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8")) == {"classifier.auto_tier.strategy": "both"}
    # Another container's configs link can read the same retained volume file.
    recreated = tmp_path / "recreated" / tuning_overrides.OVERLAY_NAME
    recreated.parent.mkdir()
    recreated.symlink_to(target)
    assert tuning_overrides.load(recreated) == {"classifier.auto_tier.strategy": "both"}


@pytest.mark.parametrize("body", ["{not json", "[]"])
def test_malformed_overlay_is_logged_and_ignored(tuning, caplog, body):
    _, overlay = tuning
    overlay.write_text(body, encoding="utf-8")
    assert tuning_overrides.load(overlay) == {}
    assert any(record.name == tuning_overrides.__name__ and "ignored" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("feature", ["auto_tier", "auto_route"])
def test_strategy_enum_saves_valid_value_and_rejects_invalid_without_writing(tmp_path, feature):
    path = tmp_path / "overlay.json"
    key = f"classifier.{feature}.strategy"
    tuning_overrides.save({key: "laya-only"}, path)
    assert tuning_overrides.load(path) == {key: "laya-only"}
    before = path.read_bytes()
    with pytest.raises(TuningError, match="must be"):
        tuning_overrides.save({key: "bogus"}, path)
    assert path.read_bytes() == before
    missing = tmp_path / "missing.json"
    with pytest.raises(TuningError):
        tuning_overrides.save({key: ["both"]}, missing)
    assert not missing.exists()


def test_tuning_view_exposes_feature_strategy_and_confidence_but_not_tier_mapping(tuning):
    path, overlay = tuning
    tuning_overrides.save({"classifier.auto_tier.strategy": "jev-only"}, overlay)
    view = config_files.tuning_view(path)
    assert view["defaults"]["classifier"]["auto_tier"] == {"strategy": "both", "min_confidence": 80}
    assert view["effective"]["classifier"]["auto_tier"] == {"strategy": "jev-only", "min_confidence": 80}
    assert view["defaults"]["classifier"]["auto_route"] == {"strategy": "both", "min_confidence": 80}


@pytest.mark.parametrize("raw", [{}, {"classifier": {"timeout_seconds": 3}}])
def test_tuning_view_shows_runtime_feature_defaults_for_legacy_file(raw):
    view = config_files._editable(raw)
    assert view["classifier"]["auto_tier"] == {"strategy": "both", "min_confidence": 60}
    assert view["classifier"]["auto_route"] == {"strategy": "both", "min_confidence": 60}
