import copy

import pytest

from src.ascension.catalog import Catalog
from src.ascension.errors import InvalidRequest
from src.ascension.records import AscendedRecord
from src.ascension.tree import passive_root_id
from src.ascension.trees import TreeService
from tests.ascension.env import Env, load_raw, run
from tests.ascension.test_trees import TREE

PASSIVE = passive_root_id("guardian")
BRANCHES = {"guardian_bulwark": "def", "guardian_rally": "def", "guardian_heavy_blow": "att", PASSIVE: "att",
            "guardian_iron_wall": "def", "guardian_stoneskin": "def", "guardian_shield_slam": "att"}
SLOTS = {"a1": ["att"], "a2": ["def"], "a3": ["att", "def"], "p1": ["att", "def"]}


def make(tmp_path):
    tree = copy.deepcopy(TREE)
    for item in tree["nodes"]:
        item["branch"] = BRANCHES[item["id"]]
    tree["slots"] = SLOTS
    raw = copy.deepcopy(load_raw())
    next(s for s in raw["ascendeds"] if s["id"] == "guardian")["tree"] = tree
    env = Env(tmp_path / "t.sqlite3")
    env.catalog = Catalog(raw)
    env.trees = TreeService(env.repo, env.writer, env.catalog)
    return env


async def owned(env):
    await env.start_player()
    await env.give(guardian=AscendedRecord("ann", "guardian", 0, 20, 0, tier_id="common"))


def test_a_node_goes_only_in_a_slot_that_takes_its_branch(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest, match="'guardian_bulwark' cannot go in slot 'a1'"):
            await env.trees.set_loadout("ann", "l1", "guardian", {"a1": "guardian_bulwark"})
        saved = await env.trees.set_loadout("ann", "l2", "guardian", {"a2": "guardian_bulwark", "a3": "guardian_heavy_blow"})
        await env.close()
        return saved

    assert run(scenario())["slots"] == {"a2": "guardian_bulwark", "a3": "guardian_heavy_blow"}


def test_a_slot_the_ascended_does_not_have_is_refused(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest, match="no slot 'a4'"):
            await env.trees.set_loadout("ann", "l1", "guardian", {"a1": "guardian_heavy_blow", "a4": "guardian_rally"})
        await env.close()

    run(scenario())


def test_a_node_in_two_slots_and_an_empty_active_loadout_are_refused(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest, match="in two slots"):
            await env.trees.set_loadout("ann", "l1", "guardian", {"a2": "guardian_bulwark", "a3": "guardian_bulwark"})
        with pytest.raises(InvalidRequest, match="at least one active"):
            await env.trees.set_loadout("ann", "l2", "guardian", {"p1": PASSIVE})
        with pytest.raises(InvalidRequest, match="at least one active"):
            await env.trees.set_loadout("ann", "l3", "guardian", {"a1": None})
        async with env.repo.transaction() as tx:
            stored = await tx.get_loadout("ann", "guardian")
        await env.close()
        return stored

    assert run(scenario()) == {}


def test_the_view_lists_the_slots_with_their_branches_and_the_loadout_by_slot(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        view = await env.trees.view("ann", "guardian")
        await env.close()
        return view

    view = run(scenario())
    assert view["slots"] == [
        {"id": "a1", "kind": "ability", "branches": ["att"]}, {"id": "a2", "kind": "ability", "branches": ["def"]},
        {"id": "a3", "kind": "ability", "branches": ["att", "def"]}, {"id": "p1", "kind": "passive", "branches": ["att", "def"]},
    ]
    assert list(view["loadout"]) == ["a1", "a2", "a3", "p1"]
    assert view["loadout"]["a1"] == "guardian_heavy_blow" and view["loadout"]["a2"] == "guardian_bulwark"


def test_a_stale_slot_is_ignored_at_battle_start(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        async with env.repo.transaction() as tx:
            await tx.put_loadout("ann", "guardian", {"a1": "guardian_bulwark", "a2": "guardian_rally"})
            kept = await env.trees.loadout_in(tx, "ann", "guardian")
            await tx.put_loadout("ann", "guardian", {"a1": "guardian_bulwark"})
            fallback = await env.trees.loadout_in(tx, "ann", "guardian")
        await env.close()
        return kept, fallback

    kept, fallback = run(scenario())
    assert [a.id for a in kept.abilities] == ["guardian_rally"]  # a1 holds a node of the wrong branch and is dropped
    assert [a.id for a in fallback.abilities] == ["guardian_bulwark", "guardian_rally", "guardian_heavy_blow"]
