import pytest

from src.providers.decision.contract import DecisionError, DecisionRequest
from src.providers.decision.gateways.jev import JevGateway


def reply(choice, confidence, probs=None):
    answer = {"choice": choice, "confidence": confidence}
    if probs:
        answer["probabilities"] = probs
    return {"answers": {"answer": answer}, "model": "jev-latest", "usage": {"input_tokens": 12}}


def gateway(monkeypatch, replies):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    sent = []

    def post(url, payload, key, timeout):
        sent.append(payload)
        return replies.pop(0)

    return JevGateway(post=post), sent


def test_choice_question(monkeypatch):
    jev, sent = gateway(monkeypatch, [reply("a", 0.95, {"a": 0.95, "b": 0.05})])
    request = DecisionRequest("text", {"q": {"type": "choice", "instructions": "Which?", "criteria": {"a": "A", "b": "B"}}})
    result = jev.ask(request)
    answer = result.answers["q"]
    assert answer["choice"] == "a" and answer["answer_confidence"] == 0.95 and answer["probabilities"]["b"] == 0.05
    assert answer["uncertain"] is False and result.tokens == 12
    assert sent[0]["questions"]["answer"]["criteria"] == {"a": "A", "b": "B"}


def test_score_is_reduced_to_levels(monkeypatch):
    jev, sent = gateway(monkeypatch, [reply("1", 0.9)])
    request = DecisionRequest("t", {"q": {"type": "score", "instructions": "Rate", "criteria": ["low", "high"]}})
    answer = jev.ask(request).answers["q"]
    assert answer["score"] == 1.0 and answer["legend"] == {"0": "low", "1": "high"}
    assert list(sent[0]["questions"]["answer"]["criteria"]) == ["0", "1"]


def test_noul_maps_to_probability(monkeypatch):
    jev, _ = gateway(monkeypatch, [reply("true", 0.8)])
    answer = jev.ask(DecisionRequest("t", {"q": {"type": "noul", "instructions": "Is it?"}})).answers["q"]
    assert answer["noul"] == 0.8


def test_low_confidence_is_uncertain(monkeypatch):
    jev, _ = gateway(monkeypatch, [reply("a", 0.5)])
    request = DecisionRequest("t", {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}, min_confidence=0.9)
    assert jev.ask(request).answers["q"]["uncertain"] is True


def test_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    jev = JevGateway(post=lambda *a: {})
    assert jev.available() is False
    with pytest.raises(DecisionError):
        jev.ask(DecisionRequest("t", {"q": {"type": "noul", "instructions": "?"}}))


def test_jev_uses_its_default_bar_without_a_minimum(monkeypatch):
    jev, _ = gateway(monkeypatch, [reply("a", 0.85), reply("a", 0.95)])
    request = DecisionRequest("t", {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}})
    assert jev.ask(request).answers["q"]["uncertain"] is True
    assert jev.ask(request).answers["q"]["uncertain"] is False
