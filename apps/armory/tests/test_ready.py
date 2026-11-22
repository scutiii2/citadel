"""Readiness uses the service assertion boundary on the real MCP HTTP app."""

import httpx

from src.citadel_auth import ServiceAuth
from src.citadel_auth.testing import make_stack
from src.server import mcp
from src.services.service_auth import install_auth


async def test_health_is_open_and_ready_reports_unreachable_peers(tmp_path):
    stack = await make_stack(tmp_path)
    app = mcp.streamable_http_app()
    install_auth(app, stack["armory"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://armory") as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).status_code == 401
        response = await client.get("/ready", auth=ServiceAuth(stack["portcullis"], "armory"))
    assert response.status_code == 200
    report = response.json()
    assert report["service"] == "armory" and report["status"] == "up"
    assert {item["name"] for item in report["dependencies"]} == {"treasury"}


async def test_builtin_tools_are_available_while_extensions_connect(tmp_path, monkeypatch):
    import asyncio
    from mcp.server.fastmcp import FastMCP
    from src.services import extensions

    started = asyncio.Event()
    finish = asyncio.Event()

    async def connect(_registry, _path):
        started.set()
        await finish.wait()

    monkeypatch.setattr(extensions.ExtensionRegistry, "connect_all", connect)
    server = FastMCP("startup-test")

    @server.tool()
    async def ping() -> str:
        return "pong"

    connection = asyncio.create_task(extensions.install_extensions(server, tmp_path / "settings.db"))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        assert [tool.name for tool in await extensions.merged_list_tools()] == ["ping"]
    finally:
        finish.set()
        await asyncio.gather(connection, return_exceptions=True)
        await extensions.shutdown_extensions()
