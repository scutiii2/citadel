from src.agents.roles.router.router_contract import RouteRequest, RouteCandidate, RouterPolicy
from src.agents.roles.router.router_engine import RouterEngine, _batches
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


class Weighted:
    """Remote gateway whose answers come from fixed per-option probabilities (unlisted: .01, `none`: .5)."""
    id, local = "jev", False

    def __init__(self, weights):
        self.weights, self.requests = weights, []

    def available(self):
        return True

    def ask(self, request, timeout=None):
        self.requests.append(request)
        answers = {}
        for qid, spec in request.questions.items():
            odds = {o: self.weights.get(o, .5 if o == "none" else .01) for o in spec["criteria"]}
            pick = max(odds, key=odds.get)
            answers[qid] = {"type": "choice", "choice": pick, "probabilities": odds,
                            "answer_confidence": odds[pick], "uncertain": odds[pick] < .25}
        return GatewayResult(answers, 5, "jev-fixture")

    def agent_questions(self):
        return [set(r.questions["agent"]["criteria"]) for r in self.requests if "agent" in r.questions]


def roster(count):
    return request().model_copy(update={"candidates": [RouteCandidate(id=f"a{i}", label="A") for i in range(count)]})


def route_weighted(weights, count):
    jev = Weighted(weights)
    engine = RouterEngine(gateways={"laya": FakeGateway("laya", True, .9, available=False), "jev": jev})
    return engine.route(roster(count), RouterPolicy(strategy="jev-only")), jev


def test_batches_are_equal_or_differ_by_one():
    assert [len(b) for b in _batches(list(range(9)))] == [9]
    assert [len(b) for b in _batches(list(range(10)))] == [5, 5]
    assert [len(b) for b in _batches(list(range(11)))] == [6, 5]
    assert [len(b) for b in _batches(list(range(19)))] == [7, 6, 6]


def test_long_roster_prunes_batches_then_picks_among_survivors_and_reports_near_tie():
    response, jev = route_weighted({"a3": .8, "a8": .7, "a7": .2}, 11)
    rounds = jev.agent_questions()
    assert sorted(len(q) for q in rounds[:2]) == [6, 7] and len(rounds) == 3
    assert rounds[-1] == {"a3", "a7", "a8", "none"}
    assert response.agent.choice == "a3" and not response.agent.uncertain
    assert response.alternatives == ["a8"]
    assert response.size.answered_by == "jev"


def test_clear_winner_has_no_alternatives():
    response, _ = route_weighted({"a3": .9, "a8": .1}, 11)
    assert response.agent.choice == "a3" and response.alternatives == []


def test_batches_that_all_pick_none_leave_the_agent_to_the_general_assistant():
    response, jev = route_weighted({"none": .9}, 11)
    assert response.agent.reason == "no_specialist" and response.agent.uncertain and response.agent.choice is None
    assert len(jev.agent_questions()) == 2 and response.size.answered_by == "jev"


def test_round_that_prunes_nothing_keeps_only_each_batch_pick():
    response, jev = route_weighted({**{f"a{i}": .3 for i in range(10)}, "none": .1}, 10)
    assert jev.agent_questions()[-1] == {"a0", "a5", "none"}
    assert response.agent.choice == "a0" and response.alternatives == ["a5"]


def test_rounds_repeat_while_more_than_nine_remain():
    flat = {**{f"a{i}": .3 for i in range(14)}, "none": .1}
    response, jev = route_weighted(flat, 28)
    rounds = jev.agent_questions()
    assert [len(q) for q in rounds] == [8, 8, 8, 8, 8, 8, 3]
    assert response.agent.choice == "a0" and response.alternatives == ["a7"]


def test_short_roster_is_one_round_and_reports_a_near_tie():
    jev = Weighted({"a1": .9, "a2": .8})
    engine = RouterEngine(gateways={"laya": FakeGateway("laya", True, .9, available=False), "jev": jev})
    response = engine.route(roster(3), RouterPolicy(strategy="jev-only"))
    assert len(jev.requests) == 1 and response.agent.choice == "a1" and response.alternatives == ["a2"]


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
