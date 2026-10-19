"""anthropic_provider.py prompt caching: cache breakpoints on the system block and
the last tool, opt-in per gateway, and usage that counts cached tokens. Plain sync
`def test_x():` wrapping `asyncio.run(...)`, like the streaming tests.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.llm import anthropic_provider

_EPHEMERAL = {"type": "ephemeral"}


def _schema(name: str) -> dict:
    return {"name": name, "description": "d", "input_schema": {"type": "object", "properties": {}}, "display_label": None}


def _round_cm(final_message):
    stream = MagicMock()

    async def chunks():
        return
        yield

    stream.text_stream = chunks()
    stream.get_final_message = AsyncMock(return_value=final_message)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=stream)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _run_chat(monkeypatch, *, cache: bool, usage: SimpleNamespace):
    """One answered round; returns (result, the kwargs the SDK was called with)."""
    response = MagicMock(stop_reason="end_turn", content=[])
    response.usage = usage
    client = MagicMock()
    client.messages.stream = MagicMock(return_value=_round_cm(response))
    monkeypatch.setattr(anthropic_provider, "_get_client", lambda: client)
    monkeypatch.setattr(anthropic_provider, "_prompt_cache_enabled", lambda: cache)
    monkeypatch.setattr(
        anthropic_provider, "_tool_schemas",
        lambda enabled_extensions=None, roster=(): [_schema("first"), _schema("last")],
    )
    result = asyncio.run(anthropic_provider.run_chat("hi", []))
    return result, client.messages.stream.call_args.kwargs


def test_cached_request_marks_the_system_block_and_the_last_tool_only():
    schemas = [_schema("first"), _schema("last")]

    system, tools = anthropic_provider._cached_request("be brief", schemas)

    assert system == [{"type": "text", "text": "be brief", "cache_control": _EPHEMERAL}]
    assert "cache_control" not in tools[0]
    assert tools[1]["cache_control"] == _EPHEMERAL
    assert "cache_control" not in schemas[1]  # the caller's list is left alone


def test_cached_request_with_no_tools_still_caches_the_system_block():
    system, tools = anthropic_provider._cached_request("be brief", [])

    assert system[0]["cache_control"] == _EPHEMERAL
    assert tools == []


def test_prompt_tokens_adds_back_what_the_cache_wrote_and_served():
    usage = SimpleNamespace(input_tokens=100, cache_creation_input_tokens=300, cache_read_input_tokens=10_000)

    assert anthropic_provider._prompt_tokens(usage) == 10_400


def test_prompt_tokens_ignores_a_missing_null_or_non_numeric_counter():
    assert anthropic_provider._prompt_tokens(SimpleNamespace(input_tokens=7)) == 7
    assert anthropic_provider._prompt_tokens(
        SimpleNamespace(input_tokens=7, cache_creation_input_tokens=None, cache_read_input_tokens=MagicMock())
    ) == 7


def test_run_chat_sends_cache_breakpoints_and_counts_cached_tokens(monkeypatch):
    usage = SimpleNamespace(
        input_tokens=50, output_tokens=20, cache_creation_input_tokens=0, cache_read_input_tokens=10_000,
    )

    result, kwargs = _run_chat(monkeypatch, cache=True, usage=usage)

    assert kwargs["system"][0]["cache_control"] == _EPHEMERAL
    assert kwargs["tools"][-1]["cache_control"] == _EPHEMERAL
    assert all("display_label" not in tool for tool in kwargs["tools"])
    assert result.input_tokens == 10_050
    assert result.context_tokens == 10_050
    assert result.total_tokens == 10_070
    assert result.cached_input_tokens == 10_000


def test_history_breakpoint_wraps_a_string_message_and_leaves_the_original_alone():
    messages = [{"role": "user", "content": "earlier"}, {"role": "user", "content": "now"}]

    marked = anthropic_provider._with_history_breakpoint(messages)

    assert marked[-1]["content"] == [{"type": "text", "text": "now", "cache_control": _EPHEMERAL}]
    assert marked[0] is messages[0]
    assert messages[-1]["content"] == "now"


def test_history_breakpoint_marks_the_last_tool_result_only():
    results = [
        {"type": "tool_result", "tool_use_id": "a", "content": "one"},
        {"type": "tool_result", "tool_use_id": "b", "content": "two"},
    ]
    messages = [{"role": "user", "content": "q"}, {"role": "user", "content": results}]

    marked = anthropic_provider._with_history_breakpoint(messages)

    assert "cache_control" not in marked[-1]["content"][0]
    assert marked[-1]["content"][1]["cache_control"] == _EPHEMERAL
    assert "cache_control" not in results[1]


def test_history_breakpoint_leaves_an_unmarkable_last_message_as_it_is():
    for content in ("", [], [object()]):
        messages = [{"role": "user", "content": content}]
        assert anthropic_provider._with_history_breakpoint(messages) is messages
    assert anthropic_provider._with_history_breakpoint([]) == []


def test_each_round_of_a_tool_loop_carries_one_history_breakpoint_on_its_last_message(monkeypatch):
    tool_block = MagicMock(type="tool_use", input={}, id="t1")
    tool_block.name = "tool_srv_listApps"
    first = MagicMock(stop_reason="tool_use", content=[tool_block])
    first.usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    second = MagicMock(stop_reason="end_turn", content=[])
    second.usage = SimpleNamespace(input_tokens=3, output_tokens=1)
    client = MagicMock()
    client.messages.stream = MagicMock(side_effect=[_round_cm(first), _round_cm(second)])
    monkeypatch.setattr(anthropic_provider, "_get_client", lambda: client)
    monkeypatch.setattr(anthropic_provider, "_prompt_cache_enabled", lambda: True)
    monkeypatch.setattr(anthropic_provider, "_dispatch", lambda name, args, depth: "2 apps running")
    monkeypatch.setattr(anthropic_provider, "_tool_schemas", lambda enabled_extensions=None, roster=(): [_schema("t")])

    asyncio.run(anthropic_provider.run_chat("status?", []))

    for call in client.messages.stream.call_args_list:
        sent = call.kwargs["messages"]
        marked = [
            block for message in sent if isinstance(message["content"], list)
            for block in message["content"] if isinstance(block, dict) and "cache_control" in block
        ]
        assert len(marked) == 1
        assert marked[0] is sent[-1]["content"][-1]


def test_run_chat_sends_plain_system_and_tools_when_the_gateway_has_not_opted_in(monkeypatch):
    usage = SimpleNamespace(input_tokens=50, output_tokens=20)

    result, kwargs = _run_chat(monkeypatch, cache=False, usage=usage)

    assert isinstance(kwargs["system"], str)
    assert all("cache_control" not in tool for tool in kwargs["tools"])
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert result.input_tokens == 50
    assert result.cached_input_tokens == 0


def test_prompt_cache_is_off_unless_the_gateway_block_sets_it(monkeypatch):
    monkeypatch.setattr(anthropic_provider.llm_config, "gateway", lambda provider, name: {"label": "x"})
    assert anthropic_provider._prompt_cache_enabled() is False

    monkeypatch.setattr(anthropic_provider.llm_config, "gateway", lambda provider, name: {"prompt_cache": True})
    assert anthropic_provider._prompt_cache_enabled() is True

    def unknown(provider, name):
        raise KeyError(name)

    monkeypatch.setattr(anthropic_provider.llm_config, "gateway", unknown)
    assert anthropic_provider._prompt_cache_enabled() is False
