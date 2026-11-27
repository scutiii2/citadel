"""Entry point for the MCP server. Run with: python -m src.run"""

from __future__ import annotations

# Must run before any src.* import: Settings' defaults read os.getenv() at import time.
# A missing .env is built from the legacy .secrets/*.env files, else .env.example.
from src.utils.env_file import load_env_file

load_env_file()

from src.capabilities.email.health_tool import register_health_tool  # noqa: E402
from src.config import settings  # noqa: E402
from src.services import capability_registry  # noqa: E402
from src.services.capability_loader import CapabilityLoader  # noqa: E402
from src.services.identity_context import IdentityContextMiddleware  # noqa: E402
from src.citadel_auth import advertised_url
from src.service_catalog import catalog
from src.citadel_auth.treasury import register_in_background  # noqa: E402
from src.services.service_auth import install_auth, keyring  # noqa: E402
from src.services.tool_handlers import install_tool_handlers  # noqa: E402
from src.utils.logging_setup import configure_logging  # noqa: E402
from src.server import mcp  # noqa: E402

# Before anything else, so uvicorn's own logging is captured on disk from the start.
configure_logging(settings.log_dir)

# Capabilities are found by scanning src/capabilities/ (services/capability_loader.py), not imported here,
# so a new folder appears on POST /capabilities/refresh. One with a config entry loads now; one without stays offline until an admin enables it.
capability_loader = CapabilityLoader(mcp, "src.capabilities", settings.settings_db_path)
capability_loader.startup()
register_health_tool(mcp)


async def _serve() -> None:
    """Everything from registering to "serve forever" runs in this one coroutine under a single asyncio.run()."""
    import asyncio
    import uvicorn

    await keyring.ensure_identity()
    catalog.start("armory", advertised_url(settings.host, settings.port, settings.advertise_url))
    # Treasury keeps no list of its callers: Armory tells it which connection its instance uses.
    registration = register_in_background(
        keyring, settings.treasury_url, settings.db_gateway_instance, [settings.db_gateway_connection])

    install_tool_handlers(mcp)
    try:
        tool_names = sorted(t.name for t in await mcp.list_tools())

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
        from src.environment_routes import install_environment_routes
        from src.file_routes import install_file_routes
        from src.help_routes import install_help_routes
        from src.upload_routes import install_upload_routes

        enabled_capabilities = [
            name for name in capability_registry.names() if capability_registry.is_enabled(name)
        ]
        banner = [
            "MCP server",
            f"  Endpoint : http://{settings.host}:{settings.port}/mcp",
            f"  Settings : {settings.settings_db_path}",
            f"  Capabilities: {', '.join(enabled_capabilities) or 'none'}",
            f"  Tools    : {len(tool_names)}",
            *(f"    - {name}" for name in tool_names),
            f"  Resources: {resource_count}",
        ]
        banner.append("  /mcp auth : signed Ed25519 service assertion required")

        # flush=True matters: stdout is block-buffered when not a terminal (Docker, systemd, files),
        # so the banner and the no-authentication warning would lag uvicorn's stderr logs.
        print("\n".join(banner), flush=True)

        # Capabilities resume their background work (e.g. server_manager's app watchers).
        capability_loader.run_startup_hooks()

        app = mcp.streamable_http_app()
        install_auth(app)
        # Where chat_app discovers which built-in tools are invocable as "/" commands; a plain route. See command_routes.py.
        install_command_routes(app)
        # Where chat_app answers "/<capability> help ..."; a plain route returning structured data. See help_routes.py.
        install_help_routes(app)
        # Where chat_app's Capabilities page toggles built-in capabilities live, rescans src/capabilities/ and reloads code on going online.
        # A plain route: a model must not change what it can do. See capability_routes.py.
        install_capability_routes(app, capability_loader)
        # Where Armory Admin edits the deployment values (addresses, link keys, folders); saved in settings.db. See environment_routes.py.
        install_environment_routes(app)
        # Where chat_app proxies a file dropped into a command-form modal; a plain route checked against
        # service assertions. See upload_routes.py.
        install_upload_routes(app)
        # Where Portcullis previews a stored file and a signed link downloads one. See file_routes.py.
        install_file_routes(app)
        # Where a caller fetches a file a tool offered it (via portcullis); a plain route checked against
        # service assertions and signed requester identity. See download_routes.py.
        install_download_routes(app)
        # Each capability mounts its own always-on routes, even when its tools are off.
        capability_loader.install_routes(app)

        # uvicorn.Server(...).serve(), not uvicorn.run(): run() calls asyncio.run() and would
        # nest a second event loop inside this one.
        server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
        await server.serve()
    finally:
        await catalog.stop()
        registration.cancel()
        await asyncio.gather(registration, return_exceptions=True)


def main() -> None:
    import asyncio

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
