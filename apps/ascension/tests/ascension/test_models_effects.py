from src.ascension.models import AbilitySpec, EffectSpec, FighterState, Status


def test_old_saved_states_and_abilities_load_without_statuses_or_effects():
    assert FighterState.from_dict({"hp": 10, "buffs": [], "defense": None, "cooldowns": []}).statuses == ()
    legacy = {"id": "a", "name": "A", "unlock_level": 1, "category": "ATTACK", "percentage": 100.0, "cooldown": 1,
              "stat": None, "duration": None}
    assert AbilitySpec.from_dict(legacy).effects == ()


def test_effects_and_statuses_round_trip():
    ability = AbilitySpec("a", "A", 1, "ATTACK", 100.0, 1, effects=(
        EffectSpec("bleed", percentage=20.0, rounds=3), EffectSpec("mark", rounds=2, name="prey", target="foe"), EffectSpec("cleanse")))
    assert AbilitySpec.from_dict(ability.to_dict()) == ability
    assert ability.to_dict()["effects"][0] == {"kind": "bleed", "percentage": 20.0, "rounds": 3}
    assert ability.to_dict()["effects"][2] == {"kind": "cleanse"}
    state = FighterState(5, statuses=(Status("bleed", 4, 2), Status("mark:prey", 0, 3)))
    assert FighterState.from_dict(state.to_dict()) == state
    assert state.to_dict()["statuses"][0] == {"id": "bleed", "amount": 4, "rounds_left": 2}


def test_a_legacy_essence_stat_still_becomes_power():
    legacy = {"id": "a", "name": "A", "unlock_level": 1, "category": "SUPPORT", "percentage": 50.0, "cooldown": 2,
              "stat": "essence", "duration": 2}
    assert AbilitySpec.from_dict(legacy).stat == "power"
