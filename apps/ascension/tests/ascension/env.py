"""Builds the service graph over a temporary database for service-level tests."""

from __future__ import annotations

import asyncio
import itertools
import json
from pathlib import Path

from src.ascension.catalog import Catalog
from src.ascension.collection import CollectionService
from src.ascension.encounters import EncounterService
from src.ascension.engine import BattleEngine
from src.ascension.idempotency import IdempotentWriter
from src.ascension.progression import ProgressionService
from src.ascension.repository import SqliteAscendedRepository
from src.ascension.runtime import RandomSource, SeededRandom
from src.ascension.shop import ShopService
from src.ascension.shop_offers import ShopOffers
from src.ascension.upgrades import UpgradeService
from src.ascension.trees import TreeService
from tests.ascension.helpers import FixedClock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / "configs" / "ascension_catalog.json"
ASCENDEDS_PATH = PROJECT_ROOT / "ascended"
CATALOG = Catalog.load(CATALOG_PATH, ASCENDEDS_PATH)


def load_raw() -> dict:
    """The shipped catalog as the raw dict Catalog() takes: the rules plus the Ascended (and their trees), by folder name."""
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    raw["ascendeds"] = []
    for f in sorted(ASCENDEDS_PATH.glob("*/catalog.json"), key=lambda f: f.parent.name):
        ascended = json.loads(f.read_text(encoding="utf-8"))
        tree_file = f.parent / "tree.json"
        if tree_file.is_file():
            ascended["tree"] = json.loads(tree_file.read_text(encoding="utf-8"))
        raw["ascendeds"].append(ascended)
    return raw
COOLDOWN = 30.0
FAINT = 300.0
PROMPT = 5.0
_KEYS = itertools.count(1)  # unique across Env instances, so a restarted Env never reuses a key


class Env:
    def __init__(self, db_path: Path, rng: RandomSource | None = None, offers=None) -> None:
        self.catalog = CATALOG
        self.clock = FixedClock()
        self.rng = rng or SeededRandom(11)
        self.repo = SqliteAscendedRepository(db_path)
        self.writer = IdempotentWriter(self.repo, self.clock)
        self.engine = BattleEngine(CATALOG)
        self.progression = ProgressionService(CATALOG, self.clock, FAINT)
        self.collection = CollectionService(self.repo, self.writer, CATALOG, self.clock, self.rng, COOLDOWN)
        self.encounters = EncounterService(self.repo, self.writer, CATALOG, self.clock, self.rng, COOLDOWN)
        self.offers = offers or ShopOffers(CATALOG, 21600.0, 5)
        self.shop = ShopService(self.repo, self.writer, CATALOG, self.progression, self.offers, self.clock)
        self.upgrades = UpgradeService(self.repo, self.writer, CATALOG)
        self.trees = TreeService(self.repo, self.writer, CATALOG)

    def coordinator(self, policy=None, reader=None, picker=None, laya=None):
        """A RoundCoordinator over this Env. Imports are local: the coordinator is built in a later task."""
        from src.laya_client import LayaClient
        from src.ascension.battle_view import BattleViewBuilder
        from src.ascension.coordinator import CoordinatorSettings, RoundCoordinator
        from src.ascension.decider import ActionDecider
        from src.ascension.emblem_picker import LayaEmblemPicker
        from src.ascension.policy import ActionPolicy, Mood
        from src.ascension.situation import HeuristicSituationReader, SituationViewBuilder
        from tests.fake_laya import FakeEngine

        views = BattleViewBuilder(self.engine, CATALOG)
        client = LayaClient(laya or FakeEngine(fail=True))
        situation_views = SituationViewBuilder(self.engine)
        decider = ActionDecider(
            CATALOG, self.engine, policy or ActionPolicy(CATALOG.policy), Mood(CATALOG),
            reader or HeuristicSituationReader(CATALOG.policy.default_aggression), situation_views,
        )
        return RoundCoordinator(
            self.repo, self.writer, CATALOG, self.engine, decider, situation_views,
            picker or LayaEmblemPicker(client), self.progression, views, self.clock, CoordinatorSettings(PROMPT),
        )

    def key(self) -> str:
        return f"key-{next(_KEYS)}"

    async def start_player(self, owner: str = "ann", starter: str = "guardian") -> dict:
        return await self.collection.initialize(owner, self.key(), starter)

    async def give(self, owner: str = "ann", insignia: int = 0, **ascendeds) -> None:
        """Test setup: add Insignia and/or replace Ascended records directly."""
        async with self.repo.transaction() as tx:
            if insignia:
                await tx.add_insignia(owner, insignia)
            for record in ascendeds.values():
                await tx.put_ascended(record)

    async def give_essence(self, tier_id: str, amount: int, owner: str = "ann") -> None:
        async with self.repo.transaction() as tx:
            await tx.add_essence(owner, tier_id, amount)

    async def close(self) -> None:
        await self.repo.close()


def run(coro):
    return asyncio.run(coro)
