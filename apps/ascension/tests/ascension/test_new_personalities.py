import pytest

from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.models import Action, PersonalityInstance
from src.ascension.policy import ActionPolicy, Mood, PolicyContext, Situation
from tests.ascension.env import CATALOG

policy, mood = ActionPolicy(CATALOG.policy), Mood(CATALOG)
ACTIONS = [Action("attack", "ATTACK"), Action("ability", "DEFENSE", "guard", 200), Action("ability", "SUPPORT", "rally", 50),
           Action("flee", "FEAR"), Action("catch", "INTERCEPT")]

NEW = ["WEIRD", "ANXIOUS", "RECKLESS", "VENGEFUL", "BERSERKER", "COCKY", "COMEBACK", "CUNNING", "MIMIC", "PATIENT",
       "OPPORTUNIST", "STUBBORN", "GAMBLER", "STOIC"]


def ctx(personality=None, tier=3, actions=ACTIONS, match=None, meters=None):
    instances = [PersonalityInstance("p", personality, tier)] if personality else []
    return PolicyContext(Situation(0.3, 0.5, 0.5), 1.0, 0.1, False, (), mood.weights(instances, 0) if instances else {},
                         match or MatchState(round=6), meters or MoodMeters(), mood.active_rules(instances, 0) if instances else ())


def cats(personality=None, **kwargs):
    return policy.explain(ACTIONS, ctx(personality, **kwargs)).categories


CALM = cats()


def test_there_are_22_personalities_and_the_first_8_keep_their_order():
    ids = list(CATALOG.personalities)
    assert ids[:8] == ["AGGRESSIVE", "DEFENSIVE", "SUPPORTIVE", "COWARD", "TENACIOUS", "BOLD", "CAUTIOUS", "DISCIPLINED"]
    assert ids[8:] == NEW and len(ids) == 22
    assert all(CATALOG.personalities[p].categories == () for p in NEW)


@pytest.mark.parametrize("personality", [p for p in NEW if p not in ("PATIENT", "OPPORTUNIST")])
def test_a_new_personality_is_calm_in_a_calm_match(personality):
    """In an even, quiet round with a fresh mood no new personality changes the odds. Patient and Opportunist
    read the round number and the enemy HP even then, so they have their own tests below."""
    assert cats(personality, match=MatchState(round=6), meters=MoodMeters()) == pytest.approx(CALM)


@pytest.mark.parametrize("personality,match,meters,up,down", [
    ("RECKLESS", MatchState(own_hp=0.3, lead=-0.3), None, ["ATTACK"], []),
    ("VENGEFUL", None, MoodMeters(rage=0.6), ["ATTACK"], []),
    ("BERSERKER", None, MoodMeters(rage=0.7), ["ATTACK"], ["FEAR"]),
    ("COCKY", None, MoodMeters(confidence=0.8), ["ATTACK"], ["DEFENSE"]),
    ("COMEBACK", MatchState(lead=-0.4), None, ["ATTACK", "SUPPORT"], []),
    ("CUNNING", MatchState(enemy_last="ATTACK"), None, ["DEFENSE"], []),
    ("MIMIC", MatchState(enemy_last="SUPPORT"), None, ["SUPPORT"], []),
    ("PATIENT", MatchState(round=1), None, ["SUPPORT", "DEFENSE"], []),
    ("OPPORTUNIST", MatchState(round=6, enemy_hp=0.2, enemy_low=True), None, ["ATTACK", "INTERCEPT"], []),
    ("STUBBORN", MatchState(own_last="DEFENSE", own_streak=1), None, ["DEFENSE"], []),
])
def test_each_personality_shifts_the_odds_the_way_its_rule_says(personality, match, meters, up, down):
    fired = cats(personality, match=match, meters=meters)
    plain = cats(personality=None, match=match, meters=meters)  # the same match, no personality
    for category in up:
        assert fired[category] > plain[category], (personality, category)
    for category in down:
        assert fired[category] < plain[category], (personality, category)


def test_patient_turns_to_attack_later_in_the_battle():
    early, late = cats("PATIENT", match=MatchState(round=1)), cats("PATIENT", match=MatchState(round=6))
    assert late["ATTACK"] > early["ATTACK"] and early["SUPPORT"] > late["SUPPORT"]


def test_opportunist_defends_a_little_more_while_the_enemy_is_healthy():
    healthy = cats("OPPORTUNIST", match=MatchState(round=6, enemy_low=False))
    assert healthy["DEFENSE"] > CALM["DEFENSE"]
    assert healthy["DEFENSE"] / healthy["SUPPORT"] == pytest.approx(CALM["DEFENSE"] / CALM["SUPPORT"] * 1.2)


def test_tier_scales_the_strength_of_a_personality():
    weak = cats("RECKLESS", tier=1, match=MatchState(own_hp=0.3))
    strong = cats("RECKLESS", tier=3, match=MatchState(own_hp=0.3))
    assert CALM["ATTACK"] < weak["ATTACK"] < strong["ATTACK"]


def test_anxious_is_plain_while_winning_and_chaotic_when_nervous():
    winning = cats("ANXIOUS", match=MatchState(lead=0.4), meters=MoodMeters(nerves=0.1))
    assert winning == pytest.approx(CALM)
    nervous = cats("ANXIOUS", match=MatchState(lead=-0.4), meters=MoodMeters(nerves=0.8))
    assert max(nervous.values()) < max(CALM.values()) and nervous["FEAR"] > CALM["FEAR"]
    assert sum(nervous.values()) == pytest.approx(1.0)


def test_weird_leaves_a_long_streak_and_only_a_long_one():
    limit = CATALOG.policy.mood.streak_base + (6 * 7) % CATALOG.policy.mood.streak_span  # round 6
    short = cats("WEIRD", match=MatchState(round=6, own_last="ATTACK", own_streak=limit - 1))
    long = cats("WEIRD", match=MatchState(round=6, own_last="ATTACK", own_streak=limit))
    assert short == pytest.approx(CALM) and long["ATTACK"] == pytest.approx(0.0)
    reset = cats("WEIRD", match=MatchState(round=6, own_last="DEFENSE", own_streak=1))  # the jump reset the streak
    assert reset == pytest.approx(CALM)


def test_stubborn_ignores_repeats_and_gambler_swings_with_the_score():
    weak, strong = Action("ability", "ATTACK", "weak", 100), Action("ability", "ATTACK", "strong", 200)
    actions = [weak, strong, Action("flee", "FEAR")]
    base = ctx("STUBBORN", actions=actions, match=MatchState(own_last="ATTACK", own_streak=2))
    repeated = PolicyContext(base.situation, 1.0, 0.1, False, ("ability:weak", "ability:weak"), base.weights, base.match, base.meters, base.rules)
    p = policy.probabilities(actions, repeated)
    assert p[0] / p[1] == pytest.approx(2 ** (-CATALOG.policy.potency_weight / CATALOG.policy.temperature))  # no repeat penalty

    def pair(match):
        values = policy.probabilities(actions, ctx("GAMBLER", actions=actions, match=match))
        return values[0], values[1]

    losing_weak, losing_strong = pair(MatchState(lead=-0.4))
    winning_weak, winning_strong = pair(MatchState(lead=0.5))
    assert losing_strong > losing_weak and winning_weak > winning_strong


def test_stoic_never_reacts():
    for match, meters in ((MatchState(own_hp=0.1, lead=-0.8, enemy_last="ATTACK"), MoodMeters(rage=1, nerves=1)),
                          (MatchState(enemy_low=True, lead=0.9, own_streak=9, own_last="ATTACK"), MoodMeters(confidence=1))):
        assert cats("STOIC", match=match, meters=meters) == pytest.approx(cats(None, match=match, meters=meters))
