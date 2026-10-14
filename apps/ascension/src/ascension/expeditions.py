"""Offline expeditions with atomic departure, availability, and reward claims."""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from src.ascension.errors import AscendedFainted, BattleInProgress, Conflict, InvalidRequest, NotFound
from src.ascension.records import ExpeditionRecord
from src.ascension.repository import AscendedTransaction
from src.ascension.runtime import new_id


async def require_available(tx: AscendedTransaction, owner: str, ascended_id: str) -> None:
    expedition = await tx.unclaimed_expedition(owner)
    if expedition is not None and expedition.ascended_id == ascended_id:
        raise Conflict('that Ascended is on expedition; claim its rewards before using or upgrading it')


def expedition_view(record: ExpeditionRecord | None, now: float) -> dict[str, Any] | None:
    if record is None:
        return None
    view = asdict(record)
    view.pop('owner')
    view.pop('receipt')
    ready = now >= record.ends_at
    return {**view, 'state': 'ready_to_claim' if ready else 'on_expedition',
            'can_claim': ready, 'seconds_remaining': max(0, record.ends_at - now)}


class ExpeditionService:
    def __init__(self, repo, writer, catalog, progression, clock) -> None:
        self._repo, self._writer, self._catalog = repo, writer, catalog
        self._progression, self._clock = progression, clock

    async def get(self, owner: str) -> dict[str, Any]:
        async with self._repo.transaction() as tx:
            if await tx.get_player(owner) is None:
                raise NotFound('choose a starter first')
            now = self._clock.now()
            return {'server_now': now, 'expedition': expedition_view(await tx.unclaimed_expedition(owner), now)}

    async def start(self, owner: str, key: str, ascended_id: str, duration_hours: int) -> dict[str, Any]:
        spec = self._catalog.activities.expeditions
        if type(duration_hours) is not int or duration_hours not in spec.durations_hours:
            raise InvalidRequest('choose a 2, 4, or 8 hour expedition')

        async def work(tx):
            owned = await tx.get_ascended(owner, ascended_id)
            if owned is None:
                raise NotFound('you do not own that Ascended')
            if await tx.active_battle(owner) is not None:
                raise BattleInProgress('finish your active battle before sending an expedition')
            if await tx.unclaimed_expedition(owner) is not None:
                raise Conflict('your expedition slot is occupied; claim its rewards first')
            now = self._clock.now()
            if owned.faint_until is not None and owned.faint_until > now:
                raise AscendedFainted('a fainted Ascended cannot depart')
            record = ExpeditionRecord(new_id(), owner, ascended_id, now, now + duration_hours * 3600,
                                      duration_hours, spec.xp_per_hour * duration_hours, spec.insignia_per_hour * duration_hours)
            await tx.add_expedition(record)
            await tx.set_squad(owner, [id for id in await tx.get_squad(owner) if id != ascended_id])
            return {'server_now': now, 'expedition': expedition_view(record, now)}
        return await self._writer.commit(owner, key, 'expedition.start', {'ascended_id': ascended_id, 'duration_hours': duration_hours}, work)

    async def claim(self, owner: str, key: str, expedition_id: str) -> dict[str, Any]:
        async def work(tx):
            record = await tx.get_expedition(owner, expedition_id)
            if record is None:
                raise NotFound('no such expedition')
            if record.claimed_at is not None:
                return record.receipt
            now = self._clock.now()
            if now < record.ends_at:
                raise Conflict('the expedition has not finished yet')
            owned = await tx.get_ascended(owner, record.ascended_id)
            level, xp = self._progression.add_xp(record.ascended_id, owned.level, owned.xp, record.xp_reward)
            await tx.put_ascended(replace(owned, level=level, xp=xp))
            await tx.add_insignia(owner, record.insignia_reward)
            receipt = dict(id=record.id, ascended_id=record.ascended_id, xp=record.xp_reward,
                           insignia=record.insignia_reward, level_before=owned.level, level_after=level, claimed_at=now)
            await tx.claim_expedition(owner, record.id, now, receipt)
            return receipt
        return await self._writer.commit(owner, key, 'expedition.claim', {'id': expedition_id}, work)
