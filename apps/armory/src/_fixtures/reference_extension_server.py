"""Minimal stdio MCP server (tools ``echo`` and ``add``), a fixture for testing the extensions proxy.
Run as a module: ``.venv_mcp\\Scripts\\python.exe -m src._fixtures.reference_extension_server``."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="reference-extension",
    instructions="Dev fixture for testing mcp_server's extension proxy. Not a real capability.",
)


@mcp.tool()
def echo(text: str) -> str:
    """Return `text` unchanged."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Return a + b."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
