"""Regression tests for reconnecting an MCP session after it terminates."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from types import SimpleNamespace

import anyio
import pytest
from mcp.shared.exceptions import MCPError
from mcp_types import CONNECTION_CLOSED, INVALID_REQUEST

from src.tools.mcp_client import registry as registry_module
from src.tools.mcp_client.config import ServerConfig
from src.tools.mcp_client.registry import McpClientRegistry


class _Session:
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    async def call_tool(self, name, arguments, read_timeout_seconds):
        if self._error is not None:
            raise self._error
        return self._result


def test_call_tool_reconnects_once_after_a_terminated_session(monkeypatch):
    """A server restart must not require restarting the AI agent."""
    registry = McpClientRegistry()
    first = _Session(error=MCPError(INVALID_REQUEST, "Session terminated"))
    recovered = _Session(result="recovered")
    registry._sessions["main"] = first

    reconnects = []

    async def reconnect(server_id):
        reconnects.append(server_id)
        registry._sessions[server_id] = recovered

    monkeypatch.setattr(registry, "_reconnect", reconnect)

    result = asyncio.run(registry.call_tool("main__parse_excel_input_tool", {"file_path": "test_input.xlsx"}))

    assert result == "recovered"
    assert reconnects == ["main"]


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


def test_a_saved_server_reconnects_from_another_task_without_breaking_its_neighbour(monkeypatch):
    @asynccontextmanager
    async def scoped_transport():
        # The SDK transports hold a task group, which only the opening task may close.
        async with anyio.create_task_group():
            yield

    class Listing:
        def __init__(self, name):
            self.name = name

        async def list_tools(self):
            return SimpleNamespace(tools=[])

        async def call_tool(self, name, arguments, read_timeout_seconds):
            return self.name

    async def fake_open(stack, config, timeout, extra_headers=None, auth=None):
        await stack.enter_async_context(scoped_transport())
        return Listing(config.id)

    monkeypatch.setattr(registry_module, "open_session", fake_open)

    async def run():
        registry = McpClientRegistry()
        for name in ("one", "two"):
            registry._configs[name] = ServerConfig(name, name, "", "http", url=f"http://{name}/mcp")
            await registry._connect_one(name, registry._configs[name])
        await asyncio.create_task(registry._reconnect("one"))
        assert await registry.call_tool("two__x", {}) == "two"
        assert await registry.call_tool("one__x", {}) == "one"
        await registry.aclose()

    asyncio.run(run())
