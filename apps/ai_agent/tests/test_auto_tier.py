"""Auto tier: the model tier of a top-level turn chosen from how hard the question looks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.agents import agent_config, agent_spec
from src.agents.agent_spec import AgentSpec, LlmSpec, TierInfo
from src.llm import auto_tier, jev_classifier, model_tiers
from src.llm.base_provider import ChatResult

LIGHT = TierInfo("light", "haiku", "quick")
STANDARD = TierInfo("standard", "sonnet", "most")
HEAVY = TierInfo("heavy", "opus", "hard")


@pytest.fixture(autouse=True)
def fresh_settings():
    jev_classifier.reset_cache()
    yield
    jev_classifier.reset_cache()


def switch_on(monkeypatch, *, enabled=True, key=True, section=None, size=("everyday", 90), error=None):
    """Settings with auto tier on, a key, and a fake classifier; returns the list of messages it was asked."""
    config = jev_classifier.ClassifierSettings(
        auto_tier=jev_classifier.AutoTierSettings(enabled=enabled, **(section or {}))
    )
    monkeypatch.setattr(jev_classifier, "settings", lambda: config)
    monkeypatch.setattr(jev_classifier, "available", lambda: key)
    asked = []

    def classify_size(message, timeout=None):
        asked.append(message)
        if error:
            raise error
        return jev_classifier.Choice(size[0], size[1], 20)

    monkeypatch.setattr(jev_classifier, "classify_size", classify_size)
    return asked


def pick(question="Summarise this long report for me", has_history=False):
    return asyncio.run(auto_tier.pick(question, has_history))


def test_nothing_is_asked_while_the_feature_is_off(monkeypatch):
    asked = switch_on(monkeypatch, enabled=False)
    assert pick() is None and asked == []


def test_nothing_is_asked_without_a_key(monkeypatch):
    asked = switch_on(monkeypatch, key=False)
    assert pick() is None and asked == []


@pytest.mark.parametrize("size, tier", [("tiny", "light"), ("everyday", "light"), ("large", "standard"), ("hardest", "heavy")])
def test_each_size_maps_to_its_default_tier(monkeypatch, size, tier):
    switch_on(monkeypatch, size=(size, 80))

    chosen = pick()

    assert chosen.tier == tier
    assert chosen.note == f"auto tier: {size} (80%) -> {tier}"


def test_the_size_to_tier_map_can_be_changed(monkeypatch):
    switch_on(monkeypatch, size=("tiny", 99), section={"tiers": (("tiny", "standard"),)})
    assert pick().tier == "standard"


def test_a_low_confidence_keeps_the_default_model(monkeypatch):
    switch_on(monkeypatch, size=("hardest", 59))
    assert pick() is None
    switch_on(monkeypatch, size=("hardest", 60))
    assert pick().tier == "heavy"


def test_a_failing_classifier_keeps_the_default_model(monkeypatch):
    switch_on(monkeypatch, error=jev_classifier.ClassifierError("down"))
    assert pick() is None


def test_a_short_follow_up_is_not_classified_but_a_first_message_is(monkeypatch):
    asked = switch_on(monkeypatch)
    assert pick("yes, do that", has_history=True) is None and asked == []
    assert pick("yes", has_history=False) is not None and asked == ["yes"]
    assert pick("   ", has_history=False) is None


def test_the_classifier_gets_at_most_the_configured_characters(monkeypatch):
    asked = switch_on(monkeypatch)
    cap = jev_classifier.settings().max_input_chars
    pick("x" * (cap + 500))
    assert len(asked[0]) == cap


# --- the settings -----------------------------------------------------------------------------

def use_section(monkeypatch, section):
    monkeypatch.setattr(jev_classifier, "read_section", lambda path, name, default=None: section)


def test_auto_tier_is_off_by_default_with_the_documented_map(monkeypatch):
    use_section(monkeypatch, {})
    config = jev_classifier.settings().auto_tier
    assert config.enabled is False and config.min_confidence == 60
    assert dict(config.tiers) == {"tiny": "light", "everyday": "light", "large": "standard", "hardest": "heavy"}


def test_auto_tier_settings_are_read_and_a_partial_map_keeps_the_rest(monkeypatch):
    use_section(monkeypatch, {"auto_tier": {"enabled": True, "min_confidence": 75, "tiers": {"hardest": "extreme"}}})
    config = jev_classifier.settings().auto_tier
    assert (config.enabled, config.min_confidence) == (True, 75)
    assert dict(config.tiers)["hardest"] == "extreme" and dict(config.tiers)["tiny"] == "light"


@pytest.mark.parametrize("auto", [
    [], {"nope": 1}, {"enabled": "yes"}, {"min_confidence": 101}, {"min_confidence": True}, {"tiers": []},
    {"tiers": {"huge": "light"}}, {"tiers": {"tiny": "giant"}},
])
def test_a_bad_auto_tier_section_is_refused(monkeypatch, auto):
    use_section(monkeypatch, {"auto_tier": auto})
    with pytest.raises(ValueError, match="auto_tier"):
        jev_classifier.settings()


# --- the turn --------------------------------------------------------------------------------

def run_turn(monkeypatch, tiers, chosen, *, depth=0, model_tier=None, history=(), feature_on=True):
    """One agent_config.run_chat with a stub provider; returns (result, models the provider got, pick mock)."""
    spec = AgentSpec(id="calc", label="Calc", port=9103, llm=LlmSpec(provider="anthropic"))
    monkeypatch.setattr(agent_spec, "_current", spec)
    monkeypatch.setattr(model_tiers, "own_tiers", lambda: tiers)
    models = []

    async def provider(question, history, model, enabled_extensions, request_id, depth, on_event=None, caveman=False):
        models.append(model)
        return ChatResult(response="x")

    monkeypatch.setattr(agent_config._PROVIDER_MODULE, "run_chat", provider)
    picker = AsyncMock(return_value=chosen)
    monkeypatch.setattr(auto_tier, "pick", picker)
    monkeypatch.setattr(auto_tier, "enabled", lambda: feature_on)
    result = asyncio.run(agent_config.run_chat(
        "write the report", list(history), [], depth=depth, **({"model_tier": model_tier} if model_tier else {}),
    ))
    return result, models, picker


def test_a_chosen_tier_picks_the_model_and_is_reported(monkeypatch):
    chosen = auto_tier.AutoTier("heavy", "auto tier: hardest (90%) -> heavy")

    result, models, _ = run_turn(monkeypatch, [LIGHT, STANDARD, HEAVY], chosen)

    assert models == ["opus"] and result.model_tier == "heavy"
    assert result.model_note == "auto tier: hardest (90%) -> heavy"


def test_the_agents_own_cap_still_limits_a_chosen_tier(monkeypatch):
    chosen = auto_tier.AutoTier("heavy", "auto tier: hardest (90%) -> heavy")

    result, models, _ = run_turn(monkeypatch, [LIGHT], chosen)

    assert models == ["haiku"] and result.model_tier == "light"
    assert result.model_note.startswith("auto tier: hardest (90%) -> heavy; heavy is not available for calc")


def test_no_choice_leaves_the_default_model_and_no_note(monkeypatch):
    result, models, _ = run_turn(monkeypatch, [LIGHT, STANDARD, HEAVY], None)

    assert models == [None] and result.model_tier is None and result.model_note == ""


def test_a_requested_tier_a_delegate_or_an_agent_without_tiers_never_asks(monkeypatch):
    chosen = auto_tier.AutoTier("heavy", "n")

    _, models, picker = run_turn(monkeypatch, [LIGHT, STANDARD, HEAVY], chosen, model_tier="light")
    assert models == ["haiku"] and not picker.called

    _, _, picker = run_turn(monkeypatch, [LIGHT, STANDARD, HEAVY], chosen, depth=1)
    assert not picker.called

    _, _, picker = run_turn(monkeypatch, [], chosen)
    assert not picker.called


def test_while_the_feature_is_off_the_picker_is_not_asked(monkeypatch):
    result, models, picker = run_turn(monkeypatch, [LIGHT, STANDARD, HEAVY], auto_tier.AutoTier("heavy", "n"), feature_on=False)

    assert models == [None] and result.model_tier is None and not picker.called


def test_the_history_flag_reaches_the_picker(monkeypatch):
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]

    _, _, picker = run_turn(monkeypatch, [LIGHT], None, history=history)

    picker.assert_awaited_once_with("write the report", True)
