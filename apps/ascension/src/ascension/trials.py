"""Owner-scoped stage progress and type-restricted Trial preparation."""
from __future__ import annotations

from dataclasses import asdict

from src.ascension.ascension_types import AscensionType
from src.ascension.errors import InvalidRequest, NotFound
from src.ascension.expeditions import require_available


class TrialService:
    def __init__(self, repo, catalog, clock, progression=None) -> None:
        self._repo, self._catalog, self._clock = repo, catalog, clock
        from src.ascension.progression import ProgressionService
        self._progression = progression or ProgressionService(catalog, clock, 0)

    @staticmethod
    def type_id(value: str) -> str:
        try:
            return AscensionType(value).value
        except ValueError:
            raise InvalidRequest('unknown Ascension type') from None

    async def progress(self, owner: str) -> dict:
        async with self._repo.transaction() as tx:
            if await tx.get_player(owner) is None:
                raise NotFound('choose a starter first')
            trials = []
            for kind in AscensionType:
                cleared = await tx.trial_clears(owner, kind.value)
                trials.append({'type_id': kind.value, 'stages': [
                    {**asdict(s), 'cleared': s.stage in cleared, 'unlocked': s.stage == 1 or s.stage-1 in cleared,
                     'first_clear': s.stage not in cleared} for s in self._catalog.activities.stages]})
            return {'trials': trials}

    async def prepare(self, owner: str, type_id: str, stage: int) -> dict:
        type_id = self.type_id(type_id)
        spec = self._catalog.activities.trial_stage(stage)
        async with self._repo.transaction() as tx:
            if await tx.get_player(owner) is None:
                raise NotFound('choose a starter first')
            cleared = await tx.trial_clears(owner, type_id)
            squad = await tx.get_squad(owner)
            expedition = await tx.unclaimed_expedition(owner)
            now = self._clock.now()
            matching = [a for a in await tx.list_ascendeds(owner) if type_id in self._catalog.ascended(a.ascended_id).ascension_types]
            eligible = [a.ascended_id for a in matching if a.ascended_id in squad and (a.faint_until is None or a.faint_until <= now)
                        and (expedition is None or expedition.ascended_id != a.ascended_id)]
            unlocked = spec.stage == 1 or spec.stage - 1 in cleared
            reason = None if eligible else ('Equip or rest a matching Ascended' if matching else 'No eligible Ascended')
            xp, insignia = self._progression.rewards_for(spec.level, spec.tier_id)
            multiplier = 2 if stage not in cleared else 1
            rewards = dict(xp=xp*multiplier, insignia=insignia*multiplier, essence=self._catalog.tier(spec.tier_id).essence_cost*multiplier, essence_tier_id=spec.tier_id)
            return dict(type_id=type_id, stage=stage, unlocked=unlocked, first_clear=stage not in cleared, rewards=rewards,
                        eligible_ascended_ids=eligible, reason=reason,
                        opponent={**asdict(spec), 'name': self._catalog.ascended(spec.ascended_id).name,
                                  'overall': self._catalog.activities.overall(spec.ascended_id, spec.tier_id, spec.level)})

    async def validate_in(self, tx, owner: str, type_id: str, stage: int, ascended_id: str):
        type_id = self.type_id(type_id)
        spec = self._catalog.activities.trial_stage(stage)
        owned = await tx.get_ascended(owner, ascended_id)
        if owned is None:
            raise NotFound('you do not own that Ascended')
        if type_id not in self._catalog.ascended(ascended_id).ascension_types:
            raise InvalidRequest('this Trial requires a matching Ascension type')
        if stage > 1 and stage-1 not in await tx.trial_clears(owner, type_id):
            raise InvalidRequest('win the previous Trial stage first')
        await require_available(tx, owner, ascended_id)
        return spec
