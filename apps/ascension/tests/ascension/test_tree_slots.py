import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.tree import AbilityTree, NodeCost, TreeError, TreeNode, passive_root_id
from tests.ascension.env import load_raw


def node(node_id, kind="ability", branch=None, requires=(), root=False, x=0, y=0):
    return TreeNode(node_id, kind, node_id, x, y, tuple(requires), 1, None if root else NodeCost("common", 1), root=root, branch=branch)


def test_passive_root_ids():
    assert passive_root_id("twoychi") == "twoychi_passive"
    assert passive_root_id("twoychi", 2) == "twoychi_passive_2"


def test_a_tree_without_slots_has_the_default_slots_and_accepts_any_node_of_the_kind():
    tree = AbilityTree([node("a", root=True), node("p", "passive", root=True, x=1)])
    assert tree.slot_ids == ("a1", "a2", "a3", "p1") and tree.declared is False
    assert tree.accepts("a2", tree.node("a")) and not tree.accepts("p1", tree.node("a")) and tree.accepts("p1", tree.node("p"))


def test_declared_slots_accept_only_their_branches():
    tree = AbilityTree(
        [node("w", branch="wolf", root=True), node("b", branch="bear", root=True, x=1), node("pw", "passive", "wolf", root=True, x=2)],
        {"a1": ("wolf",), "a2": ("bear",), "p1": ("wolf",)},
    )
    assert tree.slot_ids == ("a1", "a2", "p1") and tree.declared
    assert tree.accepts("a1", tree.node("w")) and not tree.accepts("a2", tree.node("w")) and not tree.accepts("a1", tree.node("pw"))


@pytest.mark.parametrize("slots,nodes,message", [
    ({"a1": ("x",), "p1": ("x",), "a3": ("x",)}, [node("a", branch="x", root=True), node("p", "passive", "x", root=True, x=1)], "consecutive"),
    ({"a1": ("x",)}, [node("a", branch="x", root=True)], "a1 and p1"),
    ({"a1": ("x",), "p1": ("x",), "z9": ("x",)}, [node("a", branch="x", root=True), node("p", "passive", "x", root=True, x=1)], "unknown slot"),
    ({"a1": ("x",), "p1": ("x",)}, [node("a", root=True), node("p", "passive", "x", root=True, x=1)], "needs a branch"),
    ({"a1": ("x",), "p1": ("x",)}, [node("a", branch="y", root=True), node("p", "passive", "x", root=True, x=1)], "has no slot"),
    ({"a1": (), "p1": ("x",)}, [node("a", branch="x", root=True), node("p", "passive", "x", root=True, x=1)], "at least one branch"),
])
def test_bad_slot_declarations_are_refused(slots, nodes, message):
    with pytest.raises(TreeError, match=message):
        AbilityTree(nodes, slots)


def twoychi_raw(**change):
    raw = copy.deepcopy(load_raw())
    spec = next(s for s in raw["ascendeds"] if s["id"] == "guardian")
    spec.update(change)
    return raw


def test_a_basic_ascended_cannot_have_a_fourth_ability_or_a_second_passive():
    raw = load_raw()
    spec = next(s for s in raw["ascendeds"] if s["id"] == "guardian")
    extra = copy.deepcopy(spec["abilities"][0])
    extra["id"], extra["unlock_level"] = "guardian_extra", 30
    with pytest.raises(CatalogError, match="abilities"):
        Catalog(twoychi_raw(abilities=[*spec["abilities"], extra]))
    with pytest.raises(CatalogError, match="passive_2"):
        Catalog(twoychi_raw(passive_2=spec["passive"]))


def test_the_seven_basic_ascended_keep_three_and_one():
    catalog = Catalog(load_raw())
    for sid in ("bruiser", "channeler", "forbidden", "guardian", "scout", "sentinel", "striker"):
        tree = catalog.ascended(sid).tree
        assert tree.slot_ids == ("a1", "a2", "a3", "p1") and len(tree.roots) == 4
        assert catalog.default_loadout(sid).extra_passives == ()
