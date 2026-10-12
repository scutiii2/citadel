import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.models import EffectSpec
from tests.ascension.env import load_raw

RAW = load_raw()


def build(mutate):
    data = copy.deepcopy(RAW)
    mutate(next(s for s in data["ascendeds"] if s["id"] == "guardian"))
    return Catalog(data)


def with_effects(effects):
    return lambda s: s["abilities"][2].update(effects=effects)


def test_a_valid_effects_list_parses_with_defaults():
    cases = [
        ([{"kind": "bleed", "percentage": 20, "rounds": 3}, {"kind": "mark", "name": "prey", "rounds": 3}],
         (EffectSpec("bleed", percentage=20.0, rounds=3), EffectSpec("mark", rounds=3, name="prey", target="foe"))),
        ([{"kind": "heal", "percentage": 50}, {"kind": "cleanse"}, {"kind": "ward", "rounds": 2}],
         (EffectSpec("heal", percentage=50.0), EffectSpec("cleanse"), EffectSpec("ward", rounds=2))),
    ]
    for raw, expected in cases:
        assert build(with_effects(raw)).ascended("guardian").abilities[2].effects == expected


def test_an_ability_without_effects_has_none():
    assert Catalog(copy.deepcopy(RAW)).ascended("guardian").abilities[2].effects == ()


@pytest.mark.parametrize("effects,message", [
    ("nope", "effects must be a list"),
    ([{"kind": "heal", "percentage": 5}] * 4, "at most 3"),
    (["x"], "must be an object"),
    ([{"kind": "teleport"}], "unknown effect kind"),
    ([{"kind": "heal", "percentage": 5, "color": "red"}], "unknown field"),
    ([{"kind": "heal"}], "positive percentage"),
    ([{"kind": "heal", "percentage": 0}], "positive percentage"),
    ([{"kind": "bleed", "percentage": 20}], "rounds of at least 1"),
    ([{"kind": "bleed", "percentage": 20, "rounds": 0}], "rounds of at least 1"),
    ([{"kind": "ward"}], "rounds of at least 1"),
    ([{"kind": "mark", "rounds": 2}], "lowercase name"),
    ([{"kind": "mark", "rounds": 2, "name": "Prey"}], "lowercase name"),
    ([{"kind": "mark", "rounds": 2, "name": "prey", "target": "both"}], "foe or self"),
    ([{"kind": "heal", "percentage": 5, "name": "prey"}], "only a mark"),
])
def test_a_bad_effect_is_a_catalog_error(effects, message):
    with pytest.raises(CatalogError, match=message):
        build(with_effects(effects))


def test_a_tree_node_may_carry_effects_and_shows_them_publicly():
    node = {"id": "guardian_bite", "kind": "ability", "name": "Bite", "category": "ATTACK", "percentage": 120, "cooldown": 2,
            "unlock_level": 12, "requires": ["guardian_bulwark"], "cost": {"tier": "common", "amount": 2}, "x": 900, "y": 900,
            "effects": [{"kind": "bleed", "percentage": 20, "rounds": 3}]}
    catalog = build(lambda s: s.update(tree={"nodes": [dict(n) for n in s["tree"]["nodes"]] + [node]}))
    shown = catalog.ascended("guardian").tree.node("guardian_bite").to_public()
    assert shown["effects"] == [{"kind": "bleed", "percentage": 20.0, "rounds": 3}]
