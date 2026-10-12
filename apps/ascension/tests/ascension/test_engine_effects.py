from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, Action, BattleState, EffectSpec, FighterState, Status
from tests.ascension.env import CATALOG
from tests.ascension.helpers import ScriptedRandom, ability, fighter, setup

engine = BattleEngine(CATALOG)
ATTACK = Action("attack", "ATTACK")
FLEE = Action("flee", "FEAR")
IDLE = (0.0, 0.99, 0.99)  # the player moves first and both flee attempts fail


def use(spec):
    return Action("ability", spec.category, spec.id, spec.percentage)


def fx(kind, **fields):
    return EffectSpec(kind, **fields)


def state_of(s, player=None, wild=None, rnd=1):
    return BattleState(rnd, player or FighterState(s.player.max_hp), wild or FighterState(s.wild.max_hp))


def step(s, state, player_action, wild_action, *draws):
    return engine.resolve_round(s, state, player_action, wild_action, ScriptedRandom(*draws))


def ids(fstate):
    return {st.id for st in fstate.statuses}


def get(fstate, status_id):
    return next(st for st in fstate.statuses if st.id == status_id)


def test_heal_restores_hp_up_to_the_maximum():
    spec = ability("mend", "DEFENSE", 100, effects=(fx("heal", percentage=50),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s, player=FighterState(50)), use(spec), FLEE, 0.0, 0.99)
    assert out.state.player.hp == 70 and {"type": "heal", "side": "player", "amount": 20} in out.events
    near = step(s, state_of(s, player=FighterState(90)), use(spec), FLEE, 0.0, 0.99)
    assert near.state.player.hp == 100 and {"type": "heal", "side": "player", "amount": 10} in near.events


def test_regen_heals_at_the_end_of_each_round_then_ends():
    spec = ability("flow", "SUPPORT", 10, stat="power", duration=1, effects=(fx("regen", percentage=25, rounds=3),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s, player=FighterState(50)), use(spec), FLEE, 0.0, 0.99)
    assert out.state.player.hp == 60 and {"type": "tick", "side": "player", "kind": "regen", "amount": 10, "hp": 60} in out.events
    state = out.state
    for expected in (70, 80, 80):
        state = step(s, state, FLEE, FLEE, *IDLE).state
        assert state.player.hp == expected
    assert state.player.statuses == ()


def test_bleed_hurts_at_the_end_of_each_round_and_expires():
    spec = ability("bite", "ATTACK", 100, effects=(fx("bleed", percentage=25, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert out.state.wild.hp == 100 - 40 - 10 and get(out.state.wild, "bleed").amount == 10
    assert {"type": "status", "side": "player", "target": "wild", "status": "bleed", "amount": 10, "rounds": 2} in out.events
    second = step(s, out.state, FLEE, FLEE, *IDLE)
    assert second.state.wild.hp == 40 and second.state.wild.statuses == ()
    assert step(s, second.state, FLEE, FLEE, *IDLE).state.wild.hp == 40


def test_a_bleed_that_kills_ends_the_battle_and_the_wild_side_is_checked_first():
    s = setup()

    def bleeding(hp):
        return FighterState(hp, statuses=(Status("bleed", 10, 2),))

    wild = step(s, state_of(s, wild=bleeding(8)), FLEE, FLEE, *IDLE)
    assert wild.terminal == "won" and wild.state.round == 1
    assert step(s, state_of(s, player=bleeding(8)), FLEE, FLEE, *IDLE).terminal == "knocked_out"
    assert step(s, state_of(s, player=bleeding(8), wild=bleeding(8)), FLEE, FLEE, *IDLE).terminal == "won"


def test_a_ward_leaves_one_hp_once():
    s = setup()
    warded = FighterState(30, statuses=(Status("ward", 0, 2),))
    out = step(s, state_of(s, player=warded), FLEE, ATTACK, 0.99, 0.99)  # the wild attacks first; the player's flee fails
    assert out.state.player.hp == 1 and out.terminal is None and "ward" not in ids(out.state.player)
    assert {"type": "ward_triggered", "side": "player"} in out.events
    assert step(s, out.state, FLEE, ATTACK, 0.99, 0.99).terminal == "knocked_out"


def test_a_ward_also_saves_from_a_bleed_and_is_used_up():
    s = setup()
    state = state_of(s, player=FighterState(5, statuses=(Status("bleed", 10, 3), Status("ward", 0, 3))))
    out = step(s, state, FLEE, FLEE, *IDLE)
    assert out.terminal is None and out.state.player.hp == 1 and "ward" not in ids(out.state.player)
    assert step(s, out.state, FLEE, FLEE, *IDLE).terminal == "knocked_out"


def test_slow_and_weaken_lower_speed_and_power_with_a_floor_of_one():
    spec = ability("chill", "ATTACK", 100, effects=(fx("slow", percentage=50, rounds=2), fx("weaken", percentage=25, rounds=2)))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert engine.stat(s.wild, out.state.wild, "speed") == 10 and engine.stat(s.wild, out.state.wild, "power") == 30
    harsh = ability("freeze", "ATTACK", 100, effects=(fx("slow", percentage=900, rounds=2),))
    s2 = setup(fighter(PLAYER, abilities=(harsh,)), fighter(WILD))
    out2 = step(s2, state_of(s2), use(harsh), FLEE, 0.0, 0.99)
    assert engine.stat(s2.wild, out2.state.wild, "speed") == 1


def test_exposed_weakens_the_targets_shield():
    shield = ability("wall", "DEFENSE", 100)
    s = setup(fighter(PLAYER), fighter(WILD, abilities=(shield,)))
    plain = step(s, state_of(s), ATTACK, use(shield), 0.0)
    exposed = step(s, state_of(s, wild=FighterState(100, statuses=(Status("exposed", 20, 2),))), ATTACK, use(shield), 0.0)
    assert 100 - plain.state.wild.hp == 28 and 100 - exposed.state.wild.hp == 33


def test_an_exposed_effect_puts_the_status_on_the_target():
    spec = ability("break", "ATTACK", 100, effects=(fx("exposed", percentage=50, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert get(out.state.wild, "exposed").amount == 20


def test_marks_sit_on_the_chosen_target_and_expire():
    spec = ability("brand", "ATTACK", 100, effects=(fx("mark", name="prey", rounds=3, target="foe"),
                                                    fx("mark", name="soaked", rounds=2, target="self")))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert get(out.state.wild, "mark:prey").rounds_left == 2 and get(out.state.player, "mark:soaked").rounds_left == 1
    later = step(s, step(s, out.state, FLEE, FLEE, *IDLE).state, FLEE, FLEE, *IDLE).state
    assert "mark:soaked" not in ids(later.player) and "mark:prey" not in ids(later.wild)


def test_cleanse_removes_the_four_harmful_statuses_only():
    spec = ability("clear", "DEFENSE", 100, effects=(fx("cleanse"),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    statuses = (Status("bleed", 5, 3), Status("slow", -3, 3), Status("weaken", -3, 3), Status("exposed", 4, 3),
                Status("mark:prey", 0, 3), Status("regen", 5, 3), Status("ward", 0, 3))
    out = step(s, state_of(s, player=FighterState(50, statuses=statuses)), use(spec), FLEE, 0.0, 0.99)
    assert ids(out.state.player) == {"mark:prey", "regen", "ward"}
    assert {"type": "cleanse", "side": "player", "removed": ["bleed", "slow", "weaken", "exposed"]} in out.events


def test_applying_a_status_again_refreshes_it_instead_of_stacking():
    spec = ability("bite", "ATTACK", 100, effects=(fx("bleed", percentage=25, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    old = FighterState(100, statuses=(Status("bleed", 3, 1),))
    out = step(s, state_of(s, wild=old), use(spec), FLEE, 0.0, 0.99)
    bleeds = [st for st in out.state.wild.statuses if st.id == "bleed"]
    assert len(bleeds) == 1 and bleeds[0].amount == 10 and bleeds[0].rounds_left == 1  # two rounds, one tick done


def test_attack_effects_do_not_apply_when_the_attack_wins_the_battle():
    spec = ability("bite", "ATTACK", 100, effects=(fx("bleed", percentage=25, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s, wild=FighterState(30)), use(spec), FLEE, 0.0, 0.99)
    assert out.terminal == "won" and not any(e["type"] == "status" for e in out.events)


def test_an_ability_without_effects_changes_no_statuses():
    spec = ability("plain", "ATTACK", 100)
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert out.state.player.statuses == () and out.state.wild.statuses == () and out.state.wild.hp == 60
