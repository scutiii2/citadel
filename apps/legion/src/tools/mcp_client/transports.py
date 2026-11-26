"""Open a live, authenticated MCP session for one configured server.

Two responsibilities live here: resolving `ServerConfig.auth` into
whatever the wire actually needs (an HTTP header today), and opening the
transport itself (stdio subprocess or streamable HTTP) the same way
mcp_server/src/infra/extensions.py does, including the TCP-reachability
pre-check that module's docstring explains at length: a real HTTP connect
failure reaching streamable_http_client directly corrupts anyio's
cancel-scope tree for the caller's task, so an unreachable host must
never be allowed to reach it in the first place.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from urllib.parse import urlsplit

import httpx2
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from src.tools.mcp_client.config import ServerConfig
from src.citadel_auth import resolved

# Citadel's own servers stay on the handshake-era protocol; every other connection is probed.
_INTERNAL_IDS = frozenset({"main", "stronghold"})


class AuthResolutionError(RuntimeError):
    """Raised when a server's auth block names something not actually
    available at connect time - e.g. an unset environment variable."""


def resolve_headers(config: ServerConfig) -> dict[str, str]:
    """The extra HTTP headers `config`'s auth block requires, or {} for
    no auth. Only meaningful for transport 'http' - open_session never
    calls this for 'stdio'."""
    auth = config.auth
    if auth is None or auth.type == "none":
        return {}
    if auth.type == "header":
        return {auth.header_name: auth.header_value}  # type: ignore[dict-item]
    if auth.type == "bearer_env":
        value = os.environ.get(auth.env_var or "")
        if not value:
            raise AuthResolutionError(f"{config.id!r}: environment variable {auth.env_var!r} is not set")
        return {"Authorization": f"Bearer {value}"}
    raise AuthResolutionError(f"{config.id!r}: unknown auth type {auth.type!r}")


async def _check_tcp_reachable(url: str, timeout_seconds: float) -> None:
    """Raise a plain exception if `url`'s host:port won't accept a TCP
    connection - without ever calling streamable_http_client. Plain
    asyncio, not anyio: this opens no anyio task group, so it can't
    corrupt one - it only answers "is anyone listening"; the real
    connection is opened separately right after this returns."""
    parsed = urlsplit(url)
    if parsed.hostname is None:
        raise ValueError(f"Server URL has no host: {url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    _reader, writer = await asyncio.wait_for(asyncio.open_connection(parsed.hostname, port), timeout=timeout_seconds)
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:  # noqa: BLE001 - this was only ever a reachability probe
        pass


def _origin_client(url: str, **options) -> httpx2.AsyncClient:
    """Reject any request that would carry credentials beyond the catalog origin."""
    origin = httpx2.URL(url)
    expected = (origin.scheme, origin.host, origin.port)

    async def check_origin(request: httpx2.Request) -> None:
        target = request.url
        if (target.scheme, target.host, target.port) != expected:
            raise AuthResolutionError("MCP request left its configured origin")

    client = create_mcp_http_client(**options)
    client.event_hooks["request"].append(check_origin)
    return client


async def _open(stack: AsyncExitStack, open_streams, timeout_seconds: float) -> ClientSession:
    read_stream, write_stream = await stack.enter_async_context(open_streams())
    return await stack.enter_async_context(
        ClientSession(read_stream, write_stream, read_timeout_seconds=timeout_seconds)
    )


async def open_negotiated(
    stack: AsyncExitStack, open_streams, timeout_seconds: float, *, probe: bool
) -> ClientSession:
    """A ready session registered on `stack`. With `probe`, protocol 2026-07-28 when the
    server speaks it; otherwise, and for an older server, a fresh handshake-era session."""
    if probe:
        attempt = AsyncExitStack()
        try:
            session = await _open(attempt, open_streams, timeout_seconds)
            try:
                await session.discover()
            except (MCPError, ValidationError, RuntimeError):
                # Not a 2026 server. A real connection problem shows again in initialize().
                session = None
        except BaseException:
            await attempt.aclose()
            raise
        if session is not None:
            stack.push_async_exit(attempt.pop_all())
            return session
        await attempt.aclose()
    session = await _open(stack, open_streams, timeout_seconds)
    await session.initialize()
    return session


async def open_session(
    stack: AsyncExitStack,
    config: ServerConfig,
    timeout_seconds: float,
    extra_headers: dict[str, str] | None = None,
    auth=None,
) -> ClientSession:
    """Open a ready session for `config`, registering every
    resource it opens on `stack` so the caller controls their lifetime.
    Does not call list_tools() - that's the caller's job (registry.py).
    `extra_headers` (HTTP only) are added to the auth block's."""
    if config.transport == "http":
        assert config.url is not None  # guaranteed by config.load_servers_config
        url = resolved(config.url)
        try:
            await _check_tcp_reachable(url, timeout_seconds)
        except OSError as error:
            if not config.origins or isinstance(error, (ConnectionError, TimeoutError)):
                raise
            raise ConnectionError("Could not reach the MCP origin") from error
        headers = {**resolve_headers(config), **(extra_headers or {})}
        guarded = bool(config.origins) or (config.id == "stronghold" and auth is not None)

        @asynccontextmanager
        async def open_streams():
            build = partial(_origin_client, url) if guarded else create_mcp_http_client
            async with build(headers=headers or None, auth=auth) as http:
                async with streamable_http_client(url, http_client=http) as streams:
                    yield streams
    else:
        params = StdioServerParameters(command=config.command, args=config.args or [])
        open_streams = partial(stdio_client, params)

    return await open_negotiated(stack, open_streams, timeout_seconds, probe=config.id not in _INTERNAL_IDS)
