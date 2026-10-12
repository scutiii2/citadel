import asyncio
from datetime import timedelta
from sqlalchemy import select
from src.models import Game
from src.services.game_manifest import ManifestError
from src.services.game_sync import GameSyncScheduler
from tests.test_games_registry import FakeFetcher, game_database
from src.services.game_registry import GameRegistry


def test_sync_refreshes_changed_manifest_and_skips_unreachable_game(tmp_path):
    async def go():
        async with game_database(tmp_path) as (db, session):
            fetcher = FakeFetcher()
            await GameRegistry(session, fetcher, True).register("http://localhost:8060")
            fetcher.raw.update(version="2.0")
            sync = GameSyncScheduler(db, fetcher, True, timedelta(minutes=10))
            await sync.sync_once()
            async with db.sessions() as check:
                assert (await check.scalar(select(Game.version))) == "2.0"

            async def down(url):
                raise ManifestError("Cannot reach the game")
            fetcher.fetch = down
            await sync.sync_once()  # must not raise
            async with db.sessions() as check:
                assert (await check.scalar(select(Game.version))) == "2.0"
    asyncio.run(go())
