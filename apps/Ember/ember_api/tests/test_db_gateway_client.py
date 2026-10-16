"""DbGatewayClient against a mock transport, plus the app wiring and config."""

import asyncio
import functools
import json

import httpx
import pytest

from src.config import DbGatewaySettings
from src.services.config_validation import _check_app
from src.services.db_gateway import DbGatewayClient, DbGatewayError, DbGatewayUnavailable

BASE = "/instances/ember/connections/data"


def sync(test):
    """Run an async test with asyncio.run (this project's tests are sync, no pytest-asyncio)."""

    @functools.wraps(test)
    def run():
        asyncio.run(test())

    return run


def make_client(handler, token: str | None = "tok") -> DbGatewayClient:
    http = httpx.AsyncClient(base_url="http://gateway", transport=httpx.MockTransport(handler))
    return DbGatewayClient(http, "ember", "data", token)


@sync
async def test_get_returns_doc_and_sends_token_and_encoded_path():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"doc": {"a": 1}})

    assert await make_client(handler).get("my col", "k/1") == {"a": 1}
    assert seen[0].method == "GET"
    assert seen[0].url.raw_path.decode() == f"{BASE}/collections/my%20col/records/k%2F1"
    assert seen[0].headers["X-Internal-Token"] == "tok"


@sync
async def test_no_token_header_when_not_configured():
    def handler(request):
        assert "X-Internal-Token" not in request.headers
        return httpx.Response(200, json={"doc": {}})

    await make_client(handler, token=None).get("c", "k")


@sync
async def test_missing_record_is_none_and_false():
    def handler(request):
        return httpx.Response(404, json={"error": "no record 'k' in 'c'"})

    client = make_client(handler)
    assert await client.get("c", "k") is None
    assert await client.delete("c", "k") is False


@sync
async def test_unknown_instance_404_is_an_error_not_a_missing_record():
    def handler(request):
        return httpx.Response(404, json={"error": "ember"})

    with pytest.raises(DbGatewayError, match="404"):
        await make_client(handler).get("c", "k")


@sync
async def test_put_sends_doc_body():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    await make_client(handler).put("c", "k", {"a": 1})
    assert seen[0].method == "PUT" and json.loads(seen[0].content) == {"doc": {"a": 1}}


@sync
async def test_delete_true_when_removed():
    assert await make_client(lambda r: httpx.Response(200, json={"ok": True})).delete("c", "k") is True


@sync
async def test_query_sends_filters_and_returns_docs():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"docs": [{"r": "x"}]})

    docs = await make_client(handler).query("c", {"r": "x"}, limit=5, offset=2)
    assert docs == [{"r": "x"}]
    assert seen[0].url.path == f"{BASE}/collections/c/query"
    assert json.loads(seen[0].content) == {"filters": {"r": "x"}, "limit": 5, "offset": 2}


@sync
async def test_server_error_message_is_carried():
    def handler(request):
        return httpx.Response(401, json={"error": "Invalid or missing internal API token"})

    with pytest.raises(DbGatewayError, match="401.*Invalid or missing"):
        await make_client(handler).put("c", "k", {})


@sync
async def test_unreachable_gateway_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = make_client(handler)
    for call in (client.get("c", "k"), client.put("c", "k", {}), client.query("c")):
        with pytest.raises(DbGatewayUnavailable):
            await call


def test_app_exposes_the_injected_store(client, db_gateway):
    assert client.app.state.db_gateway is db_gateway


def test_settings_defaults_and_validation():
    assert DbGatewaySettings.from_config({}) == DbGatewaySettings("http://127.0.0.1:8071", "ember", "data")
    assert DbGatewaySettings.from_config({"url": "http://h:1/"}).url == "http://h:1"
    assert _check_app({"db_gateway": {"url": "nope", "instance": ""}}) == [
        ("db_gateway.url", "must be an http(s) URL"),
        ("db_gateway.instance", "must be a non-empty string"),
    ]
    assert _check_app({"db_gateway": {"url": "http://h:1", "instance": "i", "connection": "c"}}) == []
