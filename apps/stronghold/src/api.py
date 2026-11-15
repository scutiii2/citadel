"""Stronghold's HTTP app. Every route but /health needs the internal token."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from src.agents.directory import AgentDirectory, HttpRegistrySource
from src.agents.gateway import AgentGateway, McpAgentGateway
from src.auth import InternalTokenMiddleware
from src.calendar import routes as calendar_routes
from src.calendar.runtime import build_calendar_runtime
from src.calendar.store import CalendarError
from src.config import Settings, load_settings
from src.document_store import DbGatewayClient, DbGatewayUnavailable, DocumentStore
from src import log_privacy
from src.keys import load_keys
from src.memory import routes as memory_routes
from src.memory.client import MemoryClient
from src.notes import routes as notes_routes
from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.secret_box import SecretBox
from src.skills import routes as skills_routes
from src.skills.client import SkillsClient
from src.templates import routes as templates_routes
from src.usage import routes as usage_routes
from src.usage.service import UsageService
from src.usage.settings import Pricing

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def create_app(
    token: str, settings: Settings | None = None, *,
    store: DocumentStore | None = None, platform: PortcullisClient | None = None,
    armory: httpx.AsyncClient | None = None, agent_gateway: AgentGateway | None = None,
) -> FastAPI:
    """token: the shared internal token; "" leaves the app open (tests, loopback).
    `store`, `platform`, `armory` and `agent_gateway` are injected by tests; otherwise they are HTTP clients built at start."""
    settings = settings or load_settings()
    log_privacy.install()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        clients: list[httpx.AsyncClient] = []

        def http(base_url: str) -> httpx.AsyncClient:
            clients.append(httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT))
            return clients[-1]

        keys = load_keys(settings.data_dir)
        app.state.settings = settings
        app.state.box = SecretBox(keys.secrets)
        app.state.store = store or DbGatewayClient(
            http(settings.db_gateway_url), settings.db_instance, settings.db_connection, token or None)
        app.state.platform = platform or PortcullisClient(http(settings.portcullis_url), token or None)
        app.state.agent_gateway = agent_gateway or McpAgentGateway(token or None)
        app.state.agents = AgentDirectory(
            HttpRegistrySource(settings.agents_registry_url, http(settings.agents_registry_url), token or None)
            if settings.agents_registry_url else settings.agents_registry_path
        )
        armory_client = armory or http(settings.armory_url)
        app.state.memory = MemoryClient(armory_client, token or None)
        app.state.skills = SkillsClient(armory_client, token or None)
        app.state.usage = UsageService(app.state.store, settings.usage, Pricing(settings.pricing))
        app.state.calendar = (
            build_calendar_runtime(config=settings.calendar, store=app.state.store, box=app.state.box,
                                   keys=keys, platform=app.state.platform)
            if settings.calendar.enabled else None
        )
        try:
            yield
        finally:
            if app.state.calendar is not None:
                await app.state.calendar.close()
            for client in clients:
                await client.aclose()

    app = FastAPI(title="stronghold", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(InternalTokenMiddleware, token=token)
    app.include_router(calendar_routes.router)
    app.include_router(memory_routes.router)
    app.include_router(notes_routes.router)
    app.include_router(skills_routes.router)
    app.include_router(templates_routes.router)
    app.include_router(usage_routes.router)

    @app.exception_handler(CalendarError)
    async def calendar_error(_request: Request, error: CalendarError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(DbGatewayUnavailable)
    async def storage_down(_request: Request, _error: DbGatewayUnavailable):
        return JSONResponse({"detail": "Storage is unavailable"}, status_code=503)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami")
    async def whoami(requester: Requester = Depends(current_requester)) -> dict[str, str]:
        """Echoes the identity Portcullis sent. Proves the forwarding path end to end."""
        return asdict(requester)

    return app
