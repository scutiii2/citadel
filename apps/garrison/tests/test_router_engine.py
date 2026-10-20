import json
from dataclasses import replace

import pytest

from src.agents.router_contract import RouteRequest, RouteCandidate, RouterPolicy
from src.agents.router_engine import RouterEngine
from src.llm import decision
from src.llm.laya_provider import LayaQuestions


class Engine:
    def __init__(self, confidence=.99, choice="ops"):
        self.calls = []
        self.confidence = confidence
        self.choice = choice

    def predict(self, text, questions, **kwargs):
        self.calls.append((text, questions))
        answers = {}
        for qid, spec in questions.items():
            options = list(spec["criteria"])
            choice = self.choice if self.choice in options else options[0]
            answers[qid] = {"choice": choice, "answer_confidence": self.confidence,
                            "probabilities": {k: .99 if k == choice else .01 / (len(options)-1) for k in options}}
        return {"answers": answers, "usage": {"input_tokens": 12}}


def request(**changes):
    return RouteRequest(subject="Check my server", request_id="test", candidates=[
        RouteCandidate(id="ops", label="Ops", focus="server management")], **changes)


def router(engine=None):
    english = Engine() if engine is None else engine
    return RouterEngine({"laya-english": LayaQuestions(engine=english, window=4096),
                         "laya-typed": LayaQuestions(engine=Engine(), window=4096)}), english


def test_local_success_and_usage():
    r, model = router()
    response = r.route(request(), RouterPolicy())
    assert response.agent.choice == "ops" and not response.agent.uncertain
    assert response.size.choice == "tiny" and not response.size.uncertain
    assert len(model.calls) == 1  # both questions in one local prediction
    assert len(response.usage) == 1 and response.usage[0].input_tokens == 12
    assert response.usage[0].model == "convaiinnovations/laya"


def test_policy_isolated_and_uncertainty_never_becomes_execution():
    r, _ = router(Engine(.1))
    policy = RouterPolicy(typed=False, fallback=False)
    result = r.route(request(), policy)
    assert result.agent.uncertain
    assert decision.settings().triage_fallback is False
    assert decision.settings().triage_enabled["laya-typed"]["choice"] is True


def test_large_roster_abstains_only_agent():
    r, _ = router()
    req = request().model_copy(update={"candidates": [RouteCandidate(id=f"a{i}", label="A") for i in range(10)]})
    result = r.route(req, RouterPolicy())
    assert result.agent.uncertain and result.agent.reason == "too_many_candidates"
    assert not result.size.uncertain


def test_subject_over_remote_limit_does_not_call_any_model():
    r, engine = router()
    result = r.route(request().model_copy(update={"subject": "x" * 16001}), RouterPolicy())
    assert result.agent.reason == "input_too_long" and not engine.calls


def test_no_backend_and_explicit_tier_skip(monkeypatch):
    monkeypatch.setattr(decision, "available", lambda *args: False)
    r, engine = router()
    result = r.route(request().model_copy(update={"subject": "x" * 4001}), RouterPolicy())
    assert result.agent.uncertain and not engine.calls
    result = r.route(request(explicit_tier="heavy"), RouterPolicy())
    assert result.size.reason == "explicit_tier"


def test_cancelled_before_inference_records_no_work():
    r, engine = router()
    result = r.route(request(), RouterPolicy(), cancelled=lambda: True)
    assert result.agent.reason == "cancelled" and not engine.calls


def test_timeout_after_local_work_retains_usage_and_abstains():
    clock = [0.0]
    class Slow(Engine):
        def predict(self, *args, **kwargs):
            clock[0] = 11
            return super().predict(*args, **kwargs)
    r, _ = router(Slow())
    result = r.route(request(), RouterPolicy(), clock=lambda: clock[0])
    assert result.agent.reason == "timeout" and result.usage[0].input_tokens == 12


def test_agent_failure_does_not_discard_independent_size(monkeypatch):
    from src.llm.triage_flow import TriageFlow
    original = TriageFlow._settle_choice
    def settle(self, req, qid, spec):
        if qid == "agent":
            raise ValueError("no model could settle agent")
        return original(self, req, qid, spec)
    monkeypatch.setattr(TriageFlow, "_settle_choice", settle)
    r, _ = router()
    result = r.route(request(), RouterPolicy())
    assert result.agent.uncertain and not result.size.uncertain


def test_remote_long_input_skips_local_and_retains_backend_usage(monkeypatch):
    monkeypatch.setattr(decision, "available", lambda *args: True)
    calls = []
    class Backend:
        def available(self): return True
        def ask_choice(self, subject, criteria, question, timeout):
            calls.append(timeout)
            return decision.Choice(next(iter(criteria)), 99, 10, "jev", "jev-live")
    monkeypatch.setattr(decision, "_backend", lambda _: Backend())
    r, engine = router()
    result = r.route(request().model_copy(update={"subject": "x" * 4001}), RouterPolicy())
    assert not engine.calls and calls
    assert all(0 < timeout <= 3 for timeout in calls)
    assert result.usage[0].model == "jev-live" and not result.agent.uncertain
