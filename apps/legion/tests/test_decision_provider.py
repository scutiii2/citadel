import asyncio
import json
from src.providers.decision import provider, strategy
from src.providers.decision.contract import DecisionError

import pytest

from src.agents import agent_spec
from src.agents.agent_spec import AgentSpecError


def load(tmp_path, llm, **extra):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"port": 9111, "role": "specialist", "llm": llm, **extra}), encoding="utf-8")
    return agent_spec.load_file(path)


def test_decision_provider_defaults(tmp_path):
    spec = load(tmp_path, {"provider": "decision"})
    assert spec.llm.provider == "decision" and spec.llm.strategy == "both" and spec.llm.min_confidence == 0.9


def test_decision_strategy_validated(tmp_path):
    assert load(tmp_path, {"provider": "decision", "strategy": "laya-only"}).llm.strategy == "laya-only"
    with pytest.raises(AgentSpecError, match="strategy"):
        load(tmp_path, {"provider": "decision", "strategy": "sometimes"})


def test_decision_refuses_language_settings(tmp_path):
    for key, value in (("gateway", "laya"), ("model", "x"), ("temperature", 0.1), ("fallback_gateways", ["a"])):
        with pytest.raises(AgentSpecError):
            load(tmp_path, {"provider": "decision", key: value})


def test_strategy_only_for_decision(tmp_path):
    with pytest.raises(AgentSpecError, match="strategy"):
        load(tmp_path, {"provider": "anthropic", "strategy": "both"})


def test_laya_is_no_longer_a_provider(tmp_path):
    with pytest.raises(AgentSpecError, match="provider"):
        load(tmp_path, {"provider": "laya"})



def test_answer_runs_the_agents_strategy(monkeypatch):
    seen = {}

    def fake_run(name, request, **kwargs):
        seen.update(name=name, minimum=request.min_confidence, local_only=request.local_only)
        return strategy.DecisionResult({"q": {"choice": "a", "answer_confidence": 0.95, "uncertain": False, "answered_by": "laya"}}, 7, ())

    monkeypatch.setattr(strategy, "run", fake_run)
    raw = json.dumps({"text": "hi", "questions": {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}})
    result = provider.answer(raw, "both", 0.9)
    body = json.loads(result.response)
    assert seen == {"name": "both", "minimum": 0.9, "local_only": False}
    assert body["answers"]["q"]["answered_by"] == "laya" and result.total_tokens == 7


def test_answer_reports_decision_error(monkeypatch):
    monkeypatch.setattr(strategy, "run", lambda *a, **k: (_ for _ in ()).throw(DecisionError("nothing answered")))
    raw = json.dumps({"text": "hi", "questions": {"q": {"type": "noul", "instructions": "?"}}})
    try:
        provider.answer(raw, "both", 0.9)
    except ValueError as error:
        assert "nothing answered" in str(error)
    else:
        raise AssertionError("expected an error")


@pytest.mark.parametrize("question", [
    None, [], {}, {"type": "unknown", "instructions": "?"},
    {"type": "noul"}, {"type": "noul", "instructions": " "},
    {"type": "choice", "instructions": "?"},
    {"type": "choice", "instructions": "?", "criteria": []},
    {"type": "choice", "instructions": "?", "criteria": {}},
    {"type": "choice", "instructions": "?", "criteria": {"a": 3}},
    {"type": "score", "instructions": "?", "criteria": {"low": "Low"}},
    {"type": "score", "instructions": "?", "criteria": []},
    {"type": "score", "instructions": "?", "criteria": ["low", None]},
    {"type": "noul", "instructions": "?", "criteria": {"maybe": "Maybe"}},
])
def test_malformed_questions_fail_before_gateway_dispatch(monkeypatch, question):
    calls = []
    monkeypatch.setattr(strategy, "run", lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match="Invalid decision request:.*questions.q"):
        provider.answer(json.dumps({"text": "hi", "questions": {"q": question}}), "jev-only", 0.9)
    assert calls == []


@pytest.mark.parametrize("question", [
    {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}},
    {"type": "score", "instructions": "?", "criteria": ["low", "high"]},
    {"type": "noul", "instructions": "?"},
    {"type": "noul", "instructions": "?", "criteria": {"false": "No", "true": "Yes"}},
])
def test_valid_questions_need_no_live_laya_validation(question):
    request = provider.parse_request(json.dumps({"text": "hi", "questions": {"q": question}}))
    assert request.questions == {"q": question}


def _detailed(monkeypatch):
    answer = {"choice": "a", "answer_confidence": 0.95, "uncertain": False, "answered_by": "laya",
              "rounds": [{"step": "laya-english"}], "voters": {"laya-english": {}}, "resolved_by": "english"}
    monkeypatch.setattr(strategy, "run", lambda *a, **k: strategy.DecisionResult({"q": dict(answer)}, 1, ()))


def test_answer_drops_service_detail_unless_trace_is_requested(monkeypatch):
    _detailed(monkeypatch)
    question = {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}
    compact = json.loads(provider.answer(json.dumps({"text": "hi", "questions": question}), "both", 0.9).response)
    full = json.loads(provider.answer(json.dumps({"text": "hi", "questions": question, "trace": True}), "both", 0.9).response)
    assert "rounds" not in compact["answers"]["q"] and compact["answers"]["q"]["choice"] == "a"
    assert full["answers"]["q"]["rounds"] and full["answers"]["q"]["resolved_by"] == "english"
