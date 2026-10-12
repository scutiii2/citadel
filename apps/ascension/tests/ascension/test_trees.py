import copy

import pytest

from src.ascension.catalog import Catalog
from src.ascension.errors import InsufficientEssence, InvalidRequest, NotFound, UpgradeNotReady, WrongPhase
from src.ascension.records import AscendedRecord
from src.ascension.tree import passive_root_id
from src.ascension.trees import TreeService
from tests.ascension.env import Env, load_raw, run
from tests.ascension.helpers import battle_record

TREE = {"nodes": [
    {"id": "guardian_bulwark", "root": True, "x": 0, "y": 0}, {"id": "guardian_rally", "root": True, "x": 0, "y": 100},
    {"id": "guardian_heavy_blow", "root": True, "x": 0, "y": 200}, {"id": passive_root_id("guardian"), "root": True, "x": 100, "y": 100},
    {"id": "guardian_iron_wall", "kind": "ability", "name": "Iron Wall", "category": "DEFENSE", "percentage": 260, "cooldown": 3,
     "unlock_level": 12, "requires": ["guardian_bulwark"], "cost": {"tier": "common", "amount": 3}, "x": 200, "y": 0},
    {"id": "guardian_stoneskin", "kind": "passive", "name": "Stoneskin", "unlock_level": 15,
     "passive": {"kind": "defense_rating_bonus", "params": {"power_fraction": 0.4}},
     "requires": ["guardian_iron_wall"], "cost": {"tier": "rare", "amount": 2}, "x": 300, "y": 0},
    {"id": "guardian_shield_slam", "kind": "ability", "name": "Shield Slam", "category": "ATTACK", "percentage": 190, "cooldown": 2,
     "unlock_level": 5, "requires": ["guardian_heavy_blow"], "cost": {"tier": "common", "amount": 1}, "x": 200, "y": 200},
]}


def make(tmp_path):
    raw = copy.deepcopy(load_raw())
    next(s for s in raw["ascendeds"] if s["id"] == "guardian")["tree"] = TREE
    env = Env(tmp_path / "t.sqlite3")
    env.catalog = Catalog(raw)
    env.trees = TreeService(env.repo, env.writer, env.catalog)
    return env


async def owned(env, level=20):
    await env.start_player()
    await env.give(guardian=AscendedRecord("ann", "guardian", 0, level, 0, tier_id="common"))


def states(view):
    return {n["id"]: (n["state"], n["reason"]) for n in view["nodes"]}


def test_the_view_shows_roots_learned_and_why_other_nodes_are_locked(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env, level=3)
        view = await env.trees.view("ann", "guardian")
        await env.close()
        return view

    view = run(scenario())
    s = states(view)
    assert s["guardian_bulwark"] == ("learned", None) and s[passive_root_id("guardian")][0] == "learned"
    assert s["guardian_iron_wall"] == ("locked", "needs level 12")
    assert s["guardian_stoneskin"] == ("locked", "needs Iron Wall")
    assert s["guardian_shield_slam"] == ("locked", "needs level 5")
    assert view["loadout"] == {"a1": "guardian_bulwark", "a2": "guardian_rally", "a3": "guardian_heavy_blow",
                               "p1": passive_root_id("guardian")}
    assert view["level"] == 3 and view["essences"] == {}


def test_a_node_without_the_essence_says_so_and_then_becomes_learnable(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        before = states(await env.trees.view("ann", "guardian"))
        await env.give_essence("common", 3)
        after = states(await env.trees.view("ann", "guardian"))
        await env.close()
        return before, after

    before, after = run(scenario())
    assert before["guardian_iron_wall"] == ("locked", "needs 3 common essence")
    assert after["guardian_iron_wall"] == ("learnable", None)


def test_learning_spends_the_essence_once_and_unlocks_the_next_node(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        await env.give_essence("common", 4)
        first = await env.trees.learn("ann", "k1", "guardian", "guardian_iron_wall")
        again = await env.trees.learn("ann", "k1", "guardian", "guardian_iron_wall")  # same key: replayed
        view = await env.trees.view("ann", "guardian")
        async with env.repo.transaction() as tx:
            essences = await tx.essence_counts("ann")
        await env.close()
        return first, again, view, essences

    first, again, view, essences = run(scenario())
    assert first == again and (first["node_id"], first["essence_tier"], first["essence_spent"]) == ("guardian_iron_wall", "common", 3)
    assert essences == {"common": 1} and states(view)["guardian_iron_wall"][0] == "learned"
    assert states(view)["guardian_stoneskin"] == ("locked", "needs 2 rare essence")


@pytest.mark.parametrize("node,level,essence,error", [
    ("guardian_iron_wall", 5, 9, UpgradeNotReady),   # level
    ("guardian_stoneskin", 20, 9, UpgradeNotReady),  # prerequisite
    ("guardian_iron_wall", 20, 2, InsufficientEssence),
    ("guardian_bulwark", 20, 9, UpgradeNotReady),    # a root is already learned
    ("nope", 20, 9, InvalidRequest),
])
def test_learning_refusals_change_nothing(tmp_path, node, level, essence, error):
    async def scenario():
        env = make(tmp_path)
        await owned(env, level=level)
        await env.give_essence("common", essence)
        with pytest.raises(error):
            await env.trees.learn("ann", "k1", "guardian", node)
        async with env.repo.transaction() as tx:
            return await tx.learned_nodes("ann", "guardian"), await tx.essence_counts("ann")

    learned, essences = run(scenario())
    assert learned == set() and essences == {"common": essence}


def test_you_cannot_learn_for_an_ascended_you_do_not_own(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        for call in (lambda: env.trees.learn("ann", "k1", "scout", "scout_quickstep"), lambda: env.trees.view("ann", "scout"),
                     lambda: env.trees.learn("ann", "k2", "dragon", "x")):
            with pytest.raises(NotFound):
                await call()
        await env.close()

    run(scenario())


def test_a_loadout_swaps_in_learned_nodes_and_is_what_a_battle_resolves(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        await env.give_essence("common", 9)
        await env.give_essence("rare", 9)
        for key, node in (("a", "guardian_iron_wall"), ("b", "guardian_stoneskin"), ("c", "guardian_shield_slam")):
            await env.trees.learn("ann", key, "guardian", node)
        saved = await env.trees.set_loadout("ann", "l1", "guardian",
                                            ["guardian_shield_slam", "guardian_iron_wall", "guardian_heavy_blow"], "guardian_stoneskin")
        view = await env.trees.view("ann", "guardian")
        async with env.repo.transaction() as tx:
            kit = await env.trees.loadout_in(tx, "ann", "guardian")
        await env.close()
        return saved, view, kit

    saved, view, kit = run(scenario())
    assert saved["abilities"] == ["guardian_shield_slam", "guardian_iron_wall", "guardian_heavy_blow"] and saved["passive"] == "guardian_stoneskin"
    assert view["loadout"] == {"a1": "guardian_shield_slam", "a2": "guardian_iron_wall", "a3": "guardian_heavy_blow", "p1": "guardian_stoneskin"}
    assert [a.id for a in kit.abilities] == ["guardian_shield_slam", "guardian_iron_wall", "guardian_heavy_blow"]
    assert kit.passive.kind == "defense_rating_bonus"


def test_a_loadout_may_be_all_attack_and_have_no_passive(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        await env.give_essence("common", 5)
        await env.trees.learn("ann", "a", "guardian", "guardian_shield_slam")
        await env.trees.set_loadout("ann", "l1", "guardian", ["guardian_shield_slam", "guardian_heavy_blow"], None)
        async with env.repo.transaction() as tx:
            kit = await env.trees.loadout_in(tx, "ann", "guardian")
        await env.close()
        return kit

    kit = run(scenario())
    assert [a.category for a in kit.abilities] == ["ATTACK", "ATTACK"] and kit.passive.kind == "none"


@pytest.mark.parametrize("abilities,passive", [
    ([], None),                                                                              # at least one
    (["guardian_bulwark"] * 2, None),                                                         # duplicates
    (["guardian_bulwark", "guardian_rally", "guardian_heavy_blow", "guardian_shield_slam"], None),  # too many
    (["guardian_iron_wall"], None),                                                           # not learned
    (["guardian_passive"], None),                                                             # a passive in an ability slot
    (["guardian_bulwark"], "guardian_rally"),                                                 # an ability in the passive slot
    (["guardian_bulwark"], "guardian_stoneskin"),                                             # passive not learned
    (["ghost"], None),
])
def test_a_bad_loadout_is_refused_and_changes_nothing(tmp_path, abilities, passive):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest):
            await env.trees.set_loadout("ann", "l1", "guardian", abilities, passive)
        async with env.repo.transaction() as tx:
            return await tx.get_loadout("ann", "guardian")

    assert run(scenario()) == {}


def test_the_loadout_cannot_change_while_that_ascended_fights(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        async with env.repo.transaction() as tx:
            await tx.add_battle(battle_record())  # an active battle for ann whose fighter is the guardian
        with pytest.raises(WrongPhase):
            await env.trees.set_loadout("ann", "l1", "guardian", ["guardian_bulwark"], None)
        await env.close()

    run(scenario())
