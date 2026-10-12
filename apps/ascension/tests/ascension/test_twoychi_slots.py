from tests.ascension.env import CATALOG

TWOYCHI = CATALOG.ascended("twoychi")


def test_twoychi_has_four_active_and_two_passive_slots_by_branch():
    tree = TWOYCHI.tree
    assert tree.slot_ids == ("a1", "a2", "a3", "a4", "p1", "p2")
    assert [tree.branches(s) for s in tree.slot_ids] == [("wolf",), ("bear",), ("dog",), ("aya",), ("wolf", "bear", "dog"), ("aya",)]
    assert len(TWOYCHI.abilities) == 4 and TWOYCHI.passive_2 is not None and len(tree.roots) == 6


def test_every_twoychi_node_can_be_equipped_somewhere():
    tree = TWOYCHI.tree
    for node in tree.nodes:
        assert any(tree.accepts(slot, node) for slot in tree.slot_ids), node.id


def test_each_branch_has_passives_for_its_slot():
    tree = TWOYCHI.tree
    for slot in ("p1", "p2"):
        assert sum(1 for n in tree.nodes if tree.accepts(slot, n)) >= 3


def test_the_default_slots_put_each_root_in_its_own_branch_slot():
    slots = CATALOG.default_slots("twoychi")
    assert slots == {"a1": "twoychi_troys_hunt", "a2": "twoychi_mournful_veil", "a3": "twoychi_comforting_presence",
                     "a4": "twoychi_tidecall", "p1": "twoychi_passive", "p2": "twoychi_passive_2"}


def test_the_default_loadout_has_both_passives():
    kit = CATALOG.default_loadout("twoychi")
    assert len(kit.abilities) == 4 and len(kit.extra_passives) == 1


def test_default_and_saved_root_loadouts_use_the_same_slot_order_in_battle(tmp_path):
    from src.ascension.engine import BattleEngine
    from src.ascension.models import BattleSetup, PLAYER, WILD
    from src.ascension.records import AscendedRecord
    from tests.ascension.env import Env, run

    async def scenario():
        env = Env(tmp_path / "slots.sqlite3")
        await env.start_player()
        await env.give(twoychi=AscendedRecord("ann", "twoychi", 0, 30, 0, tier_id="unique"))
        async with env.repo.transaction() as tx:
            unsaved = await env.trees.loadout_in(tx, "ann", "twoychi")
        await env.trees.set_loadout("ann", "root-kit", "twoychi", CATALOG.default_slots("twoychi"))
        async with env.repo.transaction() as tx:
            saved = await env.trees.loadout_in(tx, "ann", "twoychi")
            await tx.put_loadout("ann", "twoychi", {"a1": "twoychi_tidecall"})
            stale = await env.trees.loadout_in(tx, "ann", "twoychi")
        await env.close()
        return unsaved, saved, stale

    unsaved, saved, stale = run(scenario())
    assert unsaved == saved == stale
    engine = BattleEngine(CATALOG)
    setup = BattleSetup(engine.build_fighter(PLAYER, "twoychi", "unique", 30, unsaved),
                        engine.build_fighter(WILD, "guardian", "common", 1))
    actions = engine.legal_actions(setup, engine.start_state(setup), PLAYER, can_collect=False)
    assert [a.ability_id for a in actions if a.kind == "ability"] == [
        "twoychi_troys_hunt", "twoychi_mournful_veil", "twoychi_comforting_presence", "twoychi_tidecall"]


def test_fourth_ability_resolves_with_both_frozen_passives():
    from dataclasses import replace
    import math
    from src.ascension.engine import BattleEngine
    from src.ascension.models import Action, BattleSetup, PLAYER, WILD
    from tests.ascension.helpers import ScriptedRandom

    engine = BattleEngine(CATALOG)
    player = engine.build_fighter(PLAYER, "twoychi", "unique", 30)
    # Tidecall is A4. Add a direct heal to its frozen effect list so Waterbound
    # has an observable effect alongside Troy's support-duration passive.
    from src.ascension.models import EffectSpec
    tidecall = next(a for a in player.abilities if a.id == "twoychi_tidecall")
    tidecall = replace(tidecall, effects=(EffectSpec("heal", percentage=10),))
    player = replace(player, abilities=tuple(tidecall if a.id == tidecall.id else a for a in player.abilities))
    setup = BattleSetup.from_dict(BattleSetup(player, engine.build_fighter(WILD, "guardian", "common", 1)).to_dict())
    assert len(setup.player.abilities) == 4 and len(setup.player.extra_passives) == 1
    state = engine.start_state(setup)
    state = replace(state, player=replace(state.player, hp=setup.player.max_hp - 100))
    actions = [a for a in engine.legal_actions(setup, state, PLAYER, can_collect=False) if a.kind == "ability"]
    assert len(actions) == 4 and actions[3].ability_id == "twoychi_tidecall"
    outcome = engine.resolve_round(setup, state, actions[3], Action("catch", "INTERCEPT"), ScriptedRandom(0.0))
    assert next(b for b in outcome.state.player.buffs if b.source == tidecall.id).rounds_left == tidecall.duration
    healed = next(e["amount"] for e in outcome.events if e["type"] == "heal" and e["side"] == PLAYER)
    assert healed == math.floor(math.floor(setup.player.power * 0.1) * 1.15)
