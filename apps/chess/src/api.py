"""HTTP API used by ember_api and, later, the MCP extension tools.

Every route but /health needs X-Internal-Token (once configured) and an
X-Requester-Username naming the session owner.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.auth import REQUESTER_USERNAME_HEADER, InternalTokenMiddleware
from src.games.base import Game, IllegalMove, InvalidOptions
from src.sessions import GameOver, SessionLimit, SessionNotFound, SessionStore, WrongTurn


class CreateBody(BaseModel):
    game: str
    options: dict[str, Any] = Field(default_factory=dict)
    difficulty: str = "medium"
    picker: str | None = None


class MoveBody(BaseModel):
    move: dict[str, Any]


def _owner(name: str) -> str:
    owner = name.strip()
    if not owner:
        raise HTTPException(400, f"{REQUESTER_USERNAME_HEADER} header is required")
    return owner


def _error(status: int):
    async def handler(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=status)

    return handler


def create_app(store: SessionStore, games: dict[str, Game], token: str = "") -> FastAPI:
    app = FastAPI(title="chess", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(InternalTokenMiddleware, token=token)

    for error, status in (
        (IllegalMove, 400), (InvalidOptions, 400), (SessionNotFound, 404),
        (WrongTurn, 409), (GameOver, 409), (SessionLimit, 409),
    ):
        app.add_exception_handler(error, _error(status))

    @app.exception_handler(RequestValidationError)
    async def bad_body(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "invalid request body", "detail": str(error.errors()[:3])}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse({"error": error.detail}, status_code=error.status_code)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/games")
    async def list_games(x_requester_username: str = Header(default="")) -> dict[str, Any]:
        _owner(x_requester_username)
        return {"games": [{"id": g.id, "options": g.option_schema()} for g in games.values()]}

    @app.post("/sessions", status_code=201)
    async def create_session(body: CreateBody, x_requester_username: str = Header(default="")) -> dict[str, Any]:
        session = await store.create(_owner(x_requester_username), body.game, body.options, body.difficulty, body.picker)
        return store.view(session)

    @app.get("/sessions/{sid}")
    async def get_session(sid: str, x_requester_username: str = Header(default="")) -> dict[str, Any]:
        return store.view(await store.get(_owner(x_requester_username), sid))

    @app.post("/sessions/{sid}/moves")
    async def player_move(sid: str, body: MoveBody, x_requester_username: str = Header(default="")) -> dict[str, Any]:
        return store.view(await store.player_move(_owner(x_requester_username), sid, body.move))

    @app.post("/sessions/{sid}/bot-move")
    async def bot_move(sid: str, x_requester_username: str = Header(default="")) -> dict[str, Any]:
        session, entry = await store.bot_move(_owner(x_requester_username), sid)
        return {**store.view(session), "bot_move": entry}

    @app.delete("/sessions/{sid}", status_code=204)
    async def delete_session(sid: str, x_requester_username: str = Header(default="")) -> None:
        await store.delete(_owner(x_requester_username), sid)

    return app
