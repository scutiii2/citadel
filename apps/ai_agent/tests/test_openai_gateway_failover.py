"""OpenAI rounds retain completed tool outputs while discarding gateway-bound reasoning."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import openai
import pytest

from src.agents import agent_spec
from src.llm import openai_provider as provider, cooldown, gateway_failover
from src.llm.base_provider import ChatCancelled
from tests.test_openai_provider import _fake_stream
from tests.test_gateway_failover import sdk_error


def response(output=None):
    return NS(output=output or [], output_text="answer", usage=NS(input_tokens=5, output_tokens=2, total_tokens=7))


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    cooldown.reset()
    monkeypatch.setenv("AI_AGENT_GATEWAY", "gpt")
    spec = agent_spec.current()
    monkeypatch.setattr(agent_spec, "_current", replace(spec, llm=replace(spec.llm, provider="openai",
                        fallback_gateways=(agent_spec.GatewayChoice("backup", "mapped"),))))
    monkeypatch.setattr(provider, "has_api_key", lambda gateway=None: True)
    monkeypatch.setattr(provider, "list_tools", lambda *args: [])
    monkeypatch.setattr(provider.agent_routing, "roster_for", AsyncMock(return_value=[]))
    monkeypatch.setattr(gateway_failover, "read_section", lambda *args, **kwargs: {})
    yield
    cooldown.reset()


def clients(monkeypatch, primary_steps, backup_steps):
    primary = NS(responses=NS(stream=Mock(side_effect=primary_steps)))
    backup = NS(responses=NS(stream=Mock(side_effect=backup_steps)))
    monkeypatch.setattr(provider, "_get_client", lambda gateway=None: backup if gateway == "backup" else primary)
    return primary, backup


@pytest.mark.parametrize("status,reason,seconds", [(429, "rate_limit", 60), (402, "quota", 3600),
                                                  (401, "auth", 3600), (500, "unavailable", 30)])
def test_stream_switches_and_reports_gateway(monkeypatch, status, reason, seconds):
    clients(monkeypatch, [sdk_error(openai, status)], [_fake_stream(["answer"], response())])
    events = []
    async def emit(event):
        events.append(event)
    result = asyncio.run(provider.run_chat("hello", [], on_event=emit))
    switch = {"from": "gpt", "to": "backup", "reason": reason}
    assert result.response == "answer"
    assert (result.gateway, result.model) == ("backup", "mapped")
    assert result.gateway_switches == [switch]
    assert {"type": "gateway_switch", **switch} in events
    assert seconds - 2 < cooldown.seconds_remaining("openai:gpt") <= seconds


def test_reasoning_stripped_and_completed_tool_runs_once(monkeypatch):
    tool = NS(type="function_call", name="lookup", arguments="{}", call_id="t1")
    tool.model_dump = lambda **kwargs: {"type": "function_call", "name": "lookup", "arguments": "{}",
                                       "call_id": "t1", "parsed_arguments": {}}
    reasoning = NS(type="reasoning", model_dump=lambda **kwargs: {"type": "reasoning", "id": "signed", "summary": []})
    _, backup = clients(monkeypatch, [_fake_stream([], response([reasoning, tool])), sdk_error(openai, 500)],
                        [_fake_stream(["done"], response())])
    dispatch = Mock(return_value="saved result")
    monkeypatch.setattr(provider, "_dispatch", dispatch)
    result = asyncio.run(provider.run_chat("hello", []))
    sent = backup.responses.stream.call_args.kwargs["input"]
    assert not any(item.get("type") == "reasoning" for item in sent)
    assert next(item for item in sent if item.get("type") == "function_call_output")["output"] == "saved result"
    call = next(item for item in sent if item.get("type") == "function_call")
    assert "parsed_arguments" not in call
    assert dispatch.call_count == 1
    assert result.tools_used == ["lookup"]


def test_failed_partial_stream_resets_tokens(monkeypatch):
    cm = _fake_stream(["discard"], response())
    cm.__aenter__.return_value.get_final_response.side_effect = sdk_error(openai, 500)
    clients(monkeypatch, [cm], [_fake_stream(["answer"], response())])
    events = []
    async def emit(event):
        events.append(event)
    result = asyncio.run(provider.run_chat("hello", [], on_event=emit))
    assert result.response == "answer"
    reset = next(i for i, event in enumerate(events) if event["type"] == "token_reset")
    assert reset < next(i for i, event in enumerate(events) if event.get("text") == "answer")


@pytest.mark.parametrize("error", [sdk_error(openai, 400), ChatCancelled(), ValueError("credit")])
def test_non_gateway_error_is_unchanged(monkeypatch, error):
    _, backup = clients(monkeypatch, [error], [])
    with pytest.raises(type(error)) as raised:
        asyncio.run(provider.run_chat("hello", []))
    assert raised.value is error
    assert backup.responses.stream.call_count == 0
    assert not cooldown.is_in_cooldown("openai:gpt")


def test_all_candidates_fail_with_last_error(monkeypatch):
    last = sdk_error(openai, 402)
    clients(monkeypatch, [sdk_error(openai, 500)], [last])
    with pytest.raises(type(last)) as raised:
        asyncio.run(provider.run_chat("hello", []))
    assert raised.value is last
    assert cooldown.is_in_cooldown("openai:backup")


def test_interpret_failover(monkeypatch):
    primary = NS(responses=NS(create=Mock(side_effect=sdk_error(openai, 401))))
    backup = NS(responses=NS(create=Mock(return_value=response())))
    monkeypatch.setattr(provider, "_get_sync_client", lambda gateway=None: backup if gateway == "backup" else primary)
    result = provider.run_interpret("hello")
    assert (result.response, result.gateway, result.model) == ("answer", "backup", "mapped")


def test_clients_cached_per_gateway(monkeypatch):
    cls = provider._OpenAI
    monkeypatch.setattr(cls, "_clients", {}, raising=False)
    monkeypatch.setattr(cls, "_sync_clients", {}, raising=False)
    monkeypatch.setattr(provider.llm_config, "gateway", lambda *args: {"api_key": "fake", "base_url": "https://fake.invalid"})
    monkeypatch.setattr(provider, "AsyncOpenAI", Mock(side_effect=lambda **kwargs: object()))
    monkeypatch.setattr(provider, "OpenAI", Mock(side_effect=lambda **kwargs: object()))
    for get_client in (cls.get_client, cls.get_sync_client):
        assert get_client() is get_client("gpt")
        assert get_client("backup") is get_client("backup")
        assert get_client("backup") is not get_client()
