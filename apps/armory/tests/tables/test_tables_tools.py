"""The tables capability through its real MCP tools: which tools exist and how the slash commands map onto them."""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from src import capability_help, commands
from src.services import capability_meta, capability_registry
from src.services.capability_loader import CapabilityLoader


@pytest.fixture
def capability(tmp_path, monkeypatch):
    import src.server

    server = FastMCP("tables-test")
    monkeypatch.setattr(src.server, "mcp", server)
    monkeypatch.setattr(capability_registry, "_REGISTRY", {})
    monkeypatch.setattr(capability_meta, "_BY_FOLDER", {})
    monkeypatch.setattr(commands, "_COMMANDS", {})
    config = tmp_path / "capabilities.json"
    config.write_text("{}")
    loader = CapabilityLoader(server, "src.capabilities", config)
    loader.scan()
    asyncio.run(loader.set_online("data", True))
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def test_the_row_tools_are_one_tool(capability):
    assert set(capability) == {
        "tool_tables_listTables", "tool_tables_describe", "tool_tables_rows",
        "tool_tables_aggregate", "tool_tables_valueCounts",
    }


def test_rows_takes_only_a_table_id_and_has_the_ranking_and_filter_options(capability):
    schema = capability["tool_tables_rows"].inputSchema

    assert schema["required"] == ["table_id"]
    assert set(schema["properties"]) == {"table_id", "conditions", "sort_by", "descending", "limit"}
    assert schema["properties"]["limit"]["maximum"] == 50
    assert all(prop.get("description") for prop in schema["properties"].values())


def test_head_and_top_are_two_slash_commands_over_the_rows_tool(capability):
    by_name = {spec.name: spec.tool_name for spec in commands._COMMANDS.values() if spec.capability == "data"}

    assert by_name == {
        "list": "tool_tables_listTables", "describe": "tool_tables_describe", "head": "tool_tables_rows",
        "top": "tool_tables_rows", "counts": "tool_tables_valueCounts",
    }


def test_help_lists_the_commands_and_the_rows_tool(capability):
    result = capability_help.build_help("data", target="all")

    assert {row["slash_command"] for row in result["commands"]} == {
        "/data list", "/data describe", "/data head", "/data top", "/data counts",
    }
    assert "tool_tables_rows" in str(result)
    assert not any(old in str(result) for old in ("tool_tables_head", "tool_tables_filter", "tool_tables_topN"))
