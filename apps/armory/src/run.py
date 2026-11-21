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
from src.citadel_auth import advertised_url
from src.service_catalog import catalog
from src.citadel_auth.treasury import register_in_background  # noqa: E402
from src.services.service_auth import install_auth, keyring  # noqa: E402
from src.utils.logging_setup import configure_logging  # noqa: E402
from src.server import mcp  # noqa: E402

# Before anything else, so uvicorn's own logging is captured on disk from the start.
configure_logging(settings.log_dir)

# Capabilities are found by scanning src/capabilities/ (services/capability_loader.py), not imported here,
# so a new folder appears on POST /capabilities/refresh. One with a config entry loads now; one without stays offline until an admin enables it.
capability_loader = CapabilityLoader(mcp, "src.capabilities", settings.settings_db_path)
capability_loader.startup()


async def _serve() -> None:
    """Everything from "connect to extensions" to "serve forever" runs in this one coroutine under a single asyncio.run().
    Extension connections are bound to the loop they were opened in; separate loops break proxied calls ("Attempted to exit cancel scope in a different task")."""
    import asyncio
    import logging
    import sqlite3
    import httpx
    import uvicorn

    from src.services import extensions

    await keyring.ensure_identity()
    catalog.start("armory", advertised_url(settings.host, settings.port, settings.advertise_url))
    # Treasury keeps no list of its callers: Armory tells it which connection its instance uses.
    registration = register_in_background(
        keyring, settings.treasury_url, settings.db_gateway_instance, [settings.db_gateway_connection])

    try:
        # Before tool_names on purpose: extensions register proxied tools onto `mcp`,
        # so connecting first puts them in the merged list and the counts below.
        extension_statuses = await extensions.install_extensions(mcp, settings.settings_db_path)

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

        from src.capabilities.obsidian import brain_admin
        from src.capabilities.obsidian.utils import brain_resolver
        from src.capabilities.obsidian.utils.instance_brain import InstanceBrainStore, load_box
        from src.capabilities.obsidian.utils.instance_migration import migrate
        from src.capability_routes import install_capability_routes
        from src.command_routes import install_command_routes
        from src.connection_admin import install_connection_admin
        from src.connection_routes import install_connection_routes
        from src.download_routes import install_download_routes
        from src.environment_routes import install_environment_routes
        from src.extension_routes import install_extension_routes
        from src.help_routes import install_help_routes
        from src.upload_routes import install_upload_routes
        from src.services.connections import ConnectionStore
        from src.services.dictation import STREAM_FRAME_BYTES

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
            f"  Extensions: {', '.join(f'{s.id} ({s.status})' for s in extension_statuses) or 'none'}",
        ]
        banner.append("  /mcp auth : signed Ed25519 service assertion required")

        # flush=True matters: stdout is block-buffered when not a terminal (Docker, systemd, files),
        # so the banner and the no-authentication warning would lag uvicorn's stderr logs.
        print("\n".join(banner), flush=True)

        # Capabilities resume their background work (e.g. server_manager's app watchers).
        capability_loader.run_startup_hooks()

        app = mcp.streamable_http_app()
        install_auth(app)
        # Where a human or chat_app's sidebar checks what's connected; a plain route, not a tool. See extension_routes.py.
        install_extension_routes(app)
        # Where chat_app discovers which built-in tools are invocable as "/" commands; a plain route. See command_routes.py.
        install_command_routes(app)
        # Where chat_app answers "/<capability> help ..."; a plain route returning structured data. See help_routes.py.
        install_help_routes(app)
        # Where chat_app's Capabilities page toggles built-in capabilities live, rescans src/capabilities/ and reloads code on going online.
        # A plain route: a model must not change what it can do. See capability_routes.py.
        install_capability_routes(app, capability_loader)
        # Where Armory Admin edits the deployment values (addresses, link keys, Obsidian, folders); saved in settings.db. See environment_routes.py.
        install_environment_routes(app)
        # Where chat_app proxies a file dropped into a command-form modal; a plain route checked against
        # service assertions. See upload_routes.py.
        install_upload_routes(app)
        # Where a caller fetches a file a tool offered it (via portcullis); a plain route checked against
        # service assertions and signed requester identity. See download_routes.py.
        install_download_routes(app)
        # Each capability mounts its own always-on routes (obsidian), even when its tools are off.
        capability_loader.install_routes(app)

        # uvicorn.Server(...).serve(), not uvicorn.run(): run() calls asyncio.run() and would
        # nest a second event loop inside this one.
        try:
            box = await asyncio.to_thread(load_box, keyring.identity_dir, settings.settings_db_path)
        except (OSError, ValueError, sqlite3.Error):
            logging.getLogger(__name__).error("Instance Brain encryption is unavailable. Check the Armory identity backup.")
            box = None
        instance_brain = InstanceBrainStore(settings.settings_db_path, box)
        brain_resolver.instance_store = instance_brain
        brain_admin.install(app, instance_brain)

        async with httpx.AsyncClient(trust_env=False) as client:
            connections = ConnectionStore(settings.settings_db_path)
            install_connection_routes(app, connections, client)
            install_connection_admin(app, connections, client)
            server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port,
                                                   ws_max_size=STREAM_FRAME_BYTES, ws_max_queue=4))
            migration = asyncio.create_task(migrate(instance_brain, keyring, catalog)) if box is not None else None
            try:
                await server.serve()
            finally:
                if migration is not None:
                    migration.cancel()
                    await asyncio.gather(migration, return_exceptions=True)
    finally:
        await catalog.stop()
        registration.cancel()
        # Mirrors install_extensions() at the top: subprocesses opened get closed on shutdown or startup failure.
        await extensions.shutdown_extensions()


def main() -> None:
    import asyncio

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
