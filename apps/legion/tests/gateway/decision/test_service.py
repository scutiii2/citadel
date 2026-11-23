import asyncio
import base64
import json

import httpx
import pytest

from src.gateway.decision.settings import Settings
from src.gateway.decision.contract import parse_request
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.service import DecisionService
from src.gateway.decision.store import GatewayStore

PNG = base64.b64encode(b"\x89PNG fake").decode()
CHOICE = {"type": "choice", "instructions": "Team?", "criteria": {"a": "A", "b": "B"}}
LAYA_ANSWER = {"type": "choice", "choice": "a", "probabilities": {"a": 0.95, "b": 0.05}, "answer_confidence": 0.95,
               "uncertain": False, "rounds": 2, "voters": {"x": 1}}


def make(tmp_path, handler, **settings):
    store = GatewayStore(tmp_path / "gateways.json")
    store.put("laya", {"kind": "scuti", "url": "http://127.0.0.1:29220"})
    store.put("jev", {"kind": "typesafe", "api_key": "sk-secret", "model": "jev-latest"})
    store.put("d3", {"kind": "ollama", "url": "http://127.0.0.1:11434", "model": "d3:2b"})
    calls = []

    def counting(request):
        calls.append(str(request.url))
        return handler(request)

    return DecisionService(store, Settings(**settings), httpx.MockTransport(counting)), calls


def laya_handler(request):
    body = json.loads(request.content)
    if body.get("stream"):
        lines = [{"type": "answer", "id": "q", "answer": LAYA_ANSWER},
                 {"type": "done", "model": "laya", "answers": {"q": LAYA_ANSWER}, "calls": [{"input_tokens": 5}]}]
        return httpx.Response(200, content="\n".join(map(json.dumps, lines)).encode())
    return httpx.Response(200, json={"model": "laya", "answers": {"q": LAYA_ANSWER}, "calls": [{"input_tokens": 5}]})


def req(**extra):
    return parse_request({"gateway": "laya", "text": "hello", "questions": {"q": CHOICE}, **extra}, 16000)


async def test_decide_sets_answered_by_and_drops_trace_keys(tmp_path):
    service, _ = make(tmp_path, laya_handler)
    body = await service.decide(req())
    assert body["gateway"] == "laya" and body["streamed"] is False and body["tokens"] == 5
    answer = body["answers"]["q"]
    assert answer["answered_by"] == "laya" and "rounds" not in answer and "voters" not in answer
    assert "rounds" in (await service.decide(req(trace=True)))["answers"]["q"]


async def test_unknown_gateway_and_capability_checks_make_no_upstream_call(tmp_path):
    service, calls = make(tmp_path, laya_handler)
    with pytest.raises(GatewayError, match="unknown|Unknown|no gateway"):
        await service.decide(parse_request({"gateway": "nope", "text": "t", "questions": {"q": CHOICE}}, 16000))
    box = {"gateway": "laya", "text": "see img1", "questions": {"b": {"type": "box", "instructions": "find it in img1"}},
           "assets": {"img1": {"type": "image", "format": "png", "data_base64": PNG}}}
    with pytest.raises(GatewayError, match="cannot read images"):
        await service.decide(parse_request(box, 16000))
    with pytest.raises(GatewayError, match="cannot read images"):
        await service.decide(parse_request({**box, "gateway": "d3"}, 16000))
    assert calls == []


async def test_cache_hit_skips_the_gateway_and_stream_is_not_in_the_key(tmp_path):
    service, calls = make(tmp_path, laya_handler)
    await service.decide(req())
    await service.decide(req())
    await service.decide(req(stream=True))
    assert len(calls) == 1
    await service.decide(req(min_confidence=0.5))
    assert len(calls) == 2


async def test_cache_can_be_switched_off(tmp_path):
    service, calls = make(tmp_path, laya_handler, cache_enabled=False)
    await service.decide(req())
    await service.decide(req())
    assert len(calls) == 2


async def test_native_stream_and_emulated_stream(tmp_path):
    service, _ = make(tmp_path, laya_handler)
    items = [i async for i in service.stream(req(stream=True))]
    assert [i["type"] for i in items] == ["answer", "done"]
    assert items[0]["answer"]["answered_by"] == "laya" and items[1]["streamed"] is True and items[1]["tokens"] == 5

    ollama = lambda r: httpx.Response(200, json={"answers": {"q": {"choice": "a", "confidence": 0.9, "probabilities": {"a": 0.9, "b": 0.1}}}, "usage": {"input_tokens": 3}})
    other = tmp_path / "other"
    other.mkdir()
    service, _ = make(other, ollama)
    emulated = [i async for i in service.stream(parse_request({"gateway": "d3", "text": "t", "questions": {"q": CHOICE}, "stream": True}, 16000))]
    assert [i["type"] for i in emulated] == ["answer", "done"] and emulated[1]["streamed"] is False


async def test_stream_preflight_error_is_raised_before_any_item(tmp_path):
    service, _ = make(tmp_path, laya_handler)
    with pytest.raises(GatewayError):
        async for _ in service.stream(parse_request({"gateway": "nope", "text": "t", "questions": {"q": CHOICE}, "stream": True}, 16000)):
            pass


async def test_inflight_cap(tmp_path):
    gate = asyncio.Event()

    async def slow_transport(request):
        await gate.wait()
        return laya_handler(request)

    store = GatewayStore(tmp_path / "gateways.json")
    store.put("laya", {"kind": "scuti", "url": "http://127.0.0.1:29220"})
    service = DecisionService(store, Settings(max_inflight=1, cache_enabled=False), httpx.MockTransport(slow_transport))
    first = asyncio.create_task(service.decide(req()))
    await asyncio.sleep(0.05)
    with pytest.raises(GatewayError) as error:
        await service.decide(req())
    assert error.value.status == 429 and error.value.retry_after == 1
    gate.set()
    await first


async def test_gateways_listing_has_flags_and_no_secrets(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"ready": True, "models": []})

    service, _ = make(tmp_path, handler)
    rows = {row["id"]: row for row in await service.gateways()}
    assert rows["jev"]["images"] is True and rows["jev"]["types"] == ["box", "choice", "noul", "score"]
    assert rows["laya"]["streams"] is True and rows["laya"]["reachable"] is True
    assert "sk-secret" not in json.dumps(rows)


async def test_test_unknown_gateway(tmp_path):
    service, _ = make(tmp_path, laya_handler)
    with pytest.raises(GatewayError) as error:
        await service.test("nope")
    assert error.value.status == 404


async def test_a_test_that_gets_no_answer_gives_up_with_a_message(tmp_path, monkeypatch):
    async def silent(request):
        await asyncio.sleep(30)

    monkeypatch.setattr("src.gateway.decision.service.TEST_SECONDS", 0.2)
    service, _ = make(tmp_path, silent)
    with pytest.raises(GatewayError) as error:
        await service.test("laya")
    assert error.value.code == "gateway_timeout" and "No answer within" in error.value.message
