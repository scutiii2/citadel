"""Anthropic-shaped requests and replies translated to and from ConversationGateway."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

from src.providers.gateway_client import GatewayCallError
from src.providers.language.anthropic_gateway_shim import GatewayShim, request_body, response_message

CACHE = {"type": "ephemeral"}
TOOL = {"name": "get_time", "description": "Now.", "input_schema": {"type": "object", "properties": {}}}


def base(**extra):
    return {"model": "claude-sonnet-5-5", "max_tokens": 512, "system": "Be brief.",
            "messages": [{"role": "user", "content": "Hello"}], "tools": [], **extra}


def test_plain_request():
    assert request_body("claude", base()) == {
        "gateway": "claude", "model": "claude-sonnet-5-5", "max_tokens": 512,
        "system": "Be brief.", "messages": [{"role": "user", "content": "Hello"}],
    }


def test_cache_markers_become_the_cache_flag_and_are_stripped():
    body = request_body("claude", base(
        system=[{"type": "text", "text": "Be brief.", "cache_control": CACHE}],
        tools=[{**TOOL, "cache_control": CACHE}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "Hello", "cache_control": CACHE}]}],
    ))
    assert body["cache"] is True
    assert body["system"] == "Be brief."
    assert body["tools"] == [{"name": "get_time", "description": "Now.",
                              "parameters": {"type": "object", "properties": {}}}]
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}]


def test_options_map_to_temperature_and_reasoning():
    body = request_body("claude", base(extra_body={"temperature": 0.2}, output_config={"effort": "high"}))
    assert body["temperature"] == 0.2
    assert body["reasoning"] == {"effort": "high"}


def test_a_tool_round_trip_keeps_ids_and_reasoning_state():
    assistant = [NS(type="thinking", state="opaque-1"), NS(type="text", text="Checking."),
                 NS(type="tool_use", id="c1", name="get_time", input={"zone": "UTC"})]
    results = [{"type": "tool_result", "tool_use_id": "c1", "content": "12:00"}]
    body = request_body("claude", base(messages=[
        {"role": "user", "content": "Time?"},
        {"role": "assistant", "content": assistant},
        {"role": "user", "content": results},
    ]))
    assert body["messages"] == [
        {"role": "user", "content": "Time?"},
        {"role": "assistant", "reasoning_state": "opaque-1", "content": [
            {"type": "text", "text": "Checking."},
            {"type": "tool_call", "id": "c1", "name": "get_time", "arguments": {"zone": "UTC"}}]},
        {"role": "tool", "content": [{"type": "tool_result", "id": "c1", "text": "12:00", "is_error": False}]},
    ]


def test_empty_text_blocks_are_dropped():
    body = request_body("claude", base(messages=[
        {"role": "assistant", "content": [NS(type="text", text=""), NS(type="text", text="Hi")]}]))
    assert body["messages"] == [{"role": "assistant", "content": [{"type": "text", "text": "Hi"}]}]


def test_an_image_block_is_flattened():
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
    body = request_body("claude", base(messages=[{"role": "user", "content": [image]}]))
    assert body["messages"][0]["content"] == [{"type": "image", "media_type": "image/png", "data": "AAAA"}]


def test_an_unknown_block_is_refused():
    with pytest.raises(ValueError, match="Unsupported content block: video"):
        request_body("claude", base(messages=[{"role": "user", "content": [{"type": "video"}]}]))


def test_reply_becomes_an_anthropic_shaped_message():
    message = response_message({
        "content": [{"type": "text", "text": "Checking."},
                    {"type": "tool_call", "id": "c1", "name": "get_time", "arguments": {"zone": "UTC"}}],
        "stop_reason": "tool_call", "reasoning_state": "opaque-1",
        "usage": {"input_tokens": 100, "output_tokens": 7, "cached_input_tokens": 60, "reasoning_tokens": 0},
    })
    assert [block.type for block in message.content] == ["thinking", "text", "tool_use"]
    assert message.content[0].state == "opaque-1"
    assert (message.content[2].id, message.content[2].name, message.content[2].input) == ("c1", "get_time", {"zone": "UTC"})
    assert message.stop_reason == "tool_use"
    usage = message.usage
    # The provider adds the three input counters back together to get the whole prompt.
    assert usage.input_tokens + usage.cache_read_input_tokens + usage.cache_creation_input_tokens == 100
    assert (usage.cache_read_input_tokens, usage.output_tokens) == (60, 7)


@pytest.mark.parametrize("gateway,anthropic", [("end", "end_turn"), ("tool_call", "tool_use"),
                                               ("max_tokens", "max_tokens"), ("refusal", "refusal"), ("error", "error")])
def test_stop_reasons(gateway, anthropic):
    assert response_message({"content": [], "stop_reason": gateway}).stop_reason == anthropic


class FakeClient:
    def __init__(self, events=(), reply=None, error=None):
        self.events, self.reply, self.error, self.bodies = list(events), reply, error, []

    async def stream(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        for event in self.events:
            yield event

    def chat_sync(self, body):
        self.bodies.append(body)
        return self.reply


DONE = {"type": "done", "content": [{"type": "text", "text": "Hello"}], "stop_reason": "end",
        "usage": {"input_tokens": 3, "output_tokens": 1, "cached_input_tokens": 0}}


def read_round(client: FakeClient):
    """Legion has no async pytest plugin; tests drive coroutines with asyncio.run."""
    async def run():
        async with GatewayShim("claude", client).messages.stream(**base()) as stream:
            chunks = [chunk async for chunk in stream.text_stream]
            return chunks, await stream.get_final_message()

    return asyncio.run(run())


def test_stream_yields_text_and_the_final_message():
    client = FakeClient([{"type": "reasoning", "delta": "hm"}, {"type": "text", "delta": "Hel"},
                         {"type": "tool_call", "id": "c", "name": "n", "arguments_delta": "{}"},
                         {"type": "text", "delta": "lo"}, DONE])
    chunks, message = read_round(client)
    assert chunks == ["Hel", "lo"]
    assert message.stop_reason == "end_turn"
    assert client.bodies[0]["gateway"] == "claude"


def test_a_gateway_error_surfaces_while_streaming():
    client = FakeClient(error=GatewayCallError(429, "gateway_rate_limit", "slow", kind="rate_limit"))
    with pytest.raises(GatewayCallError):
        read_round(client)


def test_create_is_one_sync_reply():
    client = FakeClient(reply={"content": [{"type": "text", "text": "Hi"}], "stop_reason": "end",
                               "usage": {"input_tokens": 2, "output_tokens": 1}})
    message = GatewayShim("claude", client).messages.create(**base())
    assert message.content[0].text == "Hi"
    assert message.usage.input_tokens == 2


def test_count_tokens_is_not_offered():
    with pytest.raises(NotImplementedError):
        asyncio.run(GatewayShim("claude", FakeClient()).messages.count_tokens(model="m", messages=[]))
