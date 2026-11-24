"""An agent whose gateways speak both chat protocols moves a turn to the next protocol when the first has none left."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents import agent_config, agent_spec, protocol_chain
from src.providers import cooldown, gateway_client, gateway_protocols
from src.providers.gateway_client import GatewayCallError
from src.runtime import turn_effects

PROTOCOLS = {"gpt": "openai"}


@pytest.fixture(autouse=True)
def mixed_agent(monkeypatch):
    base = agent_spec.current()
    llm = replace(base.llm, provider="anthropic", gateway="omniroute", fallback_gateways=(
        agent_spec.GatewayChoice("claude", None), agent_spec.GatewayChoice("gpt", "gpt-x")))
    monkeypatch.setattr(agent_spec, "_current", replace(base, llm=llm))
    monkeypatch.setattr(gateway_protocols, "protocol_of", lambda name, own: PROTOCOLS.get(name, own))
    monkeypatch.setattr(gateway_client, "is_saved", lambda name: True)
    monkeypatch.setattr(gateway_client, "is_trusted", lambda name: True)
    monkeypatch.setenv("AI_AGENT_GATEWAY", "omniroute")  # what the supervisor pins from llm.gateway
    monkeypatch.setattr(agent_config, "PROVIDER_ID", "anthropic")
    monkeypatch.setattr(agent_config.router_routing, "route_turn", AsyncMock(return_value=(None, None, "")))


def result():
    return SimpleNamespace(response="ok", delegated_usage=[], model_tier=None, model_note=None, reasoning_effort=None,
                           effort_note=None, private_extension_errors=[], gateway_switches=[])


def run(first, second, events=None):
    async def on_event(event):
        events.append(event)

    calls = []

    async def second_run(question, history, model, *args, **kw):
        calls.append(("openai", model))
        return await second(question)

    async def first_run(question, history, model, *args, **kw):
        calls.append(("anthropic", model))
        return await first(question)

    agent_config._PROVIDER_MODULE = SimpleNamespace(run_chat=first_run, DEFAULT_MODEL="m")
    protocol_chain.module_for = lambda protocol: SimpleNamespace(run_chat=second_run)
    return asyncio.run(agent_config.run_chat("q", [], on_event=on_event if events is not None else None)), calls


@pytest.fixture(autouse=True)
def restore(monkeypatch):
    monkeypatch.setattr(agent_config, "_PROVIDER_MODULE", agent_config._PROVIDER_MODULE)
    monkeypatch.setattr(protocol_chain, "module_for", protocol_chain.module_for)


def quota(_question):
    raise GatewayCallError(429, "quota", "no quota", kind="quota")


async def fine(_question):
    return result()


def test_gateways_are_grouped_by_protocol_in_order():
    assert gateway_protocols.order("anthropic") == ("omniroute", "claude")
    assert gateway_protocols.order("openai") == ("gpt",)
    assert gateway_protocols.protocols() == ("anthropic", "openai")


def test_a_turn_moves_to_the_next_protocol_when_the_first_is_used_up():
    events = []

    async def failing(question):
        quota(question)

    answer, calls = run(failing, fine, events)
    assert calls == [("anthropic", None), ("openai", "gpt-x")]  # the openai gateway's own pinned model, not the anthropic one
    assert [event["type"] for event in events if event["type"] in ("token_reset", "gateway_switch")] == ["token_reset", "gateway_switch"]
    assert answer.gateway_switches == [{"from": "omniroute", "to": "gpt", "reason": "protocol"}]


def test_a_turn_that_changed_something_is_not_rerun():
    async def failing(question):
        turn_effects.mark()
        quota(question)

    with pytest.raises(GatewayCallError):
        run(failing, fine)


def test_an_error_that_is_not_a_gateway_failure_is_not_a_reason_to_move():
    async def failing(_question):
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        run(failing, fine)


def test_the_turn_starts_on_a_protocol_that_has_a_usable_gateway(monkeypatch):
    down = {cooldown.gateway_key("anthropic", name) for name in ("omniroute", "claude")}
    monkeypatch.setattr(cooldown, "is_in_cooldown", lambda key: key in down)
    answer, calls = run(fine, fine)
    assert [name for name, _ in calls] == ["openai"]
