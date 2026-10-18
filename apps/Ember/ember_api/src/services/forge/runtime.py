"""Builds and owns the long-lived Forge components for one app."""

from __future__ import annotations

from src.db import Database
from src.services.forge.connections import WorkerRegistry
from src.services.forge.coordinator import TurnCoordinator
from src.services.forge.events import GroupEventBus, GroupStreamer
from src.services.forge.messages import MessageStore
from src.services.forge.routing import TurnRouter


class ForgeRuntime:
    def __init__(self, database: Database) -> None:
        self.registry = WorkerRegistry()
        self.bus = GroupEventBus()
        self.store = MessageStore(database)
        self.coordinator = TurnCoordinator(database, self.registry, self.bus, self.store, TurnRouter())
        self.streamer = GroupStreamer(self.bus, self.store, self.coordinator.is_running)

    async def shutdown(self) -> None:
        await self.coordinator.shutdown()
