"""Entry point for the MCP server. Run with: python -m src.run"""

from __future__ import annotations

# Must run before any src.* import: Settings' defaults read os.getenv() at import time.
# A missing .env is built from the legacy .secrets/*.env files, else .env.example.
from src.utils.env_file import load_env_file

load_env_file()

from src.config import settings  # noqa: E402
from src.services import capability_registry  # noqa: E402
from src.services.capability_loader import CapabilityLoader  # noqa: E402
from src.services.identity_context import IdentityContextMiddleware  # noqa: E402
from src.services.internal_token import InternalTokenMiddleware, is_exposed_without_token  # noqa: E402
from src.utils.logging_setup import configure_logging  # noqa: E402
from src.server import mcp  # noqa: E402

# Before anything else, so uvicorn's own logging is captured on disk from the start.
configure_logging(settings.log_dir)

# Capabilities are found by scanning src/capabilities/ (services/capability_loader.py), not imported here,
# so a new folder appears on POST /capabilities/refresh. One with a config entry loads now; one without stays offline until an admin enables it.
capability_loader = CapabilityLoader(mcp, "src.capabilities", settings.capabilities_config_path)
capability_loader.startup()


async def _serve() -> None:
    """Everything from "connect to extensions" to "serve forever" runs in this one coroutine under a single asyncio.run().
    Extension connections are bound to the loop they were opened in; separate loops break proxied calls ("Attempted to exit cancel scope in a different task")."""
    import uvicorn

    from src.services import extensions

    try:
        # Before tool_names on purpose: extensions register proxied tools onto `mcp`,
        # so connecting first puts them in the merged list and the counts below.
        extension_statuses = await extensions.install_extensions(mcp, settings.extensions_config_path)

        # Use extensions.merged_list_tools(), not mcp.list_tools(): proxied tools are visible only
        # through the handlers install_extensions() installed.
        tool_names = sorted(t.name for t in await extensions.merged_list_tools())

        # Both calls are needed (verified against mcp==1.28.0): templated URIs appear only in
        # list_resource_templates() and fixed URIs only in list_resources().
        resource_count: int | str
        try:
            concrete = len(await mcp.list_resources())
            templated = len(await mcp.list_resource_templates())
            resource_count = concrete + templated
        except Exception as error:  # noqa: BLE001 - a banner line must never block startup
            resource_count = f"unknown ({error})"

        from src.capability_routes import install_capability_routes
        from src.command_routes import install_command_routes
        from src.download_routes import install_download_routes
        from src.capabilities.memory.routes import install_memory_routes
        from src.capabilities.tickets.routes import install_ticket_routes
        from src.extension_routes import install_extension_routes
        from src.help_routes import install_help_routes
        from src.upload_routes import install_upload_routes

        enabled_capabilities = [
            name for name in capability_registry.names() if capability_registry.is_enabled(name)
        ]
        banner = [
            "MCP server",
            f"  Endpoint : http://{settings.host}:{settings.port}/mcp",
            f"  Config   : {settings.configs_dir}",
            f"  Capabilities: {', '.join(enabled_capabilities) or 'none'}",
            f"  Tools    : {len(tool_names)}",
            *(f"    - {name}" for name in tool_names),
            f"  Resources: {resource_count}",
            f"  Extensions: {', '.join(f'{s.id} ({s.status})' for s in extension_statuses) or 'none'}",
        ]
        banner.append(
            "  /mcp auth : X-Internal-Token required"
            if settings.internal_api_token
            else "  /mcp auth : none (set INTERNAL_API_TOKEN in .env)"
        )
        if is_exposed_without_token(settings.host, settings.internal_api_token):
            # No authentication here, so a non-loopback bind lets anything that can reach the port call every tool.
            banner.append(f"  WARNING  : bound to {settings.host} with no authentication.")

        # flush=True matters: stdout is block-buffered when not a terminal (Docker, systemd, files),
        # so the banner and the no-authentication warning would lag uvicorn's stderr logs.
        print("\n".join(banner), flush=True)

        # Restart the app watchers that were running when the server last stopped.
        if "server" in capability_registry.names() and capability_registry.is_enabled("server"):
            from src.capabilities.server_manager.utils.server_watcher import ServerWatcher

            ServerWatcher.resume_all(settings.watchers_dir)

        app = mcp.streamable_http_app()
        # Reads chat_app's X-Requester-Username/X-Requester-Email headers into per-request contextvars
        # so identity-gated capabilities don't take identity as a tool argument (see services/identity_context.py).
        app.add_middleware(IdentityContextMiddleware)
        # Added last, so it runs first: /mcp requests without the shared internal token never reach the transport
        # (only when a token is configured). See services/internal_token.py.
        app.add_middleware(InternalTokenMiddleware, token=settings.internal_api_token)
        # Where a human or chat_app's sidebar checks what's connected; a plain route, not a tool. See extension_routes.py.
        install_extension_routes(app)
        # Where chat_app discovers which built-in tools are invocable as "/" commands; a plain route. See command_routes.py.
        install_command_routes(app)
        # Where chat_app answers "/<capability> help ..."; a plain route returning structured data. See help_routes.py.
        install_help_routes(app)
        # Where chat_app's Capabilities page toggles built-in capabilities live, rescans src/capabilities/ and reloads code on going online.
        # A plain route: a model must not change what it can do. See capability_routes.py.
        install_capability_routes(app, capability_loader)
        # Where chat_app proxies a file dropped into a command-form modal; a plain route checked against
        # the internal shared secret. See upload_routes.py.
        install_upload_routes(app)
        # Where a caller fetches a file a tool offered it (via ember_api); a plain route checked against
        # the internal token and the requester. See download_routes.py.
        install_download_routes(app)
        # Deletes an account's memory notes when ember_api deletes the account. See capabilities/memory/routes.py.
        install_memory_routes(app)
        # The user's side of learned skills: approve, retire, delete, purge. See capabilities/skills/routes.py.
        from src.capabilities.skills.routes import install_skill_routes
        install_skill_routes(app)
        from src.capabilities.obsidian.routes import install_brain_routes
        install_brain_routes(app)
        # Support tickets are always available to ember_api, even when chat tools are off.
        install_ticket_routes(app)

        # uvicorn.Server(...).serve(), not uvicorn.run(): run() calls asyncio.run() and would
        # nest a second event loop inside this one.
        server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
        await server.serve()
    finally:
        # Mirrors install_extensions() at the top: subprocesses opened get closed on shutdown or startup failure.
        await extensions.shutdown_extensions()


def main() -> None:
    import asyncio

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
