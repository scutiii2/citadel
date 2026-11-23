import json

import httpx
import pytest

from src.gateway.conversation.settings import Settings
from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.service import ChatService
from src.gateway.conversation.store import GatewayStore
from tests.gateway.conversation.helpers import chat

BODY = {"content": "Hello", "thinking": None, "tool_calls": [], "finish_reason": "stop", "model": "lfm3",
        "usage": {"input_tokens": 3, "output_tokens": 2}}


@pytest.fixture
def store(tmp_path):
    s = GatewayStore(tmp_path / "gateways.json")
    s.put("lfm3", {"provider": "scuti", "url": "http://127.0.0.1:29202", "model": "lfm3", "max_tokens_limit": 100})
    s.put("minicpm", {"provider": "scuti", "url": "http://127.0.0.1:29200", "capabilities": {"tools": True}})
    return s


def service(store, handler=lambda r: httpx.Response(200, json=BODY), **settings):
    return ChatService(store, Settings(**settings), httpx.MockTransport(handler))


async def refused(coro, code):
    with pytest.raises(GatewayError) as error:
        await coro
    assert error.value.status in (422, 429) and error.value.code == code


async def test_chat_body(store):
    body = await service(store).chat(chat("lfm3"))
    assert body["gateway"] == "lfm3" and body["provider"] == "scuti" and body["model"] == "lfm3"
    assert body["content"] == [{"type": "text", "text": "Hello"}] and body["stop_reason"] == "end" and body["streamed"] is False
    assert body["usage"] == {"input_tokens": 3, "output_tokens": 2, "cached_input_tokens": 0, "reasoning_tokens": 0}
    assert "reasoning" not in body and "reasoning_state" not in body and body["duration_ms"] >= 0


async def test_unknown_gateway(store):
    await refused(service(store).chat(chat("nope")), "unknown_gateway")


async def test_capability_refusals_never_call_the_gateway(store):
    def boom(request):
        raise AssertionError("called")

    svc = service(store, boom)
    await refused(svc.chat(chat("lfm3", tools=[{"name": "t"}])), "tools_unsupported")
    await refused(svc.chat(chat("lfm3", reasoning={"effort": "low"})), "reasoning_unsupported")
    await refused(svc.chat(chat("lfm3", schema={"name": "o", "schema": {}})), "schema_unsupported")
    await refused(svc.chat(chat("lfm3", model="other")), "model_unsupported")
    await refused(svc.chat(chat("lfm3", max_tokens=101)), "max_tokens_too_large")


async def test_scuti_forwards_images_and_the_service_decides(store):
    def refuse(request):
        return httpx.Response(422, json={"detail": "images is not supported"})

    request = chat("lfm3", messages=[{"role": "user", "content": [{"type": "image", "media_type": "image/png", "data": "aGk="}]}])
    with pytest.raises(GatewayError) as error:
        await service(store, refuse).chat(request)
    assert error.value.status == 422 and "images" in error.value.message


async def test_in_flight_cap(store):
    svc = service(store, max_inflight=1)
    svc._inflight = 1
    with pytest.raises(GatewayError) as error:
        await svc.chat(chat("lfm3"))
    assert error.value.status == 429 and error.value.retry_after == 1
    svc._inflight = 0
    await svc.chat(chat("lfm3"))
    assert svc._inflight == 0


async def test_failure_releases_the_slot(store):
    svc = service(store, lambda r: httpx.Response(503, json={"detail": "x"}))
    with pytest.raises(GatewayError):
        await svc.chat(chat("lfm3"))
    assert svc._inflight == 0


async def test_native_stream(store):
    lines = [{"type": "content", "text": "Hel"}, {"type": "content", "text": "lo"}, {"type": "done", **BODY}]
    svc = service(store, lambda r: httpx.Response(200, content="\n".join(map(json.dumps, lines)).encode()))
    out = [x async for x in svc.stream(chat("lfm3", stream=True))]
    assert [x["delta"] for x in out if x["type"] == "text"] == ["Hel", "lo"]
    assert out[-1]["type"] == "done" and out[-1]["streamed"] is True and out[-1]["content"] == [{"type": "text", "text": "Hello"}]


async def test_emulated_stream_when_the_gateway_cannot_stream(tmp_path):
    s = GatewayStore(tmp_path / "g.json")
    s.put("nostream", {"provider": "scuti", "url": "http://127.0.0.1:1", "capabilities": {"streams": False, "tools": True}})
    reply = {**BODY, "thinking": "hm", "content": "Hi", "finish_reason": "tool_calls", "tool_calls": [{"id": "c1", "name": "t", "arguments": {"a": 1}}]}
    out = [x async for x in service(s, lambda r: httpx.Response(200, json=reply)).stream(chat("nostream", stream=True, tools=[{"name": "t"}]))]
    assert [x["type"] for x in out] == ["reasoning", "text", "tool_call", "done"]
    assert out[2] == {"type": "tool_call", "id": "c1", "name": "t", "arguments_delta": "{\"a\": 1}"}
    assert out[-1]["streamed"] is False and out[-1]["reasoning"] == "hm"


async def test_stream_preflight_errors_raise_before_the_first_line(store):
    with pytest.raises(GatewayError):
        await anext(service(store).stream(chat("nope", stream=True)))


async def test_gateways_list_has_capabilities_and_no_secrets(tmp_path):
    s = GatewayStore(tmp_path / "g.json")
    s.put("claude", {"provider": "anthropic", "api_key": "sk-1", "model": "m"})
    s.put("lfm3", {"provider": "scuti", "url": "http://127.0.0.1:29202"})
    rows = {r["id"]: r for r in await service(s, lambda r: httpx.Response(200, json={"ready": True})).gateways()}
    assert rows["claude"]["images"] is True and rows["claude"]["provider"] == "anthropic" and "reachable" not in rows["claude"]
    assert rows["lfm3"]["tools"] is False and rows["lfm3"]["reachable"] is True
    assert "sk-1" not in json.dumps(rows)


async def test_test_unknown_gateway_is_404(store):
    with pytest.raises(GatewayError) as error:
        await service(store).test("nope")
    assert error.value.status == 404


async def test_a_tier_picks_the_model_the_gateway_saved_for_it(tmp_path):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content)["model"])
        return httpx.Response(200, json={"id": "1", "model": sent[-1], "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    s = GatewayStore(tmp_path / "gateways.json")
    s.put("vllm", {"provider": "openai", "base_url": "http://h:8000/v1", "api": "chat", "model": "base",
                   "models": {"light": "small"}})
    svc = service(s, handler)
    await svc.chat(chat("vllm", tier="light"))
    await svc.chat(chat("vllm", tier="heavy"))  # no model saved for heavy: the gateway's own model
    await svc.chat(chat("vllm", model="asked"))
    await svc.chat(chat("vllm", tier="extreme"))
    assert sent == ["small", "base", "asked", "base"]


def test_tier_and_model_together_are_refused():
    with pytest.raises(GatewayError):
        chat("g", tier="light", model="m")
    with pytest.raises(GatewayError):
        chat("g", tier="giant")


async def test_a_test_that_gets_no_answer_gives_up_with_a_message(store, monkeypatch):
    import asyncio

    async def silent(request):
        await asyncio.sleep(30)

    monkeypatch.setattr("src.gateway.conversation.service.TEST_SECONDS", 0.2)
    with pytest.raises(GatewayError) as error:
        await service(store, silent).test("lfm3")
    assert error.value.code == "gateway_timeout" and "No answer within" in error.value.message


async def test_a_paid_provider_shows_the_result_of_its_last_test_as_reachable(tmp_path):
    ok = {"value": True}

    def handler(request):
        return httpx.Response(200, json={"object": "list", "data": []}) if ok["value"] else httpx.Response(401, json={"error": {"message": "bad key"}})

    s = GatewayStore(tmp_path / "gateways.json")
    s.put("gpt", {"provider": "openai", "api_key": "sk-1", "model": "m"})
    svc = service(s, handler)

    async def reachable():
        return {row["id"]: row.get("reachable") for row in await svc.gateways()}["gpt"]

    assert await reachable() is None  # a listing never spends a request on a paid provider
    await svc.test("gpt")
    assert await reachable() is True
    ok["value"] = False
    with pytest.raises(GatewayError):
        await svc.test("gpt")
    assert await reachable() is False
    s.put("gpt", {"provider": "openai", "api_key": "sk-1", "model": "other"})
    assert await reachable() is None  # an edited gateway has not been tested yet
