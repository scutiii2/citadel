import json

import httpx
import pytest

from src.gateway.decision.contract import DecisionRequest
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways import build_gateway

ENTRY = {"kind": "scuti", "url": "http://127.0.0.1:29220", "token": "laya_tok", "strategy": "auto", "window": 4096, "timeout_s": 5}
CHOICE = {"type": "choice", "instructions": "Team?", "criteria": {"a": "A", "b": "B"}}
ANSWER = {"type": "choice", "choice": "a", "probabilities": {"a": 0.95, "b": 0.05}, "answer_confidence": 0.95, "uncertain": False}
BODY = {"strategy": "auto", "model": "laya", "answers": {"q": ANSWER}, "uncertain": [], "calls": [{"input_tokens": 30}, {"input_tokens": 12}]}


def gateway(handler, entry=ENTRY):
    return build_gateway("laya", entry, httpx.MockTransport(handler))


async def test_ask_body_headers_and_summed_tokens():
    seen = {}

    def handler(request):
        seen["url"], seen["token"], seen["body"] = str(request.url), request.headers["x-internal-token"], json.loads(request.content)
        return httpx.Response(200, json=BODY)

    result = await gateway(handler).ask(DecisionRequest("laya", "hello", {"q": CHOICE}, min_confidence=0.8, trace=True))
    assert seen["url"] == "http://127.0.0.1:29220/v1/ask" and seen["token"] == "laya_tok"
    assert seen["body"] == {"text": "hello", "questions": {"q": CHOICE}, "trace": True, "strategy": "auto", "max_len": 4096, "min_confidence": 0.8}
    assert result.answers["q"]["choice"] == "a" and result.tokens == 42 and result.model == "laya"


async def test_optional_fields_are_left_out():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=BODY)

    entry = {"kind": "scuti", "url": "http://127.0.0.1:29221", "timeout_s": 5}
    await gateway(handler, entry).ask(DecisionRequest("d3", "hello", {"q": CHOICE}))
    assert seen["body"] == {"text": "hello", "questions": {"q": CHOICE}, "trace": False}


async def test_busy_service_is_retried_with_retry_after(monkeypatch):
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr("src.gateway.decision.gateways.scuti.asyncio.sleep", fake_sleep)
    replies = iter([httpx.Response(429, headers={"retry-after": "2"}), httpx.Response(429, headers={"retry-after": "99"}), httpx.Response(200, json=BODY)])
    result = await gateway(lambda r: next(replies)).ask(DecisionRequest("laya", "t", {"q": CHOICE}))
    assert waits == [2.0, 10.0] and result.answers["q"]["choice"] == "a"


async def test_still_busy_after_retries_is_503(monkeypatch):
    async def no_sleep(seconds):
        return None

    monkeypatch.setattr("src.gateway.decision.gateways.scuti.asyncio.sleep", no_sleep)
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(429)).ask(DecisionRequest("laya", "t", {"q": CHOICE}))
    assert error.value.status == 503


@pytest.mark.parametrize("response,status", [(httpx.Response(422, json={"detail": "bad"}), 422), (httpx.Response(413), 413), (httpx.Response(502, json={"detail": {"message": "x"}}), 502)])
async def test_errors_are_mapped(response, status):
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: response).ask(DecisionRequest("laya", "t", {"q": CHOICE}))
    assert error.value.status == status and "bad" not in error.value.message


async def test_stream_relays_answers_then_done():
    lines = [{"type": "answer", "id": "q", "answer": ANSWER}, {"type": "done", **BODY}]
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content="\n".join(json.dumps(line) for line in lines).encode(), headers={"content-type": "application/x-ndjson"})

    items = [item async for item in gateway(handler).ask_stream(DecisionRequest("laya", "t", {"q": CHOICE}, stream=True))]
    assert seen["body"]["stream"] is True
    assert items[0] == ("answer", "q", ANSWER)
    assert items[1][0] == "done" and items[1][1].tokens == 42 and items[1][1].answers["q"]["choice"] == "a"


async def test_stream_error_line():
    content = json.dumps({"type": "error", "status": 502, "detail": "secret"}).encode()
    with pytest.raises(GatewayError) as error:
        [i async for i in gateway(lambda r: httpx.Response(200, content=content)).ask_stream(DecisionRequest("laya", "t", {"q": CHOICE}, stream=True))]
    assert error.value.status == 502 and "secret" not in error.value.message


async def test_probe_reports_not_ready():
    assert "ready" in (await gateway(lambda r: httpx.Response(200, json={"status": "ok", "ready": True})).probe()).lower()
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(200, json={"status": "ok", "ready": False})).probe()
    assert error.value.status == 503


def test_capabilities():
    g = gateway(lambda r: httpx.Response(200, json={}))
    assert (g.streams, g.images) == (True, False) and g.types == {"choice", "score", "noul"}
