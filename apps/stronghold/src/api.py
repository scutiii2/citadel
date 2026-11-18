"""Stronghold HTTP routes require service assertions except public health checks."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict

import logging
import os

import httpx
from dotenv import dotenv_values
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from src.agents import routes as agents_routes
from src.agents.directory import AgentDirectory, HttpRegistrySource
from src.extensions import routes as extensions_routes
from src.extensions.probe import ExtensionProbe
from src.agents.gateway import AgentGateway, McpAgentGateway
from src.attachments import routes as attachments_routes
from src import tool_tokens
from src.usage import settings_routes as usage_settings_routes
from src import tool_token_routes
from src.attachments import services as tool_services
from src.attachments.services import ArmoryUploads
from src.bard import routes as bard_routes
from src.brains import routes as brains_routes
from src.brains.connections import BrainError
from src.brains.gateway import BrainGateway
from pathlib import Path
from src.citadel_auth import Keyring, ServiceAuthMiddleware, ServiceCatalog, CatalogTransport, logical_url, advertised_url, from_env
from src.citadel_auth.treasury import register_in_background
from src.chats import routes as chats_routes
from src.chats.store import ChatStore
from src.config import Settings, load_settings
from src.document_store import DbGatewayClient, DbGatewayError, DbGatewayUnavailable, DocumentStore
from src import log_privacy
from src.keys import load_keys
from src.memory import routes as memory_routes
from src.memory.client import MemoryClient
from src.notes import routes as notes_routes
from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.schema import migrations
from src.schema import routes as schema_routes
from src.secret_box import SecretBox
from src.skills import routes as skills_routes
from src.skills.client import SkillsClient
from src.shares import routes as shares_routes
from src.shares.store import ShareStore
from src.templates import routes as templates_routes
from src.tickets import routes as tickets_routes
from src.tickets.client import ArmoryTickets, TicketRefused, TicketUnavailable
from src.tickets.unread import TicketUnread
from src.triage import routes as triage_routes
from src.tuning import routes as tuning_routes
from src.tuning.limits import LegionTuning, LimitsStore
from src.usage import routes as usage_routes
from src.usage.service import UsageService
from src.turns import routes as turns_routes
from src.turns.engine import TurnRegistry
from src.turns.logs import PlatformLogs
from src.usage.settings import Pricing

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def create_app(
    keyring: Keyring | None = None, settings: Settings | None = None, *,
    store: DocumentStore | None = None, platform: PortcullisClient | None = None,
    armory: httpx.AsyncClient | None = None, agent_gateway: AgentGateway | None = None,
    tools: dict[str, httpx.AsyncClient] | None = None, legion: httpx.AsyncClient | None = None,
) -> FastAPI:
    """Service authentication is mandatory; tests inject isolated signing identities.
    `store`, `platform`, `armory`, `agent_gateway` and `tools` (clients for "bard", "scribe" and "reader") and `legion` are injected by tests;
    otherwise they are HTTP clients built at start."""
    settings = settings or load_settings()
    keyring = keyring or from_env("stronghold", data_dir=settings.data_dir)
    log_privacy.install()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await keyring.ensure_identity()
        catalog = ServiceCatalog(keyring, settings.treasury_url, cache_path=settings.data_dir / "catalog_cache.json")
        app.state.catalog = catalog
        if store is None:
            catalog.start("stronghold", advertised_url(settings.host, settings.port, settings.advertise_url))
        clients: list[httpx.AsyncClient] = []

        def http(base_url: str) -> httpx.AsyncClient:
            clients.append(httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT))
            return clients[-1]

        def http_catalog(name: str) -> httpx.AsyncClient:
            clients.append(httpx.AsyncClient(base_url=logical_url(name), timeout=_TIMEOUT, transport=CatalogTransport(catalog)))
            return clients[-1]

        keys = load_keys(settings.data_dir)
        app.state.settings = settings
        app.state.box = SecretBox(keys.secrets)
        app.state.store = store or DbGatewayClient(
            http_catalog("treasury"), settings.db_instance, settings.db_connection, keyring)
        registration = None if store is not None else register_in_background(
            keyring, settings.treasury_url, settings.db_instance, [settings.db_connection])
        app.state.platform = platform or PortcullisClient(http_catalog("portcullis"), keyring)
        app.state.agent_gateway = agent_gateway or McpAgentGateway(keyring)
        app.state.agents = AgentDirectory(
            HttpRegistrySource(settings.agents_registry_url, http(settings.agents_registry_url), keyring)
            if settings.agents_registry_url else settings.agents_registry_path
        )
        app.state.extension_probe = ExtensionProbe(app.state.agent_gateway)
        armory_client = armory or http_catalog("armory")
        app.state.memory = MemoryClient(armory_client, keyring)
        app.state.skills = SkillsClient(armory_client, keyring)
        app.state.brain_gateway = BrainGateway(armory_client, keyring)
        app.state.tickets = ArmoryTickets(armory_client, keyring)
        app.state.ticket_unread = TicketUnread(app.state.store)
        app.state.limits = LimitsStore(app.state.store)
        app.state.legion = LegionTuning(legion or http(""), app.state.agents, keyring)
        tools_in = tools or {}
        env = dotenv_values(ENV_PATH) if tools is None and ENV_PATH.exists() else {}  # tests inject `tools` and read no .env

        settings_db = settings.data_dir / "settings.db"
        env_tokens = {name: os.getenv(f"{name.upper()}_TOKEN") or env.get(f"{name.upper()}_TOKEN") or None
                      for name in tool_tokens.NAMES}
        app.state.env_tokens = env_tokens

        def service_token(name: str) -> str | None:
            # Tool services issue their own tokens; the shared internal token is no fallback.
            # A token saved on the Tool services page wins over the environment's.
            return tool_tokens.token_for(settings_db if tools is None else None, name, env_tokens[name])

        app.state.uploads = ArmoryUploads(armory_client, keyring)
        app.state.scribe = tool_services.scribe(tools_in.get("scribe") or http(settings.scribe_url), service_token("scribe"))
        app.state.reader = tool_services.reader(tools_in.get("reader") or http(settings.reader_url), service_token("reader"))
        app.state.bard = tool_services.bard(tools_in.get("bard") or http(settings.bard_url), service_token("bard"))
        app.state.shares = ShareStore(app.state.store)
        app.state.chats = ChatStore(app.state.store, app.state.shares)
        app.state.pricing = Pricing(settings.pricing)
        app.state.usage = UsageService(app.state.store, settings.usage, app.state.pricing)
        app.state.turns = TurnRegistry(
            app.state.chats, app.state.usage, app.state.agent_gateway, settings.usage, PlatformLogs(app.state.platform),
            pricing=app.state.pricing, directory=app.state.agents, keyring=keyring,
            requester_refresh=app.state.platform.requester_token)
        if registration is not None:
            # Migrate only once Treasury knows this instance: a cold start would answer 404 and skip the migration.
            try:
                await asyncio.wait_for(asyncio.shield(registration), timeout=20)
            except asyncio.TimeoutError:
                pass  # shortcut: Treasury is slow to answer, so the migration may fail and is logged below; upgrade with a retry loop
        app.state.schema_version = None
        try:
            app.state.schema_version = (await migrations.migrate(app.state.store))["version"]
        except (DbGatewayError, migrations.SchemaTooNew) as error:
            # Storage down: Stronghold still starts (a feature fails alone). Data newer than this code: leave it alone.
            logging.getLogger(__name__).error("schema migration not run: %s", error)
        try:
            yield
        finally:
            await catalog.stop()
            if registration is not None:
                registration.cancel()
            await app.state.turns.shutdown()
            for client in clients:
                await client.aclose()

    app = FastAPI(title="stronghold", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(ServiceAuthMiddleware, keyring=keyring, audience="stronghold")
    app.include_router(agents_routes.router)
    app.include_router(extensions_routes.router)
    app.include_router(attachments_routes.router)
    app.include_router(bard_routes.router)
    app.include_router(brains_routes.router)
    app.include_router(chats_routes.router)
    app.include_router(chats_routes.folder_router)
    app.include_router(memory_routes.router)
    app.include_router(notes_routes.router)
    app.include_router(skills_routes.router)
    app.include_router(templates_routes.router)
    app.include_router(usage_routes.router)
    app.include_router(schema_routes.router)
    app.include_router(shares_routes.router)
    app.include_router(tickets_routes.router)
    app.include_router(usage_settings_routes.router)
    app.include_router(tool_token_routes.router)
    app.include_router(tickets_routes.admin_router)
    app.include_router(triage_routes.router)
    app.include_router(turns_routes.router)
    app.include_router(tuning_routes.router)

    @app.exception_handler(BrainError)
    async def brain_error(_request: Request, error: BrainError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(TicketRefused)
    async def ticket_refused(_request: Request, error: TicketRefused):
        return JSONResponse({"detail": str(error)}, status_code=404 if error.status == 404 else 400)

    @app.exception_handler(TicketUnavailable)
    async def tickets_down(_request: Request, _error: TicketUnavailable):
        return JSONResponse({"detail": "armory is unreachable"}, status_code=502)

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
