import asyncio

import httpx

from src.runtime import connection_probe
from src.runtime.gateway_settings import GatewaySettings


def _probe(handler, call):
    connection_probe._TRANSPORT = httpx.MockTransport(handler)
    try:
        return asyncio.run(call)
    finally:
        connection_probe._TRANSPORT = None


def test_gateway_ready_not_ready_and_refused():
    settings = GatewaySettings("http://gw.test:29407", "cg_secret")
    seen = {}

    def ready(request):
        seen["token"] = request.headers.get("x-internal-token")
        return httpx.Response(200, json={"ok": True, "ready": True})

    assert _probe(ready, connection_probe.probe_gateway(settings))["ok"] is True
    assert seen["token"] == "cg_secret"
    empty = _probe(lambda r: httpx.Response(200, json={"ok": True, "ready": False}), connection_probe.probe_gateway(settings))
    assert empty["ok"] is False and "no gateway is saved" in empty["message"]
    refused = _probe(lambda r: httpx.Response(401), connection_probe.probe_gateway(settings))
    assert refused == {"ok": False, "message": "The token was refused."}


def test_gateway_unreachable_has_a_message_and_no_secret():
    def down(request):
        raise httpx.ConnectError("boom cg_secret")

    answer = _probe(down, connection_probe.probe_gateway(GatewaySettings("http://gw.test:29407", "cg_secret")))
    assert answer == {"ok": False, "message": "Could not connect to this address."}


def test_server_checks_each_address_and_stdio_is_not_testable():
    entry = {"transport": "http", "url": "http://mcp.test/mcp", "auth": {"type": "header", "header_name": "X-Key", "header_value": "k"}}
    seen = {}

    def answer(request):
        seen["key"] = request.headers.get("x-key")
        return httpx.Response(405)

    result = _probe(answer, connection_probe.probe_server(entry))
    assert result["ok"] is True and seen["key"] == "k"
    assert _probe(lambda r: httpx.Response(503), connection_probe.probe_server(entry))["ok"] is False
    assert asyncio.run(connection_probe.probe_server({"transport": "stdio", "command": "x"}))["ok"] is False
