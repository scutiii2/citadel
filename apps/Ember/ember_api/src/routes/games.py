"""Game catalog, administration, launch and server-to-server ticket redemption."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import Settings
from src.deps import (current_account, get_db_session, get_game_registry, get_ticket_service,
                      get_log_writer, get_settings, require_internal_token, require_permission)
from src.models import Account, Game
from src.services.game_manifest import ManifestError
from src.services.game_registry import GameRegistry, GameError, GameConflict, GameNotFound
from src.services.game_tickets import TicketService
from src.services.log_service import LogWriter
from src.services.permissions import GAMES_MANAGE, game_play_permission

router = APIRouter(prefix="/api/games", tags=["games"])
internal_router = APIRouter(prefix="/internal/games", tags=["games-internal"])
require_manage = require_permission(GAMES_MANAGE)


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2000)


class RedeemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=1, max_length=200)
    game_id: str = Field(min_length=1, max_length=63)


class GameInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    icon: str
    version: str
    url: str


class RegistryGameInfo(GameInfo):
    enabled: bool


class GameRoutes:
    """Request-scoped controller; all persistence and logging are injected."""
    def __init__(self, registry: GameRegistry, tickets: TicketService, logs: LogWriter, settings: Settings) -> None:
        self._registry = registry
        self._tickets = tickets
        self._logs = logs
        self._settings = settings

    @staticmethod
    def _http_error(error: GameError | ManifestError) -> HTTPException:
        code = 404 if isinstance(error, GameNotFound) else 409 if isinstance(error, GameConflict) else 400
        return HTTPException(code, str(error))

    def _can_play(self, account: Account, game: Game) -> bool:
        verified = account.email_verified or not self._settings.require_email_verification
        return verified and game_play_permission(game.id) in account.permission_names

    async def list(self, account: Account, *, registry: bool = False) -> dict:
        games = await self._registry.list()
        if registry:
            return {"games": [RegistryGameInfo.model_validate(game) for game in games]}
        return {"games": [GameInfo.model_validate(game) for game in games if game.enabled and self._can_play(account, game)]}

    async def register(self, account: Account, url: str) -> RegistryGameInfo:
        try:
            game = await self._registry.register(url)
        except (GameError, ManifestError) as error:
            raise self._http_error(error) from error
        await self._logs.action(account, "games.register", f"Registered game '{game.id}'")
        return RegistryGameInfo.model_validate(game)

    async def refresh(self, account: Account, game_id: str) -> RegistryGameInfo:
        try:
            game = await self._registry.refresh(game_id)
        except (GameError, ManifestError) as error:
            raise self._http_error(error) from error
        await self._logs.action(account, "games.refresh", f"Refreshed game '{game.id}'")
        return RegistryGameInfo.model_validate(game)

    async def deregister(self, account: Account, game_id: str) -> None:
        try:
            await self._registry.deregister(game_id)
        except GameError as error:
            raise self._http_error(error) from error
        await self._logs.action(account, "games.deregister", f"Deregistered game '{game_id}'")

    async def launch(self, account: Account, game_id: str) -> dict[str, str]:
        try:
            game = await self._registry.get(game_id)
        except GameError as error:
            raise self._http_error(error) from error
        if not game.enabled:
            raise HTTPException(404, "Game not found")
        if not self._can_play(account, game):
            raise HTTPException(403, f"Missing permission: {game_play_permission(game_id)}")
        ticket = await self._tickets.issue(game.id, account.id)
        await self._logs.action(account, "games.launch", f"Launched game '{game.id}'")
        return {"url": f"{game.url}/#ticket={ticket}"}


class TicketRedemption:
    def __init__(self, session: AsyncSession, tickets: TicketService) -> None:
        self._session = session
        self._tickets = tickets

    async def redeem(self, raw: Any) -> dict[str, str]:
        try:
            body = RedeemIn.model_validate(raw)
        except ValidationError as error:
            raise HTTPException(401, "Invalid ticket") from error
        account_id = await self._tickets.redeem(body.game_id, body.ticket)
        account = await self._session.scalar(select(Account).where(Account.id == account_id)) if account_id is not None else None
        if account is None or not account.is_active:
            raise HTTPException(401, "Invalid ticket")
        return {"account_id": str(account.id), "display_name": account.username}


def get_game_routes(registry: GameRegistry = Depends(get_game_registry), tickets: TicketService = Depends(get_ticket_service),
                    logs: LogWriter = Depends(get_log_writer), settings: Settings = Depends(get_settings)) -> GameRoutes:
    return GameRoutes(registry, tickets, logs, settings)


@router.get("/registry")
async def registry(account: Account = Depends(require_manage), controller: GameRoutes = Depends(get_game_routes)) -> dict:
    return await controller.list(account, registry=True)


@router.get("")
async def list_games(account: Account = Depends(current_account), controller: GameRoutes = Depends(get_game_routes)) -> dict:
    return await controller.list(account)


@router.post("", status_code=201)
async def register(body: RegisterIn, account: Account = Depends(require_manage), controller: GameRoutes = Depends(get_game_routes)) -> RegistryGameInfo:
    return await controller.register(account, body.url)


@router.post("/{game_id}/launch")
async def launch(game_id: str, account: Account = Depends(current_account), controller: GameRoutes = Depends(get_game_routes)) -> dict[str, str]:
    return await controller.launch(account, game_id)


@router.post("/{game_id}/refresh")
async def refresh(game_id: str, account: Account = Depends(require_manage), controller: GameRoutes = Depends(get_game_routes)) -> RegistryGameInfo:
    return await controller.refresh(account, game_id)


@router.delete("/{game_id}", status_code=204)
async def deregister(game_id: str, account: Account = Depends(require_manage), controller: GameRoutes = Depends(get_game_routes)) -> Response:
    await controller.deregister(account, game_id)
    return Response(status_code=204)


@internal_router.post("/tickets/redeem", dependencies=[Depends(require_internal_token)])
async def redeem(raw: Any = Body(default=None), session: AsyncSession = Depends(get_db_session),
                 tickets: TicketService = Depends(get_ticket_service)) -> dict[str, str]:
    return await TicketRedemption(session, tickets).redeem(raw)
