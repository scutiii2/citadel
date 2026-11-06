"""MCP surfaces expose coverage controls and independent batch results."""

from __future__ import annotations

import pytest

from test_tool import capability  # noqa: F401 - shared real capability loader fixture


@pytest.mark.asyncio
async def test_batch_tool_has_two_required_parameters_and_read_only_metadata(capability):
    server, _ = capability
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert "tool_math_batch" in tools
    tool = tools["tool_math_batch"]
    assert set(tool.inputSchema["properties"]) == {"equation", "data"}
    assert set(tool.inputSchema["required"]) == {"equation", "data"}
    assert tool.annotations.readOnlyHint is True
    assert tool.meta["keywords"]
    result = await server.call_tool("tool_math_batch", {"equation": "y=x+1", "data": [
        {"id": "a", "data": [{"type": "constant", "name": "x", "value": 2}]},
    ]})
    assert result[1]["records"][0]["result"]["solutions"][0]["values"]["y"]["exact"] == "3"


@pytest.mark.asyncio
async def test_certification_and_cases_dispatch_through_original_solve(capability):
    server, _ = capability
    result = await server.call_tool("tool_math_solve", {"equation": {
        "expression": ["x^2=2"], "method": "certified", "domain": "real", "solve_for": ["x"],
    }, "data": []})
    assert result[1]["certificate"]["distinct_roots"] == 2
    split = await server.call_tool("tool_math_solve", {"equation": {
        "expression": "m*x=0", "solve_for": ["x"], "split_cases": True,
    }, "data": []})
    assert len(split[1]["cases"]) == 2


@pytest.mark.asyncio
async def test_malformed_batch_envelope_does_not_reject_valid_neighbors(capability):
    server, _ = capability
    result = await server.call_tool("tool_math_batch", {"equation": "x=1", "data": [{"data": []}, None, {"data": []}]})
    assert [row["result"]["status"] for row in result[1]["records"]] == ["unique", "invalid", "unique"]
