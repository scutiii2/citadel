"""Tools of Legion's own MCP connections (bard__..., lens__...) reach an agent only through its tools.allow."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from mcp import types

from src.agents import agent_routing, agent_spec
from src.agents.agent_spec import ToolScope
from src.runtime import approvals
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


def call(name, allow=(), deny=()):
    with patch.object(mcp_upstream.agent_spec, "current", return_value=agent(allow, deny)):
        return mcp_upstream.call_tool(name, {})


def test_a_call_by_exact_name_reaches_the_connection_not_the_proxied_extension(upstream):
    assert call("bard__tool_bard_speak", allow=("bard__*",)) == "ok"
    assert upstream == ["bard__tool_bard_speak"]


def test_a_bare_main_tool_name_still_reaches_the_built_in(upstream):
    assert call("tool_ticket_create") == "ok"
    assert upstream == ["main__tool_ticket_create"]


def test_a_connection_tool_the_allow_list_does_not_name_is_refused(upstream):
    with pytest.raises(PermissionError):
        call("lens__tool_ocr", allow=("bard__*",))
    with pytest.raises(PermissionError):
        call("lens__tool_ocr")  # an empty allow list never exposes a connection
    assert upstream == []


def test_a_denied_or_switched_off_connection_tool_is_refused(upstream, monkeypatch):
    with pytest.raises(PermissionError):
        call("bard__tool_bard_speak", allow=("bard__*",), deny=("*speak",))
    monkeypatch.setattr(mcp_upstream.tool_filter, "is_blocked", lambda name: name == "bard__tool_bard_speak")
    with pytest.raises(PermissionError):
        call("bard__tool_bard_speak", allow=("bard__*",))
    assert upstream == []


def test_requester_metadata_reaches_armory_and_stronghold_with_chat_id_only_for_stronghold(upstream, monkeypatch):
    meta = {"requester_token": "test-requester", "chat_id": "chat-1"}
    monkeypatch.setattr(mcp_upstream.internal_auth, "requester_meta", lambda: meta.copy())
    stack_tool = "stronghold__tool_stack_add"
    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: [*CATALOG, tool(stack_tool)])
    assert stack_tool not in listed()
    assert listed(allow=("stronghold__*",)) == [stack_tool]
    with patch.object(mcp_upstream.client, "call_tool", wraps=mcp_upstream.client.call_tool) as dispatch:
        assert call("lens__tool_ocr", allow=("lens__*",)) == "ok"
        dispatch.assert_called_once_with("lens__tool_ocr", {})
        dispatch.reset_mock()
        assert call("tool_ticket_create") == "ok"
        dispatch.assert_called_once_with("main__tool_ticket_create", {}, meta={"requester_token": "test-requester"})
        dispatch.reset_mock()
        assert call(stack_tool, allow=("stronghold__*",)) == "ok"
        dispatch.assert_called_once_with(stack_tool, {}, meta=meta)


def test_an_outside_read_only_hint_does_not_skip_approval(upstream, monkeypatch):
    annotated = CATALOG[-1].model_copy(update={"annotations": types.ToolAnnotations(readOnlyHint=True)})
    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: [annotated])
    assert listed(allow=("lens__*",)) == ["lens__tool_ocr"]
    policy = approvals.ApprovalPolicy("ask", read_only_check=mcp_upstream.is_read_only_builtin)
    assert policy.needs_approval("lens__tool_ocr") is True


def test_the_roster_check_sees_every_connections_tools(upstream):
    names = agent_routing._live_tool_names()
    assert "tool_ticket_create" in names and "bard__tool_bard_speak" in names and "lens__tool_ocr" in names


def test_a_glob_that_matches_no_tool_of_any_connection_is_warned_about(upstream, caplog):
    with patch.object(mcp_upstream.agent_spec, "current", return_value=agent(allow=("lens__*", "nope__*"), deny=("nope__*",))):
        with caplog.at_level(logging.WARNING):
            mcp_upstream.warn_unmatched_tool_globs()
    assert caplog.text.count("nope__*") == 1
    assert "lens__*" not in caplog.text
