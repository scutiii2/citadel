"""Stronghold HTTP routes require service assertions except public health checks."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from http.cookiejar import CookieJar, DefaultCookiePolicy

import logging

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from src.agents import routes as agents_routes
from src.agents.directory import AgentDirectory, HttpRegistrySource
from src.extensions import routes as extensions_routes
from src.extensions.probe import ExtensionProbe
from src.agents.gateway import AgentGateway, McpAgentGateway
from src.attachments import routes as attachments_routes
from src.usage import settings_routes as usage_settings_routes
from src.usage import allowance_routes as usage_allowance_routes
from src.attachments.services import ArmoryUploads
from src.bard import routes as bard_routes
from src import ready
from src.citadel_auth.ready import Probe
from src.citadel_auth import Keyring, ServiceAuthMiddleware, ServiceCatalog, CatalogTransport, logical_url, advertised_url, from_env
from src.citadel_auth.treasury import register_in_background
from src.chats import routes as chats_routes
from src.chats.armory_holds import ArmoryHolds
from src.chats.file_holds import ChatFileHolds
from src.chats.hold_sender import HoldSender
from src.chats.store import ChatStore
from src.config import Settings, load_settings
from src.brain import files_routes as brain_files_routes
from src.brain import global_routes as brain_global_routes
from src.brain import proposal_routes as brain_proposal_routes
from src.brain import share_routes as brain_share_routes
from src.brain import routes as stack_routes
from src.brain import settings_routes as brain_settings_routes
from src.brain.compaction import StackCompactor
from src.brain.files import BrainFiles
from src.brain.global_brain import GlobalBrain
from src.brain.limits import brain_root, load_limits, load_long_term, load_sharing
from src.brain.proposals import BrainProposals
from src.brain.shares import BrainShares
from src.brain.skills import SkillFiles
from src.brain.stack import StackStore
from starlette.routing import Route

from src.mcp_tools.server import LegionOnlyMcp, build_server
from src.document_store import DbGatewayClient, DbGatewayError, DbGatewayUnavailable, DocumentStore
from src import log_privacy
from src.keys import load_keys
from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.schema import migrations
from src.schema import routes as schema_routes
from src.secret_box import SecretBox
from src.skills import routes as skills_routes
from src.shares import routes as shares_routes
from src.shares.store import ShareStore
from src.templates import routes as templates_routes
from src.tickets import routes as tickets_routes
from src.tickets import settings as ticket_settings
from src.tickets.classifier import TicketClassifier
from src.tickets.service import TicketError, TicketNotFound, TicketService
from src.tickets.store import TicketStore
from src.triage.questions import TriageQuestions
from src.tickets.unread import TicketUnread
from src.tool_services import routes as tool_services_routes
from src.tool_services.client import ToolServices
from src.tool_services.dictation import DictationRelay
from src.tool_services.outside import OutsideRegistry
from src.tool_services.store import ToolStore
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


def create_app(
    keyring: Keyring | None = None, settings: Settings | None = None, *,
    store: DocumentStore | None = None, platform: PortcullisClient | None = None,
    armory: httpx.AsyncClient | None = None, agent_gateway: AgentGateway | None = None,
    legion: httpx.AsyncClient | None = None,
    tool_http: httpx.AsyncClient | None = None, tool_origins: Callable[[str], str] | None = None,
) -> FastAPI:
    """Service authentication is mandatory; tests inject isolated signing identities.
    Tests may inject clients and an outside-origin resolver."""
    settings = settings or load_settings()
    keyring = keyring or from_env("stronghold", data_dir=settings.data_dir)
    log_privacy.install()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await keyring.ensure_identity()
        catalog = ServiceCatalog(keyring, settings.treasury_url, cache_path=settings.data_dir / "catalog_cache.json")
        app.state.keyring = keyring
        app.state.catalog = catalog
        app.state.readiness = Probe("stronghold")
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
        app.state.ticket_unread = TicketUnread(app.state.store)
        app.state.limits = LimitsStore(app.state.store)
        app.state.legion = LegionTuning(legion or http(""), app.state.agents, keyring)
        app.state.uploads = ArmoryUploads(armory_client, keyring)
        data_settings = settings.data_dir / "settings.db"
        app.state.tool_store = ToolStore(data_settings)
        app.state.outside = OutsideRegistry(keyring, catalog)
        app.state.tool_http = tool_http
        if tool_http is None:
            app.state.tool_http = httpx.AsyncClient(timeout=120, trust_env=False)
            clients.append(app.state.tool_http)
        # Cookies ignore ports. Keep credentials isolated between outside origins.
        app.state.tool_http.cookies = CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))
        app.state.tool_settings_lock = asyncio.Lock()
        app.state.connections = ToolServices(app.state.tool_store, app.state.tool_http, tool_origins or catalog.outside_origin)
        app.state.dictation = DictationRelay()
        app.state.shares = ShareStore(app.state.store)
        app.state.file_holds = ChatFileHolds(app.state.store)
        app.state.chats = ChatStore(app.state.store, app.state.shares, app.state.file_holds)
        app.state.stacks = StackStore(
            app.state.store, await asyncio.to_thread(load_limits, data_settings), app.state.chats.generation,
        )
        app.state.brain_settings_lock = asyncio.Lock()
        app.state.brain_folder = await asyncio.to_thread(brain_root, settings.data_dir, data_settings)
        app.state.brain_files = BrainFiles(
            app.state.brain_folder, await asyncio.to_thread(load_long_term, data_settings),
        )
        app.state.skill_files = SkillFiles(app.state.brain_files)
        app.state.global_brain = GlobalBrain(app.state.brain_folder, app.state.brain_files.limits)
        app.state.brain_shares = BrainShares(
            app.state.store, app.state.brain_files, app.state.skill_files, app.state.stacks, app.state.global_brain,
            await asyncio.to_thread(load_sharing, data_settings),
        )
        app.state.brain_proposals = BrainProposals(
            app.state.store, app.state.brain_files, app.state.stacks,
        )
        app.state.compactor = StackCompactor(app.state.stacks, app.state.agent_gateway, app.state.agents)
        app.state.pricing = Pricing(settings.pricing)
        app.state.usage = UsageService(app.state.store, settings.usage, app.state.pricing)
        ticket_config = await asyncio.to_thread(ticket_settings.load, data_settings)
        app.state.tickets = TicketService(
            TicketStore(app.state.store), ticket_config,
            TicketClassifier(TriageQuestions(app.state.agent_gateway, app.state.agents), app.state.usage,
                             min_confidence=ticket_config.laya_min_confidence,
                             timeout=ticket_config.laya_timeout_seconds),
            settings_path=data_settings,
        )
        app.state.turns = TurnRegistry(
            app.state.chats, app.state.usage, app.state.agent_gateway, settings.usage, PlatformLogs(app.state.platform),
            pricing=app.state.pricing, directory=app.state.agents, keyring=keyring,
            requester_refresh=app.state.platform.requester_token, compactor=app.state.compactor)
        app.state.schema_version = None

        async def migrate_schema() -> None:
            try:
                if registration is not None:
                    await registration
                app.state.schema_version = (await migrations.migrate(app.state.store))["version"]
            except (DbGatewayError, migrations.SchemaTooNew) as error:
                logging.getLogger(__name__).error("schema migration not run: %s", error)

        schema_task = None
        if registration is None:
            await migrate_schema()
        else:
            schema_task = asyncio.create_task(migrate_schema())
        hold_sender = HoldSender(app.state.file_holds, ArmoryHolds(armory_client, keyring), app.state.chats.exists)
        hold_task = asyncio.create_task(hold_sender.run())
        app.state.mcp = build_server(app, settings.host)
        mcp_app = app.state.mcp.streamable_http_app()
        mount = Route("/mcp", LegionOnlyMcp(mcp_app))
        app.router.routes.append(mount)
        try:
            async with app.state.mcp.session_manager.run():
                yield
        finally:
            app.router.routes.remove(mount)
            await catalog.stop()
            if schema_task is not None and registration is not None:
                schema_task.cancel()
                registration.cancel()
                await asyncio.gather(schema_task, registration, return_exceptions=True)
            await app.state.turns.shutdown()
            hold_task.cancel()
            await asyncio.gather(hold_task, return_exceptions=True)
            for client in clients:
                await client.aclose()

    app = FastAPI(title="stronghold", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(ServiceAuthMiddleware, keyring=keyring, audience="stronghold", websocket_paths=("/speech/dictate",))
    app.include_router(agents_routes.router)
    app.include_router(extensions_routes.router)
    app.include_router(attachments_routes.router)
    app.include_router(bard_routes.router)
    app.include_router(tool_services_routes.router)
    app.include_router(stack_routes.router)
    app.include_router(brain_files_routes.router)
    app.include_router(brain_global_routes.router)
    app.include_router(brain_share_routes.router)
    app.include_router(brain_share_routes.blocks_router)
    app.include_router(brain_proposal_routes.router)
    app.include_router(brain_settings_routes.router)
    app.include_router(chats_routes.router)
    app.include_router(chats_routes.folder_router)
    app.include_router(skills_routes.router)
    app.include_router(templates_routes.router)
    app.include_router(usage_routes.router)
    app.include_router(schema_routes.router)
    app.include_router(shares_routes.router)
    app.include_router(tickets_routes.router)
    app.include_router(usage_settings_routes.router)
    app.include_router(usage_allowance_routes.router)
    app.include_router(tickets_routes.admin_router)
    app.include_router(triage_routes.router)
    app.include_router(turns_routes.router)
    app.include_router(tuning_routes.router)

    @app.exception_handler(TicketError)
    async def ticket_refused(_request: Request, error: TicketError):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(TicketNotFound)
    async def ticket_missing(_request: Request, error: TicketNotFound):
        return JSONResponse({"detail": str(error)}, status_code=404)

    @app.exception_handler(DbGatewayUnavailable)
    async def storage_down(_request: Request, _error: DbGatewayUnavailable):
        return JSONResponse({"detail": "Storage is unavailable"}, status_code=503)

    @app.get("/ready")
    async def readiness() -> dict:
        return await app.state.readiness.check(ready.dependencies(app.state.catalog))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami")
    async def whoami(requester: Requester = Depends(current_requester)) -> dict[str, str]:
        """Echoes the identity Portcullis sent. Proves the forwarding path end to end."""
        return asdict(requester)

    return app
