"""Keeps registered games in step with their manifests (wallpaper, version, description)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from src.db import Database
from src.services.game_manifest import ManifestError, ManifestFetcher
from src.services.game_registry import GameError, GameRegistry

logger = logging.getLogger(__name__)


class GameSyncScheduler:
    """Refreshes every registered game at start and then on a fixed interval, until stopped.

    A game that is down or answers badly is skipped and retried next round;
    its stored manifest stays as it was.
    """

    def __init__(
        self,
        database: Database,
        fetcher: ManifestFetcher,
        allow_private: bool,
        every: timedelta,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._database = database
        self._fetcher = fetcher
        self._allow_private = allow_private
        self._every = every
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="game-manifest-sync")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def sync_once(self) -> None:
        async with self._database.sessions() as session:
            registry = GameRegistry(session, self._fetcher, self._allow_private)
            game_ids = [game.id for game in await registry.list()]
            for game_id in game_ids:
                try:
                    await registry.refresh(game_id)
                except (GameError, ManifestError) as error:
                    logger.info("game '%s' manifest not refreshed: %s", game_id, error)

    async def _loop(self) -> None:
        while True:
            try:
                await self.sync_once()
            except Exception:  # never let one bad round end the loop
                logger.exception("game manifest sync failed")
            await self._sleep(self._every.total_seconds())
