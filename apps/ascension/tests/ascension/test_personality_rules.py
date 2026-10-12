import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.personality_rules import holds, parse_rules
from tests.ascension.env import load_raw


def test_a_valid_rule_list_parses():
    rules = parse_rules([
        {"when": {"nerves_over": 0.5, "enemy_low": False}, "chaos": 0.6},
        {"multiply": {"ATTACK": 1.5, "FEAR": 0.5}, "stay": 2.0, "repeat": 1.0, "pick_by_percentage": "high"},
        {"counter": True}, {"copy_enemy": True}, {"break_streak": True},
    ], "personality 'X'")
    assert len(rules) == 5 and rules[0].when == {"nerves_over": 0.5, "enemy_low": False} and rules[0].effects == {"chaos": 0.6}
    assert rules[2].when == {} and rules[2].effects == {"counter": True}


@pytest.mark.parametrize("raw,message", [
    ("nope", "must be a list"),
    ([5], "must be an object"),
    ([{"chaos": 0.5, "color": "red"}], "unknown key 'color'"),
    ([{"when": {"mood_over": 1}, "chaos": 0.5}], "unknown condition"),
    ([{"when": {"lead_over": "high"}, "chaos": 0.5}], "lead_over needs a number"),
    ([{"when": {"enemy_low": 1}, "chaos": 0.5}], "enemy_low needs true or false"),
    ([{"when": {"enemy_last_is": "DANCE"}, "chaos": 0.5}], "enemy_last_is needs a category"),
    ([{"when": {"lead_over": 0}}], "at least one effect"),
    ([{"multiply": {"DANCE": 2}}], "multiply"),
    ([{"multiply": {"ATTACK": 0}}], "multiply"),
    ([{"chaos": 1.5}], "chaos"),
    ([{"counter": False}], "counter"),
    ([{"stay": -1}], "stay"),
    ([{"repeat": 1.5}], "repeat"),
    ([{"pick_by_percentage": "middle"}], "pick_by_percentage"),
])
def test_a_bad_rule_is_rejected_with_a_clear_message(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_rules(raw, "personality 'X'")


M = MatchState(own_hp=0.4, enemy_hp=0.2, lead=0.2, round=5, own_streak=3, own_last="ATTACK", enemy_last="SUPPORT", hit_taken=0.2, enemy_low=True)
K = MoodMeters(rage=0.7, confidence=0.9, nerves=0.1)


@pytest.mark.parametrize("when,expected", [
    ({}, True),
    ({"lead_over": 0.1}, True), ({"lead_over": 0.2}, False), ({"lead_under": 0.3}, True), ({"lead_under": 0.2}, False),
    ({"own_hp_under": 0.5}, True), ({"own_hp_under": 0.4}, False),
    ({"enemy_low": True}, True), ({"enemy_low": False}, False),
    ({"rage_over": 0.6}, True), ({"rage_over": 0.7}, False),
    ({"confidence_over": 0.8}, True), ({"nerves_over": 0.5}, False),
    ({"hit_taken_over": 0.1}, True), ({"streak_over": 2}, True), ({"streak_over": 3}, False),
    ({"round_under": 6}, True), ({"round_under": 5}, False), ({"round_over": 4}, True),
    ({"enemy_last_is": "SUPPORT"}, True), ({"enemy_last_is": "ATTACK"}, False),
    ({"lead_over": 0.1, "nerves_over": 0.5}, False),  # every condition must hold
])
def test_conditions_read_the_match_and_the_mood(when, expected):
    assert holds(when, M, K) is expected


def build(raw_personality):
    data = copy.deepcopy(load_raw())
    data["personalities"].append(raw_personality)
    return Catalog(data)


def test_a_personality_may_have_rules_and_no_categories():
    catalog = build({"id": "TESTY", "categories": [], "rules": [{"counter": True}]})
    spec = catalog.personalities["TESTY"]
    assert spec.categories == () and spec.rules[0].effects == {"counter": True}


def test_the_catalog_rejects_a_bad_rule_and_bad_policy_numbers():
    with pytest.raises(CatalogError, match="unknown condition"):
        build({"id": "TESTY", "categories": [], "rules": [{"when": {"x": 1}, "chaos": 0.5}]})
    data = copy.deepcopy(load_raw())
    data["policy"]["temperature"] = 0
    with pytest.raises(CatalogError, match="temperature"):
        Catalog(data)
    data = copy.deepcopy(load_raw())
    data["policy"]["mood"] = {"rage_decay": 2.0}
    with pytest.raises(CatalogError, match="mood"):
        Catalog(data)


def test_the_shipped_policy_has_the_defaults():
    policy = Catalog(load_raw()).policy
    assert (policy.potency_weight, policy.pick_weight, policy.temperature, policy.counter_boost) == (0.3, 1.5, 0.7, 3.0)
    assert policy.mood.streak_base == 2 and policy.mood.streak_span == 3
