import copy

import pytest

from src.ascension.activity_rules import ActivityRules, hunt_multiplier
from src.ascension.catalog import Catalog, CatalogError
from tests.ascension.env import CATALOG, load_raw


def test_overall_and_penalty_boundaries():
    rules = ActivityRules(CATALOG)
    assert rules.overall('guardian', 'common', 1) == 185
    assert rules.overall('cindrax', 'forbidden', 1) == 1080
    assert hunt_multiplier(299, 299) == 1
    assert hunt_multiplier(720, 599) == pytest.approx(1 - 121 / 599)
    assert hunt_multiplier(1049, 599) == .25
    assert rules.expeditions.durations_hours == (2, 4, 8)


def test_candidates_are_legal_and_in_band():
    rules = ActivityRules(CATALOG)
    for hunt in rules.hunts:
        candidates = rules.candidates(hunt.id)
        assert candidates
        for tier, species in candidates.items():
            for ascended, levels in species.items():
                assert CATALOG._rank(CATALOG.start_tier(ascended)) <= CATALOG._rank(tier) <= CATALOG._rank(CATALOG.end_tier(ascended))
                assert all(hunt.enemy_min <= rules.overall(ascended, tier, level) <= hunt.enemy_max for level in levels)
    assert 'cindrax' in rules.candidates('forbidden_grounds')['forbidden']


@pytest.mark.parametrize('change', ['empty', 'bool', 'stage', 'duration'])
def test_config_validation(change):
    from src.ascension.activity_rules import DEFAULT_ACTIVITIES
    raw = load_raw()
    raw['activities'] = copy.deepcopy(DEFAULT_ACTIVITIES)
    if change == 'empty':
        raw['activities']['hunts'][0].update(enemy_min=99999, enemy_max=100000)
    elif change == 'bool':
        raw['activities']['hunts'][0]['recommended_min'] = True
    elif change == 'stage':
        raw['activities']['trial_stages'][0]['tier_id'] = 'forbidden'
    else:
        raw['activities']['expeditions']['durations_hours'] = [2, 3.5, 8]
    with pytest.raises(CatalogError):
        Catalog(raw)
