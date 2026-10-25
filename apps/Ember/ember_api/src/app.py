"""FastAPI application factory."""

from __future__ import annotations

import logging
import traceback
from datetime import timedelta
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from src.routes import brains
from src.services.brain_connections import BrainError

from src.config import Settings
from src.db import Database
from src.body_limit import BodyLimitMiddleware
from src.json_only import JsonOnlyMiddleware
from src.security import SecurityMiddleware
from src.routes import (
    account,
    account_agents,
    admin,
    agent_admin,
    attachments,
    bard,
    capability_files,
    calendar as calendar_routes,
    auth,
    chat_folders,
    chats,
    config_issues,
    tickets as tickets_routes,
    logs,
    mcp,
    memory,
    nav_preferences,
    notes,
    server_info,
    settings as settings_routes,
    shares,
    skills,
    templates,
    traffic as traffic_routes,
    triage,
    usage,
    user_extensions,
)
from src.services.agent_directory import AgentDirectory, HttpRegistrySource
from src.services.agent_gateway import AgentGateway, McpAgentGateway
from src.services.auth_service import AuthService
from src.services.capability_files import CapabilityFailure
from src.services.calendar_runtime import build_calendar_runtime
from src.services.calendar_store import CalendarError
from src.services.backup_service import BackupScheduler, DatabaseBackup
from src.services.migrations import MigrationRunner
from src.services.chat_service import MAX_CHAT_BYTES
from src.services.db_gateway import DbGatewayClient, DbGatewayError, DocumentStore
from src.services.email_service import EmailSender, McpEmailSender
from src.services.extension_probe import ExtensionProbe
from src.services.log_service import LogWriter
from src.services.mcp_proxy import McpProxy
from src.services.memory_purger import MemoryPurger
from src.services.memory import MemoryClient
from src.services.skills import SkillsClient
from src.services.otp_service import OtpService
from src.services.secret_box import SecretBox, ensure_secrets_key
from src.services.public_rate_limiter import PublicReadLimiter
from src.services.share_service import purge_expired_shares
from src.services.server_tools import McpServerTools, ServerTools
from src.services.session_service import SessionService
from src.services.traffic import TrafficMiddleware, TrafficRecorder
from src.services.turns import TurnRegistry
from src.utils.config_loader import load_env_secrets

logger = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 16 * MAX_CHAT_BYTES
# Anywhere else a body is a few fields of JSON; login and registration need no more.
DEFAULT_REQUEST_BYTES = 1024 * 1024
# The routes that take big bodies: chats (history imports, questions with
# attached text), attachment files and command-form uploads.
LARGE_BODY_PREFIXES = ("/api/chats", "/api/attachments", "/api/uploads", "/api/pdf-merger/files")

# No read timeout: an MCP event stream stays open for as long as a chat turn
# (or the session) lasts. Connect/write/pool still fail fast.
_UPSTREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
# db_gateway answers quickly or not at all; a feature using it should fail fast.
_DB_GATEWAY_TIMEOUT = httpx.Timeout(5.0)


def create_app(
    settings: Settings,
    email_sender: EmailSender | None = None,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
    agent_gateway: AgentGateway | None = None,
    server_tools: ServerTools | None = None,
    traffic: TrafficRecorder | None = None,
    *,
    db_gateway: DocumentStore | None = None,
) -> FastAPI:
    """email_sender defaults to the MCP Email capability,
    upstream_transport to real HTTP, agent_gateway to a real MCP client for
    ai_agent, server_tools to one for mcp_server and db_gateway to one for the
    db_gateway service; tests pass fakes. traffic
    defaults to a recorder saving to the database; tests pass their own."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        database = Database(settings.database_url)
        # A backup first: SQLite cannot roll a half-finished migration back.
        pre_migration = DatabaseBackup(settings.database_path, settings.backup_dir, settings.backup.keep)
        await MigrationRunner(database.engine, before_upgrade=pre_migration.run).run()
        async with database.sessions() as session:
            auth_service = AuthService(session)
            generated = await auth_service.ensure_bootstrap_admin(settings.env_path)
            await auth_service.ensure_default_role(settings.default_role)
            await SessionService(session, settings.session_hours).purge_expired()
            await OtpService(session).purge_stale()
            await auth_service.purge_login_attempts()
            await purge_expired_shares(session)
        log_writer = LogWriter(database)
        await log_writer.purge_old()
        recorder = traffic or TrafficRecorder(database)
        await recorder.purge_old()
        if generated:
            # Printed once, like chat_app; never logged to a file.
            print(f"Bootstrap admin created with password: {generated} (save it now, it won't be shown again)")

        internal_token = load_env_secrets(settings.env_path).get("INTERNAL_API_TOKEN")
        # Raises SecretBoxError (a clear one-line message) when .env holds a key that is not valid.
        secret_box = SecretBox(ensure_secrets_key(settings.env_path))
        upstream = httpx.AsyncClient(transport=upstream_transport, timeout=_UPSTREAM_TIMEOUT)

        gateway_client = httpx.AsyncClient(base_url=settings.db_gateway.url, timeout=_DB_GATEWAY_TIMEOUT)
        app.state.db_gateway = db_gateway or DbGatewayClient(
            gateway_client, settings.db_gateway.instance, settings.db_gateway.connection, internal_token or None
        )

        app.state.settings = settings
        app.state.database = database
        app.state.email_sender = email_sender or McpEmailSender(settings.mcp_server_url, internal_token or None, recorder)
        app.state.upstream = upstream
        app.state.internal_token = internal_token or None
        app.state.secret_box = secret_box
        app.state.agent_directory = AgentDirectory(
            HttpRegistrySource(settings.agents_registry_url, upstream, internal_token or None)
            if settings.agents_registry_url
            else settings.agents_registry_path
        )
        app.state.mcp_proxy = McpProxy(upstream, internal_token or None, recorder)
        app.state.memory_purger = MemoryPurger(upstream, settings.mcp_server_url, internal_token or None)
        app.state.memory = MemoryClient(upstream, settings.mcp_server_url, internal_token or None)
        app.state.skills = SkillsClient(upstream, settings.mcp_server_url, internal_token or None)
        app.state.agent_gateway = agent_gateway or McpAgentGateway(internal_token or None, recorder)
        app.state.extension_probe = ExtensionProbe(app.state.agent_gateway)
        app.state.server_tools = server_tools or McpServerTools(settings.mcp_server_url, internal_token or None, recorder)
        app.state.logs = log_writer
        app.state.traffic = recorder
        recorder.start()
        app.state.share_limiter = PublicReadLimiter()
        from src.services.pricing import Pricing

        app.state.pricing = Pricing(settings.pricing)
        app.state.turns = TurnRegistry(database, app.state.agent_gateway, settings.usage, log_writer,
            pricing=app.state.pricing, directory=app.state.agent_directory)
        app.state.calendar = (
            build_calendar_runtime(
                settings=settings, database=database, store=app.state.db_gateway, box=secret_box,
                email_sender=app.state.email_sender, log_writer=log_writer,
            )
            if settings.calendar.enabled
            else None
        )
        backups: BackupScheduler | None = None
        app.state.backups = None
        if settings.backup.enabled:
            backups = BackupScheduler(
                DatabaseBackup(settings.database_path, settings.backup_dir, settings.backup.keep),
                timedelta(hours=settings.backup.every_hours),
                on_error=lambda message: log_writer.error(None, "backup", message),
            )
            backups.start()
            app.state.backups = backups
        try:
            yield
        finally:
            if app.state.calendar is not None:
                await app.state.calendar.close()
            if backups is not None:
                await backups.stop()
            # Before the database closes: running turns save what they have.
            await app.state.turns.shutdown()
            # Saves the counters (turns just ended may have added some).
            await recorder.stop()
            await upstream.aclose()
            await gateway_client.aclose()
            await database.dispose()

    app = FastAPI(title="ember_api", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(JsonOnlyMiddleware)
    # Largest legitimate body: a chat-history import of several 2 MB chats.
    app.add_middleware(
        BodyLimitMiddleware,
        max_bytes=DEFAULT_REQUEST_BYTES,
        path_limits={prefix: MAX_REQUEST_BYTES for prefix in LARGE_BODY_PREFIXES},
    )
    # Added last, so it runs first: blocked IPs never reach JSON checks or
    # routes, and even those rejections carry the security headers.
    app.add_middleware(SecurityMiddleware, settings=settings.security)
    # Outermost, so blocked and rejected requests are counted too.
    app.add_middleware(TrafficMiddleware)
    app.include_router(auth.router)
    app.include_router(account.router)
    app.include_router(admin.router)
    app.include_router(agent_admin.router)
    app.include_router(agent_admin.prompts_router)
    app.include_router(chats.router)
    app.include_router(chat_folders.router)
    app.include_router(templates.router)
    app.include_router(nav_preferences.router)
    app.include_router(notes.router)
    app.include_router(brains.router)
    app.include_router(memory.router)
    app.include_router(skills.router)
    app.include_router(triage.router)
    app.include_router(account_agents.router)
    app.include_router(user_extensions.router)
    app.include_router(shares.router)
    app.include_router(shares.public_router)
    app.include_router(usage.router)
    app.include_router(settings_routes.router)
    app.include_router(mcp.router)
    app.include_router(server_info.router)
    app.include_router(logs.router)
    app.include_router(traffic_routes.router)
    app.include_router(attachments.router)
    app.include_router(bard.router)
    app.include_router(capability_files.router)
    app.include_router(calendar_routes.router)

    @app.exception_handler(CalendarError)
    async def calendar_error(_request: Request, error: CalendarError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(CapabilityFailure)
    async def capability_failure(_request: Request, error: CapabilityFailure):
        return JSONResponse(status_code=error.status, content={
            "detail": str(error), "error": {"code": error.code, "message": str(error)},
        })
    app.include_router(config_issues.router)
    app.include_router(tickets_routes.router)
    app.include_router(tickets_routes.admin_router)

    @app.exception_handler(BrainError)
    async def brain_error(_request: Request, error: BrainError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        if request.url.path.startswith("/api/brains"):
            return JSONResponse({"detail": "Invalid brain request. Check the fields and limits."}, status_code=422)
        return await request_validation_exception_handler(request, error)

    @app.exception_handler(DbGatewayError)
    async def storage_unavailable(request: Request, error: DbGatewayError) -> JSONResponse:
        """A route that keeps its data in db_gateway and did not handle the outage itself."""
        return JSONResponse({"detail": "Storage is unavailable"}, status_code=503)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        """Any unhandled exception: logged for the Logs page's Errors tab
        (under the account, when the request had one) and answered with a
        generic 500 - the details stay server-side."""
        logs_writer: LogWriter | None = getattr(request.app.state, "logs", None)
        if logs_writer is not None:
            await logs_writer.error(
                getattr(request.state, "account_id", None),
                f"http {request.method} {request.url.path}",
                f"{type(error).__name__}: {error}",
                "".join(traceback.format_exception(error)),
            )
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
