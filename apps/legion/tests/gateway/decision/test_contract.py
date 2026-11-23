import base64

import pytest

from src.gateway.decision.contract import assets_for, parse_questions, parse_request
from src.gateway.decision.errors import GatewayError

PNG = base64.b64encode(b"\x89PNG fake").decode()
CHOICE = {"type": "choice", "instructions": "Which team?", "criteria": {"billing": "Invoices", "returns": "Refunds"}}


def body(**extra):
    return {"gateway": "jev", "text": "card charged twice", "questions": {"team": CHOICE}, **extra}


def bad(data, message, **kwargs):
    with pytest.raises(GatewayError) as error:
        parse_request(data, 16000, **kwargs)
    assert error.value.status == 422 and message in error.value.message


def test_minimal_request():
    r = parse_request(body(), 16000)
    assert (r.gateway, r.text, r.assets, r.min_confidence, r.trace, r.stream) == ("jev", "card charged twice", {}, None, False, False)


def test_unknown_field_and_missing_parts():
    bad(body(extra=1), "unknown field")
    bad({**body(), "gateway": ""}, "gateway")
    bad({k: v for k, v in body().items() if k != "text"}, "text")
    with pytest.raises(GatewayError, match="at most 16 characters"):
        parse_request({**body(), "text": "x" * 17}, 16)


def test_gateway_not_required_for_validate():
    data = {k: v for k, v in body().items() if k != "gateway"}
    assert parse_request(data, 16000, require_gateway=False).gateway == ""


@pytest.mark.parametrize("questions,message", [
    ({}, "1 to 8"),
    ({"q": {"type": "pick", "instructions": "x"}}, "type"),
    ({"q": {"type": "choice", "instructions": " ", "criteria": {"a": "x", "b": "y"}}}, "instructions"),
    ({"q": {"type": "choice", "instructions": "x", "criteria": {"a": "x"}}}, "2 to 10"),
    ({"q": {"type": "score", "instructions": "x", "criteria": "no"}}, "list"),
    ({"q": {"type": "noul", "instructions": "x", "criteria": {"yes": "a", "no": "b"}}}, "false"),
    ({"q": {"type": "box", "instructions": "x", "criteria": {"a": "b"}}}, "criteria"),
    ({"q": {"type": "choice", "instructions": "x", "criteria": {"a": "x", "b": "y"}, "extra": 1}}, "unknown field"),
])
def test_bad_questions(questions, message):
    with pytest.raises(GatewayError) as error:
        parse_questions(questions)
    assert message in error.value.message


def test_good_questions_of_every_type():
    parse_questions({
        "c": CHOICE,
        "s": {"type": "score", "instructions": "How urgent?", "criteria": ["low", "high"]},
        "n": {"type": "noul", "instructions": "Billing?"},
        "n2": {"type": "noul", "instructions": "Billing?", "criteria": {"true": "yes", "false": "no"}},
    })


def test_min_confidence_trace_stream_types():
    bad(body(min_confidence=0), "min_confidence")
    bad(body(min_confidence=1.5), "min_confidence")
    bad(body(min_confidence=True), "min_confidence")
    bad(body(trace="yes"), "trace")
    bad(body(stream=1), "stream")
    r = parse_request(body(min_confidence=0.8, trace=True, stream=True), 16000)
    assert (r.min_confidence, r.trace, r.stream) == (0.8, True, True)


def test_assets_valid_and_referenced():
    questions = {"where": {"type": "box", "instructions": "Locate the red box in img1"}}
    data = body(questions=questions, assets={"img1": {"type": "image", "format": "png", "data_base64": PNG}})
    assert parse_request(data, 16000).assets["img1"]["format"] == "png"


@pytest.mark.parametrize("assets,message", [
    ({}, "assets"),
    ({"img1": {"type": "image", "format": "gif", "data_base64": PNG}}, "format"),
    ({"img1": {"type": "audio", "format": "png", "data_base64": PNG}}, "type"),
    ({"img1": {"type": "image", "format": "png", "data_base64": "not base64!!"}}, "base64"),
    ({"img1": {"type": "image", "format": "png"}}, "data_base64"),
    ({"img1": {"type": "image", "format": "png", "data_base64": PNG, "part": "x"}}, "unknown field"),
    ({"zzz": {"type": "image", "format": "png", "data_base64": PNG}}, "not used"),
])
def test_bad_assets(assets, message):
    data = body(text="see img1", assets=assets)
    bad(data, message)


def test_box_needs_assets():
    bad(body(questions={"b": {"type": "box", "instructions": "find it"}}), "box")


def test_asset_size_limit(monkeypatch):
    import src.gateway.decision.contract as contract
    monkeypatch.setattr(contract, "MAX_IMAGE_BYTES", 4)
    bad(body(text="img1", assets={"img1": {"type": "image", "format": "png", "data_base64": PNG}}), "16 MiB")


def test_assets_for_picks_only_referenced_placeholders():
    assets = {"imgA": {"x": 1}, "imgB": {"x": 2}, "imgC": {"x": 3}}
    spec = {"type": "noul", "instructions": "is it like imgB?"}
    assert assets_for("photo imgA", spec, assets) == {"imgA": {"x": 1}, "imgB": {"x": 2}}
