from dataclasses import replace

from src.ascension.battle_view import BattleViewBuilder
from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, BattleState, EffectSpec, FighterState, Status
from tests.ascension.env import CATALOG
from tests.ascension.helpers import ability, battle_record, fighter, setup


def test_the_public_view_shows_statuses_and_ability_effects():
    spec = ability("bite", "ATTACK", 100, effects=(EffectSpec("bleed", percentage=20.0, rounds=3),))
    record = replace(
        battle_record(),
        setup=setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD)),
        state=BattleState(1, FighterState(100, statuses=(Status("mark:prey", 0, 2),)), FighterState(100, statuses=(Status("bleed", 5, 3),))),
    )
    view = BattleViewBuilder(BattleEngine(CATALOG), CATALOG).build(record, {}, 0.0)
    assert view["player"]["statuses"] == [{"id": "mark:prey", "amount": 0, "rounds_left": 2}]
    assert view["wild"]["statuses"] == [{"id": "bleed", "amount": 5, "rounds_left": 3}]
    assert view["player"]["abilities"][0]["effects"] == [{"kind": "bleed", "percentage": 20.0, "rounds": 3}]
    assert view["wild"]["abilities"] == []
    assert view["actions"][1]["effects"] == [{"kind": "bleed", "percentage": 20.0, "rounds": 3}]
    assert view["actions"][0]["effects"] == []  # the basic attack has none
