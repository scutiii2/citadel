import base64
import json

import httpx
import pytest

from src.gateway.decision.contract import DecisionRequest
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways import build_gateway

PNG = base64.b64encode(b"\x89PNG fake").decode()
ENTRY = {"kind": "typesafe", "url": "https://api.typesafe.ai/v1/systemone", "api_key": "sk-secret", "model": "jev-latest", "timeout_s": 5}
CHOICE = {"type": "choice", "instructions": "Which team?", "criteria": {"billing": "Invoices", "returns": "Refunds"}}


def gateway(handler):
    return build_gateway("jev", ENTRY, httpx.MockTransport(handler))


def reply(answer, tokens=12, model="jev-1.14.0"):
    return httpx.Response(200, json={"model": model, "answers": {"answer": answer}, "usage": {"input_tokens": tokens, "output_tokens": 1}})


def req(questions, **kwargs):
    return DecisionRequest("jev", "card charged twice", questions, **kwargs)


async def test_choice_call_and_mapping():
    seen = {}

    def handler(request):
        seen["auth"], seen["images"] = request.headers["authorization"], request.headers.get("typesafe-danger-zone-images")
        seen["body"] = json.loads(request.content)
        return reply({"type": "choice", "choice": "billing", "confidence": 0.95, "probabilities": {"billing": 0.95, "returns": 0.05}})

    result = await gateway(handler).ask(req({"team": CHOICE}))
    assert seen["auth"] == "Bearer sk-secret" and seen["images"] is None
    assert seen["body"] == {"model": "jev-latest", "state": "card charged twice", "questions": {"answer": CHOICE}}
    answer = result.answers["team"]
    assert answer["choice"] == "billing" and answer["uncertain"] is False
    assert (result.tokens, result.model) == (12, "jev-1.14.0")


async def test_default_bar_is_point_nine_and_caller_minimum_wins():
    low = {"type": "choice", "choice": "billing", "confidence": 0.8, "probabilities": {"billing": 0.8, "returns": 0.2}}
    assert (await gateway(lambda r: reply(low)).ask(req({"team": CHOICE}))).answers["team"]["uncertain"] is True
    assert (await gateway(lambda r: reply(low)).ask(req({"team": CHOICE}, min_confidence=0.7))).answers["team"]["uncertain"] is False


async def test_score_noul_are_sent_natively():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body["questions"]["answer"])
        if body["questions"]["answer"]["type"] == "score":
            return reply({"type": "score", "score": 0.7, "confidence": 0.95, "legend": {"0": "a", "1": "b"}, "probabilities": {"0": 0.1, "1": 0.9}})
        return reply({"type": "noul", "noul": 0.98})

    questions = {"u": {"type": "score", "instructions": "How urgent?", "criteria": ["low", "high"]},
                 "b": {"type": "noul", "instructions": "Billing?"}}
    result = await gateway(handler).ask(req(questions))
    assert {b["type"] for b in bodies} == {"score", "noul"}
    assert result.answers["u"]["score"] == 0.7 and result.answers["b"]["noul"] == 0.98


async def test_images_send_header_and_only_referenced_assets():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.headers.get("typesafe-danger-zone-images"), sorted(body.get("assets", {}))))
        if body["questions"]["answer"]["type"] == "box":
            return reply({"type": "box", "box": {"top": 0.2, "bottom": 0.6, "left": 0.1, "right": 0.5}, "confidence": None})
        return reply({"type": "noul", "noul": 0.9})

    assets = {"imgA": {"type": "image", "format": "png", "data_base64": PNG}, "imgB": {"type": "image", "format": "png", "data_base64": PNG}}
    questions = {"where": {"type": "box", "instructions": "Locate the box in imgA"},
                 "same": {"type": "noul", "instructions": "Is imgB a dog?"}}
    result = await gateway(handler).ask(req(questions, assets=assets, min_confidence=0.5))
    assert sorted(calls) == [("true", ["imgA"]), ("true", ["imgB"])]
    assert result.answers["where"]["box"]["top"] == 0.2 and result.answers["where"]["uncertain"] is True


async def test_no_assets_no_header_when_question_has_none():
    seen = []

    def handler(request):
        seen.append(request.headers.get("typesafe-danger-zone-images"))
        return reply({"type": "noul", "noul": 0.9})

    assets = {"imgA": {"type": "image", "format": "png", "data_base64": PNG}}
    questions = {"a": {"type": "noul", "instructions": "no images here"}}
    await gateway(handler).ask(DecisionRequest("jev", "plain text", questions, assets={}))
    assert seen == [None]


@pytest.mark.parametrize("status,code,http", [(400, "gateway_refused", 422), (401, "gateway_auth", 502), (413, "too_large", 413),
                                               (429, "gateway_busy", 503), (500, "gateway_error", 502)])
async def test_error_mapping_hides_upstream_text(status, code, http):
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: httpx.Response(status, text="secret upstream body sk-secret")).ask(req({"team": CHOICE}))
    assert (error.value.code, error.value.status) == (code, http)
    assert "sk-secret" not in error.value.message and "secret upstream" not in error.value.message


async def test_unreachable_and_bad_reply():
    def boom(request):
        raise httpx.ConnectError("no route to api.typesafe.ai")

    with pytest.raises(GatewayError) as error:
        await gateway(boom).ask(req({"team": CHOICE}))
    assert error.value.code == "gateway_unreachable" and "typesafe.ai" not in error.value.message
    with pytest.raises(GatewayError) as error:
        await gateway(lambda r: reply({"type": "choice", "choice": "nope", "confidence": 0.9, "probabilities": {"billing": 0.5, "returns": 0.5}})).ask(req({"team": CHOICE}))
    assert error.value.code == "gateway_bad_reply"


async def test_probe_uses_models_endpoint():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"models": []})

    assert "reachable" in (await gateway(handler).probe()).lower()
    assert seen == ["https://api.typesafe.ai/v1/models"]


def test_capabilities():
    g = gateway(lambda r: reply({}))
    assert (g.streams, g.images, g.kind) == (False, True, "typesafe") and g.types == {"choice", "score", "noul", "box"}
