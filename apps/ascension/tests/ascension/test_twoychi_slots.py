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
