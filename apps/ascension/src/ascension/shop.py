"""The shop: buy EMBLEMs, buy this rotation's limited copy offers, sell spare copies back."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.ascension.squad import SquadService
from src.ascension.catalog import Catalog
from src.ascension.errors import BattleInProgress, Conflict, InsufficientFunds, InvalidRequest, NotFound, NothingToSell, SoldOut, WrongPhase
from src.ascension.idempotency import IdempotentWriter
from src.ascension.progression import ProgressionService
from src.ascension.records import AscendedRecord
from src.ascension.repository import AscendedRepository, AscendedTransaction
from src.ascension.runtime import Clock
from src.ascension.shop_offers import ShopOffers

MAX_EMBLEM_PURCHASE = 99


class ShopService:
    def __init__(self, repository: AscendedRepository, writer: IdempotentWriter, catalog: Catalog,
                 progression: ProgressionService, offers: ShopOffers, clock: Clock) -> None:
        self._repository, self._writer, self._catalog = repository, writer, catalog
        self._progression, self._offers, self._clock = progression, offers, clock

    # -- prices --------------------------------------------------------------------

    def copy_price(self, ascended_id: str, owned: AscendedRecord | None, tier_id: str) -> tuple[int, int]:
        """(price, copies granted) for buying the regular `tier_id` package.
        The price is twice the resale value of the granted copies at the Ascended's tier and level."""
        granted = self._catalog.tier(tier_id).copy_reward
        current = self._catalog.tier_of(ascended_id, owned.tier_id if owned else None)
        per_copy = self._catalog.sale_value(ascended_id, current, owned.level if owned else 1)
        return self._catalog.economy.purchase_factor * granted * per_copy, granted

    # -- operations ----------------------------------------------------------------

    @staticmethod
    async def _spend(tx: AscendedTransaction, owner: str, price: int) -> None:
        player = await tx.get_player(owner)
        if player is None:
            raise NotFound("no profile yet; choose a starter first")
        if player.insignia < price:
            raise InsufficientFunds(f"that costs {price} Insignia and you have {player.insignia}")
        await tx.add_insignia(owner, -price)

    @staticmethod
    async def _reject_if_fighting(tx: AscendedTransaction, owner: str, ascended_id: str) -> None:
        battle = await tx.active_battle(owner)
        if battle is not None and battle.setup.player.ascended_id == ascended_id:
            raise WrongPhase("that Ascended is fighting in the active battle")

    async def buy_emblems(self, owner: str, key: str, tier_id: str, quantity: int) -> dict[str, Any]:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_EMBLEM_PURCHASE:
            raise InvalidRequest(f"quantity must be a whole number from 1 to {MAX_EMBLEM_PURCHASE}")
        tier = self._catalog.tier(tier_id)  # forbidden EMBLEMs are sold too

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            price = tier.emblem_price * quantity
            await self._spend(tx, owner, price)
            await tx.add_emblems(owner, tier_id, quantity)
            return {"kind": "emblems", "tier_id": tier_id, "quantity": quantity, "price": price}

        return await self._writer.commit(owner, key, "shop.emblems", {"tier": tier_id, "quantity": quantity}, work)

    async def list_offers(self, owner: str) -> dict[str, Any]:
        """This account's current window: each offer with its remaining stock and today's price."""
        now = self._clock.now()
        window = self._offers.window(owner, now)
        async with self._repository.transaction() as tx:
            if await tx.get_player(owner) is None:
                raise NotFound("no profile yet; choose a starter first")
            bought = await tx.shop_bought(owner, window.rotation)
            owned = {record.ascended_id: record for record in await tx.list_ascendeds(owner)}
        offers = []
        for offer in window.offers:
            record = owned.get(offer.ascended_id)
            price, granted = self.copy_price(offer.ascended_id, record, offer.tier_id)
            offers.append({
                "slot": offer.slot, "ascended_id": offer.ascended_id, "tier_id": offer.tier_id,
                "copies_granted": granted, "stock": offer.stock, "left": max(0, offer.stock - bought.get(offer.slot, 0)),
                "price": price, "owned": record is not None, "owned_copies": record.copies if record else 0,
            })
        return {"rotation": window.rotation, "refreshes_at": window.refreshes_at,
                "seconds_left": max(0.0, window.refreshes_at - now), "offers": offers}

    async def buy_offer(self, owner: str, key: str, rotation: int, slot: int) -> dict[str, Any]:
        for value in (rotation, slot):
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidRequest("rotation and slot must be whole numbers")

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            window = self._offers.window(owner, self._clock.now())
            if rotation != window.rotation:
                raise Conflict("the shop has refreshed; look at the new offers")
            offer = next((o for o in window.offers if o.slot == slot), None)
            if offer is None:
                raise InvalidRequest("there is no such offer")
            bought = (await tx.shop_bought(owner, rotation)).get(slot, 0)
            if bought >= offer.stock:
                raise SoldOut("that offer is sold out")
            await self._reject_if_fighting(tx, owner, offer.ascended_id)
            owned = await tx.get_ascended(owner, offer.ascended_id)
            if (owned is None and len(await tx.get_squad(owner)) < self._catalog.economy.squad_size
                    and await tx.active_battle(owner) is not None):
                raise BattleInProgress("finish your active battle before adding an Ascended to your squad")
            price, granted = self.copy_price(offer.ascended_id, owned, offer.tier_id)
            await self._spend(tx, owner, price)
            if owned is None:  # the first copy is the Ascended itself; the rest are spare
                start = self._catalog.start_tier(offer.ascended_id)
                await tx.put_ascended(AscendedRecord(owner, offer.ascended_id, max(0, granted - 1), 1, 0, tier_id=start))
                await SquadService.auto_equip(tx, owner, offer.ascended_id, self._catalog.economy.squad_size)
            else:
                await tx.put_ascended(replace(owned, copies=owned.copies + granted))
            await tx.add_shop_purchase(owner, rotation, slot)
            await tx.prune_shop(owner, rotation)
            return {"kind": "copies", "ascended_id": offer.ascended_id, "tier_id": offer.tier_id, "copies_granted": granted,
                    "price": price, "slot": slot, "rotation": rotation,
                    "left": offer.stock - bought - 1}

        return await self._writer.commit(owner, key, "shop.offer", {"rotation": rotation, "slot": slot}, work)

    async def sell_copy(self, owner: str, key: str, ascended_id: str) -> dict[str, Any]:
        self._catalog.ascended(ascended_id)

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            await self._reject_if_fighting(tx, owner, ascended_id)
            owned = await tx.get_ascended(owner, ascended_id)
            if owned is None or owned.copies == 0:
                raise NothingToSell("there is no spare copy to sell")
            tier_id = self._catalog.tier_of(ascended_id, owned.tier_id)
            value = self._catalog.sale_value(ascended_id, tier_id, owned.level)
            await tx.put_ascended(replace(owned, copies=owned.copies - 1))
            await tx.add_insignia(owner, value)
            return {"kind": "sale", "ascended_id": ascended_id, "value": value, "copies": owned.copies - 1, "tier_id": tier_id}

        return await self._writer.commit(owner, key, "shop.sell", {"ascended": ascended_id}, work)
