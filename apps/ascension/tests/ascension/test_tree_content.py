import pytest

from tests.ascension.env import CATALOG

IDS = [s.id for s in CATALOG.all_ascendeds()]


@pytest.mark.parametrize("ascended_id", IDS)
def test_each_shipped_ascended_has_a_real_tree(ascended_id):
    tree = CATALOG.ascended(ascended_id).tree
    extra = [n for n in tree.nodes if not n.root]
    assert len(tree.roots) == 4 and 3 <= len(extra) <= 5
    assert any(n.kind == "passive" for n in extra) and any(n.kind == "ability" for n in extra)
    assert all(n.cost.amount >= 1 for n in extra)


def test_every_tree_has_its_own_shape():
    shapes = {s.id: frozenset((n.x, n.y) for n in s.tree.nodes) for s in CATALOG.all_ascendeds()}
    assert len(set(shapes.values())) == len(shapes)
