import random

import pytest

from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.personality_rules import ActiveRule, Rule
from src.ascension.models import Action, PersonalityInstance
from src.ascension.policy import ActionPolicy, Mood, PolicyContext, Situation
from tests.ascension.env import CATALOG

policy = ActionPolicy(CATALOG.policy)
mood = Mood(CATALOG)

ATTACK = Action("attack", "ATTACK")
FLEE = Action("flee", "FEAR")
CATCH = Action("catch", "INTERCEPT")
DEFEND = Action("ability", "DEFENSE", "guard", 200)
BUFF = Action("ability", "SUPPORT", "rally", 50)
ACTIONS = [ATTACK, DEFEND, BUFF, FLEE, CATCH]


def ctx(danger=0.3, aggression=0.5, advantage=0.5, weights=None, recent=(), collector=False, enemy_hp=1.0, flee_share=0.1):
    return PolicyContext(Situation(danger, aggression, advantage), enemy_hp, flee_share, collector, tuple(recent), weights or {})


def probs(actions=ACTIONS, **kwargs):
    return dict(zip([a.key for a in actions], policy.probabilities(actions, ctx(**kwargs))))


# -- mood ----------------------------------------------------------------------------

AGGRESSIVE3 = PersonalityInstance("p1", "AGGRESSIVE", 3)
CAUTIOUS2 = PersonalityInstance("p2", "CAUTIOUS", 2)


def test_mood_draw_is_uniform_over_instances():
    assert [Mood.pick(3, u) for u in (0.0, 0.33, 0.34, 0.66, 0.67, 0.999)] == [0, 0, 1, 1, 2, 2]
    assert Mood.pick(1, 0.7) == 0


def test_mood_weights_follow_the_spec_example():
    assert mood.weights([AGGRESSIVE3, CAUTIOUS2], 0) == {"ATTACK": 3, "DEFENSE": 1, "SUPPORT": 0, "FEAR": 1, "INTERCEPT": 0}
    assert mood.weights([AGGRESSIVE3, CAUTIOUS2], 1) == {"ATTACK": 1.5, "DEFENSE": 2, "SUPPORT": 0, "FEAR": 2, "INTERCEPT": 0}


def test_a_single_personality_is_always_the_mood():
    assert mood.weights([AGGRESSIVE3], 0)["ATTACK"] == 3


def test_repeated_types_add():
    three = [PersonalityInstance(f"p{i}", "AGGRESSIVE", 3) for i in range(3)]
    assert mood.weights(three, 0)["ATTACK"] == 3 + 1.5 + 1.5


# -- probabilities -------------------------------------------------------------------

def test_probabilities_sum_to_one_and_cover_every_action():
    p = probs()
    assert sum(p.values()) == pytest.approx(1.0) and set(p) == {"attack", "ability:guard", "ability:rally", "flee", "catch"}


def test_every_legal_action_stays_possible():
    assert all(value > 0 for value in probs(weights={"ATTACK": 9}, danger=0.0, advantage=1.0).values())


def test_personality_weight_raises_its_category_without_forcing_it():
    base, aggressive = probs(), probs(weights={"ATTACK": 3})
    assert aggressive["attack"] > base["attack"] and aggressive["attack"] < 0.9


def test_low_hp_still_raises_defense_and_flee_for_an_aggressive_ascended():
    safe = probs(weights={"ATTACK": 3}, danger=0.0, advantage=0.5)
    critical = probs(weights={"ATTACK": 3}, danger=1.0, advantage=0.1)
    assert critical["ability:guard"] > safe["ability:guard"] and critical["flee"] > safe["flee"]
    assert critical["attack"] < safe["attack"]


def test_a_repeat_lowers_an_action_inside_its_category_and_leaves_other_categories_alone():
    first, second = Action("ability", "ATTACK", "first", 100), Action("ability", "ATTACK", "second", 100)
    actions = [first, second, DEFEND, FLEE]
    calm = dict(zip([a.key for a in actions], policy.probabilities(actions, ctx())))
    tired = dict(zip([a.key for a in actions], policy.probabilities(actions, ctx(recent=["ability:first", "ability:first"]))))
    assert tired["ability:first"] < calm["ability:first"] and tired["ability:second"] > calm["ability:second"]
    assert tired["ability:first"] + tired["ability:second"] == pytest.approx(calm["ability:first"] + calm["ability:second"])
    assert tired["ability:guard"] == pytest.approx(calm["ability:guard"])
    ended = dict(zip([a.key for a in actions], policy.probabilities(actions, ctx(recent=["ability:first", "ability:first", "flee"]))))
    assert ended["ability:first"] == pytest.approx(calm["ability:first"])  # the run ended at flee


def test_stronger_abilities_are_preferred_within_a_category_by_the_potency_weight():
    weak, strong = Action("ability", "ATTACK", "weak", 100), Action("ability", "ATTACK", "strong", 200)
    p = probs([weak, strong, FLEE])
    spec = CATALOG.policy
    assert p["ability:strong"] / p["ability:weak"] == pytest.approx(2 ** (spec.potency_weight / spec.temperature))


def test_the_number_of_actions_in_a_category_does_not_change_the_category():
    one = policy.explain([ATTACK, DEFEND, FLEE], ctx()).categories
    three_attacks = [ATTACK, Action("ability", "ATTACK", "a2", 150), Action("ability", "ATTACK", "a3", 120), DEFEND, FLEE]
    many = policy.explain(three_attacks, ctx()).categories
    assert many == pytest.approx(one)
    p = dict(zip([a.key for a in three_attacks], policy.probabilities(three_attacks, ctx())))
    assert p["attack"] + p["ability:a2"] + p["ability:a3"] == pytest.approx(one["ATTACK"])


def test_a_missing_category_is_not_offered_and_the_rest_share_the_mass():
    only_attacks = [ATTACK, Action("ability", "ATTACK", "a2", 150), Action("ability", "ATTACK", "a3", 150)]
    p = policy.probabilities(only_attacks, ctx())
    assert sum(p) == pytest.approx(1.0) and all(v > 0 for v in p)


def test_a_lone_action_in_its_category_has_unit_potency():
    p1 = probs([ATTACK, FLEE])
    assert p1["attack"] > p1["flee"]


def test_collector_catch_grows_as_the_enemy_weakens():
    healthy = probs(collector=True, enemy_hp=1.0)["catch"]
    weak = probs(collector=True, enemy_hp=0.1)["catch"]
    assert weak > healthy


def test_wild_catch_follows_the_enemys_flee_share():
    low = probs(collector=False, flee_share=0.1)["catch"]
    high = probs(collector=False, flee_share=0.9)["catch"]
    assert high > low


def test_no_actions_is_an_error():
    with pytest.raises(ValueError):
        policy.probabilities([], ctx())


# -- choosing ------------------------------------------------------------------------

def test_choose_walks_the_cumulative_distribution():
    p = policy.probabilities(ACTIONS, ctx())
    assert policy.choose(ACTIONS, ctx(), 0.0).action == ATTACK
    assert policy.choose(ACTIONS, ctx(), p[0] + 1e-6).action == DEFEND
    assert policy.choose(ACTIONS, ctx(), 0.999999).action == CATCH
    assert policy.choose(ACTIONS, ctx(), 0.0).probabilities == tuple(p)


def sample(weights, n=4000, **kwargs):
    rng = random.Random(7)
    counts: dict[str, int] = {}
    for _ in range(n):
        key = policy.choose(ACTIONS, ctx(weights=weights, **kwargs), rng.random()).action.key
        counts[key] = counts.get(key, 0) + 1
    return {k: v / n for k, v in counts.items()}


def test_aggressive_attacks_more_and_coward_flees_more_over_many_draws():
    aggressive = sample(mood.weights([AGGRESSIVE3], 0))
    coward = sample(mood.weights([PersonalityInstance("c", "COWARD", 3)], 0))
    neutral = sample({})
    assert aggressive["attack"] > neutral["attack"] > coward["attack"]
    assert coward["flee"] > neutral["flee"] > aggressive["flee"]


def test_no_personality_picks_one_action_every_time():
    freq = sample(mood.weights([AGGRESSIVE3], 0), danger=0.2, advantage=0.8)
    assert max(freq.values()) < 0.8 and len(freq) == len(ACTIONS)


# -- personality rules ---------------------------------------------------------------

def rule(name="R#0", strength=1.0, **effects):
    when = effects.pop("when", {})
    return ActiveRule(name, Rule(when, effects), strength)


def ruled(rules, match=None, meters=None, actions=ACTIONS, **kwargs):
    base = ctx(**kwargs)
    return PolicyContext(base.situation, base.enemy_hp_fraction, base.enemy_flee_share, base.collector, base.recent_keys, base.weights,
                         match or MatchState(), meters or MoodMeters(), tuple(rules))


def cats(rules, **kwargs):
    return policy.explain(ACTIONS, ruled(rules, **kwargs)).categories


def ratio(c, a, b):
    return c[a] / c[b]


CALM = cats([])


def test_a_rule_whose_condition_fails_changes_nothing_and_a_missing_match_ignores_rules():
    never = rule(when={"lead_over": 0.9}, multiply={"ATTACK": 5.0})
    assert cats([never]) == pytest.approx(CALM)
    no_match = PolicyContext(Situation(0.3, 0.5, 0.5), 1.0, 0.1, False, (), {}, None, None, (rule(multiply={"ATTACK": 5.0}),))
    assert policy.explain(ACTIONS, no_match).categories == pytest.approx(CALM)


def test_multiply_scales_with_strength():
    full, half = cats([rule(multiply={"ATTACK": 2.0})]), cats([rule(strength=0.5, multiply={"ATTACK": 2.0})])
    base = ratio(CALM, "ATTACK", "DEFENSE")
    assert ratio(full, "ATTACK", "DEFENSE") == pytest.approx(base * 2.0)
    assert ratio(half, "ATTACK", "DEFENSE") == pytest.approx(base * 1.5)


def test_two_firing_rules_stack_and_report_their_names():
    explanation = policy.explain(ACTIONS, ruled([rule("A#0", multiply={"ATTACK": 2.0}), rule("B#1", multiply={"ATTACK": 2.0})]))
    assert ratio(explanation.categories, "ATTACK", "DEFENSE") == pytest.approx(ratio(CALM, "ATTACK", "DEFENSE") * 4.0)
    assert explanation.fired == ["A#0", "B#1"] and explanation.audit()["fired"] == ["A#0", "B#1"]


def test_chaos_flattens_the_categories_toward_the_unlikely():
    chaotic = cats([rule(chaos=1.0)])
    most = max(CALM, key=CALM.get)
    least = min(CALM, key=CALM.get)
    assert chaotic[most] < CALM[most] and chaotic[least] > CALM[least]
    assert sum(chaotic.values()) == pytest.approx(1.0)
    assert max(chaotic.values()) - min(chaotic.values()) < max(CALM.values()) - min(CALM.values())


def test_counter_and_copy_enemy_lift_the_right_category():
    counter = cats([rule(counter=True)], match=MatchState(enemy_last="ATTACK"))
    assert ratio(counter, "DEFENSE", "SUPPORT") == pytest.approx(ratio(CALM, "DEFENSE", "SUPPORT") * CATALOG.policy.counter_boost)
    after_support = cats([rule(counter=True)], match=MatchState(enemy_last="SUPPORT"))
    assert ratio(after_support, "ATTACK", "DEFENSE") == pytest.approx(ratio(CALM, "ATTACK", "DEFENSE") * CATALOG.policy.counter_boost)
    assert cats([rule(counter=True)], match=MatchState(enemy_last="FEAR")) == pytest.approx(CALM)  # nothing counters a flee
    copy = cats([rule(copy_enemy=True)], match=MatchState(enemy_last="SUPPORT"))
    assert ratio(copy, "SUPPORT", "DEFENSE") == pytest.approx(ratio(CALM, "SUPPORT", "DEFENSE") * CATALOG.policy.counter_boost)


def test_stay_lifts_the_category_it_chose_last():
    stay = cats([rule(stay=3.0)], match=MatchState(own_last="DEFENSE", own_streak=1))
    assert ratio(stay, "DEFENSE", "SUPPORT") == pytest.approx(ratio(CALM, "DEFENSE", "SUPPORT") * 3.0)


def test_break_streak_leaves_the_streak_for_the_least_likely_category_only_after_the_hidden_limit():
    limit = CATALOG.policy.mood.streak_base + (1 * 7) % CATALOG.policy.mood.streak_span  # round 1
    early = cats([rule(break_streak=True)], match=MatchState(round=1, own_last="ATTACK", own_streak=limit - 1))
    assert early == pytest.approx(CALM)
    broken = cats([rule(break_streak=True)], match=MatchState(round=1, own_last="ATTACK", own_streak=limit))
    least = min((c for c in CALM if c not in ("ATTACK", "FEAR", "INTERCEPT")), key=CALM.get)  # a turn, not a retreat
    assert broken[least] == pytest.approx(1.0) and broken["ATTACK"] == pytest.approx(0.0)
    half = cats([rule(strength=0.5, break_streak=True)], match=MatchState(round=1, own_last="ATTACK", own_streak=limit))
    assert half[least] == pytest.approx(0.5 + 0.5 * CALM[least])


def test_the_hidden_streak_limit_varies_between_two_and_four_rounds():
    mood_c = CATALOG.policy.mood
    limits = {mood_c.streak_base + (r * 7) % mood_c.streak_span for r in range(1, 20)}
    assert limits == {2, 3, 4}


def test_a_repeat_rule_replaces_the_repeat_factor():
    a, b = Action("ability", "ATTACK", "a", 100), Action("ability", "ATTACK", "b", 100)
    actions = [a, b, FLEE]
    repeated = ctx(recent=["ability:a", "ability:a"])
    plain = dict(zip(["a", "b", "flee"], policy.probabilities(actions, repeated)))
    stubborn_ctx = PolicyContext(repeated.situation, 1.0, 0.1, False, repeated.recent_keys, {}, MatchState(), MoodMeters(), (rule(repeat=1.0),))
    stubborn = dict(zip(["a", "b", "flee"], policy.probabilities(actions, stubborn_ctx)))
    assert plain["a"] < plain["b"] and stubborn["a"] == pytest.approx(stubborn["b"])


def test_pick_by_percentage_prefers_the_strong_or_the_weak_inside_a_category():
    weak, strong = Action("ability", "ATTACK", "weak", 100), Action("ability", "ATTACK", "strong", 200)
    actions = [weak, strong, FLEE]
    high = dict(zip(["weak", "strong", "flee"], policy.explain(actions, ruled([rule(pick_by_percentage="high")], actions=actions)).probabilities))
    low = dict(zip(["weak", "strong", "flee"], policy.explain(actions, ruled([rule(pick_by_percentage="low")], actions=actions)).probabilities))
    assert high["strong"] > high["weak"] and low["weak"] > low["strong"]
    assert high["strong"] / high["weak"] == pytest.approx(low["weak"] / low["strong"])


def test_choose_carries_the_audit_details():
    decision = policy.choose(ACTIONS, ruled([rule("R#0", multiply={"ATTACK": 2.0})]), 0.0)
    assert decision.details["fired"] == ["R#0"] and set(decision.details["categories"]) == {"ATTACK", "DEFENSE", "SUPPORT", "FEAR", "INTERCEPT"}


def test_active_rules_scale_with_tier_and_the_leading_instance():
    from src.ascension.catalog import Catalog
    from tests.ascension.env import load_raw
    import copy

    data = copy.deepcopy(load_raw())
    data["personalities"].append({"id": "TESTY", "categories": [], "rules": [{"chaos": 0.5}, {"stay": 2.0}]})
    local = Mood(Catalog(data))
    lead, other = PersonalityInstance("a", "TESTY", 3), PersonalityInstance("b", "TESTY", 1)
    rules = local.active_rules([lead, other], 0)
    assert [(r.name, round(r.strength, 4)) for r in rules] == [
        ("TESTY#0", 1.0), ("TESTY#1", 1.0),
        ("TESTY#0", round(1 / 3 * CATALOG.policy.off_mood_factor, 4)), ("TESTY#1", round(1 / 3 * CATALOG.policy.off_mood_factor, 4))]
    assert local.active_rules([], None) == ()
