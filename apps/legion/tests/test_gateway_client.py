"""Legion's client for the built-in ConversationGateway: requests in, typed errors out."""

from __future__ import annotations

import asyncio

import pytest

from src import gateway
from src.gateway.conversation.errors import GatewayError
from src.providers import gateway_client
from src.providers.gateway_client import ConversationGatewayClient, GatewayCallError

# conftest replaces is_saved for every test; these tests check the real one.
is_saved = gateway_client.is_saved

DONE = {"type": "done", "content": [{"type": "text", "text": "Hi"}], "stop_reason": "end",
        "usage": {"input_tokens": 3, "output_tokens": 1, "cached_input_tokens": 0, "reasoning_tokens": 0}}
BODY = {"gateway": "claude", "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]}


class FakeChat:
    def __init__(self, events=(), error: GatewayError | None = None, reply=None):
        self.events, self.error, self.reply, self.requests = list(events), error, reply, []

    async def stream(self, request):
        self.requests.append(request)
        for event in self.events:
            yield event
        if self.error:
            raise self.error

    async def chat(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.reply


class FakeStore:
    def __init__(self, ids):
        self.ids, self.reads = ids, 0

    def all(self):
        self.reads += 1
        return {i: {} for i in self.ids}


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    gateway_client.reset_cache()
    yield
    gateway_client.reset_cache()


def use(monkeypatch, chat: FakeChat) -> FakeChat:
    monkeypatch.setattr(gateway, "chat_service", lambda: chat)
    return chat


def collect(body: dict) -> list[dict]:
    client = ConversationGatewayClient()

    async def run() -> list[dict]:
        return [event async for event in client.stream(body)]

    return asyncio.run(run())


def test_stream_yields_events_in_order(monkeypatch):
    chat = use(monkeypatch, FakeChat([{"type": "text", "delta": "Hi"}, DONE]))
    events = collect(BODY)
    assert [event["type"] for event in events] == ["text", "done"]
    assert chat.requests[0].gateway == "claude" and chat.requests[0].stream is True


def test_a_gateway_error_becomes_a_typed_error_with_retry_after(monkeypatch):
    use(monkeypatch, FakeChat(error=GatewayError(429, "gateway_rate_limit", "slow down", "rate_limit", 7)))
    with pytest.raises(GatewayCallError) as caught:
        collect(BODY)
    error = caught.value
    assert (error.status, error.code, error.kind, error.retry_after, str(error)) == (
        429, "gateway_rate_limit", "rate_limit", 7.0, "slow down")


def test_error_mid_stream_raises(monkeypatch):
    use(monkeypatch, FakeChat([{"type": "text", "delta": "Hi"}], GatewayError(502, "gateway_unavailable", "cut", "unavailable")))
    with pytest.raises(GatewayCallError) as caught:
        collect(BODY)
    assert (caught.value.status, caught.value.kind) == (502, "unavailable")


def test_stream_without_done_is_unavailable(monkeypatch):
    use(monkeypatch, FakeChat([{"type": "text", "delta": "Hi"}]))
    with pytest.raises(GatewayCallError) as caught:
        collect(BODY)
    assert caught.value.kind == "unavailable"


def test_an_invalid_request_keeps_kind_none(monkeypatch):
    use(monkeypatch, FakeChat())
    with pytest.raises(GatewayCallError) as caught:
        collect({"gateway": "claude", "messages": "nope"})
    assert (caught.value.status, caught.value.kind) == (422, None)


def test_chat_sync_returns_the_reply(monkeypatch):
    chat = use(monkeypatch, FakeChat(reply={"content": [{"type": "text", "text": "Hi"}], "stop_reason": "end"}))
    assert ConversationGatewayClient().chat_sync(BODY)["stop_reason"] == "end"
    assert chat.requests[0].stream is False


def test_saved_gateway_ids_is_cached(monkeypatch):
    store = FakeStore(["claude", "openrouter"])
    monkeypatch.setattr(gateway, "chat_store", lambda: store)
    assert gateway_client.saved_gateway_ids() == frozenset({"claude", "openrouter"})
    assert is_saved("claude") and not is_saved("bedrock")
    assert store.reads == 1
