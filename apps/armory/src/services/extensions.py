"""Connect OUT to other MCP servers as a client and re-expose their tools as namespaced tools of our own.
Lives here (a long-lived process) rather than chat_app. FastMCP can't register runtime-schema tools, so it re-registers the low-level ``list_tools``/``call_tool`` handlers through ``_mcp_server`` (verified on mcp==1.28.0); concurrent ``call_tool()`` on one session is safe as built, so no per-extension lock."""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP

from src.services.app_config import (
    ExtensionConfig,
    delete_extension_config,
    load_extensions_config,
    save_extension_config,
)
from src.services.identity_context import REQUESTER_META_KEY, current_email, current_username

logger = logging.getLogger(__name__)

# "__" rather than "_": single underscores are ordinary word separators in tool names elsewhere,
# so only a double underscore can mark the namespace boundary unambiguously.
NAMESPACE_SEPARATOR = "__"

# Max time to connect one extension (spawn + initialize + list_tools) before it is recorded as failed,
# so a hung upstream can't stall startup. Also the session's default read timeout, which ExtensionRegistry.call() overrides per call.
CONNECT_TIMEOUT_SECONDS = 10.0

# Max time for one proxied tool call; separate from CONNECT_TIMEOUT_SECONDS because
# real upstream work routinely exceeds a connect handshake's budget.
CALL_TIMEOUT_SECONDS = 120.0


async def _check_tcp_reachable(url: str) -> None:
    """Raise a plain exception if `url`'s host:port won't accept a TCP connection, without calling streamablehttp_client.
    A real connect failure inside it crashes the whole server (see ExtensionRegistry._open_and_list); a raw asyncio connect makes no anyio task group and closes the probe socket at once."""
    parsed = urlsplit(url)
    if parsed.hostname is None:
        raise ValueError(f"Extension URL has no host: {url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    _reader, writer = await asyncio.wait_for(
        asyncio.open_connection(parsed.hostname, port), timeout=CONNECT_TIMEOUT_SECONDS
    )
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:  # noqa: BLE001 - this was only ever a reachability probe
        pass


async def _check_handshake_accepted(url: str, headers: dict[str, str] | None) -> None:
    """Raise a plain exception if `url` answers an MCP ``initialize`` POST with an HTTP error status (401, 403, 404, 5xx).
    Companion to _check_tcp_reachable: a rejected handshake inside streamablehttp_client hits the cancel-scope bug, while plain httpx fails normally. Only the status is read, never headers."""
    request_headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": types.LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp_server-preflight", "version": "0"},
        },
    }
    async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT_SECONDS) as client:
        async with client.stream("POST", url, json=payload, headers=request_headers) as response:
            if response.status_code >= 400:
                hint = " (check the extension's token/headers)" if response.status_code in (401, 403) else ""
                raise ConnectionError(f"Extension at {url} rejected the MCP handshake: HTTP {response.status_code}{hint}")


@dataclass
class ExtensionStatus:
    """What GET /extensions and the startup banner report for one configured extension.
    Field names and `status` values ("connected" | "error") match extension_routes.py; do not change them."""

    id: str
    label: str
    description: str
    status: str
    error: str | None = None
    tools: list[str] = field(default_factory=list)
    # The extension's own web app, shown as a link by ember; reported even
    # when the MCP connection failed, since the app can work without it.
    web_url: str | None = None


@dataclass
class _ProxiedTool:
    """One upstream tool, registered here under its namespaced name."""

    extension_id: str
    upstream_name: str
    definition: types.Tool  # already carries the *namespaced* name


def _requester_meta() -> dict[str, Any] | None:
    """The asking user in the ``_meta.requester`` shape ai_agent sends (see identity_context.py), so upstreams can tell users apart.
    None when the caller sent no identity."""
    username, email = current_username(), current_email()
    if not (username or email):
        return None
    return {REQUESTER_META_KEY: {"username": username, "email": email}}


class ExtensionRegistry:
    """Owns every live upstream connection for the life of the process.
    A class, not module globals, so tests can spin it up and tear it down; the real server has one instance, held by ``install_extensions``."""

    def __init__(self) -> None:
        # One AsyncExitStack per extension: a shared one can only close everything in LIFO order,
        # but `remove()` must close exactly one extension's connection.
        self._extension_stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}  # extension id -> session
        self._forward_requester: set[str] = set()  # ids whose config opted in to requester forwarding
        self._proxied: dict[str, _ProxiedTool] = {}  # namespaced name -> tool
        self._statuses: list[ExtensionStatus] = []
        self._mcp: FastMCP | None = None
        # Guards add()/remove() (and the module-level wrappers, which hold it across the registry mutation and config.json write)
        # against concurrent HTTP requests; connect_all() doesn't need it at startup.
        self._mutation_lock = asyncio.Lock()

    def statuses(self) -> list[ExtensionStatus]:
        """One entry per configured extension, connected or not, in config order."""
        return list(self._statuses)

    def proxied_tool_definitions(self) -> list[types.Tool]:
        return [proxied.definition for proxied in self._proxied.values()]

    def is_proxied(self, name: str) -> bool:
        return name in self._proxied

    async def connect_all(self, config_path: Path) -> None:
        """Connect to every extension in config.json's "extensions" section.
        Each is isolated (see _connect_one): a failure is recorded as its status, never raised, so siblings and our own tools still start."""
        for extension_id, extension_config in load_extensions_config(config_path).items():
            await self._connect_one(extension_id, extension_config)

    async def _connect_one(self, extension_id: str, config: ExtensionConfig) -> ExtensionStatus:
        """Connect one extension, append its ExtensionStatus and return it.
        Never raises (failures are recorded as status); not locked, since connect_all() runs it in a plain loop and add() locks around it."""
        # A local stack until the connection is known to work: registering half-open resources
        # would keep a broken extension's subprocess alive for the server's whole run.
        local_stack = AsyncExitStack()
        try:
            # No external timeout wrapper (asyncio.wait_for or anyio.fail_after): both corrupted anyio's cancel-scope tree
            # (see _open_and_list). CONNECT_TIMEOUT_SECONDS goes into ClientSession, whose own request timeout is correctly scoped.
            session, listed = await self._open_and_list(local_stack, config)
        except Exception as error:  # noqa: BLE001 - one bad extension must not block the others
            try:
                await local_stack.aclose()
            except Exception:  # noqa: BLE001 - a messy close must not escape a failed connect
                pass
            status = ExtensionStatus(
                id=extension_id,
                label=config.label,
                description=config.description,
                status="error",
                error=str(error) or type(error).__name__,
                web_url=config.web_url,
            )
            self._statuses.append(status)
            return status

        # Success: hand the local stack's resources to this extension's long-lived stack,
        # so they close at shutdown or removal, not when this function returns.
        opened = local_stack.pop_all()
        self._extension_stacks[extension_id] = opened

        tool_names: list[str] = []
        for tool in listed.tools:
            namespaced = f"{extension_id}{NAMESPACE_SEPARATOR}{tool.name}"
            self._proxied[namespaced] = _ProxiedTool(
                extension_id=extension_id,
                upstream_name=tool.name,
                definition=types.Tool(
                    name=namespaced,
                    description=tool.description,
                    inputSchema=tool.inputSchema,
                    outputSchema=tool.outputSchema,
                    # mcp.types.Tool aliases "meta" to "_meta" without populate_by_name, and extra="allow" would make
                    # a `meta=` keyword a stray attribute (verified on mcp==1.28.0). Do not "normalize" this back.
                    _meta=tool.meta,
                    annotations=tool.annotations,
                    icons=tool.icons,
                ),
            )
            tool_names.append(namespaced)

        self._sessions[extension_id] = session
        if config.forward_requester:
            self._forward_requester.add(extension_id)
        status = ExtensionStatus(
            id=extension_id,
            label=config.label,
            description=config.description,
            status="connected",
            error=None,
            tools=tool_names,
            web_url=config.web_url,
        )
        self._statuses.append(status)
        return status

    async def _remove_one(self, extension_id: str) -> bool:
        """The unlocked core of remove(); split out like _connect_one so add_extension()/remove_extension()
        can hold the lock across the registry mutation and config.json write without deadlocking."""
        if extension_id not in {status.id for status in self._statuses}:
            return False

        stack = self._extension_stacks.pop(extension_id, None)
        if stack is not None:
            # Only present for an extension that connected; an "error" one has just a status entry,
            # which the filter below removes.
            try:
                await stack.aclose()
            except Exception:  # noqa: BLE001 - a messy close must not stop removal
                pass

        self._sessions.pop(extension_id, None)
        self._forward_requester.discard(extension_id)
        for name in [n for n, proxied in self._proxied.items() if proxied.extension_id == extension_id]:
            del self._proxied[name]
        self._statuses = [status for status in self._statuses if status.id != extension_id]
        return True

    async def add(self, extension_id: str, config: ExtensionConfig) -> ExtensionStatus:
        """Connect a new extension at runtime, like connect_all() at startup; a connect error is recorded as an "error" status, not raised.
        Locked against concurrent add()/remove()."""
        async with self._mutation_lock:
            return await self._connect_one(extension_id, config)

    async def remove(self, extension_id: str) -> bool:
        """Disconnect a runtime extension: close its connection (an "error" status had none) and drop it from the registry.
        False for an unknown id; locked like add()."""
        async with self._mutation_lock:
            return await self._remove_one(extension_id)

    @staticmethod
    async def _open_and_list(
        local_stack: AsyncExitStack, config: ExtensionConfig
    ) -> tuple[ClientSession, types.ListToolsResult]:
        """Open the upstream connection (stdio subprocess or http URL), complete the MCP handshake and list what it offers.
        No caller-side timeout wrapper (asyncio.wait_for or anyio.fail_after): both corrupt anyio's cancel-scope tree, since the task group must outlive this function. Real connect failures inside streamablehttp_client do the same, so _check_tcp_reachable probes first and CONNECT_TIMEOUT_SECONDS bounds the handshake via read_timeout_seconds."""
        if config.transport == "http":
            assert config.url is not None  # guaranteed by _build_extension/the POST route
            await _check_tcp_reachable(config.url)
            await _check_handshake_accepted(config.url, config.headers)
            read_stream, write_stream, _get_session_id = await local_stack.enter_async_context(
                streamablehttp_client(config.url, headers=config.headers or None)
            )
        else:
            params = StdioServerParameters(command=config.command, args=config.args)
            read_stream, write_stream = await local_stack.enter_async_context(stdio_client(params))
        session = await local_stack.enter_async_context(
            ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=CONNECT_TIMEOUT_SECONDS))
        )
        await session.initialize()
        listed = await session.list_tools()
        return session, listed

    async def call(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Forward a call to whichever upstream session owns `name`; callers must check ``is_proxied(name)`` first, otherwise this raises.
        With ``forward_requester``, the caller's identity goes upstream as ``_meta.requester``, trusted only as far as this server is (hence the internal token in ``headers``)."""
        proxied = self._proxied.get(name)
        if proxied is None:
            raise KeyError(f"No proxied tool named {name!r}")
        session = self._sessions[proxied.extension_id]
        return await session.call_tool(
            proxied.upstream_name,
            arguments,
            read_timeout_seconds=timedelta(seconds=CALL_TIMEOUT_SECONDS),
            meta=_requester_meta() if proxied.extension_id in self._forward_requester else None,
        )

    async def merged_list_tools(self) -> list[types.Tool]:
        """FastMCP's own tools plus every connected extension's; registered as the ListToolsRequest handler by install().
        Tools with meta={"hidden": True} are dropped from the listing but stay callable by name."""
        assert self._mcp is not None, "install() must run before merged_list_tools()"
        own_tools = await self._mcp.list_tools()
        visible_own_tools = [t for t in own_tools if not (t.meta or {}).get("hidden")]
        return [*visible_own_tools, *self.proxied_tool_definitions()]

    async def merged_call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Route by namespace prefix: a proxied name goes upstream, anything else through FastMCP's normal dispatch.
        Returns `Any`: the upstream CallToolResult verbatim, or FastMCP's looser shape, which the low-level decorator normalizes."""
        assert self._mcp is not None, "install() must run before merged_call_tool()"
        # Who asked, when the caller said (identity headers, or ai_agent's
        # per-call _meta - see identity_context.py); "-" otherwise.
        logger.info("tool call %s by %s", name, current_username() or current_email() or "-")
        if self.is_proxied(name):
            return await self.call(name, arguments)
        return await self._mcp.call_tool(name, arguments)

    def install(self, mcp: FastMCP) -> None:
        """Wire this registry's tools into `mcp`'s list_tools/call_tool by re-registering the handlers (see module docstring).
        validate_input=False is kept from FastMCP's own registration, which coerces input before validating."""
        self._mcp = mcp
        mcp._mcp_server.list_tools()(self.merged_list_tools)
        mcp._mcp_server.call_tool(validate_input=False)(self.merged_call_tool)

    async def aclose(self) -> None:
        """Close every open upstream connection, in no particular order; one failing to close must not stop the others."""
        for stack in self._extension_stacks.values():
            try:
                await stack.aclose()
            except Exception:  # noqa: BLE001 - a messy shutdown must not block the rest
                pass
        self._extension_stacks.clear()


_registry: ExtensionRegistry | None = None


async def install_extensions(mcp: FastMCP, config_path: Path) -> list[ExtensionStatus]:
    """Connect every configured extension and merge their tools into `mcp`; called once at startup, before the tool-count banner (see run.py).
    Always installs the merged handlers, even with zero extensions, so there is one code path."""
    global _registry
    registry = ExtensionRegistry()
    await registry.connect_all(config_path)
    registry.install(mcp)
    _registry = registry
    return registry.statuses()


async def merged_list_tools() -> list[types.Tool]:
    """The full tool list an MCP client would see now: our tools plus every connected extension's.
    Empty before install_extensions() has run, like current_statuses()."""
    if _registry is None:
        return []
    return await _registry.merged_list_tools()


def current_statuses() -> list[ExtensionStatus]:
    """Read by extension_routes.py's GET /extensions.
    Empty before install_extensions() has run, meaning "nothing to report", not an error."""
    if _registry is None:
        return []
    return _registry.statuses()


async def shutdown_extensions() -> None:
    """Close every open upstream connection; the mirror of install_extensions().
    run.py calls it from a `finally` so no subprocess outlives the server."""
    global _registry
    if _registry is not None:
        await _registry.aclose()
        _registry = None


async def add_extension(config: ExtensionConfig, config_path: Path) -> ExtensionStatus | None:
    """Connect a new extension at runtime and persist it to config.json, as one operation (extension_routes.py's POST). None before install_extensions() has run.
    Persists first, since `_connect_one` never raises while `save_extension_config` can; the lock spans both write and mutation, so it goes straight to the unlocked `_connect_one` (the lock is not reentrant)."""
    if _registry is None:
        return None
    async with _registry._mutation_lock:
        save_extension_config(config_path, config)
        status = await _registry._connect_one(config.id, config)
    return status


async def remove_extension(extension_id: str, config_path: Path) -> bool:
    """Disconnect a runtime extension and remove it from config.json, as one operation (extension_routes.py's DELETE). False for an unknown id.
    Deletes config first so a write failure leaves the live registry untouched; `_remove_one` decides whether the id is known. See add_extension for the locking."""
    if _registry is None:
        return False
    async with _registry._mutation_lock:
        delete_extension_config(config_path, extension_id)
        removed = await _registry._remove_one(extension_id)
    return removed
