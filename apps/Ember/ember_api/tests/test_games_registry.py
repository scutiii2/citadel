import asyncio
from contextlib import asynccontextmanager
import pytest
from sqlalchemy import select
from src.db import Database
from src.models import Account, Game, Permission, Role
from src.services.game_manifest import Manifest
from src.services.game_registry import GameRegistry, GameConflict, GameError, GameNotFound
from src.services.auth_service import AuthService


class FakeFetcher:
    def __init__(self):
        self.raw = {"id": "ascension", "name": "Ascension", "description": "Collect.", "icon": "", "version": "1.0"}
        self.calls = []
    async def fetch(self, url):
        self.calls.append(url)
        return Manifest(**self.raw, raw=dict(self.raw))


@asynccontextmanager
async def game_database(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'games.db').as_posix()}")
    await db.create_tables()
    try:
        async with db.sessions() as session:
            session.add(Role(name="Administrator", permissions=[]))
            session.add(Account(username="player", email="player@example.com", password_hash="unused", roles=[]))
            await session.commit()
            yield db, session
    finally:
        await db.dispose()


def test_registration_permissions_refresh_and_reregister(tmp_path):
    async def go():
        async with game_database(tmp_path) as (_, session):
            fetcher = FakeFetcher()
            registry = GameRegistry(session, fetcher, True)
            game = await registry.register("http://localhost:8060/?x=1")
            assert game.url == "http://localhost:8060"
            assert game.enabled and game.manifest
            permission = await session.scalar(select(Permission).where(Permission.name == "games.ascension.play"))
            permission_id = permission.id
            admin = await session.scalar(select(Role).where(Role.name == "Administrator"))
            assert permission in admin.permissions
            assert permission.description == "Play ascension"
            # A bootstrap sync must preserve dynamic grants, too.
            await AuthService(session)._ensure_admin_role()
            assert permission in admin.permissions
            fetcher.raw.update(name="New name", version="2.0")
            updated = await registry.refresh("ascension")
            assert updated.name == "New name" and updated.version == "2.0"
            assert updated.updated_at >= updated.created_at
            assert [g.id for g in await registry.list()] == ["ascension"]
            await registry.deregister("ascension")
            assert await registry.list() == []
            assert permission in admin.permissions
            await registry.register("http://localhost:8061")
            assert (await session.scalar(select(Permission).where(Permission.name == permission.name))).id == permission_id
    asyncio.run(go())


def test_conflicts_and_changed_identity_leave_game_intact(tmp_path):
    async def go():
        async with game_database(tmp_path) as (_, session):
            fetcher = FakeFetcher()
            registry = GameRegistry(session, fetcher, True)
            await registry.register("http://localhost:8060")
            with pytest.raises(GameConflict):
                await registry.register("http://localhost:8061")
            fetcher.raw["id"] = "other"
            with pytest.raises(GameConflict):
                await registry.register("http://localhost:8060/")
            with pytest.raises(GameError):
                await registry.refresh("ascension")
            assert (await registry.get("ascension")).name == "Ascension"
            for operation in (registry.get, registry.refresh, registry.deregister):
                with pytest.raises(GameNotFound):
                    await operation("unknown")
    asyncio.run(go())
