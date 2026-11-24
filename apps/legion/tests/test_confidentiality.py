"""Trusted gateways and the confidential-data check."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from src import gateway
from src.agents import agent_registry, agent_store
from src.agents.agent_store import AgentStoreError
from src.agents.roles.orchestrator import delegation
from src.gateway import trust
from src.gateway.conversation.store import GatewayStore
from src.providers import cooldown, gateway_client
from src.providers.gateway_failover import GatewayRoute, NoTrustedGateway
from src.runtime import confidentiality
from src.runtime.confidentiality import is_confidential as real_is_confidential  # conftest patches the module's name
from tests.roster import write_roster


@pytest.fixture(autouse=True)
def _no_cooldowns():
    cooldown.reset()
    yield
    cooldown.reset()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "_database", lambda: tmp_path / "settings.db")
    for name in ("_chat", "_chat_store", "_decision", "_decision_store"):
        monkeypatch.setattr(gateway, name, None)
    return gateway.chat_store()


def test_defaults_trust_the_named_hosted_models_and_local_services():
    assert all(trust.conversation(name) for name in ("claude", "gpt", "gemini", "ollama"))
    assert trust.conversation("minicpm", {"provider": "scuti"})
    assert not any(trust.conversation(name) for name in ("omniroute", "openrouter", "freellmapi", "bedrock"))
    assert trust.decision("jev") and trust.decision("laya") and trust.decision("x", {"kind": "ollama"})
    assert not trust.decision("freellmapi", {"kind": "freellmapi"})


def test_a_saved_flag_beats_the_default_and_is_listed(store):
    entry = {"provider": "openai", "base_url": "http://host.docker.internal:29652/v1", "model": "m"}
    assert store.put("freellmapi", entry)["trusted"] is False
    assert store.put("freellmapi", {**entry, "trusted": True})["trusted"] is True
    assert store.put("claude", {"provider": "anthropic", "api_key": "k", "model": "m", "trusted": False})["trusted"] is False
    with pytest.raises(ValueError, match="trusted"):
        store.put("x", {**entry, "trusted": "yes"})
    assert gateway_client.is_trusted("freellmapi") is True and gateway_client.is_trusted("claude") is False


def _route(has=lambda name: True):
    return GatewayRoute.for_turn("anthropic", "omniroute", ["openrouter", "claude"], has)


def test_a_confidential_turn_moves_to_the_trusted_gateway_and_stays_there():
    route = _route()
    assert route.current == "omniroute"
    switch = route.require_trusted(lambda name: name == "claude")
    assert (switch.from_gateway, switch.to_gateway, switch.reason) == ("omniroute", "claude", "confidential")
    assert route.current == "claude" and route.require_trusted(lambda name: name == "claude") is None


def test_no_trusted_gateway_available_refuses_instead_of_using_an_untrusted_one():
    with pytest.raises(NoTrustedGateway):
        _route(has=lambda name: name != "claude").require_trusted(lambda name: name == "claude")


def test_failover_after_a_confidential_mark_never_picks_an_untrusted_gateway():
    from src.providers.gateway_client import GatewayCallError

    route = GatewayRoute.for_turn("anthropic", "claude", ["openrouter"], lambda name: True)
    route.require_trusted(lambda name: name == "claude")
    assert route.advance(GatewayCallError(503, "gateway_unavailable", "down", kind="unavailable")) is None


def _checker(monkeypatch, answer=None, error=None):
    monkeypatch.setattr(agent_registry, "reload", lambda: None)
    monkeypatch.setattr(agent_registry, "get_agent", lambda agent_id: {"url": "http://checker"})
    reply = AsyncMock(side_effect=error) if error else AsyncMock(return_value={"response": json.dumps({"answers": {"verdict": answer}})})
    monkeypatch.setattr(delegation, "_call_tool", reply)
    return reply


def test_the_check_asks_jev_through_the_checker_agent_and_reads_a_public_verdict(monkeypatch):
    reply = _checker(monkeypatch, {"choice": "public", "answer_confidence": 0.95, "uncertain": False})
    assert asyncio.run(real_is_confidential("what is the capital of France?")) is False
    request = json.loads(reply.call_args.args[2]["question"])
    assert set(request["questions"]["verdict"]["criteria"]) == {"confidential", "public"}


@pytest.mark.parametrize("answer", [{"choice": "confidential", "uncertain": False}, {"choice": "public", "uncertain": True}])
def test_a_confidential_or_unsure_verdict_counts_as_confidential(monkeypatch, answer):
    _checker(monkeypatch, answer)
    assert asyncio.run(real_is_confidential("my password is hunter2")) is True


def test_the_check_fails_closed(monkeypatch):
    _checker(monkeypatch, error=RuntimeError("down"))
    assert asyncio.run(real_is_confidential("hello")) is True
    monkeypatch.setattr(agent_registry, "get_agent", lambda agent_id: None)  # checker missing or disabled
    assert asyncio.run(real_is_confidential("hello")) is True
    assert asyncio.run(real_is_confidential("   ")) is False


def test_tool_results_are_checked_only_while_an_untrusted_gateway_could_get_them(monkeypatch):
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(confidentiality, "is_confidential", check)
    trusted_only = lambda name: name in ("claude", "gpt")
    monkeypatch.setattr(gateway_client, "is_trusted", trusted_only)
    all_trusted = GatewayRoute.for_turn("anthropic", "claude", ["gpt"], lambda name: True)
    assert asyncio.run(confidentiality.protect_round(all_trusted, ["secret"])) is None
    check.assert_not_awaited()
    route = _route()
    token = confidentiality.bind(False)
    try:
        switch = asyncio.run(confidentiality.protect_round(route, ["ssn 123-45-6789"]))
        assert switch.to_gateway == "claude" and confidentiality.current() is False  # bound to this call's context copy
    finally:
        confidentiality.reset(token)
    assert route.trusted_only is not None
    check.assert_awaited_once()


def test_a_public_tool_result_leaves_the_route_alone(monkeypatch):
    monkeypatch.setattr(confidentiality, "is_confidential", AsyncMock(return_value=False))
    monkeypatch.setattr(gateway_client, "is_trusted", lambda name: name == "claude")
    route = _route()
    assert asyncio.run(confidentiality.protect_round(route, ["weather: sunny"])) is None and route.trusted_only is None


def _agent(port, *gateways, enabled=True):
    names = list(gateways)
    return {"role": "specialist", "label": "X", "port": port, "enabled": enabled,
            "llm": {"provider": "anthropic", "gateway": names[0], "fallback_gateways": names[1:]}}


def test_an_agent_needs_a_trusted_gateway_to_be_saved(tmp_path, store):
    write_roster(tmp_path)
    with pytest.raises(AgentStoreError) as error:
        agent_store.create_agent("calc", _agent(9103, "omniroute", "openrouter"), tmp_path)
    assert error.value.status == 409 and "trusted" in str(error.value)
    agent_store.create_agent("calc", _agent(9103, "omniroute", "claude"), tmp_path)
    agent_store.create_agent("off", _agent(9104, "omniroute", enabled=False), tmp_path)  # a disabled agent is not checked


def test_untrusting_or_deleting_a_gateway_names_the_agents_that_would_have_none(tmp_path, store):
    write_roster(tmp_path)
    agent_store.create_agent("calc", _agent(9103, "omniroute", "claude"), tmp_path)
    assert "calc" in agent_store.agents_losing_trust("claude", tmp_path)
    assert "calc" not in agent_store.agents_losing_trust("omniroute", tmp_path)


def _agent_spec(monkeypatch, *gateways):
    from dataclasses import replace

    from src.agents import agent_spec
    from tests.roster import write_roster  # noqa: F401

    base = agent_spec.current()
    llm = replace(base.llm, provider="anthropic", gateway=gateways[0], fallback_gateways=tuple(
        agent_spec.GatewayChoice(name, None) for name in gateways[1:]))
    monkeypatch.setattr(agent_spec, "_current", replace(base, llm=llm))


def test_the_turn_is_checked_only_when_the_agent_has_an_untrusted_gateway(monkeypatch):
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(confidentiality, "is_confidential", check)
    token = confidentiality.bind(False)
    try:
        _agent_spec(monkeypatch, "claude", "gpt")
        asyncio.run(confidentiality.protect_turn("my card number is 4111"))
        assert check.await_count == 0 and not confidentiality.current()
        _agent_spec(monkeypatch, "omniroute", "claude")

        async def run():
            await confidentiality.protect_turn("my card number is 4111")
            return confidentiality.current()

        assert asyncio.run(run()) is True and check.await_count == 1
    finally:
        confidentiality.reset(token)
