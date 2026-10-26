from src.agents.roles.router.router_contract import RouteRequest, RouteCandidate, RouterPolicy
from src.agents.roles.router.router_engine import RouterEngine
from src.providers.decision import settings
from src.providers.decision.contract import DecisionError, GatewayResult
from tests.decision_fakes import Fake as FakeGateway


def request(**changes):
    return RouteRequest(subject="Check my server", request_id="test", candidates=[
        RouteCandidate(id="ops", label="Ops", focus="server management")], **changes)


def local(confidence=.99):
    return FakeGateway("laya", True, confidence, pick="ops", tokens=12, model="english-then-typed")


def router(laya=None, jev=None):
    laya = laya if laya is not None else local()
    jev = jev if jev is not None else FakeGateway("jev", False, .99, available=False)
    return RouterEngine(gateways={"laya": laya, "jev": jev}), laya


def test_local_success_and_usage():
    engine, gateway = router()
    response = engine.route(request(), RouterPolicy())
    assert response.agent.choice == "ops" and not response.agent.uncertain
    assert response.size.choice == "tiny" and not response.size.uncertain
    assert gateway.asked == [["agent", "size"]]
    assert len(response.usage) == 1 and response.usage[0].input_tokens == 12
    assert response.usage[0].model == "english-then-typed"


def test_policy_isolated_and_uncertainty_never_becomes_execution():
    before = settings.settings()
    engine, _ = router(local(.1))
    response = engine.route(request(), RouterPolicy(strategy="laya-only"))
    assert response.agent.uncertain
    assert settings.settings() is before


def test_large_roster_abstains_only_agent():
    engine, _ = router()
    req = request().model_copy(update={"candidates": [RouteCandidate(id=f"a{i}", label="A") for i in range(10)]})
    response = engine.route(req, RouterPolicy())
    assert response.agent.uncertain and response.agent.reason == "too_many_candidates"
    assert not response.size.uncertain


def test_subject_over_remote_limit_does_not_call_any_gateway():
    engine, gateway = router()
    response = engine.route(request().model_copy(update={"subject": "x" * 16001}), RouterPolicy())
    assert response.agent.reason == "input_too_long" and not gateway.asked


def test_no_backend_abstains_and_explicit_tier_skips_size():
    gateway = local()
    gateway.fail = DecisionError("Laya input is over its window")
    engine, _ = router(gateway)
    response = engine.route(request().model_copy(update={"subject": "x" * 4001}), RouterPolicy())
    assert response.agent.uncertain and response.agent.reason == "unavailable"
    gateway.fail = False
    response = engine.route(request(explicit_tier="heavy"), RouterPolicy())
    assert response.size.reason == "explicit_tier" and gateway.asked[-1] == ["agent"]


def test_cancelled_before_inference_records_no_work():
    engine, gateway = router()
    response = engine.route(request(), RouterPolicy(), cancelled=lambda: True)
    assert response.agent.reason == "cancelled" and not gateway.asked


def test_timeout_after_local_work_retains_usage_and_abstains():
    clock = [0.0]
    gateway = local()
    original = gateway.ask
    def slow(request, timeout=None):
        clock[0] = 11
        return original(request, timeout)
    gateway.ask = slow
    engine, _ = router(gateway)
    response = engine.route(request(), RouterPolicy(), clock=lambda: clock[0])
    assert response.agent.reason == "timeout" and response.usage[0].input_tokens == 12


def test_missing_agent_answer_does_not_discard_independent_size():
    gateway = local()
    gateway.ask = lambda request, timeout=None: GatewayResult({
        "size": {"type": "choice", "choice": "tiny", "answer_confidence": .99, "uncertain": False}}, 12, "fixture")
    engine, _ = router(gateway)
    response = engine.route(request(), RouterPolicy())
    assert response.agent.uncertain and not response.size.uncertain


def test_remote_long_input_retains_attempt_usage_and_timeout():
    gateway = local()
    gateway.fail = DecisionError("Laya input is over its window")
    jev = FakeGateway("jev", False, .99, pick="ops", tokens=10, model="jev-live")
    engine, _ = router(gateway, jev)
    response = engine.route(request().model_copy(update={"subject": "x" * 4001}), RouterPolicy())
    assert jev.asked == [["agent", "size"]]
    assert all(0 < timeout <= 3 for timeout in jev.timeouts)
    assert not response.usage[0].ok and response.usage[0].input_tokens is None
    assert response.usage[1].model == "jev-live" and not response.agent.uncertain


def test_both_falls_back_on_low_confidence_without_executing_uncertain_choice():
    jev = FakeGateway("jev", False, .99, pick="ops", tokens=10)
    engine, _ = router(local(.1), jev)
    response = engine.route(request(), RouterPolicy())
    assert response.agent.choice == "ops" and response.agent.answered_by == "jev"
    assert not response.agent.uncertain and len(response.usage) == 2
