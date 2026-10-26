"""Decision settings tolerate legacy config and refresh on tuning edits."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.providers.decision import settings, strategy, decision
from src.runtime import tuning_overrides


def use_section(monkeypatch, section):
    monkeypatch.setattr(settings, "read_section", lambda *a, **k: section)
    settings.reset_cache()


def test_defaults_are_off_and_strategies_are_both(monkeypatch):
    use_section(monkeypatch, {})
    config = settings.settings()
    assert config == settings.ClassifierSettings()
    assert not config.auto_tier.enabled and not config.auto_route.enabled
    assert config.auto_tier.strategy == config.auto_route.strategy == "both"
    assert settings.FEATURES == ("auto_tier", "auto_route")


def test_new_strategies_and_thresholds_are_read_when_present(monkeypatch):
    use_section(monkeypatch, {"timeout_seconds": 4, "max_input_chars": 9000,
        "auto_tier": {"enabled": True, "strategy": "laya-only", "min_confidence": 87, "tiers": {"tiny": "standard"}},
        "auto_route": {"enabled": True, "strategy": "jev-only", "min_confidence": 83}})
    config = settings.settings()
    assert config.timeout_seconds == 4 and config.max_input_chars == 9000
    assert config.auto_tier.strategy == "laya-only" and config.auto_tier.min_confidence == 87
    assert dict(config.auto_tier.tiers)["tiny"] == "standard"
    assert config.auto_route.strategy == "jev-only" and config.auto_route.min_confidence == 83


@pytest.mark.parametrize("key", ["chains", "typesafe", "vercel", "triage_enabled", "triage_order",
    "triage_thresholds", "triage_window", "triage_prune_ratio", "triage_pair_ratio", "triage_fallback", "triage_trace", "triage_strategy"])
def test_retired_keys_are_ignored_without_validation(monkeypatch, caplog, key):
    use_section(monkeypatch, {key: None})
    assert settings.settings() == settings.ClassifierSettings()
    assert key in caplog.text


def test_existing_example_loads_with_default_strategies(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "configs" / "config_tuning.json.example"
    raw = json.loads(path.read_text(encoding="utf-8"))["classifier"]
    use_section(monkeypatch, raw)
    config = settings.settings()
    assert config.auto_tier.strategy == config.auto_route.strategy == "both"
    assert config.auto_tier.min_confidence == raw.get("auto_tier", {}).get("min_confidence", settings.AutoTierSettings.min_confidence)
    assert config.auto_route.min_confidence == raw.get("auto_route", {}).get("min_confidence", settings.AutoRouteSettings.min_confidence)


@pytest.mark.parametrize("value", ["bogus", "", False, 42])
def test_invalid_strategy_warns_and_uses_both(monkeypatch, caplog, value):
    use_section(monkeypatch, {"auto_route": {"strategy": value}})
    assert settings.settings().auto_route.strategy == "both"
    assert "strategy" in caplog.text and "both" in caplog.text


@pytest.mark.parametrize("raw", [{"timeout_seconds": 0}, {"max_input_chars": True},
    {"auto_tier": {"enabled": "yes"}}, {"auto_route": {"min_confidence": 101}},
    {"auto_tier": {"tiers": {"tiny": "unknown"}}}])
def test_known_settings_remain_validated(monkeypatch, raw):
    use_section(monkeypatch, raw)
    with pytest.raises(ValueError):
        settings.settings()


@pytest.mark.parametrize("chosen,expected", [("laya-only", False), ("jev-only", True), ("both", True)])
def test_availability_respects_the_feature_strategy(monkeypatch, chosen, expected):
    use_section(monkeypatch, {"auto_tier": {"strategy": chosen}})
    monkeypatch.setattr(strategy, "default_gateways", lambda: {
        "laya": SimpleNamespace(available=lambda: False), "jev": SimpleNamespace(available=lambda: True)})
    assert settings.available("auto_tier") is expected


def test_tuning_edit_refreshes_both_settings_readers(monkeypatch, tmp_path):
    overlay = tmp_path / "overlay.json"
    base = {"classifier": {"timeout_seconds": 3}}
    def read(*args, **kwargs):
        return tuning_overrides.apply(base, overlay)["classifier"]
    monkeypatch.setattr(settings, "read_section", read)
    monkeypatch.setattr(decision, "read_section", read)
    monkeypatch.setattr(tuning_overrides, "_seen", None)
    settings.reset_cache()
    decision.reset_cache()
    before_new, before_old = settings.settings(), decision.settings()
    assert before_new.timeout_seconds == before_old.timeout_seconds == 3
    tuning_overrides.save({"classifier.timeout_seconds": 4}, overlay)
    tuning_overrides.poll(overlay)
    assert settings.settings().timeout_seconds == decision.settings().timeout_seconds == 4
    assert settings.settings() is not before_new and decision.settings() is not before_old
