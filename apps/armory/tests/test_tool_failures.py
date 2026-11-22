"""Numbered failures travel through Armory's normal MCP handler."""

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from src.services.tool_handlers import ToolHandlers


@pytest.mark.parametrize(("capability", "name", "dependency", "args"), [
    ("web_research", "tool_web_search", "tavily", {"query": "q"}),
    ("firecrawl", "tool_scrape_page", "firecrawl", {"url": "https://page.invalid"}),
    ("email", "tool_email_sendEmail", "smtp", {"to": "user@example.com", "subject": "s", "body_text": "body"}),
])
async def test_transport_failure_is_numbered(monkeypatch, capability, name, dependency, args):
    from importlib import import_module

    module = import_module(f"src.capabilities.{capability}.tool")

    def down(*args, **kwargs):
        raise httpx.ConnectError("private host")

    if capability == "email":
        monkeypatch.setattr(module.domain.desk, "send", down)
    else:
        monkeypatch.setattr(module, "_client", down)

    server = FastMCP("armory-test")
    server.tool()(getattr(module, name))
    handlers = ToolHandlers(server)
    result = await handlers.call_tool(name, args)
    assert result.isError
    assert result.content[0].text == f"[1002] DEP_UNAVAILABLE {dependency} unavailable"


async def test_unexpected_tool_failure_hides_exception_text(monkeypatch):
    from src.capabilities.web_research import tool

    def broken():
        raise RuntimeError("private host")

    monkeypatch.setattr(tool, "_client", broken)
    server = FastMCP("armory-test")
    server.tool()(tool.tool_web_search)
    handlers = ToolHandlers(server)
    result = await handlers.call_tool("tool_web_search", {"query": "q"})
    assert result.isError
    assert "Something went wrong" in result.content[0].text
    assert "private host" not in result.content[0].text


async def test_malformed_tavily_score_is_a_safe_dependency_failure(monkeypatch):
    from src.capabilities.web_research import tool

    class BadTavily:
        def search(self, *args):
            return [{"url": "https://page.invalid", "score": "private details"}]

    monkeypatch.setattr(tool, "_client", BadTavily)
    server = FastMCP("armory-test")
    server.tool()(tool.tool_web_search)
    handlers = ToolHandlers(server)
    result = await handlers.call_tool("tool_web_search", {"query": "q"})
    assert result.isError
    assert result.content[0].text == "[1005] DEP_ERROR tavily returned an error"
