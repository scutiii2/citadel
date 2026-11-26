"""Origins of one outside service: order, token choice, failover and the way back."""

from __future__ import annotations

import asyncio
import socket
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace

import httpx2
import pytest
from mcp.shared.exceptions import MCPError
from mcp_types import CONNECTION_CLOSED, REQUEST_TIMEOUT

from src.tools.mcp_client import registry as registry_module
from src.tools.mcp_client.config import validate_server
from src.tools.mcp_client.registry import McpClientRegistry, is_connection_failure
from src.tools.mcp_client import transports
from src.tools.mcp_client.transports import open_session

ENTRY = {"label": "Bard", "transport": "http", "service_id": "s", "path": "/mcp",
         "auth": {"type": "header", "header_name": "X-Internal-Token", "header_value": "parent"},
         "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}
ADDRESS = {"o1": "http://one:1", "o2": "http://two:2"}


class _Listed:
    tools: list = []


class _Session:
    def __init__(self, url, error=None):
        self.url, self.error = url, error

    async def list_tools(self):
        return _Listed()

    async def call_tool(self, name, arguments, read_timeout_seconds, **extra):
        if self.error is not None:
            raise self.error
        return self.url


@pytest.fixture
def world(monkeypatch):
    state = {"down": set(), "opened": [], "clock": 100.0, "call_error": None}

    async def fake_open(stack, config, timeout, extra_headers=None, auth=None):
        if config.url in state["down"]:
            raise ConnectionError("refused")
        token = config.auth.header_value if config.auth else None
        state["opened"].append((config.url, token))
        return _Session(config.url, state["call_error"])

    monkeypatch.setattr(registry_module, "open_session", fake_open)
    registry = McpClientRegistry(resolve_origin=ADDRESS.__getitem__)
    registry._clock = lambda: state["clock"]
    registry._configs = {"bard": validate_server("bard", ENTRY)}
    return registry, state


def test_it_uses_the_first_origin_with_the_parent_token(world):
    registry, state = world
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.status == "connected" and status.origin_id == "o1"
    assert state["opened"] == [("http://one:1/mcp", "parent")]


def test_it_falls_to_the_next_origin_and_uses_its_override_token(world):
    registry, state = world
    state["down"].add("http://one:1/mcp")
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.origin_id == "o2" and state["opened"] == [("http://two:2/mcp", "second")]
    assert len(registry.statuses()) == 1


def test_all_origins_down_is_one_error_status(world):
    registry, state = world
    state["down"] |= {"http://one:1/mcp", "http://two:2/mcp"}
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.status == "error" and "ConnectionError" in status.error
    assert [s.status for s in registry.statuses()] == ["error"]


def test_an_unknown_origin_id_is_skipped(world, monkeypatch):
    registry, state = world
    registry._resolve_origin = {"o2": "http://two:2"}.__getitem__  # o1 left the catalog (KeyError)
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.origin_id == "o2"


def test_a_call_that_loses_its_origin_fails_once_and_the_next_call_uses_the_next_origin(world):
    registry, state = world
    asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    registry._sessions["bard"] = _Session("http://one:1/mcp", error=ConnectionError("gone"))
    with pytest.raises(ConnectionError):
        asyncio.run(registry.call_tool("bard__x", {}))
    assert registry._active["bard"] == "o2"
    assert asyncio.run(registry.call_tool("bard__x", {})) == "http://two:2/mcp"


def test_an_answer_that_is_not_a_connection_failure_does_not_fail_over(world):
    registry, state = world
    asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    registry._sessions["bard"] = _Session("http://one:1/mcp", error=ValueError("bad arguments"))
    with pytest.raises(ValueError):
        asyncio.run(registry.call_tool("bard__x", {}))
    assert registry._active["bard"] == "o1"


def test_it_returns_to_the_primary_when_the_cooldown_has_passed(world):
    registry, state = world
    state["down"].add("http://one:1/mcp")
    asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert registry._active["bard"] == "o2"
    state["down"].clear()
    asyncio.run(registry.list_tools())
    assert registry._active["bard"] == "o2"          # still cooling down
    state["clock"] += registry_module.ORIGIN_COOLDOWN_SECONDS + 1
    asyncio.run(registry.list_tools())
    assert registry._active["bard"] == "o1"


@pytest.mark.parametrize("error, expected", [
    (ConnectionError("x"), True), (TimeoutError(), True), (httpx2.ConnectError("x"), True),
    (httpx2.ReadTimeout("x"), True),
    (MCPError(REQUEST_TIMEOUT, "timed out"), True), (MCPError(CONNECTION_CLOSED, "closed"), True),
    (MCPError(-32602, "bad params"), False),
    (ValueError("x"), False), (RuntimeError("Session terminated"), False),
])
def test_only_a_dead_or_silent_origin_counts_as_a_connection_failure(error, expected):
    assert is_connection_failure(error) is expected


def test_a_rejected_handshake_does_not_try_another_origin(world, monkeypatch):
    registry, _ = world
    attempted = []

    async def denied(_stack, config, _timeout, _headers):
        attempted.append(config.url)
        raise MCPError(403, "denied")

    monkeypatch.setattr(registry_module, "open_session", denied)
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.status == "error"
    assert attempted == ["http://one:1/mcp"]
    asyncio.run(registry.list_tools())
    assert attempted == ["http://one:1/mcp", "http://one:1/mcp"]


def test_origins_down_at_start_are_resolved_again_after_cooldown(world):
    registry, state = world
    state["down"] |= {"http://one:1/mcp", "http://two:2/mcp"}
    asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    state["down"].clear()
    asyncio.run(registry.list_tools())
    assert registry.statuses()[0].status == "error"
    state["clock"] += registry_module.ORIGIN_COOLDOWN_SECONDS + 1
    asyncio.run(registry.list_tools())
    assert registry.statuses()[0].origin_id == "o1"


def test_dns_failure_during_origin_connect_is_a_connection_error(monkeypatch):
    async def unresolved(_host, _port):
        raise socket.gaierror("no address")

    monkeypatch.setattr(asyncio, "open_connection", unresolved)
    target = replace(validate_server("bard", ENTRY), url="http://one:1/mcp")
    async def connect():
        async with AsyncExitStack() as stack:
            await open_session(stack, target, timeout_seconds=1)

    with pytest.raises(ConnectionError):
        asyncio.run(connect())


def test_an_origin_transport_rejects_a_different_scheme_before_sending_credentials(monkeypatch):
    async def reachable(_url, _timeout):
        return None

    @asynccontextmanager
    async def attempt(url, *, http_client):
        for check in http_client.event_hooks["request"]:
            await check(httpx2.Request("POST", url))
            await check(httpx2.Request("POST", "https://one/mcp"))
        pytest.fail("Unlisted origin was accepted")
        yield

    monkeypatch.setattr(transports, "_check_tcp_reachable", reachable)
    monkeypatch.setattr(transports, "streamable_http_client", attempt)
    target = replace(validate_server("bard", ENTRY), url="http://one/mcp")

    async def connect():
        async with AsyncExitStack() as stack:
            await open_session(stack, target, timeout_seconds=1)

    with pytest.raises(transports.AuthResolutionError):
        asyncio.run(connect())


def test_a_call_timeout_does_not_mask_the_transport_owner_http_refusal(world, monkeypatch):
    registry, _ = world

    async def run():
        refused, closed = asyncio.Event(), asyncio.Event()
        target_url = "http://one:1/mcp"
        request = httpx2.Request("POST", target_url)
        refusal = httpx2.HTTPStatusError("Unauthorized", request=request,
                                       response=httpx2.Response(401, request=request))

        class RefusedSession(_Session):
            async def call_tool(self, name, arguments, read_timeout_seconds, **extra):
                refused.set()
                await closed.wait()
                raise MCPError(REQUEST_TIMEOUT, "timed out")

        @asynccontextmanager
        async def transport():
            async def respond():
                await refused.wait()
                raise refusal

            try:
                async with asyncio.TaskGroup() as requests:
                    requests.create_task(respond())
                    yield
            finally:
                closed.set()

        async def fake_open(stack, config, _timeout, _headers):
            if config.url == target_url:
                await stack.enter_async_context(transport())
                return RefusedSession(target_url)
            return _Session(config.url)

        monkeypatch.setattr(registry_module, "open_session", fake_open)
        try:
            assert (await registry._connect_one("bard", registry._configs["bard"])).origin_id == "o1"
            with pytest.raises(MCPError):
                await registry.call_tool("bard__x", {})
            assert registry.statuses()[0].origin_id == "o1"
        finally:
            await registry.aclose()

    asyncio.run(run())
