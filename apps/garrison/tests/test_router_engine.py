import json
from dataclasses import replace

import pytest

from src.agents.roles.router.router_contract import RouteRequest, RouteCandidate, RouterPolicy
from src.agents.roles.router.router_engine import RouterEngine
from src.providers.decision import decision
from tests.fake_laya import FakeService, choice, result


class Engine(FakeService):
    """The Laya service answering every question with `choice` (or the first option) at `confidence`."""

    def __init__(self, confidence=.99, pick="ops", tokens=12):
        super().__init__()
        self.confidence, self.pick, self.tokens = confidence, pick, tokens

    @property
    def calls(self):
        return self.asked

    def ask(self, strategy, text, questions, max_len, **tuning):
        self.asked.append({"strategy": strategy, "text": text, "questions": questions, "max_len": max_len, **tuning})
        answers = []
        for qid, spec in questions.items():
            options = list(spec["criteria"])
            pick = self.pick if self.pick in options else options[0]
            answers.append((qid, choice(pick, self.confidence, options, uncertain=self.confidence < .75)))
        return result(*answers, tokens=self.tokens)


def request(**changes):
    return RouteRequest(subject="Check my server", request_id="test", candidates=[
        RouteCandidate(id="ops", label="Ops", focus="server management")], **changes)


def router(engine=None):
    service = Engine() if engine is None else engine
    return RouterEngine(service), service


def test_local_success_and_usage():
    r, model = router()
    response = r.route(request(), RouterPolicy())
    assert response.agent.choice == "ops" and not response.agent.uncertain
    assert response.size.choice == "tiny" and not response.size.uncertain
    assert len(model.calls) == 1  # both questions in one service call
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
        def ask(self, *args, **kwargs):
            clock[0] = 11
            return super().ask(*args, **kwargs)
    r, _ = router(Slow())
    result = r.route(request(), RouterPolicy(), clock=lambda: clock[0])
    assert result.agent.reason == "timeout" and result.usage[0].input_tokens == 12


def test_agent_failure_does_not_discard_independent_size(monkeypatch):
    from src.providers.decision.triage_flow import TriageFlow
    original = TriageFlow._settle
    def settle(self, req, qid, spec, local):
        if qid == "agent":
            raise ValueError("no model could settle agent")
        return original(self, req, qid, spec, local)
    monkeypatch.setattr(TriageFlow, "_settle", settle)
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
