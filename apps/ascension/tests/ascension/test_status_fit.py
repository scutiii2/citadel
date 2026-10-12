from src.ascension.models import PLAYER, WILD, Action, BattleState, EffectSpec, FighterState, Status
from src.ascension.status_fit import WASTED, action_fit
from tests.ascension.helpers import ability, fighter, setup


def use(spec):
    return Action("ability", spec.category, spec.id, spec.percentage)


def build(spec, player=None, wild=None):
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    state = BattleState(1, player or FighterState(s.player.max_hp), wild or FighterState(s.wild.max_hp))
    return s, state, [use(spec)]


def test_a_heal_at_full_hp_is_poor_and_a_wounded_heal_is_better():
    spec = ability("mend", "DEFENSE", 100, effects=(EffectSpec("heal", percentage=50),))
    s, state, legal = build(spec)
    assert action_fit(s, state, PLAYER, legal)[legal[0].key] == WASTED
    s, state, legal = build(spec, player=FighterState(50))
    assert action_fit(s, state, PLAYER, legal)[legal[0].key] == 1.5


def test_cleanse_wants_a_harmful_status():
    spec = ability("shake", "DEFENSE", 100, effects=(EffectSpec("cleanse"),))
    s, state, legal = build(spec)
    assert action_fit(s, state, PLAYER, legal)[legal[0].key] == WASTED
    s, state, legal = build(spec, player=FighterState(100, statuses=(Status("bleed", 5, 2),)))
    assert action_fit(s, state, PLAYER, legal)[legal[0].key] == 2.0


def test_a_ward_that_is_up_and_a_status_the_foe_has_are_poor():
    ward = ability("ward", "DEFENSE", 100, effects=(EffectSpec("ward", rounds=3),))
    s, state, legal = build(ward, player=FighterState(100, statuses=(Status("ward", 1, 2),)))
    assert action_fit(s, state, PLAYER, legal)[legal[0].key] == WASTED
    bite = ability("bite", "ATTACK", 100, effects=(EffectSpec("bleed", percentage=20, rounds=3),))
    s, state, legal = build(bite, wild=FighterState(100, statuses=(Status("bleed", 5, 2),)))
    assert action_fit(s, state, PLAYER, legal)[legal[0].key] == 0.5


def test_plain_actions_are_not_listed():
    plain = ability("hit", "ATTACK", 100)
    s, state, legal = build(plain)
    assert action_fit(s, state, PLAYER, legal + [Action("attack", "ATTACK")]) == {}
