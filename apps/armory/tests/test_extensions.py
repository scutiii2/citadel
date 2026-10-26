"""Tests for services/extensions.py, the proxy/aggregation engine.
Mostly mocked (fake stdio_client and ClientSession); test_real_fixture_server_end_to_end spawns the reference fixture (src/_fixtures/reference_extension_server.py) to prove the real protocol path."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from mcp import types
from mcp.server.fastmcp import FastMCP

from src.services import extensions
from src.services.app_config import ExtensionConfig


# --- fakes for the mocked tests: fake stdio_client yields the fake session as `read`, fake ClientSession returns it unchanged ---
# That lets connect_all() run its real path (timeouts, isolation, namespacing) without a subprocess.


class _FakeSession:
    def __init__(self, tools: list[types.Tool], call_results: dict[str, types.CallToolResult] | None = None):
        self._tools = tools
        self._call_results = call_results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.metas: list[dict[str, Any] | None] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def initialize(self) -> None:
        return None

    async def list_tools(self) -> types.ListToolsResult:
        return types.ListToolsResult(tools=self._tools)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        read_timeout_seconds: object = None,
        *,
        meta: dict[str, Any] | None = None,
    ) -> types.CallToolResult:
        self.calls.append((name, arguments))
        self.metas.append(meta)
        return self._call_results[name]


def _fake_stdio_client(session: _FakeSession):
    @contextlib.asynccontextmanager
    async def _cm(params: object):
        yield (session, None)

    return _cm


def _fake_stdio_client_raising(error: Exception):
    @contextlib.asynccontextmanager
    async def _cm(params: object):
        raise error
        yield  # pragma: no cover - unreachable, satisfies the generator protocol

    return _cm


def _install_fake_connection(monkeypatch: pytest.MonkeyPatch, session_or_error) -> None:
    """Point extensions.stdio_client/ClientSession at one fake connection
    outcome. Used when a test only configures a single extension."""
    if isinstance(session_or_error, Exception):
        monkeypatch.setattr(extensions, "stdio_client", _fake_stdio_client_raising(session_or_error))
    else:
        monkeypatch.setattr(extensions, "stdio_client", _fake_stdio_client(session_or_error))
    # ClientSession(read, write) returns `read` (the fake session, see the module comment above).
    # Takes **kwargs because the real call passes read_timeout_seconds=; a TypeError would silently become an "error" status.
    monkeypatch.setattr(extensions, "ClientSession", lambda read, write, **kwargs: read)


# Same trick as _fake_stdio_client for the http transport: streamablehttp_client yields a 3-tuple,
# so the fake session goes first and the other two are ignored, as in _open_and_list.


def _fake_streamablehttp_client(session: _FakeSession, seen: list[dict[str, Any]] | None = None):
    @contextlib.asynccontextmanager
    async def _cm(url: str, **kwargs: Any):
        if seen is not None:
            seen.append({"url": url, **kwargs})
        yield (session, None, None)

    return _cm


def _fake_streamablehttp_client_raising(error: Exception):
    @contextlib.asynccontextmanager
    async def _cm(url: str, **kwargs: Any):
        raise error
        yield  # pragma: no cover - unreachable, satisfies the generator protocol

    return _cm


def _skip_tcp_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """_open_and_list probes host:port with a real TCP connect before
    streamablehttp_client; the fake URLs used here point nowhere real."""

    async def _no_probe(url: str) -> None:
        return None

    async def _no_handshake(url: str, headers: dict[str, str] | None) -> None:
        return None

    monkeypatch.setattr(extensions, "_check_tcp_reachable", _no_probe)
    monkeypatch.setattr(extensions, "_check_handshake_accepted", _no_handshake)


def _install_fake_http_connection(monkeypatch: pytest.MonkeyPatch, session_or_error) -> None:
    if isinstance(session_or_error, Exception):
        monkeypatch.setattr(extensions, "streamablehttp_client", _fake_streamablehttp_client_raising(session_or_error))
    else:
        monkeypatch.setattr(extensions, "streamablehttp_client", _fake_streamablehttp_client(session_or_error))
    monkeypatch.setattr(extensions, "ClientSession", lambda read, write, **kwargs: read)
    _skip_tcp_probe(monkeypatch)


def _echo_tool() -> types.Tool:
    return types.Tool(name="echo", description="Echo text back", inputSchema={"type": "object", "properties": {}})


def _add_tool() -> types.Tool:
    return types.Tool(name="add", description="Add two numbers", inputSchema={"type": "object", "properties": {}})


def _config(**overrides: Any) -> ExtensionConfig:
    base = dict(id="reference", label="Reference", description="Dev fixture", command="fake-command", args=[])
    base.update(overrides)
    return ExtensionConfig(**base)


# --- namespacing -----------------------------------------------------------


@pytest.mark.anyio
async def test_tools_are_registered_under_extension_id_double_underscore_name(monkeypatch: pytest.MonkeyPatch):
    """The feature depends on `echo` from `reference` appearing as `reference__echo`;
    otherwise same-named tools or collisions with our own tools would silently shadow each other."""
    session = _FakeSession(tools=[_echo_tool(), _add_tool()])
    _install_fake_connection(monkeypatch, session)

    registry = extensions.ExtensionRegistry()
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config()})
    await registry.connect_all(Path("unused.json"))

    names = {tool.name for tool in registry.proxied_tool_definitions()}
    assert names == {"reference__echo", "reference__add"}
    assert registry.is_proxied("reference__echo")
    assert not registry.is_proxied("echo")


@pytest.mark.anyio
async def test_status_carries_the_web_url_whether_connected_or_not(monkeypatch: pytest.MonkeyPatch):
    """The web app of an extension is reachable even when its MCP endpoint is not."""
    monkeypatch.setattr(
        extensions, "load_extensions_config", lambda path: {"reference": _config(web_url="http://127.0.0.1:5174")}
    )

    _install_fake_connection(monkeypatch, _FakeSession(tools=[_echo_tool()]))
    connected = extensions.ExtensionRegistry()
    await connected.connect_all(Path("unused.json"))
    assert connected.statuses()[0].web_url == "http://127.0.0.1:5174"

    _install_fake_connection(monkeypatch, RuntimeError("down"))
    failed = extensions.ExtensionRegistry()
    await failed.connect_all(Path("unused.json"))
    assert failed.statuses()[0].status == "error"
    assert failed.statuses()[0].web_url == "http://127.0.0.1:5174"


@pytest.mark.anyio
async def test_connected_status_lists_the_namespaced_tool_names(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession(tools=[_echo_tool()])
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config()})

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))

    [status] = registry.statuses()
    assert status == extensions.ExtensionStatus(
        id="reference",
        label="Reference",
        description="Dev fixture",
        status="connected",
        error=None,
        tools=["reference__echo"],
    )


@pytest.mark.anyio
async def test_proxied_tool_definition_preserves_meta_annotations_and_icons(monkeypatch: pytest.MonkeyPatch):
    """Regression: meta/annotations/icons were dropped when building _ProxiedTool.definition,
    breaking features (like keyword-based filtering) that rely on an extension's metadata."""
    tool = types.Tool(
        name="echo",
        description="Echo text back",
        inputSchema={"type": "object", "properties": {}},
        _meta={"keywords": ["echo", "repeat"]},
        annotations=types.ToolAnnotations(title="Echo"),
        icons=[types.Icon(src="https://example.com/icon.png")],
    )
    session = _FakeSession(tools=[tool])
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config()})

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))

    [proxied] = registry.proxied_tool_definitions()
    assert proxied.meta == {"keywords": ["echo", "repeat"]}
    assert proxied.annotations == types.ToolAnnotations(title="Echo")
    assert proxied.icons == [types.Icon(src="https://example.com/icon.png")]


# --- failure isolation -------------------------------------------------


@pytest.mark.anyio
async def test_a_broken_extension_does_not_prevent_a_working_sibling(monkeypatch: pytest.MonkeyPatch):
    """The required property: one bad `command` must not stop a different,
    correctly configured extension from connecting."""
    good_session = _FakeSession(tools=[_echo_tool()])

    def fake_stdio_client(params: Any):
        if params.command == "good-command":
            return _fake_stdio_client(good_session)(params)
        return _fake_stdio_client_raising(FileNotFoundError("no such file or directory"))(params)

    monkeypatch.setattr(extensions, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(extensions, "ClientSession", lambda read, write, **kwargs: read)
    monkeypatch.setattr(
        extensions,
        "load_extensions_config",
        lambda path: {
            "broken": _config(id="broken", command="bad-command"),
            "good": _config(id="good", command="good-command"),
        },
    )

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))

    statuses = {status.id: status for status in registry.statuses()}
    assert statuses["broken"].status == "error"
    assert statuses["broken"].error  # a message is present
    assert statuses["broken"].tools == []
    assert statuses["good"].status == "connected"
    assert statuses["good"].tools == ["good__echo"]


@pytest.mark.anyio
async def test_a_broken_extension_does_not_prevent_our_own_tools_from_working(monkeypatch: pytest.MonkeyPatch):
    """install() must still merge this server's own tools when every extension failed to connect;
    a typo in one command must never take the server down."""
    monkeypatch.setattr(extensions, "stdio_client", _fake_stdio_client_raising(ConnectionRefusedError("refused")))
    monkeypatch.setattr(extensions, "ClientSession", lambda read, write, **kwargs: read)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"broken": _config()})

    mcp = FastMCP(name="test-server")

    @mcp.tool()
    def builtin_tool() -> str:
        return "ok"

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    registry.install(mcp)

    names = {tool.name for tool in await registry.merged_list_tools()}
    assert names == {"builtin_tool"}
    assert registry.statuses()[0].status == "error"


# --- dispatch: merged list/call ------------------------------------------


@pytest.mark.anyio
async def test_merged_list_tools_includes_builtin_and_proxied(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession(tools=[_echo_tool()])
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config()})

    mcp = FastMCP(name="test-server")

    @mcp.tool()
    def builtin_tool() -> str:
        return "ok"

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    registry.install(mcp)

    names = {tool.name for tool in await registry.merged_list_tools()}
    assert names == {"builtin_tool", "reference__echo"}


@pytest.mark.anyio
async def test_merged_call_tool_routes_a_namespaced_name_upstream(monkeypatch: pytest.MonkeyPatch):
    result = types.CallToolResult(content=[types.TextContent(type="text", text="hi")])
    session = _FakeSession(tools=[_echo_tool()], call_results={"echo": result})
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config()})

    mcp = FastMCP(name="test-server")
    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    registry.install(mcp)

    returned = await registry.merged_call_tool("reference__echo", {"text": "hi"})

    assert returned is result
    assert session.calls == [("echo", {"text": "hi"})]  # upstream's own name, not the namespaced one


@pytest.mark.anyio
async def test_merged_call_tool_routes_a_plain_name_to_our_own_dispatch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {})

    mcp = FastMCP(name="test-server")

    @mcp.tool()
    def builtin_tool() -> str:
        return "from builtin"

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    registry.install(mcp)

    content, structured = await registry.merged_call_tool("builtin_tool", {})

    # FastMCP's call_tool() wraps a string return this way; the point is that a non-namespaced name
    # goes through its dispatch rather than being treated as an unknown proxied tool.
    assert structured == {"result": "from builtin"}
    [block] = content
    assert block.text == "from builtin"


# --- http transport ---
# Mirrors the stdio mocked tests (namespacing, failure isolation) via streamablehttp_client; see _open_and_list's branch on config.transport.


@pytest.mark.anyio
async def test_http_extension_connects_and_namespaces_its_tools(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession(tools=[_echo_tool()])
    _install_fake_http_connection(monkeypatch, session)
    monkeypatch.setattr(
        extensions,
        "load_extensions_config",
        lambda path: {"remote": _config(id="remote", command="", transport="http", url="http://127.0.0.1:9000/mcp")},
    )

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))

    [status] = registry.statuses()
    assert status.status == "connected"
    assert status.tools == ["remote__echo"]
    assert registry.is_proxied("remote__echo")
    assert not registry.is_proxied("echo")


@pytest.mark.anyio
async def test_a_broken_http_extension_does_not_prevent_a_working_stdio_sibling(monkeypatch: pytest.MonkeyPatch):
    good_session = _FakeSession(tools=[_echo_tool()])
    monkeypatch.setattr(extensions, "stdio_client", _fake_stdio_client(good_session))
    monkeypatch.setattr(
        extensions, "streamablehttp_client", _fake_streamablehttp_client_raising(ConnectionRefusedError("refused"))
    )
    monkeypatch.setattr(extensions, "ClientSession", lambda read, write, **kwargs: read)
    monkeypatch.setattr(
        extensions,
        "load_extensions_config",
        lambda path: {
            "broken": _config(id="broken", command="", transport="http", url="http://unreachable/mcp"),
            "good": _config(id="good", command="good-command"),
        },
    )

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))

    statuses = {status.id: status for status in registry.statuses()}
    assert statuses["broken"].status == "error"
    assert statuses["good"].status == "connected"
    assert statuses["good"].tools == ["good__echo"]


@pytest.mark.anyio
async def test_http_extension_sends_configured_headers(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession(tools=[_echo_tool()])
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(extensions, "streamablehttp_client", _fake_streamablehttp_client(session, seen))
    monkeypatch.setattr(extensions, "ClientSession", lambda read, write, **kwargs: read)
    _skip_tcp_probe(monkeypatch)
    monkeypatch.setattr(
        extensions,
        "load_extensions_config",
        lambda path: {
            "pdf_merger": _config(
                id="pdf_merger",
                command="",
                transport="http",
                url="http://127.0.0.1:8040/mcp",
                headers={"X-Internal-Token": "s3cret"},
            )
        },
    )

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))

    assert seen == [{"url": "http://127.0.0.1:8040/mcp", "headers": {"X-Internal-Token": "s3cret"}}]
    [status] = registry.statuses()
    assert "s3cret" not in repr(status)


@pytest.mark.anyio
async def test_http_extension_without_headers_sends_none(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession(tools=[_echo_tool()])
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(extensions, "streamablehttp_client", _fake_streamablehttp_client(session, seen))
    monkeypatch.setattr(extensions, "ClientSession", lambda read, write, **kwargs: read)
    _skip_tcp_probe(monkeypatch)
    monkeypatch.setattr(
        extensions,
        "load_extensions_config",
        lambda path: {"remote": _config(id="remote", command="", transport="http", url="http://127.0.0.1:9000/mcp")},
    )

    await extensions.ExtensionRegistry().connect_all(Path("unused.json"))

    assert seen == [{"url": "http://127.0.0.1:9000/mcp", "headers": None}]


def _mock_httpx(monkeypatch: pytest.MonkeyPatch, status: int, seen: list[Any] | None = None) -> None:
    import httpx

    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status)

    monkeypatch.setattr(
        extensions.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )


@pytest.mark.anyio
async def test_handshake_preflight_sends_headers_and_accepts_200(monkeypatch: pytest.MonkeyPatch):
    seen: list[Any] = []
    _mock_httpx(monkeypatch, 200, seen)

    await extensions._check_handshake_accepted("http://127.0.0.1:8040/mcp", {"X-Internal-Token": "s3cret"})

    [request] = seen
    assert request.headers["X-Internal-Token"] == "s3cret"
    assert json.loads(request.content)["method"] == "initialize"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404, 500])
async def test_handshake_preflight_raises_on_http_error_without_leaking_headers(
    monkeypatch: pytest.MonkeyPatch, status: int
):
    _mock_httpx(monkeypatch, status)

    with pytest.raises(ConnectionError) as info:
        await extensions._check_handshake_accepted("http://127.0.0.1:8040/mcp", {"X-Internal-Token": "s3cret"})

    assert f"HTTP {status}" in str(info.value)
    assert "s3cret" not in str(info.value)


@pytest.mark.anyio
async def test_rejected_http_handshake_is_an_error_status_and_never_reaches_streamablehttp_client(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    @contextlib.asynccontextmanager
    async def _must_not_open(url: str, **kwargs: Any):
        calls.append(url)
        yield None  # pragma: no cover

    async def _reachable(url: str) -> None:
        return None

    monkeypatch.setattr(extensions, "streamablehttp_client", _must_not_open)
    monkeypatch.setattr(extensions, "_check_tcp_reachable", _reachable)
    _mock_httpx(monkeypatch, 401)
    monkeypatch.setattr(
        extensions,
        "load_extensions_config",
        lambda path: {
            "pdf_merger": _config(
                id="pdf_merger", command="", transport="http", url="http://127.0.0.1:8040/mcp", headers={"X-Internal-Token": "bad"}
            )
        },
    )

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))

    [status] = registry.statuses()
    assert status.status == "error"
    assert "HTTP 401" in (status.error or "")
    assert calls == []


@pytest.mark.anyio
async def test_proxied_call_forwards_the_requester(monkeypatch: pytest.MonkeyPatch):
    result = types.CallToolResult(content=[types.TextContent(type="text", text="hi")])
    session = _FakeSession(tools=[_echo_tool()], call_results={"echo": result})
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config(forward_requester=True)})
    monkeypatch.setattr(extensions, "current_username", lambda: "alice")
    monkeypatch.setattr(extensions, "current_email", lambda: "alice@example.com")

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    await registry.call("reference__echo", {"text": "hi"})

    assert session.metas == [{"requester": {"username": "alice", "email": "alice@example.com"}}]


@pytest.mark.anyio
async def test_proxied_call_without_identity_sends_no_meta(monkeypatch: pytest.MonkeyPatch):
    result = types.CallToolResult(content=[types.TextContent(type="text", text="hi")])
    session = _FakeSession(tools=[_echo_tool()], call_results={"echo": result})
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config(forward_requester=True)})
    monkeypatch.setattr(extensions, "current_username", lambda: "")
    monkeypatch.setattr(extensions, "current_email", lambda: "")

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    await registry.call("reference__echo", {"text": "hi"})

    assert session.metas == [None]


@pytest.mark.anyio
async def test_proxied_call_without_forward_flag_sends_no_meta_even_with_identity(monkeypatch: pytest.MonkeyPatch):
    result = types.CallToolResult(content=[types.TextContent(type="text", text="hi")])
    session = _FakeSession(tools=[_echo_tool()], call_results={"echo": result})
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config()})
    monkeypatch.setattr(extensions, "current_username", lambda: "alice")
    monkeypatch.setattr(extensions, "current_email", lambda: "alice@example.com")

    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    await registry.call("reference__echo", {"text": "hi"})

    assert session.metas == [None]


# --- runtime add()/remove() ---
# Connect and disconnect one extension without disturbing others, after the registry is already running.


@pytest.mark.anyio
async def test_add_connects_a_new_extension_after_connect_all_already_ran(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {})
    mcp = FastMCP(name="test-server")
    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    registry.install(mcp)

    result = types.CallToolResult(content=[types.TextContent(type="text", text="hi")])
    session = _FakeSession(tools=[_echo_tool()], call_results={"echo": result})
    _install_fake_connection(monkeypatch, session)

    status = await registry.add("reference", _config())

    assert status.status == "connected"
    assert status.tools == ["reference__echo"]
    names = {tool.name for tool in await registry.merged_list_tools()}
    assert "reference__echo" in names
    returned = await registry.merged_call_tool("reference__echo", {"text": "hi"})
    assert returned is result


@pytest.mark.anyio
async def test_add_records_a_connect_failure_as_an_error_status_without_raising(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {})
    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    _install_fake_connection(monkeypatch, FileNotFoundError("no such file or directory"))

    status = await registry.add("broken", _config(id="broken"))

    assert status.status == "error"
    assert status.error
    assert not registry.is_proxied("broken__echo")


@pytest.mark.anyio
async def test_remove_disconnects_and_forgets_an_extension(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession(tools=[_echo_tool()])
    _install_fake_connection(monkeypatch, session)
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {"reference": _config()})

    mcp = FastMCP(name="test-server")
    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    registry.install(mcp)

    removed = await registry.remove("reference")

    assert removed is True
    names = {tool.name for tool in await registry.merged_list_tools()}
    assert "reference__echo" not in names
    assert not registry.statuses()
    with pytest.raises(KeyError):
        await registry.call("reference__echo", {})


@pytest.mark.anyio
async def test_remove_returns_false_for_an_unknown_id() -> None:
    registry = extensions.ExtensionRegistry()
    assert await registry.remove("does-not-exist") is False


@pytest.mark.anyio
async def test_remove_of_an_errored_extension_needs_no_live_connection(monkeypatch: pytest.MonkeyPatch):
    """An "error" extension never got a session or exit stack; remove() must still clean up its status entry."""
    monkeypatch.setattr(extensions, "load_extensions_config", lambda path: {})
    registry = extensions.ExtensionRegistry()
    await registry.connect_all(Path("unused.json"))
    _install_fake_connection(monkeypatch, ConnectionRefusedError("refused"))
    status = await registry.add("broken", _config(id="broken"))
    assert status.status == "error"

    removed = await registry.remove("broken")

    assert removed is True
    assert registry.statuses() == []


# --- the genuine, unmocked end-to-end path ---
# The one test that spawns a real subprocess, since the mocked tests can't show the SDK's stdio_client/ClientSession are called correctly against a real MCP server.


def _real_extension_config() -> ExtensionConfig:
    return ExtensionConfig(
        id="reference",
        label="Reference Extension (dev fixture)",
        description="Dev fixture",
        command=sys.executable,
        args=["-m", "src._fixtures.reference_extension_server"],
    )


@pytest.mark.anyio
async def test_real_fixture_server_end_to_end(tmp_path: Path):
    config_path = tmp_path / "config_extensions.json"
    config_path.write_text(
        json.dumps(
            {
                "reference": {
                    "label": "Reference Extension (dev fixture)",
                    "description": "Dev fixture",
                    "command": sys.executable,
                    "args": ["-m", "src._fixtures.reference_extension_server"],
                }
            }
        ),
        encoding="utf-8",
    )

    registry = extensions.ExtensionRegistry()
    try:
        await registry.connect_all(config_path)

        [status] = registry.statuses()
        assert status.status == "connected"
        assert status.error is None
        assert sorted(status.tools) == ["reference__add", "reference__echo"]

        result = await registry.call("reference__add", {"a": 2, "b": 3})
        assert result.isError is False
        assert result.structuredContent == {"result": 5}

        echoed = await registry.call("reference__echo", {"text": "hello"})
        assert echoed.isError is False
        [content_block] = echoed.content
        assert content_block.text == "hello"
    finally:
        await registry.aclose()


@pytest.mark.anyio
async def test_concurrent_calls_to_the_real_fixture_server_both_succeed(tmp_path: Path):
    """Two calls at once on the same session must not cross-deliver results (the concurrency question answered in the module docstring).
    Needs a real subprocess and tasks: the risk is in the SDK's request/response routing."""
    registry = extensions.ExtensionRegistry()
    try:
        await registry._connect_one("reference", _real_extension_config())

        first, second = await asyncio.gather(
            registry.call("reference__add", {"a": 1, "b": 1}),
            registry.call("reference__add", {"a": 10, "b": 10}),
        )

        assert first.structuredContent == {"result": 2}
        assert second.structuredContent == {"result": 20}
    finally:
        await registry.aclose()


@pytest.mark.anyio
async def test_add_then_remove_a_real_extension_tears_down_the_subprocess():
    """Proves the per-extension exit-stack refactor in _connect_one/remove: only a real subprocess shows that
    removing a connection tears it down rather than just forgetting it."""
    registry = extensions.ExtensionRegistry()
    try:
        status = await registry.add("reference", _real_extension_config())
        assert status.status == "connected"
        assert sorted(status.tools) == ["reference__add", "reference__echo"]

        result = await registry.call("reference__add", {"a": 2, "b": 3})
        assert result.structuredContent == {"result": 5}

        # Grab the live session first so the assertion proves this exact connection stopped working,
        # not just that the registry forgot its name.
        session = registry._sessions["reference"]

        removed = await registry.remove("reference")
        assert removed is True

        assert registry.statuses() == []
        assert "reference__add" not in {tool.name for tool in registry.proxied_tool_definitions()}
        with pytest.raises(KeyError):
            await registry.call("reference__add", {"a": 1, "b": 1})

        # The subprocess is gone: a direct call on the session (bypassing the registry) must fail
        # rather than succeed against a still-running process.
        with pytest.raises(Exception):  # noqa: B017 - any failure proves the transport is closed
            await session.list_tools()
    finally:
        await registry.aclose()
