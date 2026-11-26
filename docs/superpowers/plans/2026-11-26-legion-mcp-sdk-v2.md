# Legion on MCP SDK v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. One agent runs this straight through and reports once at the end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Legion from `mcp` 1.x to 2.x with no visible change, and make its outside connections speak protocol `2026-07-28` when the server does.

**Architecture:** The server side swaps `FastMCP` for `MCPServer` and carries requester identity through a server middleware. The client side moves to `httpx2`, and one helper in `transports.py` probes admin-added servers and private extensions with `discover()` before falling back to the old handshake. Elicitation is not in this plan.

**Tech Stack:** Python 3.11+, `mcp` 2.3, `mcp_types`, `httpx2`, Starlette, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-26-legion-sdk-v2-elicitation-design.md` (this plan covers Part 1 only; Parts 2 and 3 get their own plan after this one is built).

## Global Constraints

- Dependency: `mcp>=2.3,<3`. Legion only. Armory, Stronghold and Portcullis stay on 1.x.
- Do not edit `src/citadel_auth/` (copied from `libs/citadel_auth` and shared with 1.x services).
- Request body limit: `max_request_body_size` of 32 MiB.
- Built-in Armory (`main`) and Stronghold connections, delegation and router calls use `initialize()`. Admin-added connections and private extensions use `discover()` first.
- Private extension guard keeps every address and redirect check.
- SDK progress callbacks run as separate tasks in v2. A progress callback must not `await` before it hands its event on, or events can reorder.
- Never replay a tool call after a closed connection.
- Run only the tests listed in each task. If a run takes longer than about 2 minutes, stop and ask.
- Work in the current checkout and branch. One commit, at the end of Task 6.
- All paths below are relative to `apps/legion/`. All commands run in `apps/legion/`.

## SDK facts, read from the 2.3.0 source on 2026-11-26

| 1.x | 2.x |
|---|---|
| `mcp.server.fastmcp.FastMCP` | `mcp.server.mcpserver.MCPServer` (no `host` or `port` argument) |
| `mcp.server.fastmcp.Context` | `mcp.server.mcpserver.Context` |
| `server.lowlevel.server.request_ctx` | removed; middleware `async (context, call_next)` with `context.method`, `context.request`, `context.meta` (a dict) |
| `streamablehttp_client(url, headers=, auth=)` yields 3 values | `streamable_http_client(url, http_client=httpx2.AsyncClient)` yields 2 values |
| `McpError(types.ErrorData(...))` | `mcp.shared.exceptions.MCPError(code, message)` |
| timeout code `408` | `mcp_types.REQUEST_TIMEOUT` (-32001) |
| transport errors raise `httpx` exceptions | the request fails with `MCPError(CONNECTION_CLOSED)`; HTTP 4xx and 5xx become `MCPError` too |
| `RuntimeError("Session terminated")` | `MCPError(INVALID_REQUEST, "Session terminated")` |
| `read_timeout_seconds=timedelta(...)` | `read_timeout_seconds=float` |
| `isError`, `structuredContent`, `inputSchema`, `outputSchema`, `readOnlyHint` | `is_error`, `structured_content`, `input_schema`, `output_schema`, `read_only_hint` (constructors still accept the old names; attribute reads do not) |

`mcp.settings.log_level`, `mcp.custom_route`, `mcp.list_tools()`, `ctx.report_progress(progress, total, message)`, `ctx.request_context.request` and `create_mcp_http_client(headers, timeout, auth)` still exist. Sync tools now run on a worker thread; `src/providers/cancellation.py` already locks its registry, so `cancel`, `status` and `interpret` need no change.

## File map

| File | Change |
|---|---|
| `pyproject.toml`, `uv.lock` | SDK version |
| `src/runtime/internal_auth.py` | Identity middleware, `McpServiceAuth` for `httpx2` |
| `src/tools/mcp_client/transports.py` | `httpx2` transport, `open_negotiated` |
| `src/tools/mcp_client/registry.py` | Errors, renames, dead connection handling |
| `src/tools/private_extensions/guard.py`, `pool.py`, `turn.py` | `httpx2`, negotiation, errors, renames |
| `src/tools/mcp_client/mcp_upstream.py` | Renames, `McpServiceAuth` |
| `src/providers/language/anthropic_provider.py`, `openai_provider.py` | `input_schema` |
| `src/agents/roles/orchestrator/delegation.py`, `src/agents/roles/router/router_client.py` | v2 client |
| `src/server.py`, `src/gateway/routes.py`, `scripts/check_laya_model.py` | v2 server and script |

---

### Task 1: Prove a 2.x client talks to a 1.x server

Stop and report if this fails. Nothing in the repository changes.

**Files:**
- Create in the session scratchpad (not in the repo): `old_server.py`, `new_client.py`

- [ ] **Step 1: Write `old_server.py`**

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("old", host="127.0.0.1", port=29900)


@mcp.tool()
def echo(text: str) -> str:
    """Return text."""
    return text


mcp.run(transport="streamable-http")
```

- [ ] **Step 2: Write `new_client.py`**

```python
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

URL = "http://127.0.0.1:29900/mcp"


async def main() -> None:
    async with streamable_http_client(URL) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=10) as session:
            try:
                await session.discover()
                raise SystemExit("unexpected: a 1.x server answered discover")
            except MCPError as error:
                print("discover refused:", error.code, error.message)
    async with streamable_http_client(URL) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=10) as session:
            await session.initialize()
            result = await session.call_tool("echo", {"text": "ok"})
            print(session.protocol_version, result.is_error, result.content[0].text)


asyncio.run(main())
```

- [ ] **Step 3: Run both**

Server, in the background, from the scratchpad directory:

```bash
uv run --no-project --with "mcp==1.30.0" python old_server.py
```

Client:

```bash
uv run --no-project --with "mcp==2.3.0" python new_client.py
```

Expected: one `discover refused: ...` line, then `2025-11-25 False ok`. Stop the server afterwards.

---

### Task 2: Dependency and requester identity

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/runtime/internal_auth.py`
- Test: `tests/test_service_auth.py`

**Interfaces:**
- Produces: `internal_auth.mcp_requester(context=None)` (async context manager), `internal_auth.requester_middleware(context, call_next)`, `internal_auth.install_mcp(mcp)`, `internal_auth.McpServiceAuth(keyring, audience)` (an `httpx2.Auth`).

- [ ] **Step 1: Change the dependency**

In `pyproject.toml` replace `"mcp>=1.28.0,<2.0.0",` with `"mcp>=2.3,<3",`, then run:

```bash
uv sync
```

- [ ] **Step 2: Update `internal_auth.py`**

Add to the third-party imports, beside `import jwt`:

```python
import httpx2
import jwt
from mcp_types import CallToolResult, TextContent
```

Change the `src.citadel_auth` import to also import `ServiceAuth`:

```python
from src.citadel_auth import (
    AuthError, ServiceAuth, ServiceAuthMiddleware, current_requester as verified_requester,
    current_requester_token, from_env, requester_context,
)
```

Replace everything from `@asynccontextmanager` above `mcp_requester` to the end of `install_mcp` with:

```python
@asynccontextmanager
async def mcp_requester(context=None):
    """Bind the verified requester of one MCP request. `context` is the SDK's ServerRequestContext."""
    request = getattr(context, "request", None)
    caller, _, header_token = getattr(request, "scope", {}).get("citadel_auth", (None, None, ""))
    extras = getattr(context, "meta", None) or {}
    token = extras.get("requester_token", header_token)
    async with requester_context(keyring, caller, token, "legion") as who:
        requester = Requester.from_verified()
        if who is not None:
            _remember(who.uid, token)
            requester = Requester(who.username, who.email, who.uid, requester_token=token)
        handle = bind_requester(requester)
        try:
            yield requester
        finally:
            reset_requester(handle)


async def requester_middleware(context, call_next):
    """Run every tool call, status included, as its verified requester; refuse one that cannot be verified."""
    if context.method != "tools/call":
        return await call_next(context)
    try:
        async with mcp_requester(context):
            return await call_next(context)
    except AuthError as error:
        return CallToolResult(content=[TextContent(type="text", text=str(error))], is_error=True)


def install_mcp(mcp):
    """Add the requester middleware once, so every call can publish a verified renewal."""
    if requester_middleware not in mcp.middleware:
        mcp.middleware.append(requester_middleware)


class McpServiceAuth(httpx2.Auth):
    """`ServiceAuth` for the SDK's httpx2 clients: the same fresh signed assertion on every request."""

    def __init__(self, keyring, audience: str):
        self._signer = ServiceAuth(keyring, audience)

    async def async_auth_flow(self, request):
        async for signed in self._signer.async_auth_flow(request):
            yield signed
```

- [ ] **Step 3: Update `tests/test_service_auth.py`**

Delete the three imports `request_ctx`, `RequestContext` and `RequestParams`. Replace `_running_requester_uses_verified_renewal_without_changing_identity` with:

```python
async def _running_requester_uses_verified_renewal_without_changing_identity(tmp_path, monkeypatch):
    stack = await make_stack(tmp_path)
    monkeypatch.setattr(internal_auth, "keyring", stack["legion"])
    original = mint_requester(stack["portcullis"], "alice", "alice", "", ["legion", "armory"])
    renewed = mint_requester(stack["portcullis"], "alice", "alice", "", ["legion", "armory"])
    request = SimpleNamespace(scope={"citadel_auth": (Caller("stronghold"), None, "")})

    def context(meta):
        return SimpleNamespace(method="tools/call", request=request, meta=meta)

    async with internal_auth.mcp_requester(context({"requester_token": original})):
        assert internal_auth.requester_meta()["requester_token"] == original
        # A separate status request updates the credential while the original ask context lives.
        async def status_update():
            async with internal_auth.mcp_requester(context({"requester_token": renewed})):
                pass
        await asyncio.create_task(status_update())
        assert internal_auth.current_requester().uid == "alice"
        assert internal_auth.requester_meta()["requester_token"] == renewed
    async with internal_auth.mcp_requester(context({"requester": {"uid": "forged"}})):
        assert not internal_auth.current_requester()
        assert internal_auth.requester_meta() is None
    with pytest.raises(AuthError):
        async with internal_auth.mcp_requester(context({"requester_token": "forged"})):
            pytest.fail("forged requester reached tool")

    async def tool(_context):
        pytest.fail("forged requester reached tool")

    refused = await internal_auth.requester_middleware(context({"requester_token": "forged"}), tool)
    assert refused.is_error
```

- [ ] **Step 4: Run**

```bash
uv run pytest tests/test_service_auth.py -q
```

Expected: PASS.

---

### Task 3: Client transport, protocol choice and registry

**Files:**
- Modify: `src/tools/mcp_client/transports.py`, `src/tools/mcp_client/registry.py`
- Create: `tests/test_mcp_session_negotiation.py`
- Test: `tests/test_registry.py`, `tests/test_registry_origins.py`, `tests/test_schema.py`

**Interfaces:**
- Produces: `transports.open_negotiated(stack, open_streams, timeout_seconds, *, probe) -> ClientSession`, where `open_streams()` returns an async context manager yielding `(read, write)`. `transports.open_session(...)` keeps its signature.

- [ ] **Step 1: Rewrite the transport part of `transports.py`**

Replace the imports `from datetime import timedelta`, `import httpx` and the three `mcp` client imports so the block reads:

```python
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
```

In the module docstring and the `_check_tcp_reachable` docstring, rename `streamablehttp_client` to `streamable_http_client`.

Replace everything from `def _origin_client` to the end of the file with:

```python
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
```

- [ ] **Step 2: Update `registry.py`**

Imports: delete `from datetime import timedelta`; replace `import httpx` with `import httpx2`; replace `from mcp.shared.exceptions import McpError` with:

```python
from mcp.shared.exceptions import MCPError
from mcp_types import CONNECTION_CLOSED, REQUEST_TIMEOUT
```

Replace the end of `is_connection_failure`:

```python
    if isinstance(error, MCPError):
        return error.code in (REQUEST_TIMEOUT, CONNECTION_CLOSED)
    return isinstance(error, (ConnectionError, TimeoutError, httpx2.TransportError))
```

In `_namespace`, replace the two schema lines:

```python
            input_schema=inline_refs(tool.input_schema),
            output_schema=tool.output_schema,
```

In `_uses_builtin_url`:

```python
            return httpx2.URL(resolved(config.url)) == httpx2.URL(resolved(trusted))
        except (KeyError, ValueError, httpx2.InvalidURL):
```

In `call_tool`, pass the timeout as a float:

```python
            return await on.call_tool(
                upstream_name, arguments, read_timeout_seconds=CALL_TIMEOUT_SECONDS, **extra
            )
```

and replace the final `try` block of `call_tool` with:

```python
        try:
            return await call(session)
        except MCPError as error:
            terminated = error.message == "Session terminated"
            if not terminated and error.code != CONNECTION_CLOSED:
                raise
            if server_id in self._builtin_tasks:
                # The SDK no longer raises transport errors to the owner task: mark it for _retry_builtin.
                self._origin_errors[session] = error
                raise
            await self._reconnect(server_id)
            recovered_session = self._sessions.get(server_id)
            # A closed connection may have run the tool already, so only a terminated session is replayed.
            if not terminated or recovered_session is None:
                raise
            return await call(recovered_session)
```

- [ ] **Step 3: Create `tests/test_mcp_session_negotiation.py`**

```python
"""open_negotiated: probe for the 2026 protocol, fall back to a fresh handshake session."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from mcp.shared.exceptions import MCPError
from mcp_types import METHOD_NOT_FOUND

from src.tools.mcp_client import transports


def run(monkeypatch, discover_error, probe):
    log = []

    @asynccontextmanager
    async def streams():
        log.append("open")
        try:
            yield None, None
        finally:
            log.append("close")

    class Session:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def discover(self):
            log.append("discover")
            if discover_error:
                raise discover_error

        async def initialize(self):
            log.append("initialize")

    monkeypatch.setattr(transports, "ClientSession", Session)

    async def go():
        async with AsyncExitStack() as stack:
            await transports.open_negotiated(stack, streams, 1, probe=probe)
            log.append("ready")

    asyncio.run(go())
    return log


def test_a_new_server_keeps_the_discovered_session(monkeypatch):
    assert run(monkeypatch, None, True) == ["open", "discover", "ready", "close"]


def test_an_older_server_gets_a_fresh_handshake_session(monkeypatch):
    refused = MCPError(METHOD_NOT_FOUND, "Method not found")
    assert run(monkeypatch, refused, True) == ["open", "discover", "close", "open", "initialize", "ready", "close"]


def test_an_internal_server_is_not_probed(monkeypatch):
    assert run(monkeypatch, None, False) == ["open", "initialize", "ready", "close"]
```

- [ ] **Step 4: Update `tests/test_registry.py`**

Add the imports:

```python
import pytest
from mcp.shared.exceptions import MCPError
from mcp_types import CONNECTION_CLOSED, INVALID_REQUEST
```

Replace `_Session(error=RuntimeError("Session terminated"))` with `_Session(error=MCPError(INVALID_REQUEST, "Session terminated"))`. Add:

```python
def test_a_closed_connection_reconnects_without_replaying_the_call(monkeypatch):
    registry = McpClientRegistry()
    registry._sessions["main"] = _Session(error=MCPError(CONNECTION_CLOSED, "Connection closed"))
    reconnects = []

    async def reconnect(server_id):
        reconnects.append(server_id)
        registry._sessions[server_id] = _Session(result="replayed")

    monkeypatch.setattr(registry, "_reconnect", reconnect)

    with pytest.raises(MCPError):
        asyncio.run(registry.call_tool("main__tool", {}))
    assert reconnects == ["main"]
```

- [ ] **Step 5: Update `tests/test_registry_origins.py`**

Replace `import httpx` with `import httpx2`. Replace `from mcp.shared.exceptions import McpError` with:

```python
from mcp.shared.exceptions import MCPError
from mcp_types import CONNECTION_CLOSED, REQUEST_TIMEOUT
```

Then:
- In the `is_connection_failure` parameter table: `httpx.ConnectError("x")` becomes `httpx2.ConnectError("x")`; the two `McpError` rows become `(MCPError(REQUEST_TIMEOUT, "timed out"), True), (MCPError(CONNECTION_CLOSED, "closed"), True),` and `(MCPError(-32602, "bad params"), False),`.
- `McpError(types.ErrorData(code=403, message="denied"))` becomes `MCPError(403, "denied")`.
- Both `McpError(types.ErrorData(code=408, message="timed out"))` become `MCPError(REQUEST_TIMEOUT, "timed out")`.
- `pytest.raises(McpError)` becomes `pytest.raises(MCPError)`.
- Every other `httpx.` becomes `httpx2.`.
- `inputSchema=` becomes `input_schema=`.
- In `test_an_origin_transport_rejects_a_different_scheme_before_sending_credentials`, replace `attempt` and its patch with:

```python
    @asynccontextmanager
    async def attempt(url, *, http_client):
        for check in http_client.event_hooks["request"]:
            await check(httpx2.Request("POST", url))
            await check(httpx2.Request("POST", "https://one/mcp"))
        pytest.fail("Unlisted origin was accepted")
        yield

    monkeypatch.setattr(transports, "_check_tcp_reachable", reachable)
    monkeypatch.setattr(transports, "streamable_http_client", attempt)
```

In `tests/test_schema.py`, `inputSchema=PDF_MERGE` becomes `input_schema=PDF_MERGE` and `namespaced.inputSchema` becomes `namespaced.input_schema`.

- [ ] **Step 6: Run**

```bash
uv run pytest tests/test_mcp_session_negotiation.py tests/test_registry.py tests/test_registry_origins.py tests/test_schema.py -q
```

Expected: PASS. If an import fails inside a module that a later task ports, finish that task and run this command again.

---

### Task 4: Private extensions

**Files:**
- Modify: `src/tools/private_extensions/guard.py`, `pool.py`, `turn.py`
- Test: `tests/test_private_guard.py`, `tests/test_private_pool.py`, `tests/test_private_turn.py`, `tests/test_private_integration.py`

**Interfaces:**
- Consumes: `transports.open_negotiated` from Task 3.
- Produces: `guard.guarded_client_factory()` returns a factory `(headers=None, timeout=None, auth=None) -> httpx2.AsyncClient`.

- [ ] **Step 1: Port `guard.py`**

Replace `import httpx` with `import httpx2` and every `httpx.` with `httpx2.`. Change nothing else in the checks. In `guarded_client_factory`, change the docstring to `"""A factory for the HTTP client of one private extension connection."""` and the timeout line to:

```python
            timeout=timeout if timeout is not None else httpx2.Timeout(30.0, read=300.0),
```

- [ ] **Step 2: Port `pool.py`**

Imports: delete `from datetime import timedelta`; replace `import httpx` with `import httpx2`; replace the three `mcp.client` / `McpError` imports so the block reads:

```python
import httpx2
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import CONNECTION_CLOSED
from mcp_types.version import LATEST_HANDSHAKE_VERSION

from src.tools.mcp_client.transports import open_negotiated
from src.tools.private_extensions.guard import guarded_client_factory
from src.tools.private_extensions.spec import PrivateSpec
```

Add `from contextlib import AsyncExitStack, asynccontextmanager` in place of the existing `AsyncExitStack` import.

In `_preflight_handshake`:

```python
            "protocolVersion": LATEST_HANDSHAKE_VERSION,
```

```python
    async with factory(None, httpx2.Timeout(timeout_seconds)) as client:
        async with client.stream("POST", spec.url, json=payload, headers=headers) as response:
            # 400 is how a 2026-only server refuses the old handshake; negotiation handles it.
            if response.status_code >= 400 and response.status_code != 400:
                hint = " (check the extension's headers)" if response.status_code in (401, 403) else ""
                raise ConnectionError(f"The server rejected the MCP handshake: HTTP {response.status_code}{hint}")
```

Replace `open_private_session`:

```python
async def open_private_session(
    stack: AsyncExitStack, spec: PrivateSpec, factory: Any, timeout_seconds: float
) -> ClientSession:
    """Open a ready session for `spec`, registering what it opens on `stack`."""
    # First, so a blocked address or a bad header is reported in words; the SDK transport hides both.
    await _preflight_handshake(spec, factory, timeout_seconds)

    @asynccontextmanager
    async def open_streams():
        async with factory(spec.header_map or None) as http:
            async with streamable_http_client(spec.url, http_client=http) as streams:
                yield streams

    return await open_negotiated(stack, open_streams, timeout_seconds, probe=True)
```

Replace `_use`:

```python
    async def _use(self, account: str, spec: PrivateSpec, action: Callable[[ClientSession], Awaitable[Any]]) -> Any:
        try:
            return await action(await self.session(account, spec))
        except MCPError as error:
            if error.code == CONNECTION_CLOSED:
                # Dead connection: forget it, but never replay a call that may have run.
                await self.drop(account, spec)
                raise
            if "Session terminated" not in str(error):
                raise
        # The server dropped the session: one fresh one, one retry.
        await self.drop(account, spec)
        return await action(await self.session(account, spec))
```

Replace `call`:

```python
    async def call(self, account: str, spec: PrivateSpec, tool: str, arguments: dict[str, Any]) -> types.CallToolResult:
        return await self._use(account, spec, lambda session: session.call_tool(
            tool, arguments, read_timeout_seconds=self._call_timeout))
```

- [ ] **Step 3: Port `turn.py`**

In the `types.Tool(...)` call:

```python
                    input_schema=inline_refs(tool.input_schema),
                    output_schema=tool.output_schema,
```

- [ ] **Step 4: Update the tests**

`tests/test_private_guard.py`: `import httpx` becomes `import httpx2`; every `httpx.` becomes `httpx2.`.

`tests/test_private_turn.py`: `inputSchema=` becomes `input_schema=`; `.inputSchema` becomes `.input_schema`.

`tests/test_private_pool.py`:
- Imports: replace `McpError` with `MCPError`, and add `from mcp_types import CONNECTION_CLOSED, INVALID_REQUEST`.
- `inputSchema=` becomes `input_schema=`.
- `RuntimeError("Session terminated")` becomes `MCPError(INVALID_REQUEST, "Session terminated")`.
- `McpError(types.ErrorData(code=32600, message="Session terminated"))` becomes `MCPError(32600, "Session terminated")`.
- `McpError(types.ErrorData(code=-32602, message="Invalid params"))` becomes `MCPError(-32602, "Invalid params")`, and `pytest.raises(McpError, ...)` becomes `pytest.raises(MCPError, ...)`.
- Add:

```python
def test_a_closed_connection_is_dropped_and_the_call_is_not_replayed():
    h = Harness()

    async def go():
        await h.pool.call("a@x", spec(), "echo", {})
        h.sessions[0].fail_once = MCPError(CONNECTION_CLOSED, "Connection closed")
        await h.pool.call("a@x", spec(), "echo", {"n": 1})

    with pytest.raises(MCPError, match="Connection closed"):
        run(go())
    assert len(h.opened) == 1
    assert h.closed == ["notes"]
```

`tests/test_private_integration.py`:
- `from mcp.server.fastmcp import FastMCP` becomes `from mcp.server.mcpserver import MCPServer`.
- `FastMCP("smoke", port=port)` becomes `MCPServer("smoke")`.
- `mcp.streamable_http_app()` becomes `mcp.streamable_http_app(host="127.0.0.1")`.
- `import httpx` becomes `import httpx2`; `httpx.` becomes `httpx2.`.
- A test that expects a restarted server to be retried relies on `Session terminated`. A 2026 session has no server session, so after a restart the next call succeeds on the first try or fails once with a closed connection. If such a test fails only for that reason, assert that the call after the restart succeeds within two attempts.

- [ ] **Step 5: Run**

```bash
uv run pytest tests/test_private_guard.py tests/test_private_pool.py tests/test_private_turn.py -q
```

```bash
uv run pytest tests/test_private_integration.py -m "" -q
```

Expected: PASS.

---

### Task 5: Upstream calls, providers, delegation and router

**Files:**
- Modify: `src/tools/mcp_client/mcp_upstream.py`, `src/providers/language/anthropic_provider.py`, `src/providers/language/openai_provider.py`, `src/agents/roles/orchestrator/delegation.py`, `src/agents/roles/router/router_client.py`
- Test: listed in Step 6

**Interfaces:**
- Consumes: `internal_auth.McpServiceAuth` from Task 2.

- [ ] **Step 1: Port `mcp_upstream.py`**

Change `from src.citadel_auth import ServiceAuth, settings_store` to `from src.citadel_auth import settings_store`. In `connect`:

```python
        auth_by_server={
            _SERVER_ID: internal_auth.McpServiceAuth(internal_auth.keyring, "armory"),
            _STRONGHOLD_ID: internal_auth.McpServiceAuth(internal_auth.keyring, _STRONGHOLD_ID),
        },
```

In `_remember_read_only`, replace the `readOnlyHint` condition:

```python
        and (annotations := getattr(tool, "annotations", None)) is not None
        and annotations.read_only_hint is True
```

In `call_tool`:

```python
    if citadel_tool and result.is_error and parse(text) is not None:
        return NumberedFailureText(text)
    if name == f"{_PREFIX}tool_web_search":
        structured = result.structured_content
        hits = structured.get("results", []) if isinstance(structured, dict) else []
```

Rename `readOnlyHint` to `read_only_hint` only in code. Comments and docstrings that name the protocol hint stay.

- [ ] **Step 2: Port the providers**

In both provider files, `tool.inputSchema or {"type": "object", "properties": {}}` becomes `tool.input_schema or {"type": "object", "properties": {}}`.

- [ ] **Step 3: Port `delegation.py`**

Replace the import `from mcp.client.streamable_http import streamablehttp_client` with:

```python
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
```

Delete the `ServiceAuth` import. In `_call_tool`:

```python
    async with create_mcp_http_client(
        headers=internal_auth.outbound_headers() or None,
        auth=internal_auth.McpServiceAuth(internal_auth.keyring, "legion"),
    ) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments, progress_callback=on_progress)

    if result.is_error:
        parts = [getattr(block, "text", str(block)) for block in result.content]
        raise RuntimeError("\n".join(parts) if parts else f"{name} failed")
    return result.structured_content or {}
```

- [ ] **Step 4: Port `router_client.py`**

Replace the same import as in Step 3, delete the `ServiceAuth` import, and replace the head of `_call` and its result reads:

```python
async def _call(agent: dict, request: RouteRequest) -> dict:
    async with create_mcp_http_client(
        headers=internal_auth.outbound_headers() or None,
        auth=internal_auth.McpServiceAuth(internal_auth.keyring, "legion"),
    ) as http:
        async with streamable_http_client(agent["url"], http_client=http) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = None
                async with anyio.create_task_group() as tasks:
                    async def watch():
                        while True:
                            if cancellation.is_cancelled(request.request_id):
                                await session.call_tool("cancel", {"request_id": request.request_id})
                                tasks.cancel_scope.cancel()
                                return
                            await anyio.sleep(.05)
                    tasks.start_soon(watch)
                    try:
                        result = await session.call_tool("route", {"request": request.model_dump()})
                    finally:
                        tasks.cancel_scope.cancel()
                if result is None or result.is_error:
                    raise ValueError("Router returned no decision")
                if result.structured_content is not None:
                    return result.structured_content
                return json.loads(next(c.text for c in result.content if c.type == "text"))
```

- [ ] **Step 5: Update the tests**

- `tests/test_delegation.py`: in `_fake_session`, `SimpleNamespace(is_error=is_error, content=content, structured_content=structured)`. Every patch of `delegation.streamablehttp_client` becomes `delegation.streamable_http_client` and its fake value `_cm((None, None, None))` becomes `_cm((None, None))`. Rename "isError" in the module docstring to "is_error".
- `tests/test_mcp_output_screening.py`: `structuredContent=` becomes `structured_content=`.
- `tests/test_mcp_upstream_servers.py`: `inputSchema=` becomes `input_schema=`; `types.ToolAnnotations(readOnlyHint=True)` becomes `types.ToolAnnotations(read_only_hint=True)`.
- `tests/test_read_only_approvals.py`: `SimpleNamespace(readOnlyHint=read_only)` becomes `SimpleNamespace(read_only_hint=read_only)`.
- `tests/test_tool_scope.py`: `inputSchema={}` becomes `input_schema={}`.
- `tests/test_private_upstream.py`, `tests/test_anthropic_provider.py`, `tests/test_openai_provider.py`: `inputSchema=` becomes `input_schema=`.
- `tests/test_catalog_peers.py`, in `test_open_session_resolves_callable_again_after_reconnect`: the fake `stream` yields `(None, None)` and the patch target is `"streamable_http_client"`.
- `tests/test_mcp_client_builtin.py`, in the Stronghold origin test: the fake `stream` is

```python
    @asynccontextmanager
    async def stream(url, **options):
        yield None, None
```

  patch `"streamable_http_client"` instead of `"streamablehttp_client"`, add `import httpx2`, and replace the call and the closing assertions (from `config = validate_server(...)`) with:

```python
    guarded = []
    real = transports._origin_client

    def origin_client(url, **options):
        guarded.append(url)
        return real(url, **options)

    monkeypatch.setattr(transports, "_origin_client", origin_client)
    config = validate_server("stronghold", STRONGHOLD["stronghold"])

    async def run():
        async with AsyncExitStack() as stack:
            await transports.open_session(stack, config, 1, auth=httpx2.BasicAuth("user", "password"))

    asyncio.run(run())
    assert guarded == ["http://stronghold.test/mcp"]
```

  Delete the `transport_options` dictionary and the `partial` import if nothing else uses them.
- Any fake tool result that now raises `AttributeError` on `is_error` or `structured_content` gets `is_error=False` or `structured_content=None`.

- [ ] **Step 6: Run**

```bash
uv run pytest tests/test_delegation.py tests/test_mcp_output_screening.py tests/test_mcp_upstream_servers.py tests/test_read_only_approvals.py tests/test_tool_scope.py tests/test_private_upstream.py tests/test_anthropic_provider.py tests/test_openai_provider.py tests/test_catalog_peers.py tests/test_mcp_client_builtin.py -q
```

Expected: PASS.

---

### Task 6: Server, routes, script, and commit

**Files:**
- Modify: `src/server.py`, `src/gateway/routes.py`, `scripts/check_laya_model.py`
- Test: listed in Step 5

- [ ] **Step 1: Port `server.py`**

`from mcp.server.fastmcp import Context, FastMCP` becomes `from mcp.server.mcpserver import Context, MCPServer`. Replace the server construction:

```python
# `ask` carries the whole chat history; the SDK's 4 MiB default would refuse long chats.
MAX_REQUEST_BYTES = 32 * 1024 * 1024

mcp = MCPServer(
    name=f"ai-agent-{_AGENT_ID}",
    instructions=(
        f"Chat agent backed by {agent_config.PROVIDER_ID} "
        f"({agent_config.MODEL or 'provider default'}), with tool access to "
        "mcp_server. Call ask() with a question."
    ),
)
```

In `main`, replace `app = mcp.streamable_http_app()` with:

```python
        app = mcp.streamable_http_app(host=HOST, max_request_body_size=MAX_REQUEST_BYTES)
```

In comments that say "FastMCP", write "the MCP server".

- [ ] **Step 2: Port `gateway/routes.py`**

`from mcp.server.fastmcp import FastMCP` becomes `from mcp.server.mcpserver import MCPServer`, and `def register(mcp: FastMCP) -> None:` becomes `def register(mcp: MCPServer) -> None:`.

- [ ] **Step 3: Port `scripts/check_laya_model.py`**

`read_timeout_seconds=timedelta(seconds=120)` becomes `read_timeout_seconds=120.0`; delete `from datetime import timedelta`; `result.isError` becomes `result.is_error`.

- [ ] **Step 4: Update the tests**

- `tests/test_chat_id_meta.py`: replace the schema lines with

```python
        schema = next(tool.input_schema for tool in await server.mcp.list_tools() if tool.name == "ask")
        assert "chat_id" in schema["properties"] and "chat_id" not in schema["required"]
        assert "ctx" not in schema["properties"]
```

- `tests/test_server.py`: `ask.inputSchema` becomes `ask.input_schema` (both lines). Rename "FastMCP" in the module docstring to "MCPServer".
- `tests/test_router_transport.py`: `from mcp.server.fastmcp import Context, FastMCP` becomes `from mcp.server.mcpserver import Context, MCPServer`; `FastMCP("router-transport-test", port=port)` becomes `MCPServer("router-transport-test")`; `mcp.streamable_http_app()` becomes `mcp.streamable_http_app(host="127.0.0.1")`.

- [ ] **Step 5: Run**

```bash
uv run pytest tests/test_server.py tests/test_chat_id_meta.py tests/test_ready.py tests/test_router_transport.py tests/test_private_server.py -m "" -q
```

Expected: PASS.

- [ ] **Step 6: Look for leftover 1.x names**

```bash
git grep -nE "fastmcp|FastMCP|streamablehttp_client|McpError|\.isError|structuredContent|\.inputSchema|\.outputSchema|request_ctx|_mcp_server" -- src scripts tests ':!src/citadel_auth'
```

Expected: no code matches. Comment and docstring mentions are fine only if they are still true; fix the others.

- [ ] **Step 7: Run every file this plan touched, once**

```bash
uv run pytest tests/test_service_auth.py tests/test_mcp_session_negotiation.py tests/test_registry.py tests/test_registry_origins.py tests/test_schema.py tests/test_private_guard.py tests/test_private_pool.py tests/test_private_turn.py tests/test_delegation.py tests/test_mcp_output_screening.py tests/test_mcp_upstream_servers.py tests/test_read_only_approvals.py tests/test_tool_scope.py tests/test_private_upstream.py tests/test_anthropic_provider.py tests/test_openai_provider.py tests/test_catalog_peers.py tests/test_mcp_client_builtin.py tests/test_server.py tests/test_chat_id_meta.py tests/test_ready.py tests/test_router_transport.py tests/test_private_server.py -m "not slow" -q
```

Expected: PASS.

- [ ] **Step 8: Commit** (from the Citadel root)

```bash
git add apps/legion
git commit -m "feat(legion): move to MCP SDK v2 and probe outside servers for protocol 2026-07-28"
```

## Report at the end

State what changed, which commands ran, and what was not run: no Docker build, no live Armory or Stronghold, no real outside server, no full Legion suite.
