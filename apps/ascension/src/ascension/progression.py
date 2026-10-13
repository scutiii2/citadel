"""Progression: what a finished battle is worth.

`apply_terminal` runs inside the caller's transaction, so XP, Insignia, essence,
copies, the awarded personality, fainting and the battle result are saved together
or not at all.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from src.ascension.squad import SquadService
from src.ascension.catalog import Catalog
from src.ascension.models import PersonalityInstance
from src.ascension.records import BattleRecord, PersonalityRecord, AscendedRecord
from src.ascension.repository import AscendedTransaction
from src.ascension.runtime import Clock, RandomSource, new_id

_EPS = 1e-9
REWARDED = ("won", "captured")
FAINTING = ("knocked_out", "forfeited")


class ProgressionService:
    def __init__(self, catalog: Catalog, clock: Clock, faint_seconds: float) -> None:
        self._catalog, self._clock, self._faint_seconds = catalog, clock, faint_seconds

    # -- pure helpers --------------------------------------------------------------

    def xp_needed(self, level: int) -> int:
        return self._catalog.levels.xp_per_level * level

    def add_xp(self, ascended_id: str, level: int, xp: int, gained: int) -> tuple[int, int]:
        """Carry excess XP through level-ups; at the cap XP stops and the excess is discarded."""
        cap = self._catalog.level_cap(ascended_id)
        if level >= cap:
            return cap, 0
        xp += gained
        while level < cap and xp >= self.xp_needed(level):
            xp -= self.xp_needed(level)
            level += 1
        return level, (0 if level >= cap else xp)

    def squad_share(self, fighter_xp: int, bench_count: int) -> int:
        if bench_count == 0:
            return 0
        return math.floor(fighter_xp * self._catalog.economy.bench_xp_pool_factor / bench_count + _EPS)

    def add_copies(self, ascended_id: str, copies: int, granted: int) -> int:
        if self._catalog.ascended(ascended_id).forbidden:
            return min(copies + granted, self._catalog.economy.forbidden_copy_cap)
        return copies + granted

    def rewards_for(self, enemy_level: int, enemy_tier_id: str) -> tuple[int, int]:
        """(XP, Insignia) for beating or collecting an enemy."""
        multiplier = self._catalog.tier(enemy_tier_id).stat_multiplier
        eco = self._catalog.economy
        return (
            math.floor(eco.xp_reward_factor * enemy_level * multiplier + _EPS),
            math.floor(eco.insignia_reward_factor * enemy_level * multiplier + _EPS),
        )

    # -- a finished battle ---------------------------------------------------------

    async def apply_terminal(
        self, tx: AscendedTransaction, battle: BattleRecord, terminal: str, rng: RandomSource
    ) -> dict[str, Any]:
        """Apply the consequences of `terminal` and return the public result."""
        owner = battle.owner
        fighter, enemy = battle.setup.player, battle.setup.wild
        result: dict[str, Any] = {"kind": terminal}
        ascended = await tx.get_ascended(owner, fighter.ascended_id)

        if terminal in REWARDED:
            xp, insignia = self.rewards_for(enemy.level, enemy.tier_id)
            level, new_xp = self.add_xp(fighter.ascended_id, ascended.level, ascended.xp, xp)
            await tx.put_ascended(replace(ascended, level=level, xp=new_xp))
            bench = [a for a in await tx.get_squad(owner) if a != fighter.ascended_id]
            share = self.squad_share(xp, len(bench))
            result["squad_xp"] = []
            for ascended_id in bench:
                member = await tx.get_ascended(owner, ascended_id)
                if member is None:
                    continue
                bench_level, bench_xp = self.add_xp(ascended_id, member.level, member.xp, share)
                await tx.put_ascended(replace(member, level=bench_level, xp=bench_xp))
                result["squad_xp"].append({"ascended_id": ascended_id, "name": self._catalog.ascended(ascended_id).name,
                                           "xp": share, "level_before": member.level, "level_after": bench_level})
            await tx.add_insignia(owner, insignia)
            essence = self._catalog.tier(enemy.tier_id).essence_cost
            await tx.add_essence(owner, enemy.tier_id, essence)
            result.update(xp=xp, insignia=insignia, essence=essence, essence_tier_id=enemy.tier_id,
                          level_before=ascended.level, level_after=level)
            if terminal == "captured":
                result.update(await self._collect(tx, battle, rng))
        elif terminal in FAINTING:
            until = self._clock.now() + self._faint_seconds
            await tx.put_ascended(replace(ascended, faint_until=until))
            result["faint_until"] = until
        return result

    async def _collect(self, tx: AscendedTransaction, battle: BattleRecord, rng: RandomSource) -> dict[str, Any]:
        owner, enemy = battle.owner, battle.setup.wild
        reward = self._catalog.tier(enemy.tier_id).copy_reward
        owned = await tx.get_ascended(owner, enemy.ascended_id)
        if owned is None:
            granted = self.add_copies(enemy.ascended_id, 0, reward)
            copies = max(0, granted - 1)  # the first copy is the Ascended itself; the rest are spare
            start = self._catalog.start_tier(enemy.ascended_id)
            await tx.put_ascended(AscendedRecord(owner, enemy.ascended_id, copies, 1, 0, tier_id=start))
            await SquadService.auto_equip(tx, owner, enemy.ascended_id, self._catalog.economy.squad_size)
        else:
            copies = self.add_copies(enemy.ascended_id, owned.copies, reward)
            await tx.put_ascended(replace(owned, copies=copies))
            granted = copies - owned.copies
        instances = battle.wild_personalities
        picked = min(int(rng.next() * len(instances)), len(instances) - 1)
        chosen = instances[picked]
        award = PersonalityRecord(new_id(), owner, enemy.ascended_id, chosen.type_id, chosen.tier, self._clock.now())
        await tx.add_personality(award)
        return {
            "ascended_id": enemy.ascended_id,
            "copies_granted": granted,
            "copies": copies,
            "tier_id": self._catalog.tier_of(enemy.ascended_id, owned.tier_id if owned else None),
            "awarded_personality": _describe(award.instance()),
            "awarded_index": picked,  # position in revealed_personalities (the award itself gets a new id)
            "revealed_personalities": [_describe(i) for i in instances],  # every source instance, awarded or not
        }


def _describe(instance: PersonalityInstance) -> dict[str, Any]:
    return {"id": instance.id, "type": instance.type_id, "tier": instance.tier}
