"""Catalog-driven activities and their transparent baseline-stat rating."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from src.ascension.ascension_types import AscensionType

if TYPE_CHECKING:
    from src.ascension.catalog import Catalog

DEFAULT_ACTIVITIES = {
    'hunts': [
        dict(id='outskirts', name='Outskirts', recommended_min=100, recommended_max=299, enemy_min=100, enemy_max=299),
        dict(id='frontier', name='Frontier', recommended_min=300, recommended_max=599, enemy_min=300, enemy_max=599),
        dict(id='forbidden_grounds', name='Forbidden Grounds', recommended_min=600, recommended_max=1599, enemy_min=600, enemy_max=1599),
    ],
    'trial_stages': [
        dict(stage=1, ascended_id='guardian', tier_id='common', level=3),
        dict(stage=2, ascended_id='bruiser', tier_id='rare', level=8),
        dict(stage=3, ascended_id='twoychi', tier_id='unique', level=15),
        dict(stage=4, ascended_id='twoychi', tier_id='legendary', level=25),
    ],
    'expeditions': dict(durations_hours=[2, 4, 8], xp_per_hour=100, insignia_per_hour=25),
}


@dataclass(frozen=True)
class HuntSpec:
    id: str
    name: str
    recommended_min: int
    recommended_max: int
    enemy_min: int
    enemy_max: int


@dataclass(frozen=True)
class TrialStageSpec:
    stage: int
    ascended_id: str
    tier_id: str
    level: int


@dataclass(frozen=True)
class ExpeditionSpec:
    durations_hours: tuple[int, ...]
    xp_per_hour: int
    insignia_per_hour: int


def hunt_multiplier(overall: int, upper: int) -> float:
    return 1 - min(.75, max(0, (overall - upper) / upper))


class ActivityRules:
    def __init__(self, catalog: Catalog, raw_activities: dict | None = None) -> None:
        from src.ascension.catalog import CatalogError
        self._catalog = catalog
        raw = DEFAULT_ACTIVITIES if raw_activities is None else raw_activities
        self.hunts = tuple(HuntSpec(**h) for h in raw['hunts'])
        self.stages = tuple(TrialStageSpec(**s) for s in raw['trial_stages'])
        exp = raw['expeditions']
        self.expeditions = ExpeditionSpec(tuple(exp['durations_hours']), exp['xp_per_hour'], exp['insignia_per_hour'])
        if len(self.hunts) != 3 or len({h.id for h in self.hunts}) != 3:
            raise CatalogError('activities: exactly three distinct hunts required')
        self._candidates: dict[str, dict[str, dict[str, tuple[int, ...]]]] = {}
        for h in self.hunts:
            bounds = (h.recommended_min, h.recommended_max, h.enemy_min, h.enemy_max)
            if not h.id or not h.name or any(type(n) is not int or n < 1 for n in bounds) or h.recommended_min > h.recommended_max or h.enemy_min > h.enemy_max:
                raise CatalogError('activities: invalid hunt bounds')
            candidates = {}
            for tier in catalog.tiers:
                species = {}
                for s in catalog.all_ascendeds():
                    if not catalog._rank(catalog.start_tier(s.id)) <= catalog._rank(tier.id) <= catalog._rank(catalog.end_tier(s.id)):
                        continue
                    levels = tuple(l for l in range(1, catalog.level_cap(s.id) + 1) if h.enemy_min <= self.overall(s.id, tier.id, l) <= h.enemy_max)
                    if levels:
                        species[s.id] = levels
                if species and tier.encounter_probability > 0:
                    candidates[tier.id] = species
            if not candidates:
                raise CatalogError(f'activities: hunt {h.id} has no weighted candidates')
            self._candidates[h.id] = candidates
        if tuple(s.stage for s in self.stages) != (1, 2, 3, 4):
            raise CatalogError('activities: stages must be 1 through 4')
        for s in self.stages:
            if type(s.stage) is not int or type(s.level) is not int or not 1 <= s.level <= catalog.level_cap(s.ascended_id) or not catalog._rank(catalog.start_tier(s.ascended_id)) <= catalog._rank(s.tier_id) <= catalog._rank(catalog.end_tier(s.ascended_id)):
                raise CatalogError('activities: invalid trial opponent')
        if self.expeditions.durations_hours != (2, 4, 8) or any(type(h) is not int for h in self.expeditions.durations_hours) or any(type(n) is not int or n < 0 for n in (self.expeditions.xp_per_hour, self.expeditions.insignia_per_hour)):
            raise CatalogError('activities: invalid expedition settings')

    def overall(self, ascended_id: str, tier_id: str, level: int) -> int:
        return sum(self._catalog.stat_value(ascended_id, level, tier_id, stat) for stat in ('hp', 'power', 'speed'))

    def hunt(self, difficulty_id: str) -> HuntSpec:
        from src.ascension.errors import InvalidRequest
        for h in self.hunts:
            if h.id == difficulty_id:
                return h
        raise InvalidRequest('unknown Hunt difficulty')

    def candidates(self, difficulty_id: str) -> dict[str, dict[str, tuple[int, ...]]]:
        self.hunt(difficulty_id)
        return self._candidates[difficulty_id]

    def trial_stage(self, stage: int) -> TrialStageSpec:
        from src.ascension.errors import InvalidRequest
        if type(stage) is not int or not 1 <= stage <= len(self.stages):
            raise InvalidRequest('unknown Trial stage')
        return self.stages[stage - 1]

    def to_public(self) -> dict[str, Any]:
        return dict(hunts=[asdict(h) for h in self.hunts], trial_types=[t.value for t in AscensionType],
                    trial_stages=[asdict(s) for s in self.stages], expeditions=asdict(self.expeditions),
                    max_hunt_penalty=.75, trial_first_clear_multiplier=2)
