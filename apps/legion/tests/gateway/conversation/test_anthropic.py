import json

import httpx
import pytest

from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.gateways import build_gateway
from tests.gateway.conversation.helpers import chat

ENTRY = {"provider": "anthropic", "auth": "key", "api_key": "sk-ant-secret", "model": "claude-x", "timeout_s": 5}
MESSAGE = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-x", "stop_sequence": None,
           "content": [{"type": "text", "text": "Hello"}], "stop_reason": "end_turn",
           "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 4, "cache_creation_input_tokens": 2}}


def gateway(handler, entry=ENTRY):
    return build_gateway("claude", entry, httpx.MockTransport(handler))


def capture(reply=MESSAGE):
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), key=request.headers.get("x-api-key"), body=json.loads(request.content))
        return httpx.Response(200, json=reply)

    return seen, handler


def sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


async def test_complete_maps_request_and_reply():
    seen, handler = capture()
    result = await gateway(handler).complete(chat(system="Be brief", max_tokens=100, temperature=0.3))
    assert seen["url"].endswith("/v1/messages") and seen["key"] == "sk-ant-secret"
    assert seen["body"] == {"model": "claude-x", "max_tokens": 100, "temperature": 0.3, "system": "Be brief",
                            "messages": [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]}
    assert result.content == [{"type": "text", "text": "Hello"}] and result.stop_reason == "end"
    assert result.usage == {"input_tokens": 16, "output_tokens": 5, "cached_input_tokens": 4, "reasoning_tokens": 0}


async def test_default_max_tokens_and_model_override():
    seen, handler = capture()
    await gateway(handler).complete(chat(model="other"))
    assert seen["body"]["max_tokens"] == 4096 and seen["body"]["model"] == "other"


async def test_images_tools_and_results_are_mapped():
    seen, handler = capture()
    await gateway(handler).complete(chat(
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "x"}, {"type": "image", "media_type": "image/png", "data": "aGk="}]},
            {"role": "assistant", "content": [{"type": "tool_call", "id": "c1", "name": "t", "arguments": {"a": 1}}]},
            {"role": "tool", "content": [{"type": "tool_result", "id": "c1", "text": "ok", "is_error": True}]},
        ],
        tools=[{"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}], tool_choice="required"))
    body = seen["body"]
    assert body["messages"][0]["content"][1] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "aGk="}}
    assert body["messages"][1]["content"] == [{"type": "tool_use", "id": "c1", "name": "t", "input": {"a": 1}}]
    assert body["messages"][2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "ok", "is_error": True}]}
    assert body["tools"] == [{"name": "t", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    assert body["tool_choice"] == {"type": "any"}


async def test_tool_call_reply_and_stop_reason():
    reply = {**MESSAGE, "stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "c9", "name": "t", "input": {"x": 1}}]}
    _, handler = capture(reply)
    result = await gateway(handler).complete(chat(tools=[{"name": "t"}]))
    assert result.content == [{"type": "tool_call", "id": "c9", "name": "t", "arguments": {"x": 1}}] and result.stop_reason == "tool_call"


async def test_thinking_is_returned_and_state_is_echoed():
    reply = {**MESSAGE, "content": [{"type": "thinking", "thinking": "hmm", "signature": "sig"}, {"type": "text", "text": "A"}]}
    seen, handler = capture(reply)
    g = gateway(handler)
    result = await g.complete(chat(reasoning={"effort": "low"}, temperature=0.5))
    assert seen["body"]["thinking"] == {"type": "enabled", "budget_tokens": 1024} and "temperature" not in seen["body"]
    assert result.reasoning == "hmm" and json.loads(result.reasoning_state) == [{"type": "thinking", "thinking": "hmm", "signature": "sig"}]
    await g.complete(chat(messages=[{"role": "user", "content": "q"}, {"role": "assistant", "content": "A", "reasoning_state": result.reasoning_state},
                                    {"role": "user", "content": "again"}], reasoning={"effort": "low"}))
    assert seen["body"]["messages"][1]["content"][0] == {"type": "thinking", "thinking": "hmm", "signature": "sig"}


async def test_budget_tokens_wins_over_effort():
    seen, handler = capture()
    await gateway(handler).complete(chat(reasoning={"effort": "low", "budget_tokens": 3000}, max_tokens=8000))
    assert seen["body"]["thinking"]["budget_tokens"] == 3000


async def test_schema_uses_a_forced_tool_and_returns_json_text():
    reply = {**MESSAGE, "stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "c", "name": "out", "input": {"a": 1}}]}
    seen, handler = capture(reply)
    result = await gateway(handler).complete(chat(schema={"name": "out", "schema": {"type": "object"}}))
    assert seen["body"]["tool_choice"] == {"type": "tool", "name": "out"}
    assert seen["body"]["tools"][0]["input_schema"] == {"type": "object"}
    assert result.content == [{"type": "text", "text": '{"a": 1}'}] and result.stop_reason == "end"


def test_schema_with_reasoning_is_refused():
    with pytest.raises(GatewayError) as error:
        gateway(lambda r: None).validate(chat(schema={"name": "o", "schema": {}}, reasoning={"effort": "low"}))
    assert error.value.status == 422


async def test_cache_adds_breakpoints():
    seen, handler = capture()
    await gateway(handler).complete(chat(system="S", cache=True, tools=[{"name": "a"}, {"name": "b"}]))
    body = seen["body"]
    assert body["system"] == [{"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}]
    assert "cache_control" not in body["tools"][0] and body["tools"][1]["cache_control"] == {"type": "ephemeral"}
    assert body["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.parametrize("status,expect", [(429, ("rate_limit", 429)), (401, ("auth", 502)), (529, ("unavailable", 502)), (402, ("quota", 402))])
async def test_errors_are_classified_and_secret_free(status, expect):
    def handler(request):
        return httpx.Response(status, json={"type": "error", "error": {"type": "x", "message": "bad sk-ant-secret"}}, headers={"retry-after": "3"})

    with pytest.raises(GatewayError) as error:
        await gateway(handler).complete(chat())
    assert (error.value.kind, error.value.status) == expect and "sk-ant-secret" not in error.value.message


async def test_stream_text_thinking_and_tool_call():
    events = [
        {"type": "message_start", "message": {**MESSAGE, "content": [], "usage": {"input_tokens": 10, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hm"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hel"}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "lo"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "content_block_start", "index": 2, "content_block": {"type": "tool_use", "id": "c1", "name": "t", "input": {}}},
        {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": "{\"a\":"}},
        {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": "1}"}},
        {"type": "content_block_stop", "index": 2},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 9}},
        {"type": "message_stop"},
    ]
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse(events), headers={"content-type": "text/event-stream"})

    items = [i async for i in gateway(handler).stream(chat(stream=True, reasoning={"effort": "low"}, tools=[{"name": "t"}]))]
    assert seen["body"]["stream"] is True
    assert [i[:2] for i in items[:4]] == [("reasoning", "hm"), ("text", "Hel"), ("text", "lo"), ("tool_call", "c1")]
    assert [i[3] for i in items if i[0] == "tool_call"] == ["", "{\"a\":", "1}"]
    done = items[-1][1]
    assert items[-1][0] == "done" and done.stop_reason == "tool_call" and done.usage["output_tokens"] == 9
    assert done.content == [{"type": "text", "text": "Hello"}, {"type": "tool_call", "id": "c1", "name": "t", "arguments": {"a": 1}}]
    assert done.reasoning == "hm"


async def test_truncated_stream_is_an_error():
    events = [{"type": "message_start", "message": {**MESSAGE, "content": []}},
              {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}]
    with pytest.raises(GatewayError) as error:
        [i async for i in gateway(lambda r: httpx.Response(200, content=sse(events))).stream(chat(stream=True))]
    assert error.value.status == 502 and error.value.kind == "unavailable"


def test_capabilities_and_override():
    assert gateway(lambda r: None).capabilities == {"streams": True, "images": True, "tools": True, "reasoning": True, "schema": True}
    assert gateway(lambda r: None, {**ENTRY, "capabilities": {"images": False}}).can("images") is False


async def test_probe_asks_for_a_token_when_the_gateway_has_no_model_list():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(404, json={"type": "error", "error": {"type": "not_found_error", "message": "no such route"}})
        return httpx.Response(200, json=MESSAGE)

    assert "accepted" in await gateway(handler).probe()
    assert paths == ["/v1/models", "/v1/messages"]


async def test_models_lists_the_ids_the_provider_offers():
    body = {"data": [{"id": "claude-b", "type": "model", "display_name": "B", "created_at": "2026-01-01T00:00:00Z"},
                     {"id": "claude-a", "type": "model", "display_name": "A", "created_at": "2026-01-01T00:00:00Z"}],
            "has_more": False, "first_id": "claude-b", "last_id": "claude-a"}

    def handler(request):
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json=body)

    assert await gateway(handler).models() == ["claude-a", "claude-b"]
