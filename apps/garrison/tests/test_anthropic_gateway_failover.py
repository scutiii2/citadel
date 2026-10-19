"""Only a failed model round retries; completed tool work survives a gateway switch."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import anthropic
import pytest

from src.agents import agent_spec
from src.llm import anthropic_provider as provider, cooldown, gateway_failover, token_limits
from src.llm.base_provider import ChatCancelled
from tests.test_anthropic_provider import _stream_cm, _usage
from tests.test_gateway_failover import sdk_error


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    cooldown.reset()
    monkeypatch.setenv("AI_AGENT_GATEWAY", "claude")
    spec = agent_spec.current()
    monkeypatch.setattr(agent_spec, "_current", replace(spec, llm=replace(spec.llm,
                        fallback_gateways=(agent_spec.GatewayChoice("backup", "mapped"),))))
    monkeypatch.setattr(provider, "has_api_key", lambda gateway=None: True)
    monkeypatch.setattr(provider, "list_tools", lambda *args: [])
    monkeypatch.setattr(provider.agent_routing, "roster_for", AsyncMock(return_value=[]))
    monkeypatch.setattr(gateway_failover, "read_section", lambda *args, **kwargs: {})
    yield
    cooldown.reset()


def clients(monkeypatch, primary_steps, backup_steps):
    primary = NS(messages=NS(stream=Mock(side_effect=primary_steps)))
    backup = NS(messages=NS(stream=Mock(side_effect=backup_steps)))
    monkeypatch.setattr(provider, "_get_client", lambda gateway=None: backup if gateway == "backup" else primary)
    return primary, backup


@pytest.mark.parametrize("status,reason,seconds", [(429, "rate_limit", 60), (402, "quota", 3600),
                                                  (401, "auth", 3600), (500, "unavailable", 30)])
def test_stream_switches_and_reports_gateway(monkeypatch, status, reason, seconds):
    clients(monkeypatch, [sdk_error(anthropic, status)], [_stream_cm(["answer"])])
    events = []
    async def emit(event):
        events.append(event)
    result = asyncio.run(provider.run_chat("hello", [], on_event=emit))
    switch = {"from": "claude", "to": "backup", "reason": reason}
    assert result.response == "answer"
    assert result.gateway == "backup"
    assert result.model == "mapped"
    assert result.gateway_switches == [switch]
    assert {"type": "gateway_switch", **switch} in events
    assert seconds - 2 < cooldown.seconds_remaining("anthropic:claude") <= seconds


def test_switch_strips_signed_thinking_preserves_tools_and_cache_policy(monkeypatch):
    thought = NS(type="thinking", thinking="private", signature="gateway-specific")
    redacted = NS(type="redacted_thinking", data="signed")
    tool = NS(type="tool_use", name="lookup", input={}, id="t1")
    first = NS(content=[thought, redacted, tool], stop_reason="tool_use", usage=_usage())
    primary, backup = clients(monkeypatch, [_stream_cm([], first), sdk_error(anthropic, 500)], [_stream_cm(["done"])])
    monkeypatch.setattr(provider, "_prompt_cache_enabled", lambda gateway=None: gateway != "backup")
    dispatch = Mock(return_value="saved result")
    monkeypatch.setattr(provider, "_dispatch", dispatch)
    result = asyncio.run(provider.run_chat("hello", []))
    sent = backup.messages.stream.call_args.kwargs
    assistant = next(message for message in sent["messages"] if message["role"] == "assistant")
    assert assistant["content"] == [tool]
    assert sent["messages"][-1]["content"][0]["content"] == "saved result"
    assert dispatch.call_count == 1
    assert result.tools_used == ["lookup"]
    assert isinstance(primary.messages.stream.call_args_list[0].kwargs["system"], list)
    assert isinstance(sent["system"], str)
    assert not any("cache_control" in schema for schema in sent["tools"])


def test_failed_partial_stream_resets_tokens_before_retry(monkeypatch):
    cm = _stream_cm(["discard"])
    cm.__aenter__.return_value.get_final_message.side_effect = sdk_error(anthropic, 500)
    clients(monkeypatch, [cm], [_stream_cm(["answer"])])
    events = []
    async def emit(event):
        events.append(event)
    result = asyncio.run(provider.run_chat("hello", [], on_event=emit))
    assert result.response == "answer"
    kinds = [event["type"] for event in events]
    assert kinds.index("token_reset") < next(i for i, e in enumerate(events) if e.get("text") == "answer")


@pytest.mark.parametrize("error", [sdk_error(anthropic, 400), ChatCancelled(), ValueError("quota")])
def test_non_gateway_failure_is_unchanged(monkeypatch, error):
    _, backup = clients(monkeypatch, [error], [])
    with pytest.raises(type(error)) as raised:
        asyncio.run(provider.run_chat("hello", []))
    assert raised.value is error
    assert backup.messages.stream.call_count == 0
    assert not cooldown.is_in_cooldown("anthropic:claude")


def test_exhaustion_raises_last_error(monkeypatch):
    last = sdk_error(anthropic, 402)
    clients(monkeypatch, [sdk_error(anthropic, 500)], [last])
    with pytest.raises(type(last)) as raised:
        asyncio.run(provider.run_chat("hello", []))
    assert raised.value is last
    assert cooldown.is_in_cooldown("anthropic:backup")


def test_interpret_switches_and_records_actual_gateway(monkeypatch):
    primary = NS(messages=NS(create=Mock(side_effect=sdk_error(anthropic, 401))))
    backup = NS(messages=NS(create=Mock(return_value=NS(content=[NS(type="text", text="done")], usage=_usage()))))
    monkeypatch.setattr(provider, "_get_sync_client", lambda gateway=None: backup if gateway == "backup" else primary)
    result = provider.run_interpret("hello")
    assert (result.response, result.gateway, result.model) == ("done", "backup", "mapped")


def test_clients_are_cached_per_gateway(monkeypatch):
    cls = provider._Anthropic
    monkeypatch.setattr(cls, "_clients", {}, raising=False)
    monkeypatch.setattr(cls, "_sync_clients", {}, raising=False)
    monkeypatch.setattr(provider.llm_config, "gateway", lambda *args: {"api_key": "fake", "base_url": "https://fake.invalid"})
    monkeypatch.setattr(provider, "AsyncAnthropic", Mock(side_effect=lambda **kwargs: object()))
    monkeypatch.setattr(provider, "Anthropic", Mock(side_effect=lambda **kwargs: object()))
    for get_client in (cls.get_client, cls.get_sync_client):
        assert get_client() is get_client("claude")
        assert get_client("backup") is get_client("backup")
        assert get_client("backup") is not get_client()


def test_backup_context_limit_is_checked_before_retry(monkeypatch):
    primary, backup = clients(monkeypatch, [sdk_error(anthropic, 500)], [_stream_cm(["answer"])])
    monkeypatch.setattr(token_limits, "_config", {"default": {
        "max_output_tokens": 2048, "max_context_tokens": 100000, "max_tool_rounds": 6},
        "anthropic": {"gateways": {"backup": {"max_context_tokens": 1}}}})
    with pytest.raises(token_limits.ContextLimitError):
        asyncio.run(provider.run_chat("hello", []))
    assert primary.messages.stream.call_count == 1
    assert backup.messages.stream.call_count == 0
    assert not cooldown.is_in_cooldown("anthropic:backup")


def test_backup_output_limit_applies_to_chat_and_interpret(monkeypatch):
    _, backup = clients(monkeypatch, [sdk_error(anthropic, 500)], [_stream_cm(["answer"])])
    monkeypatch.setattr(token_limits, "_config", {"default": {
        "max_output_tokens": 2048, "max_context_tokens": 100000, "max_tool_rounds": 6},
        "anthropic": {"gateways": {"backup": {"max_output_tokens": 7}}}})
    asyncio.run(provider.run_chat("hello", []))
    assert backup.messages.stream.call_args.kwargs["max_tokens"] == 7
    sync = NS(messages=NS(create=Mock(return_value=NS(content=[], usage=_usage()))))
    monkeypatch.setattr(provider, "_get_sync_client", lambda gateway=None: sync)
    provider.run_interpret("hello")
    assert sync.messages.create.call_args.kwargs["max_tokens"] == 7


def test_interpret_honors_backup_context_limit(monkeypatch):
    cooldown.start_cooldown("anthropic:claude", 30)
    sync = NS(messages=NS(create=Mock(return_value=NS(content=[], usage=_usage()))))
    monkeypatch.setattr(provider, "_get_sync_client", lambda gateway=None: sync)
    monkeypatch.setattr(token_limits, "_config", {"default": {
        "max_output_tokens": 2048, "max_context_tokens": 100000, "max_tool_rounds": 6},
        "anthropic": {"gateways": {"backup": {"max_context_tokens": 1}}}})
    with pytest.raises(token_limits.ContextLimitError):
        provider.run_interpret("hello")
    assert sync.messages.create.call_count == 0

