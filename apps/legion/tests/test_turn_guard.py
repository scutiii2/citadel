"""Turn guards prevent further billed rounds and repeated tool execution."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents import agent_spec
from src.providers.language import anthropic_provider, openai_provider
from src.providers import llm_options
from tests.test_anthropic_provider_streaming import _round_cm
from tests.test_openai_provider import _fake_stream


@pytest.mark.parametrize("provider", [anthropic_provider, openai_provider])
@pytest.mark.parametrize("reason", ["tokens", "repeat", "time", "numbered", "lookalike"])
def test_provider_stops_before_executing_more_tools(monkeypatch, provider, reason):
    llm_options.reset_cache()
    monkeypatch.setattr(provider.token_limits, "_config", None)
    original = agent_spec.current()
    from dataclasses import replace
    limits = {"max_turn_tokens": 15} if reason == "tokens" else {"max_turn_seconds": 0.01} if reason == "time" else {}
    monkeypatch.setattr(agent_spec, "current", lambda: replace(original, llm=agent_spec.LlmSpec(provider=provider.PROVIDER_ID, **limits)))
    monkeypatch.setattr(provider.agent_routing, "roster_for", AsyncMock(return_value=[]))
    monkeypatch.setattr(provider, "_tool_schemas", lambda *args: [])
    executed = []
    def dispatch(name, args, depth):
        executed.append(args)
        if reason in ("numbered", "lookalike"):
            text = "[1004] DEP_AUTH_REJECTED treasury rejected the service token"
            if reason == "numbered":
                from src.tools.mcp_client.mcp_upstream import NumberedFailureText
                return NumberedFailureText(text)
            return text
        return "ok"

    monkeypatch.setattr(provider, "_dispatch", dispatch)
    client = MagicMock()
    rounds = []
    for index in range(4):
        arguments = {"b": 2, "a": 1} if index % 2 else {"a": 1, "b": 2}
        if provider is anthropic_provider:
            call = SimpleNamespace(type="tool_use", id=str(index), name="read", input=arguments)
            response = SimpleNamespace(stop_reason="tool_use", content=[call], usage=SimpleNamespace(input_tokens=10, output_tokens=5))
            rounds.append(_round_cm([], response))
        else:
            call = SimpleNamespace(type="function_call", call_id=str(index), name="read", arguments=json.dumps(arguments), model_dump=lambda **kwargs: {})
            response = SimpleNamespace(output=[call], output_text="", usage=SimpleNamespace(total_tokens=15, input_tokens=10, output_tokens=5))
            rounds.append(_fake_stream([], response))
    stream = client.messages.stream if provider is anthropic_provider else client.responses.stream
    stream.side_effect = rounds
    if reason == "time":
        async def slow_enter():
            await asyncio.sleep(1)
        rounds[0].__aenter__.side_effect = slow_enter
    monkeypatch.setattr(provider, "_get_client", lambda: client)
    events = []
    async def emit(event):
        events.append(event)
    if reason == "time":
        from src.providers import cancellation
        cancellation.link("budgeted-turn", "budgeted-child")
    try:
        result = asyncio.run(provider.run_chat("go", [], request_id="budgeted-turn", on_event=emit))
        counts = {"repeat": 2, "numbered": 1, "lookalike": 2}
        messages = {"tokens": "token budget", "repeat": "repeated", "time": "time budget",
                    "numbered": "1004", "lookalike": "repeated"}
        assert len(executed) == counts.get(reason, 0)
        assert messages[reason] in result.response.lower()
        if reason == "numbered":
            assert any(event.get("ok") is False and "1004" in event.get("result", "") for event in events)
        assert events[-1] == {"type": "token", "text": result.response}
        if reason == "time":
            assert cancellation.is_cancelled("budgeted-child")
    finally:
        llm_options.reset_cache()
        from src.providers import cancellation
        cancellation.clear("budgeted-child")
        cancellation.clear("budgeted-turn")


def test_agent_accepts_turn_caps(tmp_path):
    path = tmp_path / "bounded.json"
    path.write_text(json.dumps({"role": "specialist", "port": 9103, "llm": {"provider": "openai", "max_turn_tokens": 1000, "max_turn_seconds": 2.5}}))
    spec = agent_spec.load_file(path)
    assert spec.llm.max_turn_tokens == 1000
    assert spec.llm.max_turn_seconds == 2.5


@pytest.mark.parametrize("key,value", [("max_turn_tokens", 0), ("max_turn_tokens", True), ("max_turn_tokens", 1.5), ("max_turn_seconds", 0), ("max_turn_seconds", True), ("max_turn_seconds", float("inf"))])
def test_agent_rejects_invalid_turn_caps(tmp_path, key, value):
    path = tmp_path / "bounded.json"
    path.write_text(json.dumps({"role": "specialist", "port": 9103, "llm": {"provider": "openai", key: value}}))
    with pytest.raises(agent_spec.AgentSpecError, match=key):
        agent_spec.load_file(path)

def test_a_non_retryable_failure_stops_the_same_call_from_repeating():
    import pytest
    from src.providers.turn_guard import TurnGuard, TurnStopped

    guard = TurnGuard()
    guard.check_call("stronghold__tool_ticket_getTicket", {"id": "t1"})
    guard.note_result("stronghold__tool_ticket_getTicket", {"id": "t1"}, "[1004] DEP_AUTH_REJECTED treasury rejected the service token")
    with pytest.raises(TurnStopped) as stopped:
        guard.check_call("stronghold__tool_ticket_getTicket", {"id": "t1"})
    assert "1004" in str(stopped.value)


def test_a_retryable_failure_does_not_block_a_retry():
    from src.providers.turn_guard import TurnGuard

    guard = TurnGuard()
    guard.note_result("t", {}, "[1002] DEP_UNAVAILABLE treasury unavailable")
    guard.check_call("t", {})  # must not raise


@pytest.mark.parametrize("text", [
    "[1002] DEP_UNAVAILABLE treasury unavailable",
    "[1003] DEP_TIMEOUT treasury timed out",
    "[1005] DEP_ERROR treasury returned an error",
])
def test_a_numbered_retry_can_repeat_under_the_turn_budget(text):
    from src.providers.turn_guard import TurnGuard

    guard = TurnGuard()
    for _ in range(4):
        guard.check_call("t", {})
        guard.note_result("t", {}, text)
