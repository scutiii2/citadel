"""Shared FastMCP server instance; keep it free of tool definitions so modules can import `mcp` and register onto it.
`name` and `instructions` are what a client sees on connect; rewrite them to match the server's purpose."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from src.config import settings

# host=settings.host (not the library's 127.0.0.1) matters: FastMCP enables Host-header DNS-rebinding protection
# only when it thinks it is loopback-only, which made other containers' requests fail with 421.
mcp = FastMCP(
    name="mcp-server",
    instructions=(
        "MCP tool server. Each tool's own description "
        "states when to use it - prefer that over guessing from the name."
    ),
    host=settings.host,
)
