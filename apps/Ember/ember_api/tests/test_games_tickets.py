import asyncio
import hashlib
from datetime import datetime, timedelta
from sqlalchemy import func, select
from src.models import GameTicket
from src.services.game_registry import GameRegistry
from src.services.game_tickets import TicketService
from tests.test_games_registry import FakeFetcher, game_database


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 11)
    def __call__(self):
        return self.value


def test_single_use_hash_expiry_wrong_game_and_pruning(tmp_path):
    async def go():
        async with game_database(tmp_path) as (_, session):
            await GameRegistry(session, FakeFetcher(), True).register("http://localhost:8060")
            clock = Clock()
            tickets = TicketService(session, now=clock)
            token = await tickets.issue("ascension", 1)
            row = await session.scalar(select(GameTicket))
            assert row.token_hash != token
            assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
            assert row.expires_at == clock.value + timedelta(seconds=60)
            assert await tickets.redeem("other", token) is None
            assert await tickets.redeem("ascension", token) == 1
            assert await tickets.redeem("ascension", token) is None
            assert await tickets.redeem("ascension", "unknown") is None
            expiring = await tickets.issue("ascension", 1)
            clock.value += timedelta(seconds=60)
            assert await tickets.redeem("ascension", expiring) is None
            clock.value += timedelta(seconds=61)
            await tickets.issue("ascension", 1)
            assert await session.scalar(select(func.count(GameTicket.id))) == 1
            await GameRegistry(session, FakeFetcher(), True).deregister("ascension")
            assert await session.scalar(select(func.count(GameTicket.id))) == 0
    asyncio.run(go())


def test_simultaneous_redemption_has_one_winner(tmp_path):
    async def go():
        async with game_database(tmp_path) as (db, session):
            await GameRegistry(session, FakeFetcher(), True).register("http://localhost:8060")
            token = await TicketService(session).issue("ascension", 1)
            async def redeem():
                async with db.sessions() as contender:
                    return await TicketService(contender).redeem("ascension", token)
            results = await asyncio.gather(redeem(), redeem())
            assert sorted(results, key=lambda value: value is None) == [1, None]
    asyncio.run(go())
