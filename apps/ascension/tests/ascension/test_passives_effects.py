import pytest

from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, Action, BattleState, EffectSpec, FighterState, PassiveSpec, Status
from src.ascension.passives import PassiveFactory
from tests.ascension.env import CATALOG
from tests.ascension.helpers import ScriptedRandom, ability, fighter, setup

engine = BattleEngine(CATALOG)
ATTACK = Action("attack", "ATTACK")
FLEE = Action("flee", "FEAR")


def damage_dealt(passive, wild_statuses):
    s = setup(fighter(PLAYER, passive=passive), fighter(WILD))
    state = BattleState(1, FighterState(100), FighterState(100, statuses=wild_statuses))
    out = engine.resolve_round(s, state, ATTACK, FLEE, ScriptedRandom(0.0, 0.99))
    return 100 - out.state.wild.hp


def test_attack_bonus_vs_marked_only_counts_its_own_mark():
    passive = PassiveSpec("attack_bonus_vs_marked", {"mark": "prey", "power_fraction": 0.5})
    assert damage_dealt(passive, ()) == 40
    assert damage_dealt(passive, (Status("mark:prey", 0, 3),)) == 60  # 40 + 50% of 40
    assert damage_dealt(passive, (Status("mark:soaked", 0, 3),)) == 40


def heal_result(passive, hp, max_hp=200):
    spec = ability("mend", "DEFENSE", 100, effects=(EffectSpec("heal", percentage=50),))
    s = setup(fighter(PLAYER, hp=max_hp, abilities=(spec,), passive=passive), fighter(WILD))
    state = BattleState(1, FighterState(hp), FighterState(100))
    out = engine.resolve_round(s, state, Action("ability", "DEFENSE", "mend", 100), FLEE, ScriptedRandom(0.0, 0.99))
    return out.state.player.hp - hp


def test_heal_bonus_always_or_only_when_low():
    assert heal_result(PassiveSpec("none"), 100) == 20
    always = PassiveSpec("heal_bonus", {"fraction": 0.5})
    assert heal_result(always, 100) == 30
    low = PassiveSpec("heal_bonus", {"fraction": 0.5, "hp_below": 0.5})
    assert heal_result(low, 150) == 20 and heal_result(low, 60) == 30


def test_the_new_kinds_are_registered_and_bad_params_fail():
    factory = PassiveFactory()
    assert factory.create(PassiveSpec("attack_bonus_vs_marked", {"mark": "prey", "power_fraction": 0.2})).marked_bonus(40, frozenset({"prey"})) == 8
    assert factory.create(PassiveSpec("heal_bonus", {"fraction": 0.25})).heal_multiplier(10, 100) == pytest.approx(1.25)
    with pytest.raises(TypeError):
        factory.create(PassiveSpec("heal_bonus", {}))
