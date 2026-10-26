"""agent_routing.py tests: the roster is built per turn from the registry
(self and other orchestrators excluded)."""

from __future__ import annotations

import asyncio

import pytest

from src.agents import agent_registry, agent_routing, agent_spec
from src.agents.agent_spec import AgentSpec, LlmSpec
from src.runtime import tool_filter

AGENTS = [
    {"id": "orchestrator", "label": "Ember", "url": "u", "orchestrator": True, "focus": "coordination"},
    {"id": "calc", "label": "Calculator", "url": "u", "focus": "arithmetic and units"},
    {"id": "explainer", "label": "Explainer", "url": "u", "focus": "plain explanations"},
    {"id": "poet", "label": "Poet", "url": "u", "focus": "poems"},
    {"id": "blank", "label": "Blank", "url": "u"},
]


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(agent_registry, "reload", lambda: None)
    monkeypatch.setattr(agent_registry, "_AGENTS", AGENTS)
    monkeypatch.setattr(agent_registry, "_AGENTS_BY_ID", {a["id"]: a for a in AGENTS})


def _use(monkeypatch, orchestrator=True):
    spec = AgentSpec(id="orchestrator", label="Ember", port=9100, llm=LlmSpec(provider="anthropic"),
                     orchestrator=orchestrator)
    monkeypatch.setattr(agent_spec, "_current", spec)


def test_specialists_exclude_self_and_orchestrators(registry, monkeypatch):
    _use(monkeypatch)
    assert [r.id for r in agent_routing.specialists()] == ["calc", "explainer", "poet", "blank"]


def test_specialists_skip_an_agent_that_is_not_delegable(registry, monkeypatch):
    _use(monkeypatch)
    hidden = [*AGENTS, {"id": "titles", "label": "Titles", "url": "u", "focus": "titles", "delegable": False}]
    monkeypatch.setattr(agent_registry, "_AGENTS", hidden)
    assert "titles" not in [r.id for r in agent_routing.specialists()]


def test_non_orchestrator_has_no_roster(registry, monkeypatch):
    _use(monkeypatch, orchestrator=False)
    assert asyncio.run(agent_routing.roster_for()) == []


def test_orchestrator_roster_is_every_specialist(registry, monkeypatch):
    _use(monkeypatch)
    assert [r.id for r in asyncio.run(agent_routing.roster_for())] == ["calc", "explainer", "poet", "blank"]


def test_specialists_carry_their_published_tiers(monkeypatch):
    agents = [
        {"id": "orchestrator", "label": "Ember", "url": "u", "orchestrator": True},
        {"id": "calc", "label": "Calculator", "url": "u", "focus": "math", "tiers": [
            {"tier": "light", "id": "haiku", "use_for": "quick"},
            {"tier": "bogus", "id": "x", "use_for": "y"},
        ]},
        {"id": "poet", "label": "Poet", "url": "u", "focus": "poems"},
    ]
    monkeypatch.setattr(agent_registry, "reload", lambda: None)
    monkeypatch.setattr(agent_registry, "_AGENTS", agents)
    _use(monkeypatch)

    calc, poet = agent_routing.specialists()

    assert calc.tiers == (agent_spec.TierInfo("light", "haiku", "quick"),)
    assert poet.tiers == ()


def test_is_usable_needs_one_own_tool_besides_the_support_tool():
    from src.agents.agent_spec import RosterEntry

    web = RosterEntry("researcher", "R", "", tool_allow=("tool_web_search", "tool_ticket_createTicket"))
    assert not agent_routing.is_usable(web, ["tool_mem_search", "tool_ticket_createTicket"])
    assert agent_routing.is_usable(web, ["tool_web_search"])
    assert agent_routing.is_usable(RosterEntry("planner", "P", ""), [])
    assert agent_routing.is_usable(RosterEntry("t", "T", "", tool_allow=("tool_ticket_createTicket",)), [])
    pdf = RosterEntry("pdf", "P", "", tool_allow=("pdf_merger__*",))
    assert agent_routing.is_usable(pdf, ["pdf_merger__merge"])


def test_roster_leaves_out_specialists_whose_tools_are_switched_off(registry, monkeypatch):
    monkeypatch.setattr(agent_routing, "_live_tool_names", lambda: ["tool_mem_search"])
    monkeypatch.setattr(agent_routing, "specialists", lambda: [
        agent_spec.RosterEntry("calc", "Calc", "", tool_allow=("tool_calc_*",)),
        agent_spec.RosterEntry("poet", "Poet", ""),
    ])
    monkeypatch.setattr(agent_spec, "current", lambda: agent_spec.AgentSpec(
        id="ember", label="E", port=1, llm=agent_spec.LlmSpec(provider="anthropic"), orchestrator=True))
    assert [r.id for r in asyncio.run(agent_routing.roster_for())] == ["poet"]
    monkeypatch.setattr(agent_routing, "_live_tool_names", lambda: None)
    assert [r.id for r in asyncio.run(agent_routing.roster_for())] == ["calc", "poet"]


def _roster_ids(monkeypatch, live, blocked=()):
    """The roster ids for a turn where mcp_server offers `live` and the user switched off `blocked`."""
    monkeypatch.setattr(agent_routing, "_live_tool_names", lambda: live)
    monkeypatch.setattr(agent_routing, "specialists", lambda: [
        agent_spec.RosterEntry("researcher", "Researcher", "", tool_allow=("tool_web_search", "tool_ticket_createTicket")),
        agent_spec.RosterEntry("notes", "Notes", "", tool_allow=("tool_notes_*",)),
        agent_spec.RosterEntry("poet", "Poet", ""),
    ])
    monkeypatch.setattr(agent_spec, "current", lambda: agent_spec.AgentSpec(
        id="ember", label="E", port=1, llm=agent_spec.LlmSpec(provider="anthropic"), orchestrator=True))
    token = tool_filter.bind(blocked)
    try:
        return [r.id for r in asyncio.run(agent_routing.roster_for())]
    finally:
        tool_filter.reset(token)


LIVE = ["tool_web_search", "tool_notes_listNotes", "tool_mem_search"]


def test_roster_is_unchanged_when_the_user_switched_nothing_off(monkeypatch):
    assert _roster_ids(monkeypatch, LIVE) == ["researcher", "notes", "poet"]


def test_a_specialist_whose_tool_the_user_switched_off_is_not_offered(monkeypatch):
    assert _roster_ids(monkeypatch, LIVE, blocked=["tool_web_search"]) == ["notes", "poet"]


def test_a_specialist_stays_while_one_of_its_tools_is_still_on(monkeypatch):
    live = [*LIVE, "tool_notes_readNote"]
    assert _roster_ids(monkeypatch, live, blocked=["tool_notes_listNotes"]) == ["researcher", "notes", "poet"]
    assert _roster_ids(monkeypatch, live, blocked=["tool_notes_listNotes", "tool_notes_readNote"]) == ["researcher", "poet"]


def test_blocking_every_tool_leaves_only_specialists_that_need_none(monkeypatch):
    assert _roster_ids(monkeypatch, LIVE, blocked=["*"]) == ["poet"]


def test_an_empty_catalog_offers_everyone_even_when_the_user_blocked_everything(monkeypatch):
    assert _roster_ids(monkeypatch, [], blocked=["*"]) == ["researcher", "notes", "poet"]


def test_roster_leaves_out_a_specialist_the_user_switched_off(monkeypatch):
    assert _roster_ids(monkeypatch, LIVE, blocked=("agent:poet",)) == ["researcher", "notes"]


def test_roster_keeps_tool_less_specialists_when_only_tools_are_blocked(monkeypatch):
    assert _roster_ids(monkeypatch, LIVE, blocked=("*",)) == ["poet"]
    assert _roster_ids(monkeypatch, None, blocked=("agent:poet",)) == ["researcher", "notes"]
