import pytest

from src.providers.decision import strategy
from src.providers.decision.contract import DecisionError, DecisionRequest, GatewayResult
from tests.decision_fakes import Fake

Q = {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}


def gateways(laya, jev):
    return {"laya": laya, "jev": jev}


def test_laya_only_never_asks_jev():
    laya, jev = Fake("laya", True, 0.5), Fake("jev", False, 0.99)
    result = strategy.run("laya-only", DecisionRequest("t", Q), gateways=gateways(laya, jev))
    assert jev.asked == [] and result.unsettled == ("q",) and result.answers["q"]["uncertain"] is True


def test_jev_only_never_asks_laya():
    laya, jev = Fake("laya", True, 0.99), Fake("jev", False, 0.99)
    result = strategy.run("jev-only", DecisionRequest("t", Q), gateways=gateways(laya, jev))
    assert laya.asked == [] and result.answers["q"]["answered_by"] == "jev"


def test_both_stops_when_laya_is_sure():
    laya, jev = Fake("laya", True, 0.95), Fake("jev", False, 0.99)
    result = strategy.run("both", DecisionRequest("t", Q), gateways=gateways(laya, jev))
    assert jev.asked == [] and result.answers["q"]["answered_by"] == "laya" and result.unsettled == ()


def test_both_asks_jev_only_about_unsettled_questions():
    two = {**Q, "r": Q["q"]}
    laya = Fake("laya", True)
    laya.ask = lambda request, timeout=None: GatewayResult(
        {"q": {"choice": "a", "answer_confidence": 0.95, "uncertain": False},
         "r": {"choice": "a", "answer_confidence": 0.4, "uncertain": True}}, 1, "laya")
    jev = Fake("jev", False, 0.97)
    result = strategy.run("both", DecisionRequest("t", two), gateways=gateways(laya, jev))
    assert jev.asked == [["r"]]
    assert result.answers["q"]["answered_by"] == "laya" and result.answers["r"]["answered_by"] == "jev"


def test_both_falls_through_when_laya_fails():
    result = strategy.run("both", DecisionRequest("t", Q),
                          gateways=gateways(Fake("laya", True, fail=True), Fake("jev", False, 0.97)))
    assert result.answers["q"]["answered_by"] == "jev"


def test_local_only_skips_jev():
    laya, jev = Fake("laya", True, 0.4), Fake("jev", False, 0.99)
    strategy.run("both", DecisionRequest("t", Q, local_only=True), gateways=gateways(laya, jev))
    assert jev.asked == []


def test_nothing_answered_raises():
    with pytest.raises(DecisionError, match="laya down"):
        strategy.run("laya-only", DecisionRequest("t", Q), gateways=gateways(Fake("laya", True, fail=True), Fake("jev", False, 0.9)))


def test_unavailable_gateway_is_skipped_and_reported():
    with pytest.raises(DecisionError, match="not available"):
        strategy.run("laya-only", DecisionRequest("t", Q), gateways=gateways(Fake("laya", True, available=False), Fake("jev", False, 0.9)))


def test_unknown_strategy():
    with pytest.raises(ValueError):
        strategy.run("sometimes", DecisionRequest("t", Q), gateways={})


def test_usage_records_one_per_attempt():
    seen = []
    strategy.run("both", DecisionRequest("t", Q), gateways=gateways(Fake("laya", True, 0.4), Fake("jev", False, 0.97)),
                 on_usage=seen.append)
    assert [(r["provider_id"], r["ok"]) for r in seen] == [("laya", True), ("jev", True)]


def test_ask_choice_returns_percent_confidence():
    picked = strategy.ask_choice("t", {"a": "A", "b": "B"}, "?", strategy="laya-only", min_confidence=80,
                                 gateways=gateways(Fake("laya", True, 0.9), Fake("jev", False, 0.9)))
    assert (picked.choice, picked.confidence, picked.backend) == ("a", 90, "laya")
