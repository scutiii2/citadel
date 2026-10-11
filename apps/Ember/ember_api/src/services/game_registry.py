"""Persisted game registry; deregistration retains permissions and role grants."""
from __future__ import annotations
import json
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.db import utcnow
from src.models import Game, Permission, Role
from src.services.game_manifest import Manifest, ManifestFetcher, GameUrlPolicy
from src.services.permissions import ADMIN_ROLE, game_play_permission, permission_description


class GameError(Exception):
    pass


class GameConflict(GameError):
    pass


class GameNotFound(GameError):
    pass


class GameRegistry:
    def __init__(self, session: AsyncSession, fetcher: ManifestFetcher, allow_private: bool) -> None:
        self._session = session
        self._fetcher = fetcher
        self._policy = GameUrlPolicy(allow_private=allow_private)

    async def register(self, url: str) -> Game:
        base = self._policy.normalize(url)
        manifest = await self._fetcher.fetch(base)
        if await self._session.scalar(select(Game.id).where(or_(Game.id == manifest.id, Game.url == base))) is not None:
            raise GameConflict("A game with this id or URL is already registered")
        game = Game(id=manifest.id, url=base)
        self._apply(game, manifest)
        self._session.add(game)
        try:
            name = game_play_permission(game.id)
            permission = await self._session.scalar(select(Permission).where(Permission.name == name))
            if permission is None:
                permission = Permission(name=name, description=permission_description(name))
                self._session.add(permission)
            role = await self._session.scalar(select(Role).where(Role.name == ADMIN_ROLE))
            if role is not None and permission not in role.permissions:
                role.permissions.append(permission)
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise GameConflict("A game with this id or URL is already registered") from error
        return game

    async def refresh(self, game_id: str) -> Game:
        game = await self.get(game_id)
        manifest = await self._fetcher.fetch(game.url)
        if manifest.id != game.id:
            raise GameError("The refreshed manifest id must match the registered game")
        self._apply(game, manifest)
        await self._session.commit()
        return game

    async def deregister(self, game_id: str) -> None:
        game = await self.get(game_id)
        await self._session.delete(game)
        await self._session.commit()

    async def list(self) -> list[Game]:
        return list(await self._session.scalars(select(Game).order_by(Game.name, Game.id)))

    async def get(self, game_id: str) -> Game:
        game = await self._session.get(Game, game_id)
        if game is None:
            raise GameNotFound("Game not found")
        return game

    @staticmethod
    def _apply(game: Game, manifest: Manifest) -> None:
        game.name = manifest.name
        game.description = manifest.description
        game.icon = manifest.icon
        game.version = manifest.version
        game.manifest = json.dumps(manifest.raw)
        game.updated_at = utcnow()
