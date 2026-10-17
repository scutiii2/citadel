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
