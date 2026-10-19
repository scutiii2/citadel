"""llm/context_breakdown.py: the parts of a prompt always add up to the size the provider reported."""

from __future__ import annotations

from src.agents import ask_user, delegation, plan
from src.llm.context_breakdown import EstimateCounter, build_breakdown


def _by_id(parts):
    return {p["id"]: p["tokens"] for p in parts}


class FixedCounter:
    """Every text counts as its length, so the expected parts are easy to read."""

    def count(self, text: str) -> int:
        return len(text)


def test_the_parts_add_up_to_the_reported_size():
    schemas = [{"name": "tool_srv_a", "description": "x" * 400}, {"name": plan.TOOL_NAME, "description": "y" * 80}]

    parts = build_breakdown(5000, "s" * 800, "r" * 200, schemas)

    assert sum(p["tokens"] for p in parts) == 5000
    assert [p["id"] for p in parts] == ["system_prompt", "agents", "builtin_tools", "mcp_tools", "messages"]
    ids = _by_id(parts)
    assert ids["system_prompt"] == 150  # 800 chars of system prompt, minus the 200 of roster: 600 / 4
    assert ids["agents"] == 50


def test_messages_get_the_remainder_and_are_last():
    parts = build_breakdown(1000, "abcd", "", [], FixedCounter())

    assert parts == [
        {"id": "system_prompt", "label": "System prompt", "tokens": 4},
        {"id": "messages", "label": "Messages", "tokens": 996},
    ]


def test_built_in_tools_are_told_apart_from_mcp_tools():
    schemas = [
        {"name": delegation.TOOL_NAME},
        {"name": ask_user.TOOL_NAME},
        {"name": plan.TOOL_NAME},
        {"name": "tool_srv_a"},
    ]
    counter = FixedCounter()

    ids = _by_id(build_breakdown(10_000, "", "", schemas, counter))

    builtin = sum(len('{"name":"%s"}' % n) for n in (delegation.TOOL_NAME, ask_user.TOOL_NAME, plan.TOOL_NAME))
    assert ids["builtin_tools"] == builtin
    assert ids["mcp_tools"] == len('{"name":"tool_srv_a"}')


def test_static_parts_over_the_total_are_scaled_down_to_fit():
    parts = build_breakdown(100, "s" * 4000, "", [{"name": "tool_srv_a", "description": "d" * 4000}])

    assert sum(p["tokens"] for p in parts) <= 100
    assert all(p["tokens"] > 0 for p in parts)
    assert "messages" not in _by_id(parts) or _by_id(parts)["messages"] >= 0


def test_no_reported_size_gives_no_breakdown():
    assert build_breakdown(None, "system", "", []) == []
    assert build_breakdown(0, "system", "", []) == []


def test_the_estimate_is_about_four_characters_a_token():
    counter = EstimateCounter()

    assert counter.count("") == 0
    assert counter.count("abcd") == 1
    assert counter.count("abcde") == 2


# --- exact counting ------------------------------------------------------------

import asyncio  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

from src.llm import context_breakdown  # noqa: E402
from src.llm.context_breakdown import ProviderCounter, breakdown_fields  # noqa: E402


class FakeRequestCounter:
    """A provider endpoint that charges 10 tokens for the bare message, 1 per character of system text and
    2 per character of tool JSON."""

    def __init__(self, fail: bool = False, delay: float = 0.0):
        self.calls: list[tuple[str, int]] = []
        self.fail = fail
        self.delay = delay

    async def count(self, *, system: str = "", tools=()):
        self.calls.append((system, len(tools)))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("no count endpoint")
        return 10 + len(system) + 2 * sum(len(str(t)) for t in tools)


@pytest.fixture(autouse=True)
def _fresh_cache():
    ProviderCounter._cache.clear()
    yield
    ProviderCounter._cache.clear()


def _run(coro):
    return asyncio.run(coro)


def _exact(client, system="S" * 50 + "R" * 20, roster="R" * 20, schemas=(), total=1000):
    token = context_breakdown.bind_exact(True)
    try:
        return _run(breakdown_fields(total, system, roster, list(schemas), lambda: ProviderCounter(client, "m1")))
    finally:
        context_breakdown.reset_exact(token)


def test_exact_counts_each_part_less_the_baseline():
    client = FakeRequestCounter()
    schemas = [{"name": plan.TOOL_NAME}, {"name": "tool_srv_a"}]

    fields = _exact(client, schemas=schemas)

    assert fields["context_breakdown_exact"] is True
    ids = _by_id(fields["context_breakdown"])
    assert ids["system_prompt"] == 50
    assert ids["agents"] == 20
    assert ids["builtin_tools"] == 2 * len(str(schemas[0]))
    assert ids["mcp_tools"] == 2 * len(str(schemas[1]))
    assert sum(ids.values()) == 1000


def test_a_part_that_did_not_change_is_not_counted_again():
    client = FakeRequestCounter()
    schemas = [{"name": "tool_srv_a"}]

    _exact(client, schemas=schemas)
    first = len(client.calls)
    _exact(client, schemas=schemas)

    assert first == 4  # the baseline, the system prompt, the roster, the MCP tools
    assert len(client.calls) == first


def test_a_changed_part_is_counted_again_and_the_rest_are_not():
    client = FakeRequestCounter()

    _exact(client, schemas=[{"name": "tool_srv_a"}])
    before = len(client.calls)
    _exact(client, schemas=[{"name": "tool_srv_b"}])

    assert len(client.calls) == before + 1


def test_a_failing_counter_falls_back_to_the_estimate():
    fields = _exact(FakeRequestCounter(fail=True), system="s" * 400, roster="", schemas=[])

    assert fields["context_breakdown_exact"] is False
    assert _by_id(fields["context_breakdown"])["system_prompt"] == 100  # 400 chars / 4
    assert sum(_by_id(fields["context_breakdown"]).values()) == 1000


def test_a_slow_counter_falls_back_to_the_estimate(monkeypatch):
    monkeypatch.setattr(context_breakdown, "EXACT_TIMEOUT_SECONDS", 0.05)

    fields = _exact(FakeRequestCounter(delay=1.0))

    assert fields["context_breakdown_exact"] is False


def test_without_the_flag_nothing_is_counted_by_the_provider():
    client = FakeRequestCounter()

    fields = _run(breakdown_fields(1000, "s" * 40, "", [], lambda: ProviderCounter(client, "m1")))

    assert fields["context_breakdown_exact"] is False
    assert client.calls == []


def test_the_flag_is_per_turn_and_resets():
    assert context_breakdown.exact_requested() is False
    token = context_breakdown.bind_exact(True)
    assert context_breakdown.exact_requested() is True
    context_breakdown.reset_exact(token)
    assert context_breakdown.exact_requested() is False


def test_anthropic_counter_sends_one_short_message_with_the_given_system_and_tools():
    from src.llm.anthropic_provider import _AnthropicRequestCounter

    client = MagicMock()
    client.messages.count_tokens = AsyncMock(return_value=MagicMock(input_tokens=42))

    counted = _run(_AnthropicRequestCounter(client, "claude-x").count(system="sys", tools=[{"name": "t"}]))

    assert counted == 42
    client.messages.count_tokens.assert_awaited_once_with(
        model="claude-x", messages=[{"role": "user", "content": "x"}], system="sys", tools=[{"name": "t"}],
    )


def test_openai_counter_uses_the_responses_input_token_count():
    from src.llm.openai_provider import _OpenAIRequestCounter

    client = MagicMock()
    client.responses.input_tokens.count = AsyncMock(return_value=MagicMock(input_tokens=17))

    counted = _run(_OpenAIRequestCounter(client, "gpt-x").count(system="sys"))

    assert counted == 17
    client.responses.input_tokens.count.assert_awaited_once_with(
        model="gpt-x", input=[{"role": "user", "content": "x"}], instructions="sys",
    )
