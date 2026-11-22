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
    assert {item["name"] for item in report["dependencies"]} == {"treasury", "armory", "stronghold", "conversation-gateway", "decision-gateway"}


def test_gateway_probe_keeps_a_saved_address_when_treasury_is_slow(monkeypatch):
    from src.ready import _gateway_address
    from src.runtime import gateway_settings

    async def stalls():
        await asyncio.sleep(4)
        return gateway_settings.GatewaySettings("http://stale:9000", "")

    monkeypatch.setattr(gateway_settings, "current", lambda which: stalls())
    monkeypatch.setitem(gateway_settings._cache, gateway_settings.KEY,
                        (gateway_settings.GatewaySettings("http://saved:9000", ""), 0))
    assert asyncio.run(_gateway_address(gateway_settings.KEY)) == "http://saved:9000"
