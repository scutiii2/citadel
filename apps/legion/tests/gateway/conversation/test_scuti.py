import json

import httpx
import pytest

from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.gateways import build_gateway
from tests.gateway.conversation.helpers import chat

ENTRY = {"provider": "scuti", "url": "http://127.0.0.1:29200", "token": "mini_tok", "model": "minicpm", "timeout_s": 5,
         "capabilities": {"tools": True, "reasoning": True, "schema": True}, "project": "demo"}
PLAIN = {"provider": "scuti", "url": "http://127.0.0.1:29202", "model": "lfm3", "timeout_s": 5}
BODY = {"content": "Hello", "thinking": "hm", "tool_calls": [], "finish_reason": "stop", "model": "minicpm", "fallback": False,
        "usage": {"input_tokens": 12, "output_tokens": 3}, "duration_ms": 5}


def gateway(handler, entry=ENTRY):
    return build_gateway("minicpm", entry, httpx.MockTransport(handler))


def capture(reply=BODY):
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), token=request.headers.get("x-internal-token"), body=json.loads(request.content))
        return httpx.Response(200, json=reply)

    return seen, handler


async def test_request_and_reply():
    seen, handler = capture()
    result = await gateway(handler).complete(chat(system="Be brief", max_tokens=64, temperature=0.1, reasoning={"effort": "low"}))
    assert seen["url"] == "http://127.0.0.1:29200/v1/chat" and seen["token"] == "mini_tok"
    assert seen["body"] == {"messages": [{"role": "system", "content": "Be brief"}, {"role": "user", "content": "Hi"}],
                            "thinking": True, "temperature": 0.1, "max_tokens": 64, "project": "demo"}
    assert result.content == [{"type": "text", "text": "Hello"}] and result.reasoning == "hm" and result.stop_reason == "end"
    assert result.usage == {"input_tokens": 12, "output_tokens": 3, "cached_input_tokens": 0, "reasoning_tokens": 0}


async def test_thinking_is_off_unless_asked_when_the_service_supports_it():
    seen, handler = capture()
    await gateway(handler).complete(chat())
    assert seen["body"]["thinking"] is False


async def test_plain_services_get_no_extra_fields():
    seen, handler = capture()
    await gateway(handler, PLAIN).complete(chat())
    assert seen["body"] == {"messages": [{"role": "user", "content": "Hi"}]} and seen["token"] is None


async def test_tools_results_and_schema():
    reply = {**BODY, "content": "", "finish_reason": "tool_calls", "tool_calls": [{"id": "c9", "name": "t", "arguments": {"x": 1}}]}
    seen, handler = capture(reply)
    result = await gateway(handler).complete(chat(
        tools=[{"name": "t", "description": "d"}],
        messages=[{"role": "user", "content": "q"},
                  {"role": "assistant", "content": [{"type": "text", "text": "ok"}, {"type": "tool_call", "id": "c1", "name": "t", "arguments": {"a": 1}}]},
                  {"role": "tool", "content": [{"type": "tool_result", "id": "c1", "text": "42"}]}]))
    body = seen["body"]
    assert body["messages"][1] == {"role": "assistant", "content": "ok", "tool_calls": [{"id": "c1", "name": "t", "arguments": {"a": 1}}]}
    assert body["messages"][2] == {"role": "tool", "tool_name": "t", "content": "42"}
    assert body["tools"] == [{"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    assert result.content == [{"type": "tool_call", "id": "c9", "name": "t", "arguments": {"x": 1}}] and result.stop_reason == "tool_call"
    seen2, handler2 = capture()
    await gateway(handler2).complete(chat(schema={"name": "o", "schema": {"type": "object"}}))
    assert seen2["body"]["schema"] == {"type": "object"}


async def test_images_are_forwarded_and_the_service_decides():
    seen, handler = capture()
    await gateway(handler, PLAIN).complete(chat(messages=[{"role": "user", "content": [
        {"type": "text", "text": "look"}, {"type": "image", "media_type": "image/png", "data": "aGk="}]}]))
    assert seen["body"]["messages"][0] == {"role": "user", "content": "look", "images": ["aGk="]}

    def refuse(request):
        return httpx.Response(422, json={"detail": "images is not supported"})

    with pytest.raises(GatewayError) as error:
        await gateway(refuse, PLAIN).complete(chat())
    assert error.value.status == 422 and "images is not supported" in error.value.message


def test_model_override_is_refused():
    with pytest.raises(GatewayError) as error:
        gateway(lambda r: None).validate(chat(model="other"))
    assert error.value.status == 422 and error.value.code == "model_unsupported"


@pytest.mark.parametrize("status,kind,out", [(429, "rate_limit", 429), (401, "auth", 502), (503, "unavailable", 502)])
async def test_errors(status, kind, out):
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(status, json={"detail": "secret mini_tok"}, headers={"retry-after": "2"})).complete(chat())
    assert (error.value.kind, error.value.status) == (kind, out) and "mini_tok" not in error.value.message


async def test_unreachable_service():
    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(GatewayError) as error:
        await gateway(down).complete(chat())
    assert error.value.status == 502 and error.value.kind == "unavailable"


async def test_stream_relays_pieces_then_done():
    lines = [{"type": "thinking", "text": "hm"}, {"type": "content", "text": "Hel"}, {"type": "content", "text": "lo"},
             {"type": "done", **{**BODY, "content": "Hello", "tool_calls": [{"id": "c1", "name": "t", "arguments": {"a": 1}}], "finish_reason": "tool_calls"}}]
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content="\n".join(map(json.dumps, lines)).encode(), headers={"content-type": "application/x-ndjson"})

    items = [i async for i in gateway(handler).stream(chat(stream=True, tools=[{"name": "t"}]))]
    assert seen["body"]["stream"] is True
    assert items[:3] == [("reasoning", "hm"), ("text", "Hel"), ("text", "lo")]
    assert items[3] == ("tool_call", "c1", "t", "{\"a\": 1}")
    assert items[-1][0] == "done" and items[-1][1].stop_reason == "tool_call"


async def test_stream_error_line_and_truncation():
    error_line = json.dumps({"type": "error", "status": 502, "message": "secret mini_tok"})
    with pytest.raises(GatewayError) as error:
        [i async for i in gateway(lambda r: httpx.Response(200, content=error_line.encode())).stream(chat(stream=True))]
    assert error.value.status == 502 and "mini_tok" not in error.value.message
    with pytest.raises(GatewayError):
        [i async for i in gateway(lambda r: httpx.Response(200, content=json.dumps({"type": "content", "text": "x"}).encode())).stream(chat(stream=True))]


async def test_probe():
    assert "ready" in (await gateway(lambda r: httpx.Response(200, json={"status": "ok", "ready": True})).probe()).lower()
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(200, json={"status": "ok", "ready": False})).probe()
    assert error.value.status == 503


def test_capabilities():
    assert gateway(lambda r: None, PLAIN).capabilities == {"streams": True, "images": False, "tools": False, "reasoning": False, "schema": False}
    assert gateway(lambda r: None).capabilities["tools"] is True and gateway(lambda r: None).forwards_images is True
