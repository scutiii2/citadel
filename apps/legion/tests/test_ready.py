"""Readiness uses the service assertion boundary on the real MCP HTTP app."""

import asyncio

import httpx

from src.citadel_auth import ServiceAuth
from src.citadel_auth.testing import make_stack
from src.server import mcp
from src.runtime.internal_auth import install_auth


def test_health_is_open_and_ready_reports_unreachable_peers(tmp_path):
    asyncio.run(check_routes(tmp_path))


async def check_routes(tmp_path):
    stack = await make_stack(tmp_path)
    app = mcp.streamable_http_app()
    install_auth(app, stack["legion"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://legion") as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).status_code == 401
        response = await client.get("/ready", auth=ServiceAuth(stack["portcullis"], "legion"))
    assert response.status_code == 200
    report = response.json()
    assert report["service"] == "legion" and report["status"] == "up"
    assert {item["name"] for item in report["dependencies"]} == {"treasury", "armory", "stronghold"}
