"""Auto route: a confident classifier pick sends the question straight to a specialist."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.agents import agent_config, agent_routing, agent_spec
from src.agents.roles.orchestrator import auto_route, delegation
from src.agents.agent_spec import AgentSpec, LlmSpec, RosterEntry
from src.runtime import approvals
from src.providers import cancellation
from src.providers.decision import decision
from src.providers.base_provider import ChatCancelled, ChatResult

RESEARCHER = RosterEntry("researcher", "Researcher", "Web research: look up facts.", tool_allow=("tool_web_search", "tool_ticket_createTicket"))
SERVER = RosterEntry("server-ops", "Server Ops", "x" * 400, tool_allow=("tool_srv_*",))
PLANNER = RosterEntry("planner", "Planner", "Planning multi-step requests.")
ROSTER = [RESEARCHER, SERVER, PLANNER]
HISTORY = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello, how can I help?"}]


@pytest.fixture(autouse=True)
def fresh_settings():
    decision.reset_cache()
    yield
    decision.reset_cache()


def switch_on(monkeypatch, *, enabled=True, key=True, pick=("researcher", 90), error=None, min_confidence=60):
    """Settings with auto route on and a fake classifier; returns the (subject, criteria) pairs it was asked."""
    config = decision.ClassifierSettings(
        auto_route=decision.AutoRouteSettings(enabled=enabled, min_confidence=min_confidence)
    )
    monkeypatch.setattr(decision, "settings", lambda: config)
    monkeypatch.setattr(decision, "available", lambda *a, **k: key)
    asked = []

    def ask_choice(subject, criteria, question, feature, **kwargs):
        asked.append((subject, dict(criteria)))
        if error:
            raise error
        return decision.Choice(pick[0], pick[1], 25, "jev", "jev-latest")

    monkeypatch.setattr(decision, "ask_choice", ask_choice)
    return asked


def run_pick(question="who won the match last night?", history=(), roster=ROSTER):
    return asyncio.run(auto_route.pick(question, list(history), roster))


# --- choosing -------------------------------------------------------------------------------

def test_only_specialists_with_tools_of_their_own_are_offered(monkeypatch):
    asked = switch_on(monkeypatch)

    run_pick()

    criteria = asked[0][1]
    assert list(criteria) == ["researcher", "server-ops", "none"]
    assert criteria["researcher"] == "Web research: look up facts."
    assert len(criteria["server-ops"]) == 160


def test_nothing_is_asked_when_no_specialist_is_routable(monkeypatch):
    asked = switch_on(monkeypatch)
    assert run_pick(roster=[PLANNER]) is None and run_pick(roster=[]) is None and asked == []
    assert run_pick(question="  ") is None and asked == []


def test_a_confident_pick_names_the_specialist(monkeypatch):
    switch_on(monkeypatch, pick=("server-ops", 75))

    route = run_pick()

    assert (route.entry.id, route.confidence, route.prompt_tokens, route.backend) == ("server-ops", 75, 25, "jev")


@pytest.mark.parametrize("pick", [("none", 99), ("researcher", 59), ("planner", 99), ("ghost", 99)])
def test_none_a_low_confidence_or_an_unroutable_choice_means_no_route(monkeypatch, pick):
    switch_on(monkeypatch, pick=pick)
    # "planner" and "ghost" are not offered, so the fake picks something the real classifier could not.
    assert run_pick() is None


def test_the_threshold_is_the_configured_one(monkeypatch):
    switch_on(monkeypatch, pick=("researcher", 80), min_confidence=85)
    assert run_pick() is None
    switch_on(monkeypatch, pick=("researcher", 80), min_confidence=80)
    assert run_pick().entry.id == "researcher"


def test_a_failing_classifier_means_no_route(monkeypatch):
    switch_on(monkeypatch, error=decision.ClassifierError("down"))
    assert run_pick() is None


def test_the_classifier_sees_the_end_of_the_last_assistant_message_and_the_question(monkeypatch):
    asked = switch_on(monkeypatch)
    history = [{"role": "assistant", "content": "A" * 400 + "restart it?"}, {"role": "user", "content": "yes"}]

    run_pick("yes please", history)
    run_pick("what is the news?")

    first, second = asked[0][0], asked[1][0]
    assert "Previous assistant message: " + "A" * (300 - len("restart it?")) + "restart it?" in first
    assert first.endswith("User message: yes please")
    assert "Previous assistant message" not in second


# --- the settings ---------------------------------------------------------------------------

def use_section(monkeypatch, section):
    monkeypatch.setattr(decision, "read_section", lambda path, name, default=None: section)


def test_auto_route_is_off_by_default(monkeypatch):
    use_section(monkeypatch, {})
    assert decision.settings().auto_route == decision.AutoRouteSettings(False, 60)


def test_auto_route_settings_are_read(monkeypatch):
    use_section(monkeypatch, {"auto_route": {"enabled": True, "min_confidence": 70}})
    assert decision.settings().auto_route == decision.AutoRouteSettings(True, 70)


@pytest.mark.parametrize("auto", [[], {"nope": 1}, {"enabled": 1}, {"min_confidence": 101}, {"min_confidence": True}])
def test_a_bad_auto_route_section_is_refused(monkeypatch, auto):
    use_section(monkeypatch, {"auto_route": auto})
    with pytest.raises(ValueError, match="auto_route"):
        decision.settings()


# --- routing a turn -------------------------------------------------------------------------

def route_turn(monkeypatch, *, question="who won the match last night?", history=(), depth=0, answer="It was 2-1.", error=None,
               roster=ROSTER, **switch):
    """try_route with a fake roster and delegation; returns (result, events, dispatched arguments)."""
    switch_on(monkeypatch, **switch)
    monkeypatch.setattr(agent_routing, "roster_for", AsyncMock(return_value=roster))
    dispatched = []

    def dispatch(arguments, depth):
        dispatched.append((arguments, depth))
        if error:
            raise error
        return answer

    monkeypatch.setattr(delegation, "dispatch", dispatch)
    events = []

    async def on_event(event):
        events.append(event)

    result = asyncio.run(auto_route.try_route(question, list(history), on_event, "req-1", depth))
    return result, events, dispatched


def test_a_routed_turn_is_the_specialists_answer_with_the_usual_events(monkeypatch):
    result, events, dispatched = route_turn(monkeypatch)

    assert result.response == "It was 2-1."
    assert dispatched == [({"agent_id": "researcher", "question": "who won the match last night?"}, 0)]
    kinds = [e["type"] for e in events]
    assert kinds == ["step_start", "step_end", "token"]
    assert events[0]["tool"] == "delegate_to_agent" and events[0]["label"] == "Asking Researcher"
    assert events[1]["ok"] is True and events[1]["id"] == events[0]["id"] and events[2]["text"] == "It was 2-1."
    assert result.tools_used == ["delegate_to_agent"]
    assert result.tool_calls[0].arguments["agent_id"] == "researcher" and result.tool_calls[0].result == "It was 2-1."
    assert (result.provider_id, result.model, result.input_tokens, result.output_tokens) == ("jev", "jev-latest", 25, 0)
    assert result.total_tokens == 25 and result.model_note == "routed straight to Researcher (researcher, 90%)"


def test_a_follow_up_hands_the_specialist_the_previous_message_as_context(monkeypatch):
    _, _, dispatched = route_turn(monkeypatch, question="and tomorrow?", history=HISTORY)

    question = dispatched[0][0]["question"]
    assert question == "Context, the assistant's previous message: Hello, how can I help?\n\nUser message: and tomorrow?"


def test_a_failing_specialist_is_reported_not_retried(monkeypatch):
    result, events, dispatched = route_turn(monkeypatch, error=RuntimeError("agent is down"))

    assert result.response == "I sent this to Researcher, but it could not finish: agent is down"
    assert events[1]["ok"] is False and len(dispatched) == 1


@pytest.mark.parametrize("change", [{"enabled": False}, {"key": False}, {"pick": ("none", 99)}, {"pick": ("researcher", 10)}])
def test_no_route_means_none_and_no_delegation(monkeypatch, change):
    result, events, dispatched = route_turn(monkeypatch, **change)
    assert result is None and events == [] and dispatched == []


def test_only_a_top_level_turn_is_routed(monkeypatch):
    result, _, dispatched = route_turn(monkeypatch, depth=1)
    assert result is None and dispatched == []


def test_a_turn_that_needs_approval_to_delegate_is_left_to_the_orchestrator(monkeypatch):
    token = approvals.bind(approvals.ApprovalPolicy("ask"))
    try:
        result, _, dispatched = route_turn(monkeypatch)
    finally:
        approvals.reset(token)

    assert result is None and dispatched == []


def test_a_cancelled_turn_stops_before_the_specialist_is_asked(monkeypatch):
    monkeypatch.setattr(cancellation, "is_cancelled", lambda request_id: True)
    switch_on(monkeypatch)
    monkeypatch.setattr(agent_routing, "roster_for", AsyncMock(return_value=ROSTER))
    monkeypatch.setattr(delegation, "dispatch", lambda *a: pytest.fail("must not be asked"))

    with pytest.raises(ChatCancelled):
        asyncio.run(auto_route.try_route("question", [], None, "req-1", 0))


# --- the turn in agent_config ---------------------------------------------------------------

def run_chat(monkeypatch, routed):
    spec = AgentSpec(id="calc", label="Calc", port=9103, llm=LlmSpec(provider="anthropic"))
    monkeypatch.setattr(agent_spec, "_current", spec)
    provider = AsyncMock(return_value=ChatResult(response="from the model"))
    monkeypatch.setattr(agent_config._PROVIDER_MODULE, "run_chat", provider)
    monkeypatch.setattr(agent_config.router_routing, "route_turn", AsyncMock(return_value=(routed, None, "")))
    return asyncio.run(agent_config.run_chat("q", [], [])), provider


def test_a_routed_turn_never_runs_the_agents_own_model(monkeypatch):
    routed = ChatResult(response="from the specialist", model_note="routed straight to Researcher (researcher, 90%)")

    result, provider = run_chat(monkeypatch, routed)

    assert result is routed and result.response == "from the specialist" and not provider.called
    assert result.delegated_usage == []


def test_no_route_runs_the_agent_as_usual(monkeypatch):
    result, provider = run_chat(monkeypatch, None)

    assert result.response == "from the model" and provider.called
