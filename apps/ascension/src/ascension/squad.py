"""Ordered squad membership and automatic enrollment of new Ascended."""

from __future__ import annotations
from typing import Any
from src.ascension.catalog import Catalog
from src.ascension.errors import BattleInProgress, InvalidRequest, NotFound
from src.ascension.idempotency import IdempotentWriter
from src.ascension.repository import AscendedRepository, AscendedTransaction


class SquadService:
    def __init__(self, repository: AscendedRepository, writer: IdempotentWriter, catalog: Catalog) -> None:
        self._repo, self._writer, self._catalog = repository, writer, catalog

    async def get(self, owner: str) -> dict[str, Any]:
        async with self._repo.transaction() as tx:
            return {"ascended_ids": list(await tx.get_squad(owner)), "size": self._catalog.economy.squad_size}

    async def put(self, owner: str, key: str, ascended_ids: list[str]) -> dict[str, Any]:
        size = self._catalog.economy.squad_size
        if not isinstance(ascended_ids, list) or any(not isinstance(a, str) for a in ascended_ids):
            raise InvalidRequest("ascended_ids must be a list of strings")
        if not 1 <= len(ascended_ids) <= size:
            raise InvalidRequest(f"squad must contain from 1 to {size} Ascended")
        if len(set(ascended_ids)) != len(ascended_ids):
            raise InvalidRequest("squad cannot contain duplicates")

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            for ascended_id in ascended_ids:
                if not self._catalog.has_ascended(ascended_id) or await tx.get_ascended(owner, ascended_id) is None:
                    raise NotFound("you do not own that Ascended")
            if await tx.active_battle(owner) is not None:
                raise BattleInProgress("finish your active battle before editing your squad")
            await tx.set_squad(owner, ascended_ids)
            return {"ascended_ids": list(ascended_ids), "size": size}

        return await self._writer.commit(owner, key, "squad.put", {"ascended_ids": ascended_ids}, work)

    @staticmethod
    async def auto_equip(tx: AscendedTransaction, owner: str, ascended_id: str, size: int) -> None:
        squad = await tx.get_squad(owner)
        if ascended_id not in squad and len(squad) < size:
            await tx.set_squad(owner, (*squad, ascended_id))
