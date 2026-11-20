"""McpClientRegistry: connect to every server in the settings database,
merge their tools into one namespaced catalog, and dispatch calls to
whichever server owns a given name.

Generalizes mcp_server/src/infra/extensions.py's ExtensionRegistry: that
module treats "this server's own FastMCP tools" and "proxied tools" as
two different things, because it is itself an MCP server with tools of
its own. This registry has no tools of its own - every configured
server, including the main mcp_server, is symmetric: connect, namespace,
merge.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

import httpx
from mcp import types
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError

from src.tools.mcp_client.config import OriginRef, ServerConfig, load_servers_config
from src.tools.mcp_client.schema import inline_refs
from src.tools.mcp_client.transports import open_session

# "__" rather than "_": several servers this connects to (mcp_server's own
# tools among them) already use single underscores as ordinary word
# separators, so a single underscore here couldn't be told apart from
# part of the server id or the upstream tool's own name.
NAMESPACE_SEPARATOR = "__"

# How long connecting to one server (open transport + initialize +
# list_tools) may take before it's recorded as failed - bounded so one
# hung server can't stall connect_all() indefinitely. Also set as the
# connected ClientSession's default read_timeout_seconds, which is why
# call_tool() below must override it per-call with CALL_TIMEOUT_SECONDS
# instead of inheriting this connect-phase value.
CONNECT_TIMEOUT_SECONDS = 10.0

# How long a single tool call may run before it's treated as failed.
# Deliberately separate from CONNECT_TIMEOUT_SECONDS: a real tool call
# (e.g. a slow-backend one on the main mcp_server) routinely takes longer
# than a connect handshake should ever take, so reusing that shorter
# budget here would time out legitimate slow tools, not just hung ones.
CALL_TIMEOUT_SECONDS = 120.0

# How long an origin that failed is skipped before it is tried again.
ORIGIN_COOLDOWN_SECONDS = 30.0


def is_connection_failure(error: BaseException) -> bool:
    """A dead or silent origin justifies the next one. Any answer (a refusal, a bad request) never does."""
    if isinstance(error, BaseExceptionGroup):
        return all(is_connection_failure(child) for child in error.exceptions)
    if isinstance(error, McpError):
        return error.error.code == 408
    return isinstance(error, (ConnectionError, TimeoutError, httpx.TransportError))


@dataclass
class ServerStatus:
    """What statuses() reports for one configured server."""

    id: str
    label: str
    description: str
    status: str  # "connected" | "error"
    error: str | None = None
    tools: list[str] = field(default_factory=list)
    origin_id: str | None = None


def _namespace(server_id: str, tools: list[types.Tool]) -> list[types.Tool]:
    """Wrap `tools` (as returned by an upstream list_tools()) under their
    namespaced name for this server."""
    return [
        types.Tool(
            name=f"{server_id}{NAMESPACE_SEPARATOR}{tool.name}",
            description=tool.description,
            inputSchema=inline_refs(tool.inputSchema),
            outputSchema=tool.outputSchema,
            _meta=tool.meta,
            annotations=tool.annotations,
            icons=tool.icons,
        )
        for tool in tools
    ]


class McpClientRegistry:
    """Owns every live upstream connection for the life of the process.
    Connect once via connect_all(), then call list_tools()/call_tool()
    as needed, and aclose() on shutdown."""

    def __init__(self, resolve_origin: Callable[[str], str] | None = None) -> None:
        # One AsyncExitStack per server - see ExtensionRegistry's __init__
        # in mcp_server/src/infra/extensions.py for why this can't be one
        # shared stack (no way to close a single entry from a shared LIFO
        # stack).
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._last_known_tools: dict[str, list[types.Tool]] = {}
        self._statuses: list[ServerStatus] = []
        self._configs: dict[str, ServerConfig] = {}
        # Sent on every HTTP server's session on top of its own auth block
        # (the shared internal token - see mcp_upstream.connect()).
        self._extra_headers: dict[str, str] = {}
        self._auth_by_server = {}
        self._catalog_reconnect_lock = asyncio.Lock()
        self._builtin_tasks: dict[str, asyncio.Task[None]] = {}
        self._resolve_origin = resolve_origin
        self._active: dict[str, str] = {}
        self._down: dict[tuple[str, str], float] = {}
        self._clock = time.monotonic
        self._origin_locks: dict[str, asyncio.Lock] = {}
        self._origin_calls: dict[ClientSession, int] = {}
        self._origin_errors: dict[ClientSession, Exception] = {}
        self._retired_origins: dict[ClientSession, AsyncExitStack] = {}

    def statuses(self) -> list[ServerStatus]:
        return list(self._statuses)

    async def connect_all(
        self,
        config_path: Path,
        url_overrides: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
        auth_by_server=None,
        *,
        builtins: dict[str, dict] | None = None,
    ) -> list[ServerStatus]:
        """Connect to every server in `config_path`, isolated - one bad
        entry is recorded as an error status and never stops a sibling
        from connecting. `url_overrides` is forwarded to
        load_servers_config() - see its docstring. `extra_headers` go on
        every HTTP server's session, reconnects included."""
        self._configs = load_servers_config(config_path, url_overrides, builtins)
        self._extra_headers = dict(extra_headers or {})
        self._auth_by_server = dict(auth_by_server or {})
        for server_id, config in self._configs.items():
            if server_id in (builtins or {}):
                self._builtin_tasks[server_id] = asyncio.create_task(
                    self._retry_builtin(server_id), name=f"MCP connection {server_id}"
                )
            else:
                await self._connect_one(server_id, config)
        return self.statuses()

    async def _retry_builtin(self, server_id: str) -> None:
        """Keep a built-in connection available without holding up startup."""
        while True:
            session = self._sessions.get(server_id)
            if session is None or session in self._origin_errors:
                await self._reconnect(server_id)
            await asyncio.sleep(ORIGIN_COOLDOWN_SECONDS)

    async def _reconnect(self, server_id: str) -> None:
        """Replace one dead upstream session using its startup config."""
        config = self._configs.get(server_id)
        if config is None:
            raise KeyError(f"No configuration for server {server_id!r}")

        stack = self._stacks.pop(server_id, None)
        self._sessions.pop(server_id, None)
        self._last_known_tools.pop(server_id, None)
        if stack is not None:
            await stack.aclose()
        await self._connect_one(server_id, config)

    async def _open_origin(
        self, target: ServerConfig, *, extra_headers: dict[str, str] | None = None, auth=None,
    ) -> tuple[AsyncExitStack, ClientSession, list[types.Tool]]:
        """Keep the MCP transport's cancel scopes in the task that opened them."""
        ready: asyncio.Future[tuple[ClientSession, list[types.Tool]]] = asyncio.get_running_loop().create_future()
        stop = asyncio.Event()

        async def keep_open() -> None:
            session = None
            try:
                async with AsyncExitStack() as wire:
                    session = await open_session(wire, target, CONNECT_TIMEOUT_SECONDS, extra_headers,
                                                 **({"auth": auth} if auth is not None else {}))
                    tools = _namespace(target.id, (await session.list_tools()).tools)
                    if not ready.done():
                        ready.set_result((session, tools))
                    await stop.wait()
            except Exception as error:  # noqa: BLE001 - report opening failures to the registry
                if not ready.done():
                    ready.set_exception(error)
                elif session is not None and not ready.cancelled():
                    self._origin_errors[session] = error
            finally:
                if not ready.done():
                    ready.cancel()

        owner = asyncio.create_task(keep_open())
        try:
            session, tools = await ready
        except BaseException:
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
            raise

        async def close() -> None:
            stop.set()
            try:
                if not owner.done():
                    await owner
            finally:
                self._origin_errors.pop(session, None)

        stack = AsyncExitStack()
        stack.push_async_callback(close)
        return stack, session, tools

    def _target_for(self, config: ServerConfig, ref: OriginRef) -> ServerConfig:
        """Resolve only an id from this connection and select its token."""
        if self._resolve_origin is None:
            raise KeyError(ref.origin_id)
        auth = config.auth
        if auth is not None and auth.type == "header":
            auth = replace(auth, header_value=ref.header_value or auth.header_value)
        return replace(config, url=self._resolve_origin(ref.origin_id) + config.path, auth=auth)

    def _eligible_origins(self, config: ServerConfig) -> list[OriginRef]:
        now = self._clock()
        return [ref for ref in config.origins if self._down.get((config.id, ref.origin_id), 0.0) <= now]

    async def _drop_origin(self, server_id: str) -> None:
        session = self._sessions.pop(server_id, None)
        stack = self._stacks.pop(server_id, None)
        self._active.pop(server_id, None)
        self._last_known_tools.pop(server_id, None)
        if stack is not None:
            if session is not None and self._origin_calls.get(session, 0):
                self._retired_origins[session] = stack
            else:
                await stack.aclose()

    async def _connect_origins(self, config: ServerConfig, candidates: list[OriginRef]) -> ServerStatus:
        server_id = config.id
        status = ServerStatus(id=server_id, label=config.label, description=config.description,
                              status="error", error="No available origin in the outside catalog")
        for ref in candidates:
            try:
                target = self._target_for(config, ref)
            except KeyError:
                self._down[(server_id, ref.origin_id)] = self._clock() + ORIGIN_COOLDOWN_SECONDS
                continue
            try:
                stack, session, tools = await self._open_origin(target)
            except Exception as error:  # noqa: BLE001 - one upstream must not stop others
                status.error = f"MCP connection failed ({type(error).__name__})"
                if not is_connection_failure(error):
                    break
                self._down[(server_id, ref.origin_id)] = self._clock() + ORIGIN_COOLDOWN_SECONDS
                continue
            await self._drop_origin(server_id)
            self._stacks[server_id] = stack
            self._sessions[server_id] = session
            self._last_known_tools[server_id] = tools
            self._active[server_id] = ref.origin_id
            status = ServerStatus(id=server_id, label=config.label, description=config.description,
                                  status="connected", tools=[tool.name for tool in tools], origin_id=ref.origin_id)
            break
        if status.status == "error" and server_id in self._sessions:
            return next(current for current in self._statuses if current.id == server_id)
        self._statuses = [current for current in self._statuses if current.id != server_id]
        self._statuses.append(status)
        return status

    async def _refresh_origin(self, config: ServerConfig) -> None:
        """Retry an unavailable connection or probe a preferred origin."""
        async with self._origin_locks.setdefault(config.id, asyncio.Lock()):
            active = self._active.get(config.id)
            session = self._sessions.get(config.id)
            transport_error = self._origin_errors.get(session) if session is not None else None
            if active is not None and transport_error is not None:
                if is_connection_failure(transport_error):
                    self._down[(config.id, active)] = self._clock() + ORIGIN_COOLDOWN_SECONDS
                await self._drop_origin(config.id)
                active = None
            candidates = self._eligible_origins(config)
            if active is not None:
                preferred = []
                for ref in config.origins:
                    if ref.origin_id == active:
                        break
                    if ref in candidates:
                        preferred.append(ref)
                candidates = preferred
            if candidates or transport_error is not None:
                await self._connect_origins(config, candidates)

    async def _fail_over(self, config: ServerConfig, session: ClientSession) -> None:
        async with self._origin_locks.setdefault(config.id, asyncio.Lock()):
            if self._sessions.get(config.id) is not session:
                return
            active = self._active[config.id]
            self._down[(config.id, active)] = self._clock() + ORIGIN_COOLDOWN_SECONDS
            await self._drop_origin(config.id)
            await self._connect_origins(config, self._eligible_origins(config))

    async def _connect_one(self, server_id: str, config: ServerConfig) -> ServerStatus:
        if config.origins:
            return await self._connect_origins(config, self._eligible_origins(config) or list(config.origins))
        local_stack = AsyncExitStack()
        try:
            auth = self._auth_by_server.get(server_id)
            if server_id in self._builtin_tasks:
                opened, session, namespaced_tools = await self._open_origin(config, extra_headers=self._extra_headers, auth=auth)
            else:
                session = await open_session(local_stack, config, CONNECT_TIMEOUT_SECONDS, self._extra_headers,
                                             **({"auth": auth} if auth is not None else {}))
                namespaced_tools = _namespace(server_id, (await session.list_tools()).tools)
                opened = local_stack.pop_all()
        except Exception as error:  # noqa: BLE001 - one bad server must not block the others
            try:
                await local_stack.aclose()
            except Exception:  # noqa: BLE001 - a messy close must not escape a failed connect
                pass
            status = ServerStatus(
                id=server_id,
                label=config.label,
                description=config.description,
                status="error",
                error=str(error) or type(error).__name__,
            )
            self._set_status(status)
            return status

        self._stacks[server_id] = opened
        self._last_known_tools[server_id] = namespaced_tools
        self._sessions[server_id] = session
        status = ServerStatus(
            id=server_id,
            label=config.label,
            description=config.description,
            status="connected",
            tools=[tool.name for tool in namespaced_tools],
        )
        self._set_status(status)
        return status

    def _set_status(self, status: ServerStatus) -> None:
        self._statuses = [previous for previous in self._statuses if previous.id != status.id]
        self._statuses.append(status)

    async def _live_tools_for(self, server_id: str, session: ClientSession) -> list[types.Tool]:
        try:
            listed = await session.list_tools()
        except Exception:  # noqa: BLE001 - one flaky server must not break the others
            return self._last_known_tools.get(server_id, [])
        namespaced_tools = _namespace(server_id, listed.tools)
        self._last_known_tools[server_id] = namespaced_tools
        return namespaced_tools

    async def _recover_catalog_connections(self) -> None:
        """A catalog-backed Armory absent at startup may become reachable later."""
        async with self._catalog_reconnect_lock:
            for server_id, config in self._configs.items():
                if callable(config.url) and server_id not in self._sessions and server_id not in self._builtin_tasks:
                    self._statuses = [status for status in self._statuses if status.id != server_id]
                    await self._reconnect(server_id)

    async def list_tools(self) -> list[types.Tool]:
        """The merged catalog, fetched live from every connected server on
        each call - so a server's tools changing at runtime is reflected
        without a restart, the same reasoning as extensions.py's
        merged_list_tools()."""
        await self._recover_catalog_connections()
        await asyncio.gather(*(self._refresh_origin(config) for config in self._configs.values()
                               if config.origins and (config.id in self._sessions or config.id not in self._builtin_tasks)))
        results = await asyncio.gather(
            *(self._live_tools_for(server_id, session) for server_id, session in self._sessions.items())
        )
        return [tool for tools in results for tool in tools]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        on_progress: Callable[[str], None] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> types.CallToolResult:
        """Route `name` (as returned by list_tools(), e.g. "main__ping")
        to whichever server owns it. Raises KeyError for a name that
        isn't currently connected - callers are expected to only call
        names they just got from list_tools().

        `on_progress` receives each message the tool reports while it runs
        (an MCP progress notification with a message); it is called on this
        registry's own event-loop thread. `meta` becomes the request's
        `_meta` (the asking user - see internal_auth.py)."""
        server_id, separator, upstream_name = name.partition(NAMESPACE_SEPARATOR)
        config = self._configs.get(server_id) if separator else None
        origin_connection = config is not None and bool(config.origins)
        session = self._sessions.get(server_id) if separator else None
        if origin_connection and (session is None or session in self._origin_errors):
            await self._refresh_origin(config)
        elif separator and session is None:
            await self._recover_catalog_connections()
        session = self._sessions.get(server_id) if separator else None
        if session is None:
            raise KeyError(f"No tool named {name!r} on any connected server")

        extra: dict[str, Any] = {}
        if on_progress is not None:

            async def progress_callback(progress: float, total: float | None, message: str | None) -> None:
                if message:
                    on_progress(message)

            extra["progress_callback"] = progress_callback
        if meta is not None and not origin_connection:
            extra["meta"] = meta

        async def call(on: Any) -> types.CallToolResult:
            return await on.call_tool(
                upstream_name, arguments, read_timeout_seconds=timedelta(seconds=CALL_TIMEOUT_SECONDS), **extra
            )

        if origin_connection:
            self._origin_calls[session] = self._origin_calls.get(session, 0) + 1
            try:
                return await call(session)
            except Exception as error:
                # The SDK can report a timeout after the transport closed on an HTTP refusal.
                if is_connection_failure(self._origin_errors.get(session, error)):
                    await self._fail_over(config, session)
                raise
            finally:
                self._origin_calls[session] -= 1
                if self._origin_calls[session] == 0:
                    self._origin_calls.pop(session)
                    retired = self._retired_origins.pop(session, None)
                    if retired is not None:
                        await retired.aclose()

        try:
            return await call(session)
        except RuntimeError as error:
            if str(error) != "Session terminated":
                raise
            if server_id in self._builtin_tasks:
                self._origin_errors[session] = error
                raise
            await self._reconnect(server_id)
            recovered_session = self._sessions.get(server_id)
            if recovered_session is None:
                raise
            return await call(recovered_session)

    async def aclose(self) -> None:
        """Close every open connection. One server failing to close
        cleanly must not stop the others."""
        for task in self._builtin_tasks.values():
            task.cancel()
        await asyncio.gather(*self._builtin_tasks.values(), return_exceptions=True)
        self._builtin_tasks.clear()
        for stack in (*self._stacks.values(), *self._retired_origins.values()):
            try:
                await stack.aclose()
            except Exception:  # noqa: BLE001 - a messy shutdown must not block the rest
                pass
        self._stacks.clear()
        self._sessions.clear()
        self._retired_origins.clear()
        self._origin_errors.clear()
