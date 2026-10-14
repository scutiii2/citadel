"""The composition root: builds the whole Ascension object graph once at startup."""

from __future__ import annotations

from src.config import AppConfig
from src.laya_client import LayaClient
from src.ascension.api import AscendedServices
from src.ascension.battle_view import BattleViewBuilder
from src.ascension.catalog import Catalog
from src.ascension.collection import CollectionService
from src.ascension.coordinator import CoordinatorSettings, RoundCoordinator
from src.ascension.decider import ActionDecider
from src.ascension.emblem_picker import LayaEmblemPicker
from src.ascension.encounters import EncounterService
from src.ascension.engine import BattleEngine
from src.ascension.idempotency import IdempotentWriter
from src.ascension.policy import ActionPolicy, Mood
from src.ascension.progression import ProgressionService
from src.ascension.repository import AscendedRepository, SqliteAscendedRepository
from src.ascension.runtime import Clock, RandomSource, SystemClock, SystemRandom
from src.ascension.squad import SquadService
from src.ascension.shop import ShopService
from src.ascension.shop_offers import ShopOffers
from src.ascension.trees import TreeService
from src.ascension.upgrades import UpgradeService
from src.ascension.expeditions import ExpeditionService
from src.ascension.trials import TrialService
from src.ascension.situation import (
    FallbackSituationReader,
    HeuristicSituationReader,
    LayaPartialSituationReader,
    SituationReader,
    SituationViewBuilder,
)


def build_ascended_services(
    config: AppConfig, laya: LayaClient, catalog: Catalog | None = None, repository: AscendedRepository | None = None,
    clock: Clock | None = None, rng: RandomSource | None = None,
) -> AscendedServices:
    """Everything is injected, so tests and other front ends can swap any part."""
    catalog = catalog or Catalog.load()
    clock, rng = clock or SystemClock(), rng or SystemRandom()
    repository = repository or SqliteAscendedRepository(config.database_path, squad_size=catalog.economy.squad_size)
    writer = IdempotentWriter(repository, clock)
    engine = BattleEngine(catalog)
    progression = ProgressionService(catalog, clock, config.faint_seconds)
    heuristic = HeuristicSituationReader(catalog.policy.default_aggression)
    reader: SituationReader = (
        FallbackSituationReader(LayaPartialSituationReader(laya), heuristic) if config.situation_source == "laya" else heuristic
    )
    situation_views = SituationViewBuilder(engine)
    decider = ActionDecider(catalog, engine, ActionPolicy(catalog.policy), Mood(catalog), reader, situation_views)
    trees = TreeService(repository, writer, catalog)
    coordinator = RoundCoordinator(
        repository, writer, catalog, engine, decider, situation_views, LayaEmblemPicker(laya), progression,
        BattleViewBuilder(engine, catalog), clock, CoordinatorSettings(config.emblem_prompt_seconds), trees=trees,
    )
    return AscendedServices(
        catalog=catalog,
        trials=TrialService(repository, catalog, clock, progression),
        expeditions=ExpeditionService(repository, writer, catalog, progression, clock),
        collection=CollectionService(repository, writer, catalog, clock, rng, config.encounter_cooldown_seconds),
        encounters=EncounterService(repository, writer, catalog, clock, rng, config.encounter_cooldown_seconds),
        shop=ShopService(repository, writer, catalog, progression,
                         ShopOffers(catalog, config.shop_rotation_seconds, config.shop_offers), clock),
        upgrades=UpgradeService(repository, writer, catalog),
        coordinator=coordinator, trees=trees, squad=SquadService(repository, writer, catalog),
    )
