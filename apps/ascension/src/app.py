"""Ascension app shell: bearer sessions, ticket redemption, health and error shape."""

from __future__ import annotations

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from src.config import AppConfig
from src.ember_identity import EmberIdentity
from src.sessions import GameSessions
from src.session_routes import RedeemLimiter, SessionRoutes


def create_app(*, sessions: GameSessions | None = None, identity: EmberIdentity | None = None,
               config: AppConfig | None = None, internal_token: str = "") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if identity is None and config is not None:
            async with httpx.AsyncClient(follow_redirects=False) as client:
                app.state.identity = EmberIdentity(client, config.ember_api_url, internal_token, config.game_id)
                try:
                    yield
                finally:
                    app.state.identity = None
        else:
            yield

    app = FastAPI(title="ascension", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions = sessions or GameSessions((config.session_hours if config else 8) * 3600)
    app.state.identity = identity
    app.state.redeem_limiter = RedeemLimiter()
    app.state.dev_fake_owner = config.dev_fake_owner if config else ""
    SessionRoutes().mount(app)

    @app.exception_handler(RequestValidationError)
    async def bad_body(request: Request, error: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:3])
        return JSONResponse({"error": "invalid request", "detail": detail}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        # Starlette's class, so router-raised 404 and 405 get the same {"error"} shape as everything else.
        return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=error.headers)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
