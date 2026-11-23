import asyncio

import httpx

from src.runtime import connection_probe


def _probe(handler, call):
    connection_probe._TRANSPORT = httpx.MockTransport(handler)
    try:
        return asyncio.run(call)
    finally:
        connection_probe._TRANSPORT = None


def test_server_checks_each_address_and_stdio_is_not_testable():
    entry = {"transport": "http", "url": "http://mcp.test/mcp", "auth": {"type": "header", "header_name": "X-Key", "header_value": "k"}}
    seen = {}

    def answer(request):
        seen["key"] = request.headers.get("x-key")
        return httpx.Response(405)

    result = _probe(answer, connection_probe.probe_server(entry))
    assert result["ok"] is True and seen["key"] == "k"
    down = _probe(lambda r: httpx.Response(503), connection_probe.probe_server(entry))
    assert down["ok"] is False and down["code"] == "503" and down["origins"][0]["code"] == "503"
    assert _probe(lambda r: httpx.Response(401), connection_probe.probe_server(entry))["code"] == "401"
    assert asyncio.run(connection_probe.probe_server({"transport": "stdio", "command": "x"}))["ok"] is False
