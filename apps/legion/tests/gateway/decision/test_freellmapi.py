import json

import httpx
import pytest

from src.gateway.decision.contract import DecisionRequest
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways import build_gateway

ENTRY = {"kind": "freellmapi", "url": "http://h:29652", "api_key": "sk-1", "model": "", "timeout_s": 5}
CHOICE = {"type": "choice", "instructions": "Which tier?", "criteria": {"chat": "Casual", "code": "Coding", "reasoning": "Maths"}}


def gateway(handler, **extra):
    return build_gateway("free", {**ENTRY, **extra}, httpx.MockTransport(handler))


async def test_one_call_to_v1_decisions_with_the_key_and_default_noul_criteria():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        return httpx.Response(200, json={"object": "decision", "model": "clef", "provider": "cloudflare", "usage": {"input_tokens": 40, "output_tokens": 0},
                                         "answers": {"t": {"type": "choice", "choice": "code", "confidence": 0.9, "probabilities": {"chat": 0.05, "code": 0.9, "reasoning": 0.05}},
                                                     "n": {"type": "noul", "noul": 0.97}}})

    result = await gateway(handler).ask(DecisionRequest("free", "useEffect runs twice", {"t": CHOICE, "n": {"type": "noul", "instructions": "React?"}}))
    assert seen["url"] == "http://h:29652/v1/decisions" and seen["auth"] == "Bearer sk-1"
    assert "model" not in seen["body"] and seen["body"]["state"] == "useEffect runs twice"
    assert seen["body"]["questions"]["n"]["criteria"] == {"true": "Yes", "false": "No"}
    assert result.tokens == 40 and result.model == "clef"
    assert result.answers["t"]["choice"] == "code" and result.answers["t"]["uncertain"] is False
    assert result.answers["n"]["answer_confidence"] == 0.97


async def test_a_pinned_model_is_sent_and_an_address_ending_in_v1_works():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 0.2}}, "usage": {}})

    result = await gateway(handler, url="http://h:29652/v1", model="clef").ask(DecisionRequest("free", "t", {"q": {"type": "noul", "instructions": "x"}}))
    assert seen["url"] == "http://h:29652/v1/decisions" and seen["body"]["model"] == "clef" and result.model == "clef"


@pytest.mark.parametrize("body", [{}, {"answers": {}}, {"answers": {"q": {"type": "choice", "choice": "nope", "confidence": 0.9, "probabilities": {}}}}])
async def test_unusable_replies_are_a_bad_reply(body):
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(200, json=body)).ask(DecisionRequest("free", "t", {"q": CHOICE}))
    assert error.value.code == "gateway_bad_reply" and "h:29652" not in error.value.message


async def test_probe_lists_decision_models_and_a_refused_key_is_reported():
    seen = {}

    def ok(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": []})

    assert "reachable" in await gateway(ok).probe() and seen["url"] == "http://h:29652/v1/decisions/models"
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(401, text="bad key sk-1")).probe()
    assert error.value.code == "gateway_auth" and "sk-1" not in error.value.message
