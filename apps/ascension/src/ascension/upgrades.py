"""Upgrades: spend a spare copy and tier essence to add a star, then use the stars to raise the tier."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.ascension.catalog import Catalog
from src.ascension.errors import InsufficientCopies, InsufficientEssence, InvalidRequest, NotFound, UpgradeNotReady
from src.ascension.idempotency import IdempotentWriter
from src.ascension.repository import AscendedRepository, AscendedTransaction


class UpgradeService:
    def __init__(self, repository: AscendedRepository, writer: IdempotentWriter, catalog: Catalog) -> None:
        self._repository, self._writer, self._catalog = repository, writer, catalog

    async def _owned(self, tx: AscendedTransaction, owner: str, ascended_id: str):
        if not self._catalog.has_ascended(ascended_id):
            raise NotFound("you do not own that Ascended")
        owned = await tx.get_ascended(owner, ascended_id)
        if owned is None:
            raise NotFound("you do not own that Ascended")
        return owned, self._catalog.tier_of(ascended_id, owned.tier_id)

    async def add_star(self, owner: str, key: str, ascended_id: str) -> dict[str, Any]:
        """One star costs one spare copy and the tier's essence cost in that tier's essence."""

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            owned, tier_id = await self._owned(tx, owner, ascended_id)
            tier = self._catalog.tier(tier_id)
            stars_needed = self._catalog.stars_to_advance(ascended_id, tier_id)
            if stars_needed is None:
                raise UpgradeNotReady("that Ascended is at the top of its ladder and cannot gain stars")
            if owned.stars >= stars_needed:
                raise UpgradeNotReady("the stars are full; raise the tier instead")
            if owned.copies < 1:
                raise InsufficientCopies("a star needs one spare copy and you have none")
            have = (await tx.essence_counts(owner)).get(tier_id, 0)
            if have < tier.essence_cost:
                raise InsufficientEssence(f"a star costs {tier.essence_cost} {tier_id} essence and you have {have}")
            await tx.add_essence(owner, tier_id, -tier.essence_cost)
            stars = owned.stars + 1
            await tx.put_ascended(replace(owned, copies=owned.copies - 1, stars=stars, tier_id=tier_id))
            return {"kind": "star", "ascended_id": ascended_id, "tier_id": tier_id, "stars": stars,
                    "stars_needed": stars_needed, "essence_spent": tier.essence_cost,
                    "copies": owned.copies - 1, "can_tier_up": stars >= stars_needed}

        return await self._writer.commit(owner, key, "upgrade.star", {"ascended": ascended_id}, work)

    async def raise_tier(self, owner: str, key: str, ascended_id: str) -> dict[str, Any]:
        """With enough stars, move to the next tier; the stars start again at zero."""

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            owned, tier_id = await self._owned(tx, owner, ascended_id)
            needed = self._catalog.stars_to_advance(ascended_id, tier_id)
            upper = self._catalog.next_tier(ascended_id, tier_id)
            if needed is None or upper is None:
                raise InvalidRequest("that Ascended is at the top of its ladder")
            if owned.stars < needed:
                raise UpgradeNotReady(f"the next tier needs {needed} stars and it has {owned.stars}")
            await tx.put_ascended(replace(owned, tier_id=upper, stars=0))
            return {"kind": "tier", "ascended_id": ascended_id, "from_tier_id": tier_id, "tier_id": upper, "stars": 0}

        return await self._writer.commit(owner, key, "upgrade.tier", {"ascended": ascended_id}, work)
