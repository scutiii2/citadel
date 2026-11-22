"""Armory's own MCP tool handlers: who asked, hidden tools, and numbered dependency failures.

FastMCP's defaults are replaced through ``_mcp_server`` (verified on mcp==1.28.0) so every call runs under the signed requester
and a ``DependencyToolError`` becomes a numbered tool result instead of a generic failure."""

from __future__ import annotations

import logging
from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from src.errors import DependencyToolError
from src.services.identity_context import current_email, current_username
from src.services.service_auth import mcp_requester

logger = logging.getLogger(__name__)


class ToolHandlers:
    """The list_tools and call_tool handlers of one FastMCP server."""

    def __init__(self, mcp: FastMCP) -> None:
        self._mcp = mcp

    async def list_tools(self) -> list[types.Tool]:
        """FastMCP's tools minus those with meta={"hidden": True}, which stay callable by name."""
        return [t for t in await self._mcp.list_tools() if not (t.meta or {}).get("hidden")]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Run one tool as the verified requester; a numbered dependency failure is returned as an error result."""
        async with mcp_requester():
            logger.info("tool call %s by %s", name, current_username() or current_email() or "-")
            try:
                return await self._mcp.call_tool(name, arguments)
            except ToolError as error:
                if isinstance(error.__cause__, DependencyToolError):
                    return types.CallToolResult(
                        isError=True, content=[types.TextContent(type="text", text=str(error.__cause__))]
                    )
                raise


def install_tool_handlers(mcp: FastMCP) -> ToolHandlers:
    """Register the handlers on `mcp`; validate_input=False is kept from FastMCP's own registration, which coerces input first."""
    handlers = ToolHandlers(mcp)
    mcp._mcp_server.list_tools()(handlers.list_tools)
    mcp._mcp_server.call_tool(validate_input=False)(handlers.call_tool)
    return handlers
