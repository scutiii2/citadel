import json

import httpx
import pytest

from src.gateway.decision.contract import DecisionRequest
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways import build_gateway

ENTRY = {"kind": "ollama", "url": "http://127.0.0.1:11434", "model": "d3:2b", "timeout_s": 5}
CHOICE = {"type": "choice", "instructions": "Team?", "criteria": {"a": "A", "b": "B", "c": "C"}}


def gateway(handler):
    return build_gateway("d3", ENTRY, httpx.MockTransport(handler))


async def test_one_call_for_all_questions_and_default_noul_criteria():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"answers": {
            "t": {"type": "choice", "choice": "a", "confidence": 0.8, "probabilities": {"a": 0.8, "b": 0.1, "c": 0.1}},
            "n": {"type": "noul", "noul": 0.97}}, "usage": {"input_tokens": 40}})

    questions = {"t": CHOICE, "n": {"type": "noul", "instructions": "Billing?"}}
    result = await gateway(handler).ask(DecisionRequest("d3", "state text", questions))
    assert seen["url"] == "http://127.0.0.1:11434/v1/systemone"
    assert seen["body"]["questions"]["n"]["criteria"] == {"true": "Yes", "false": "No"}
    assert seen["body"]["model"] == "d3:2b" and seen["body"]["state"] == "state text"
    assert result.tokens == 40 and result.model == "d3:2b"
    assert result.answers["t"]["uncertain"] is False   # 0.8 >= 0.75 (three options)
    assert result.answers["n"]["answer_confidence"] == 0.97


async def test_two_option_bar_and_caller_minimum():
    answer = {"type": "choice", "choice": "a", "confidence": 0.8, "probabilities": {"a": 0.8, "b": 0.2}}
    two = {"type": "choice", "instructions": "x", "criteria": {"a": "A", "b": "B"}}
    handler = lambda r: httpx.Response(200, json={"answers": {"q": answer}, "usage": {}})
    assert (await gateway(handler).ask(DecisionRequest("d3", "t", {"q": two}))).answers["q"]["uncertain"] is True
    assert (await gateway(handler).ask(DecisionRequest("d3", "t", {"q": two}, min_confidence=0.5))).answers["q"]["uncertain"] is False


@pytest.mark.parametrize("response", [httpx.ConnectError("down"), httpx.Response(404, text="model not found"),
                                      httpx.Response(500, text="llama crashed at /home/x")])
async def test_unavailable_model_is_503_without_details(response):
    def handler(request):
        if isinstance(response, Exception):
            raise response
        return response

    with pytest.raises(GatewayError) as error:
        await gateway(handler).ask(DecisionRequest("d3", "t", {"q": CHOICE}))
    assert error.value.status == 503 and error.value.code == "gateway_not_ready"
    assert "llama crashed" not in error.value.message and "/home/x" not in error.value.message and "127.0.0.1" not in error.value.message


async def test_bad_answers_are_a_bad_reply():
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(200, json={"answers": {"q": {"choice": "zzz"}}})).ask(DecisionRequest("d3", "t", {"q": CHOICE}))
    assert error.value.code == "gateway_bad_reply"


async def test_probe_checks_the_model_is_installed():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"details": {}})

    assert "installed" in await gateway(handler).probe()
    assert seen == {"url": "http://127.0.0.1:11434/api/show", "body": {"model": "d3:2b"}}


def test_capabilities():
    g = gateway(lambda r: httpx.Response(200, json={}))
    assert (g.streams, g.images) == (False, False) and "box" not in g.types
