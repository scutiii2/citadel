"""Legion's HTTP client for ConversationGateway: wire format in, typed errors out."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.providers import gateway_client
from src.providers.gateway_client import ConversationGatewayClient, GatewayCallError

# conftest replaces is_saved for every test; these tests check the real one.
is_saved = gateway_client.is_saved

DONE = {"type": "done", "content": [{"type": "text", "text": "Hi"}], "stop_reason": "end",
        "usage": {"input_tokens": 3, "output_tokens": 1, "cached_input_tokens": 0, "reasoning_tokens": 0}}


def ndjson(*events: dict) -> bytes:
    return "".join(json.dumps(event) + "\n" for event in events).encode()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("CONVERSATION_GATEWAY_URL", "http://gateway.test:29407/")
    monkeypatch.setenv("CONVERSATION_GATEWAY_TOKEN", "cg_test")
    gateway_client.reset_cache()
    yield
    gateway_client.reset_cache()


def collect(handler, body: dict) -> list[dict]:
    """Legion has no async pytest plugin; tests drive coroutines with asyncio.run."""
    client = ConversationGatewayClient(transport=httpx.MockTransport(handler))

    async def run() -> list[dict]:
        return [event async for event in client.stream(body)]

    return asyncio.run(run())


def test_stream_posts_the_body_and_yields_events():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ndjson({"type": "text", "delta": "Hi"}, DONE))

    events = collect(handler, {"gateway": "claude", "messages": []})
    assert [event["type"] for event in events] == ["text", "done"]
    assert str(seen[0].url) == "http://gateway.test:29407/api/chat"
    assert seen[0].headers["x-internal-token"] == "cg_test"
    assert seen[0].headers["x-requester-username"] == "legion"
    assert json.loads(seen[0].content) == {"gateway": "claude", "messages": [], "stream": True}


def test_http_error_becomes_a_typed_error_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "7"},
                              json={"error": {"code": "gateway_rate_limit", "message": "slow down", "kind": "rate_limit"}})

    with pytest.raises(GatewayCallError) as caught:
        collect(handler, {"gateway": "claude"})
    error = caught.value
    assert (error.status, error.code, error.kind, error.retry_after, str(error)) == (
        429, "gateway_rate_limit", "rate_limit", 7.0, "slow down")


def test_error_line_mid_stream_raises():
    line = {"type": "error", "status": 502, "error": {"code": "gateway_unavailable", "message": "cut", "kind": "unavailable"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson({"type": "text", "delta": "Hi"}, line))

    with pytest.raises(GatewayCallError) as caught:
        collect(handler, {"gateway": "claude"})
    assert (caught.value.status, caught.value.kind) == (502, "unavailable")


def test_stream_without_done_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson({"type": "text", "delta": "Hi"}))

    with pytest.raises(GatewayCallError) as caught:
        collect(handler, {"gateway": "claude"})
    assert caught.value.kind == "unavailable"


def test_unreachable_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(GatewayCallError) as caught:
        collect(handler, {"gateway": "claude"})
    assert (caught.value.status, caught.value.kind) == (502, "unavailable")


def test_an_error_without_kind_keeps_kind_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": {"code": "invalid_request", "message": "bad body"}})

    with pytest.raises(GatewayCallError) as caught:
        collect(handler, {"gateway": "claude"})
    assert (caught.value.status, caught.value.kind) == (422, None)


def test_chat_sync_returns_the_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Hi"}], "stop_reason": "end"})

    client = ConversationGatewayClient(sync_transport=httpx.MockTransport(handler))
    assert client.chat_sync({"gateway": "claude"})["stop_reason"] == "end"


def test_saved_gateway_ids_is_cached(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"gateways": [{"id": "claude"}, {"id": "openrouter"}]})

    monkeypatch.setattr(gateway_client, "_SYNC_TRANSPORT", httpx.MockTransport(handler))
    assert gateway_client.saved_gateway_ids() == frozenset({"claude", "openrouter"})
    assert is_saved("claude") and not is_saved("bedrock")
    assert calls == ["/api/gateways"]


def test_an_unreachable_service_is_unknown_and_not_cached(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(gateway_client, "_SYNC_TRANSPORT", httpx.MockTransport(handler))
    assert gateway_client.saved_gateway_ids() is None
    assert gateway_client._ids is None
    # Unknown counts as saved: the call itself reports the outage, and Legion can start first.
    assert is_saved("claude")
