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
