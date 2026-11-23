import json

import httpx
import pytest

from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.gateways import build_gateway
from tests.gateway.conversation.helpers import chat

CHAT = {"provider": "openai", "api": "chat", "api_key": "sk-secret", "base_url": "https://compat.test/v1", "model": "m", "timeout_s": 5}
RESPONSES = {"provider": "openai", "api": "responses", "api_key": "sk-secret", "model": "gpt-x", "timeout_s": 5}
COMPLETION = {"id": "c", "object": "chat.completion", "created": 1, "model": "m",
              "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hello"}}],
              "usage": {"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17,
                        "prompt_tokens_details": {"cached_tokens": 3}, "completion_tokens_details": {"reasoning_tokens": 2}}}


def gateway(handler, entry=CHAT):
    return build_gateway("g", entry, httpx.MockTransport(handler))


def capture(reply):
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), auth=request.headers.get("authorization"), body=json.loads(request.content))
        return httpx.Response(200, json=reply)

    return seen, handler


def sse(chunks):
    return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


async def test_chat_request_and_reply():
    seen, handler = capture(COMPLETION)
    result = await gateway(handler).complete(chat(system="Be brief", max_tokens=50, temperature=0.2))
    assert seen["url"] == "https://compat.test/v1/chat/completions" and seen["auth"] == "Bearer sk-secret"
    assert seen["body"] == {"model": "m", "max_tokens": 50, "temperature": 0.2,
                            "messages": [{"role": "system", "content": "Be brief"}, {"role": "user", "content": "Hi"}]}
    assert result.content == [{"type": "text", "text": "Hello"}] and result.stop_reason == "end"
    assert result.usage == {"input_tokens": 11, "output_tokens": 6, "cached_input_tokens": 3, "reasoning_tokens": 2}


async def test_max_completion_tokens_option():
    seen, handler = capture(COMPLETION)
    await gateway(handler, {**CHAT, "max_tokens_param": "max_completion_tokens"}).complete(chat(max_tokens=9))
    assert seen["body"]["max_completion_tokens"] == 9 and "max_tokens" not in seen["body"]


async def test_chat_tools_images_results_schema_reasoning():
    seen, handler = capture(COMPLETION)
    await gateway(handler).complete(chat(
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "x"}, {"type": "image", "media_type": "image/png", "data": "aGk="}]},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}, {"type": "tool_call", "id": "c1", "name": "t", "arguments": {"a": 1}}]},
            {"role": "tool", "content": [{"type": "tool_result", "id": "c1", "text": "42"}]},
        ],
        tools=[{"name": "t", "description": "d"}], tool_choice={"name": "t"}, reasoning={"effort": "high"}, temperature=0.4))
    body = seen["body"]
    assert body["messages"][0]["content"] == [{"type": "text", "text": "x"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGk="}}]
    assert body["messages"][1] == {"role": "assistant", "content": "ok",
                                   "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{\"a\": 1}"}}]}
    assert body["messages"][2] == {"role": "tool", "tool_call_id": "c1", "content": "42"}
    assert body["tools"] == [{"type": "function", "function": {"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}}]
    assert body["tool_choice"] == {"type": "function", "function": {"name": "t"}}
    assert body["reasoning_effort"] == "high" and "temperature" not in body


async def test_chat_schema_becomes_response_format():
    seen, handler = capture(COMPLETION)
    await gateway(handler).complete(chat(schema={"name": "out", "schema": {"type": "object"}, "strict": True}))
    assert seen["body"]["response_format"] == {"type": "json_schema", "json_schema": {"name": "out", "schema": {"type": "object"}, "strict": True}}


async def test_chat_tool_call_and_reasoning_reply():
    reply = {**COMPLETION, "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "reasoning_content": "thinking...",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{\"a\": 1}"}},
                       {"id": "c2", "type": "function", "function": {"name": "t", "arguments": "not json"}}]}}]}
    _, handler = capture(reply)
    result = await gateway(handler).complete(chat(tools=[{"name": "t"}]))
    assert result.content == [{"type": "tool_call", "id": "c1", "name": "t", "arguments": {"a": 1}},
                              {"type": "tool_call", "id": "c2", "name": "t", "arguments": {"_raw": "not json"}}]
    assert result.stop_reason == "tool_call" and result.reasoning == "thinking..."


@pytest.mark.parametrize("finish,expect", [("length", "max_tokens"), ("content_filter", "refusal"), ("stop", "end")])
async def test_chat_stop_reasons(finish, expect):
    reply = {**COMPLETION, "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": "x"}}]}
    _, handler = capture(reply)
    assert (await gateway(handler).complete(chat())).stop_reason == expect


async def test_chat_stream_text_reasoning_and_tool_call():
    chunks = [
        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [{"index": 0, "delta": {"role": "assistant", "reasoning_content": "hm"}, "finish_reason": None}]},
        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [{"index": 0, "delta": {"content": "Hel"}, "finish_reason": None}]},
        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": None}]},
        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function", "function": {"name": "t", "arguments": "{\"a\":"}}]}, "finish_reason": None}]},
        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "1}"}}]}, "finish_reason": "tool_calls"}]},
        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}},
    ]
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse(chunks), headers={"content-type": "text/event-stream"})

    items = [i async for i in gateway(handler).stream(chat(stream=True, tools=[{"name": "t"}]))]
    assert seen["body"]["stream"] is True and seen["body"]["stream_options"] == {"include_usage": True}
    assert [i[:2] for i in items if i[0] in ("reasoning", "text")] == [("reasoning", "hm"), ("text", "Hel"), ("text", "lo")]
    assert [i[3] for i in items if i[0] == "tool_call"] == ["{\"a\":", "1}"]
    done = items[-1][1]
    assert done.content == [{"type": "text", "text": "Hello"}, {"type": "tool_call", "id": "c1", "name": "t", "arguments": {"a": 1}}]
    assert done.stop_reason == "tool_call" and done.usage["output_tokens"] == 7 and done.reasoning == "hm"


async def test_stream_usage_can_be_turned_off():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse([]))

    with pytest.raises(GatewayError):
        [i async for i in gateway(handler, {**CHAT, "stream_usage": False}).stream(chat(stream=True))]
    assert "stream_options" not in seen["body"]


async def test_chat_truncated_stream_is_an_error():
    chunk = {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": None}]}
    with pytest.raises(GatewayError) as error:
        [i async for i in gateway(lambda r: httpx.Response(200, content=sse([chunk]))).stream(chat(stream=True))]
    assert error.value.kind == "unavailable"


RESP = {"id": "r", "object": "response", "created_at": 1, "status": "completed", "model": "gpt-x", "parallel_tool_calls": True,
        "tool_choice": "auto", "tools": [], "output": [
            {"id": "rs", "type": "reasoning", "summary": [{"type": "summary_text", "text": "plan"}]},
            {"id": "m", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "Hello", "annotations": []}]},
            {"id": "f", "type": "function_call", "call_id": "c1", "name": "t", "arguments": "{\"a\": 1}", "status": "completed"}],
        "usage": {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13, "input_tokens_details": {"cached_tokens": 2}, "output_tokens_details": {"reasoning_tokens": 1}}}


async def test_responses_request_and_reply():
    seen, handler = capture(RESP)
    result = await gateway(handler, RESPONSES).complete(chat(
        system="S", max_tokens=80, reasoning={"effort": "low"}, tools=[{"name": "t", "description": "d"}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "x"}, {"type": "image", "media_type": "image/png", "data": "aGk="}]},
                  {"role": "assistant", "content": [{"type": "text", "text": "ok"}, {"type": "tool_call", "id": "c0", "name": "t", "arguments": {}}]},
                  {"role": "tool", "content": [{"type": "tool_result", "id": "c0", "text": "42"}]}]))
    body = seen["body"]
    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert body["instructions"] == "S" and body["max_output_tokens"] == 80 and body["reasoning"] == {"effort": "low", "summary": "auto"}
    assert body["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "x"}, {"type": "input_image", "image_url": "data:image/png;base64,aGk="}]},
        {"role": "assistant", "content": "ok"},
        {"type": "function_call", "call_id": "c0", "name": "t", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c0", "output": "42"}]
    assert body["tools"] == [{"type": "function", "name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    assert result.content == [{"type": "text", "text": "Hello"}, {"type": "tool_call", "id": "c1", "name": "t", "arguments": {"a": 1}}]
    assert result.reasoning == "plan" and result.stop_reason == "tool_call"
    assert result.usage == {"input_tokens": 9, "output_tokens": 4, "cached_input_tokens": 2, "reasoning_tokens": 1}


async def test_responses_schema_and_incomplete():
    seen, handler = capture({**RESP, "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []})
    result = await gateway(handler, RESPONSES).complete(chat(schema={"name": "out", "schema": {"type": "object"}}))
    assert seen["body"]["text"] == {"format": {"type": "json_schema", "name": "out", "schema": {"type": "object"}, "strict": False}}
    assert result.stop_reason == "max_tokens"


async def test_responses_stream():
    created = {"type": "response.created", "sequence_number": 0, "response": {**RESP, "status": "in_progress", "output": []}}
    events = [
        created,
        {"type": "response.output_item.added", "sequence_number": 1, "output_index": 0, "item": {"id": "f", "type": "function_call", "call_id": "c1", "name": "t", "arguments": "", "status": "in_progress"}},
        {"type": "response.function_call_arguments.delta", "sequence_number": 2, "item_id": "f", "output_index": 0, "delta": "{\"a\": 1}"},
        {"type": "response.reasoning_summary_text.delta", "sequence_number": 3, "item_id": "rs", "output_index": 0, "summary_index": 0, "delta": "plan"},
        {"type": "response.output_text.delta", "sequence_number": 4, "item_id": "m", "output_index": 1, "content_index": 0, "delta": "Hello"},
        {"type": "response.completed", "sequence_number": 5, "response": RESP},
    ]
    body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
    items = [i async for i in gateway(lambda r: httpx.Response(200, content=body, headers={"content-type": "text/event-stream"}), RESPONSES).stream(chat(stream=True, tools=[{"name": "t"}]))]
    assert items[0] == ("tool_call", "c1", "t", "") and items[1] == ("tool_call", "c1", "t", "{\"a\": 1}")
    assert ("reasoning", "plan") in items and ("text", "Hello") in items
    assert items[-1][0] == "done" and items[-1][1].stop_reason == "tool_call"


async def test_responses_stream_without_completion_is_an_error():
    body = f"event: response.created\ndata: {json.dumps({'type': 'response.created', 'sequence_number': 0, 'response': {**RESP, 'status': 'in_progress', 'output': []}})}\n\n".encode()
    with pytest.raises(GatewayError):
        [i async for i in gateway(lambda r: httpx.Response(200, content=body), RESPONSES).stream(chat(stream=True))]


async def test_azure_client_is_used():
    seen = {}

    def handler(request):
        seen["url"], seen["key"] = str(request.url), request.headers.get("api-key")
        return httpx.Response(200, json=COMPLETION)

    entry = {"provider": "openai", "auth": "azure", "api": "chat", "azure_endpoint": "https://res.openai.azure.com", "api_version": "2024-10-21", "api_key": "az-secret", "model": "dep", "timeout_s": 5}
    await gateway(handler, entry).complete(chat())
    assert "res.openai.azure.com" in seen["url"] and "api-version=2024-10-21" in seen["url"] and seen["key"] == "az-secret"


@pytest.mark.parametrize("status,kind", [(429, "rate_limit"), (401, "auth"), (503, "unavailable")])
async def test_errors_are_classified_and_secret_free(status, kind):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "bad sk-secret", "type": "x"}}, headers={"retry-after": "2"})

    with pytest.raises(GatewayError) as error:
        await gateway(handler).complete(chat())
    assert error.value.kind == kind and "sk-secret" not in error.value.message


def test_no_key_is_allowed_for_a_local_server():
    g = gateway(lambda r: None, {"provider": "openai", "api": "chat", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen", "timeout_s": 5})
    assert g.provider == "openai"


async def test_probe_asks_for_tokens_when_the_provider_has_no_model_list():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(404, json={"error": {"message": "no such route"}})
        return httpx.Response(200, json=COMPLETION)

    assert "accepted" in await gateway(handler).probe()
    assert paths == ["/v1/models", "/v1/chat/completions"]


async def test_probe_does_not_hide_a_wrong_key_behind_the_fallback():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(GatewayError) as error:
        await gateway(handler).probe()
    assert error.value.kind == "auth"


async def test_models_lists_what_the_provider_offers_sorted_and_without_duplicates():
    def handler(request):
        assert request.url.path == "/v1/models" and request.headers["authorization"] == "Bearer sk-secret"
        return httpx.Response(200, json={"object": "list", "data": [{"id": "b", "object": "model", "created": 1, "owned_by": "x"},
                                                                    {"id": "a", "object": "model", "created": 1, "owned_by": "x"},
                                                                    {"id": "a", "object": "model", "created": 1, "owned_by": "x"}]})

    assert await gateway(handler).models() == ["a", "b"]


async def test_azure_has_no_model_list():
    azure = {"provider": "openai", "auth": "azure", "api": "responses", "api_key": "k", "azure_endpoint": "https://x.openai.azure.com",
             "api_version": "2025-01-01", "model": "dep", "timeout_s": 5}
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(200, json={}), azure).models()
    assert error.value.code == "models_unsupported"
