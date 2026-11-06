"""Verify real capability loading, recursive MCP schema, and dispatch."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP

from src import capability_help, commands
from src.services import capability_meta, capability_registry
from src.services.capability_loader import CapabilityLoader


@pytest.fixture
async def capability(tmp_path, monkeypatch):
    import src.server

    server = FastMCP("math-test")
    monkeypatch.setattr(src.server, "mcp", server)
    monkeypatch.setattr(capability_registry, "_REGISTRY", {})
    monkeypatch.setattr(capability_meta, "_BY_FOLDER", {})
    monkeypatch.setattr(commands, "_COMMANDS", {})
    config = tmp_path / "capabilities.json"
    config.write_text("{}", encoding="utf-8")
    loader = CapabilityLoader(server, "src.capabilities", config)
    loader.scan()
    await loader.set_online("math", True)
    return server, loader


@pytest.mark.asyncio
async def test_mcp_schema_has_exactly_two_required_parameters(capability):
    server, _ = capability
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert "tool_math_solve" in tools
    tool = tools["tool_math_solve"]
    schema = tool.inputSchema
    assert set(schema["properties"]) == {"equation", "data"}
    assert set(schema["required"]) == {"equation", "data"}
    assert schema["properties"]["data"]["type"] == "array"
    assert "EquationBinding" in json.dumps(schema)
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.openWorldHint is False
    assert "equation" in tool.meta["keywords"]
    assert tool.meta["display_label"]
    for name in ("batch", "continue", "table", "matrix", "calculus"):
        fields = {"operation", "data"} if name == "matrix" else {"expression", "data"} if name == "calculus" else {"equation", "data"}
        assert set(tools[f"tool_math_{name}"].inputSchema["properties"]) == fields
        assert set(tools[f"tool_math_{name}"].inputSchema["required"]) == fields


@pytest.mark.asyncio
async def test_advanced_and_continuation_dispatch_in_isolated_workers(capability):
    server, _ = capability
    first = (await server.call_tool("tool_math_solve", {"equation": "y=1/2", "data": []}))[1]
    following = (await server.call_tool("tool_math_continue", {"equation": "z=y+1", "data": {"previous": first}}))[1]
    assert following["solutions"][0]["values"]["z"]["exact"] == "3/2"
    matrix = (await server.call_tool("tool_math_matrix", {"operation": "determinant", "data": {"matrices": [[[1, 2], [3, 4]]]}}))[1]
    assert matrix["value"]["exact"] == "-2"
    derivative = (await server.call_tool("tool_math_calculus", {"expression": "x^3", "data": {"operation": "differentiate", "variable": "x"}}))[1]
    assert derivative["value"]["exact"] == "3*x**2"
    assert derivative["resources"]["hard_limits"] is True


@pytest.mark.asyncio
async def test_table_mcp_identity_and_complete_progress_records(capability, monkeypatch):
    from mcp.server.fastmcp import Context
    from src.capabilities.tables.utils import tables
    from src.capabilities.tables.utils.tables import ParsedTable, TableRegistry
    from src.services import identity_context

    server, _ = capability
    registry = TableRegistry()
    monkeypatch.setattr(tables, "registry", registry)
    attached = registry.add("alice", "input.csv", ParsedTable(columns=["Input"], kinds=["number"], data=[[2, 3]], row_count=2, sheet=None, notes=[]), size_bytes=100)
    events = []
    async def progress(self, completed, total, message):
        events.append(json.loads(message))
    monkeypatch.setattr(Context, "report_progress", progress)
    token = identity_context._username.set("alice")
    try:
        args = {"equation": "y=2*x", "data": {"table_id": attached.id, "columns": {"x": "Input"}}}
        result = (await server.call_tool("tool_math_table", args))[1]
        assert result["success_count"] == 2 and result["progress_delivered"] == 2, result
        assert [event["completed"] for event in events] == [1, 2]
        assert {event["record"]["result"]["solutions"][0]["values"]["y"]["exact"] for event in events} == {"4", "6"}
        identity_context._username.set("bob")
        denied = (await server.call_tool("tool_math_table", args))[1]
        assert denied["status"] == "invalid" and not denied["records"]
    finally:
        identity_context._username.reset(token)


@pytest.mark.asyncio
async def test_mcp_dispatches_recursive_complex_math(capability):
    server, _ = capability
    result = await server.call_tool("tool_math_solve", {"equation": "y = b + 1", "data": [
        {"type": "equation", "name": "b", "value": {"equation": "b = sqrt(-1)", "data": []}},
    ]})
    # FastMCP returns text content plus structured output for typed models.
    structured = result[1]
    assert structured["status"] == "unique"
    assert structured["solutions"][0]["values"]["y"]["exact"] == "1 + I"


@pytest.mark.asyncio
async def test_help_and_slash_command_use_registered_tool(capability):
    registered = [item for item in commands.all_commands() if item.capability == "math"]
    assert [(item.name, item.tool_name) for item in registered] == [(name, f"tool_math_{name}") for name in ("solve", "batch", "continue", "table", "matrix", "calculus")]
    index = capability_help.build_index()
    assert any(row["capability"] == "/math" for row in index["capabilities"])


@pytest.mark.asyncio
async def test_capability_can_be_disabled_and_reloaded(capability):
    server, loader = capability
    await loader.set_online("math", False)
    assert "tool_math_solve" not in {tool.name for tool in await server.list_tools()}
    await loader.set_online("math", True)
    result = await server.call_tool("tool_math_solve", {"equation": "2 + 2", "data": []})
    assert result[1]["value"]["exact"] == "4"


@pytest.mark.asyncio
async def test_structured_equation_dispatch_keeps_exactly_two_parameters(capability):
    server, _ = capability
    result = await server.call_tool("tool_math_solve", {
        "equation": {"expression": "cos(x)=x", "method": "numeric", "domain": "real", "precision": 30,
                     "numerical": {"initial_guesses": [{"x": 0.5}]}, "trace": True},
        "data": [],
    })
    assert result[1]["status"] == "approximate"
    assert result[1]["completeness"] == "partial"
    assert result[1]["verification"]["status"] == "numeric"
    assert result[1]["trace"]
