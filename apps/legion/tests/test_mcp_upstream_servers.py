"""Tools of Legion's own MCP connections (bard__..., lens__...) reach an agent only through its tools.allow."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from mcp import types

from src.agents import agent_spec
from src.agents.agent_spec import ToolScope
from src.tools.mcp_client import mcp_upstream


def tool(name: str) -> types.Tool:
    return types.Tool(name=name, description="d", inputSchema={"type": "object"})


# main is Armory; bard and lens are Legion connections; main__bard__* is Armory's proxied extension of the same name.
CATALOG = [tool("main__tool_ticket_create"), tool("main__bard__tool_bard_speak"), tool("main__scribe__tool_x"),
           tool("bard__tool_bard_speak"), tool("lens__tool_ocr")]


def agent(allow=(), deny=()):
    return SimpleNamespace(id="a", tools=ToolScope(tuple(allow), tuple(deny)))


@pytest.fixture
def upstream(monkeypatch):
    calls: list[str] = []

    def call(name, arguments, **extra):
        calls.append(name)
        return types.CallToolResult(content=[types.TextContent(type="text", text="ok")])

    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: CATALOG)
    monkeypatch.setattr(mcp_upstream.client, "call_tool", call)
    return calls


def listed(allow=(), deny=(), enabled=()):
    with patch.object(mcp_upstream.agent_spec, "current", return_value=agent(allow, deny)):
        return [t.name for t in mcp_upstream.list_tools(list(enabled))]


def test_allows_explicitly_needs_a_matching_allow_glob():
    assert ToolScope().allows_explicitly("bard__x") is False
    assert ToolScope(("bard__*",)).allows_explicitly("bard__x") is True
    assert ToolScope(("bard__*",)).allows_explicitly("lens__x") is False
    assert ToolScope(("bard__*",), ("*x",)).allows_explicitly("bard__x") is False


def test_an_agent_without_an_allow_list_sees_main_tools_only(upstream):
    assert listed() == ["main__tool_ticket_create"]


def test_an_allow_glob_offers_a_connections_tools_without_an_enabled_extension(upstream):
    assert listed(allow=("bard__*", "lens__*")) == ["bard__tool_bard_speak", "lens__tool_ocr"]


def test_deny_wins_over_allow(upstream):
    assert listed(allow=("bard__*",), deny=("*speak",)) == []


def test_the_connection_replaces_the_proxied_extension_of_the_same_name(upstream):
    # main__bard__tool_bard_speak would match bard__* too; only the Legion connection's tool is offered.
    assert listed(allow=("bard__*",), enabled=["bard"]) == ["bard__tool_bard_speak"]


def test_a_proxied_extension_without_a_connection_is_unchanged(upstream):
    assert listed(enabled=["scribe"]) == ["main__tool_ticket_create", "main__scribe__tool_x"]
    assert listed(enabled=[]) == ["main__tool_ticket_create"]


def test_a_tool_the_user_switched_off_is_not_offered(upstream, monkeypatch):
    monkeypatch.setattr(mcp_upstream.tool_filter, "is_blocked", lambda name: name == "lens__tool_ocr")
    assert listed(allow=("bard__*", "lens__*")) == ["bard__tool_bard_speak"]


def test_shared_extensions_uses_the_connection_then_falls_back_to_armory(upstream, monkeypatch):
    shared = agent_spec.load_file(Path(__file__).resolve().parents[1] / "agents" / "shared-extensions.json")
    monkeypatch.setattr(agent_spec, "current", lambda: shared)
    assert [tool.name for tool in mcp_upstream.list_tools(["bard"])] == ["bard__tool_bard_speak"]
    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: CATALOG[:3])
    assert [tool.name for tool in mcp_upstream.list_tools(["bard"])] == ["main__bard__tool_bard_speak"]


def test_no_tool_is_blocked_outside_a_turn():
    assert mcp_upstream.tool_filter.is_blocked("bard__tool_bard_speak") is False
