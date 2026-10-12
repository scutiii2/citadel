import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.tree import passive_root_id
from tests.ascension.env import load_raw


@pytest.fixture(scope="module")
def raw():
    return load_raw()


def build(raw, mutate):
    data = copy.deepcopy(raw)
    mutate(next(s for s in data["ascendeds"] if s["id"] == "guardian"))
    return Catalog(data)


def tree_of(**extra):
    roots = [
        {"id": "guardian_bulwark", "root": True, "x": 0, "y": 0},
        {"id": "guardian_rally", "root": True, "x": 0, "y": 100},
        {"id": "guardian_heavy_blow", "root": True, "x": 0, "y": 200},
        {"id": passive_root_id("guardian"), "root": True, "x": 100, "y": 100},
    ]
    return {"nodes": roots + extra.get("nodes", [])}


ABILITY = {"id": "guardian_iron_wall", "kind": "ability", "name": "Iron Wall", "category": "DEFENSE", "percentage": 260,
           "cooldown": 3, "unlock_level": 12, "requires": ["guardian_bulwark"],
           "cost": {"tier": "common", "amount": 3}, "x": 200, "y": 0}
PASSIVE = {"id": "guardian_stoneskin", "kind": "passive", "name": "Stoneskin", "unlock_level": 15,
           "passive": {"kind": "defense_rating_bonus", "params": {"power_fraction": 0.4}},
           "requires": ["guardian_iron_wall"], "cost": {"tier": "rare", "amount": 3}, "x": 300, "y": 0}


def test_an_ascended_without_a_tree_has_only_its_roots(raw):
    catalog = build(raw, lambda s: s.pop("tree", None))
    tree = catalog.ascended("guardian").tree
    assert [n.id for n in tree.nodes] == ["guardian_bulwark", "guardian_rally", "guardian_heavy_blow", "guardian_passive"]
    assert all(n.root and n.cost is None for n in tree.nodes)
    assert tree.node("guardian_passive").passive == catalog.ascended("guardian").passive
    assert tree.node("guardian_rally").ability == catalog.ascended("guardian").abilities[1]


def test_a_tree_adds_abilities_and_passives(raw):
    catalog = build(raw, lambda s: s.update(tree=tree_of(nodes=[ABILITY, PASSIVE])))
    tree = catalog.ascended("guardian").tree
    wall, skin = tree.node("guardian_iron_wall"), tree.node("guardian_stoneskin")
    assert (wall.ability.category, wall.ability.percentage, wall.unlock_level, wall.cost.tier, wall.cost.amount) == ("DEFENSE", 260.0, 12, "common", 3)
    assert (skin.passive.kind, skin.unlock_level, skin.requires) == ("defense_rating_bonus", 15, ("guardian_iron_wall",))


def test_the_default_loadout_is_the_catalog_kit(raw):
    catalog = build(raw, lambda s: None)
    kit = catalog.default_loadout("guardian")
    assert [a.id for a in kit.abilities] == ["guardian_bulwark", "guardian_rally", "guardian_heavy_blow"]
    assert kit.passive.kind == "defense_extension"


@pytest.mark.parametrize("mutate,message", [
    (lambda s: s.update(tree={"nodes": tree_of()["nodes"][:3]}), "every root"),
    (lambda s: s.update(tree={"nodes": tree_of()["nodes"] + [{"id": "ghost", "root": True, "x": 9, "y": 9}]}), "a root must be one of"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "requires": ["nope"]}])), "unknown node"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "category": "HEAL"}])), "category must be"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "cost": {"tier": "forbidden", "amount": 1}}])), "regular tier"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "cost": {"tier": "common", "amount": 0}}])), "amount"),
    (lambda s: s.update(tree=tree_of(nodes=[{k: v for k, v in ABILITY.items() if k != "cost"}])), "needs a cost"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "x": "far"}])), "x and y"),
    (lambda s: s.update(tree=tree_of(nodes=[{**PASSIVE, "passive": {"kind": "teleport", "params": {}}}, ABILITY])), "unknown passive"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "kind": "spell"}])), "kind must be"),
    (lambda s: s.update(tree=tree_of(nodes=[ABILITY, {**ABILITY, "x": 250}])), "unique"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "requires": []}])), "unreachable"),
    (lambda s: s.update(tree={"nodes": tree_of()["nodes"], "extra": 1}), "only nodes"),
])
def test_a_broken_tree_is_a_catalog_error(raw, mutate, message):
    with pytest.raises(CatalogError, match=message):
        build(raw, mutate)


def test_node_ids_are_unique_across_all_ascended(raw):
    data = copy.deepcopy(raw)
    next(s for s in data["ascendeds"] if s["id"] == "guardian")["tree"] = tree_of(nodes=[ABILITY])
    scout = next(s for s in data["ascendeds"] if s["id"] == "scout")
    scout["tree"] = {"nodes": [
        {"id": "scout_quickstep", "root": True, "x": 0, "y": 0}, {"id": "scout_swift_slash", "root": True, "x": 0, "y": 100},
        {"id": "scout_evade", "root": True, "x": 0, "y": 200}, {"id": "scout_passive", "root": True, "x": 100, "y": 100},
        {**ABILITY, "requires": ["scout_evade"]}]}
    with pytest.raises(CatalogError, match="unique across all Ascended"):
        Catalog(data)
