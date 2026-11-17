"""Armory auth wiring and per-tool requester verification on shared MCP sessions."""

from contextlib import asynccontextmanager

from src.citadel_auth import ServiceAuthMiddleware, from_env, requester_context

keyring = from_env("armory")


def install_auth(app, identity=None):
    """Install once even when multiple capability route installers share an app."""
    if not getattr(app.state, "citadel_auth_installed", False):
        app.add_middleware(ServiceAuthMiddleware, keyring=identity or keyring, audience="armory")
        app.state.citadel_auth_installed = True


@asynccontextmanager
async def mcp_requester(identity=None):
    from mcp.server.lowlevel.server import request_ctx
    try:
        context = request_ctx.get()
    except LookupError:
        context = None
    request = getattr(context, "request", None)
    caller, _, header_token = getattr(request, "scope", {}).get("citadel_auth", (None, None, ""))
    meta = getattr(context, "meta", None)
    extras = (meta.model_extra or {}) if meta is not None else {}
    token = extras.get("requester_token", header_token)
    async with requester_context(identity or keyring, caller, token, "armory") as requester:
        yield requester
