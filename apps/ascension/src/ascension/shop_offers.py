"""The rotating shop window: which copy packages an account may buy now.

Offers are not stored. They are derived from (owner, rotation), so the same account sees the
same offers until the rotation changes, and no job has to run at the turn of a rotation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.ascension.catalog import Catalog
from src.ascension.runtime import SeededRandom


@dataclass(frozen=True)
class Offer:
    slot: int
    ascended_id: str
    tier_id: str
    stock: int


@dataclass(frozen=True)
class ShopWindow:
    rotation: int
    refreshes_at: float
    offers: tuple[Offer, ...]


class ShopOffers:
    def __init__(self, catalog: Catalog, rotation_seconds: float, offer_count: int) -> None:
        self._catalog = catalog
        self._seconds = rotation_seconds
        self._count = offer_count

    def rotation_at(self, now: float) -> int:
        return int(now // self._seconds)

    def window(self, owner: str, now: float) -> ShopWindow:
        rotation = self.rotation_at(now)
        digest = hashlib.sha256(f"{owner}:{rotation}".encode()).digest()
        rng = SeededRandom(int.from_bytes(digest[:8], "big"))
        pool = sorted(s.id for s in self._catalog.all_ascendeds() if not s.forbidden)
        offers: list[Offer] = []
        for slot in range(min(self._count, len(pool))):
            ascended_id = pool.pop(int(rng.next() * len(pool)))
            tier_id = self._pick_tier(rng.next(), ascended_id)
            offers.append(Offer(slot, ascended_id, tier_id, self._catalog.shop.stock[tier_id]))
        return ShopWindow(rotation, (rotation + 1) * self._seconds, tuple(offers))

    def _pick_tier(self, draw: float, ascended_id: str) -> str:
        """A weighted tier from the ones this Ascended can be at."""
        weights = self._catalog.shop.tier_weights
        low, high = self._catalog.start_tier(ascended_id), self._catalog.end_tier(ascended_id)
        ids = [t.id for t in self._catalog.regular_tiers]
        tiers = ids[ids.index(low):ids.index(high) + 1]
        target = draw * sum(weights[t] for t in tiers)
        for tier_id in tiers:
            target -= weights[tier_id]
            if target < 0:
                return tier_id
        return tiers[-1]
