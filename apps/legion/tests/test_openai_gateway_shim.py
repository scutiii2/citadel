"""Responses-API requests and replies translated to and from ConversationGateway."""

from __future__ import annotations

import asyncio

import pytest

from src.providers.gateway_client import GatewayCallError
from src.providers.language.openai_gateway_shim import GatewayShim, request_body, response
from src.providers.language.openai_provider import _output_as_input_items, _strip_reasoning
from tests.test_anthropic_gateway_shim import FakeClient

TOOL = {"type": "function", "name": "get_time", "description": "Now.",
        "parameters": {"type": "object", "properties": {}}}
REPLY = {"reasoning_state": "opaque-1", "stop_reason": "tool_call",
         "content": [{"type": "text", "text": "Checking."},
                     {"type": "tool_call", "id": "c1", "name": "get_time", "arguments": {"zone": "UTC"}}],
         "usage": {"input_tokens": 10, "output_tokens": 4, "cached_input_tokens": 6}}
DONE = {"type": "done", "content": [{"type": "text", "text": "Hello"}], "stop_reason": "end",
        "usage": {"input_tokens": 3, "output_tokens": 1}}


def base(**extra):
    return {"model": "gpt-6.1-sol", "max_output_tokens": 512, "tools": None,
            "input": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hello"}], **extra}


def test_plain_request():
    assert request_body("gpt", base()) == {
        "gateway": "gpt", "model": "gpt-6.1-sol", "max_tokens": 512,
        "system": "Be brief.", "messages": [{"role": "user", "content": "Hello"}],
    }


def test_tools_and_options():
    body = request_body("gpt", base(tools=[TOOL], temperature=0.2, reasoning={"effort": "high"}))
    assert body["tools"] == [{"name": "get_time", "description": "Now.",
                              "parameters": {"type": "object", "properties": {}}}]
    assert body["temperature"] == 0.2
    assert body["reasoning"] == {"effort": "high"}


def test_reply_becomes_a_responses_shaped_object():
    reply = response(REPLY)
    assert [item.type for item in reply.output] == ["reasoning", "message", "function_call"]
    call = reply.output[2]
    assert (call.call_id, call.name, call.arguments) == ("c1", "get_time", '{"zone": "UTC"}')
    assert reply.output_text == "Checking."
    assert (reply.usage.input_tokens, reply.usage.output_tokens, reply.usage.total_tokens) == (10, 4, 14)


def test_a_tool_round_trip_keeps_ids_and_reasoning_state():
    """The provider's own resend path: output items back in, then the tool outputs."""
    items = [*base()["input"], *_output_as_input_items(response(REPLY).output),
             {"type": "function_call_output", "call_id": "c1", "output": "12:00"},
             {"type": "function_call_output", "call_id": "c2", "output": "13:00"}]
    assert request_body("gpt", base(input=items))["messages"] == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "reasoning_state": "opaque-1", "content": [
            {"type": "text", "text": "Checking."},
            {"type": "tool_call", "id": "c1", "name": "get_time", "arguments": {"zone": "UTC"}}]},
        {"role": "tool", "content": [
            {"type": "tool_result", "id": "c1", "text": "12:00", "is_error": False},
            {"type": "tool_result", "id": "c2", "text": "13:00", "is_error": False}]},
    ]
    # After a gateway switch the provider drops reasoning items; the state must not be sent.
    switched = request_body("backup", base(input=_strip_reasoning(items)))
    assert "reasoning_state" not in switched["messages"][1]


def test_two_tool_rounds_stay_separate_messages():
    call = lambda call_id: {"type": "function_call", "call_id": call_id, "name": "get_time", "arguments": "{}"}  # noqa: E731
    out = lambda call_id: {"type": "function_call_output", "call_id": call_id, "output": "x"}  # noqa: E731
    messages = request_body("gpt", base(input=[call("a"), out("a"), call("b"), out("b")]))["messages"]
    assert [message["role"] for message in messages] == ["assistant", "tool", "assistant", "tool"]


def test_unreadable_arguments_become_an_empty_object():
    item = {"type": "function_call", "call_id": "a", "name": "n", "arguments": "{broken"}
    assert request_body("gpt", base(input=[item]))["messages"][0]["content"][0]["arguments"] == {}


def test_an_unknown_item_is_refused():
    with pytest.raises(ValueError, match="Unsupported"):
        request_body("gpt", base(input=[{"type": "computer_call"}]))


def read_round(client: FakeClient):
    async def run():
        async with GatewayShim("gpt", client).responses.stream(**base()) as stream:
            events = [(event.type, event.delta) async for event in stream]
            return events, await stream.get_final_response()

    return asyncio.run(run())


def test_stream_yields_delta_events_and_the_final_response():
    client = FakeClient([{"type": "reasoning", "delta": "hm"}, {"type": "text", "delta": "Hel"},
                         {"type": "tool_call", "id": "c", "name": "n", "arguments_delta": "{}"},
                         {"type": "text", "delta": "lo"}, DONE])
    events, reply = read_round(client)
    assert events == [("response.reasoning_text.delta", "hm"), ("response.output_text.delta", "Hel"),
                      ("response.output_text.delta", "lo")]
    assert reply.output_text == "Hello"
    assert client.bodies[0]["gateway"] == "gpt"


def test_a_stream_without_done_is_an_outage():
    with pytest.raises(GatewayCallError) as raised:
        read_round(FakeClient([{"type": "text", "delta": "Hel"}]))
    assert raised.value.kind == "unavailable"


def test_a_gateway_error_surfaces_while_streaming():
    with pytest.raises(GatewayCallError):
        read_round(FakeClient(error=GatewayCallError(429, "gateway_rate_limit", "slow", kind="rate_limit")))


def test_create_is_one_sync_reply():
    reply = GatewayShim("gpt", FakeClient(reply=DONE)).responses.create(**base())
    assert reply.output_text == "Hello"


def test_count_tokens_is_not_offered():
    with pytest.raises(NotImplementedError):
        asyncio.run(GatewayShim("gpt", FakeClient()).responses.input_tokens.count(model="m", input=[]))


def test_a_tier_marker_asks_the_gateway_for_its_own_model_name():
    light = request_body("vllm", base(model="tier:light"))
    assert light["tier"] == "light" and "model" not in light
    default = request_body("vllm", base(model="tier:default"))
    assert "tier" not in default and "model" not in default
    assert request_body("vllm", base(model="llama-3"))["model"] == "llama-3"
