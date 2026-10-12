import pytest

from src.ascension.models import AbilitySpec, PassiveSpec
from src.ascension.tree import AbilityTree, NodeCost, TreeError, TreeNode, passive_root_id


def ability(node_id, requires=(), root=False, x=0.0, y=0.0, level=1):
    spec = AbilitySpec(node_id, node_id.title(), level, "ATTACK", 100.0, 1)
    return TreeNode(node_id, "ability", spec.name, x, y, tuple(requires), level,
                    None if root else NodeCost("common", 1), root, ability=spec)


def test_a_valid_tree_is_found_by_node_id():
    tree = AbilityTree([ability("r", root=True), ability("a", ["r"], x=1), ability("b", ["a"], x=2)])
    assert tree.node("b").requires == ("a",) and tree.node("zzz") is None
    assert [n.id for n in tree.roots] == ["r"]


def test_node_ids_must_be_unique():
    with pytest.raises(TreeError, match="unique"):
        AbilityTree([ability("r", root=True), ability("r", x=1)])


def test_a_requirement_must_exist():
    with pytest.raises(TreeError, match="unknown node"):
        AbilityTree([ability("r", root=True), ability("a", ["ghost"], x=1)])


def test_a_cycle_or_an_unreachable_node_is_rejected():
    with pytest.raises(TreeError, match="unreachable"):
        AbilityTree([ability("r", root=True), ability("a", ["b"], x=1), ability("b", ["a"], x=2)])
    with pytest.raises(TreeError, match="unreachable"):
        AbilityTree([ability("r", root=True), ability("a", [], x=1)])


def test_roots_have_no_requirements_and_a_tree_needs_a_root():
    with pytest.raises(TreeError, match="root"):
        AbilityTree([ability("a", x=1)])
    with pytest.raises(TreeError, match="root"):
        AbilityTree([ability("r", root=True), ability("r2", ["r"], root=True, x=1)])


def test_two_nodes_cannot_share_a_point():
    with pytest.raises(TreeError, match="same point"):
        AbilityTree([ability("r", root=True), ability("a", ["r"])])


def test_the_public_form_hides_nothing_secret_and_carries_the_numbers():
    node = ability("a", ["r"], x=5, y=6, level=12)
    shown = node.to_public()
    assert shown["id"] == "a" and shown["kind"] == "ability" and shown["requires"] == ["r"]
    assert shown["unlock_level"] == 12 and shown["cost"] == {"tier": "common", "amount": 1}
    assert (shown["x"], shown["y"], shown["category"], shown["percentage"], shown["cooldown"]) == (5, 6, "ATTACK", 100.0, 1)
    passive = TreeNode("p", "passive", "P", 1, 1, passive=PassiveSpec("none", {}))
    assert passive.to_public()["passive"] == {"kind": "none", "params": {}} and passive.to_public()["cost"] is None


def test_the_passive_root_id_follows_the_ascended():
    assert passive_root_id("guardian") == "guardian_passive"
