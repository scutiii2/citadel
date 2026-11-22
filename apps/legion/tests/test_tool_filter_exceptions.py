import pytest

from src.runtime import tool_filter


@pytest.mark.parametrize(("names", "allowed", "blocked"), [
    (["*", "!stronghold__tool_brain_search"], ["stronghold__tool_brain_search"],
     ["stronghold__tool_brain_write", "armory__tool_web_search"]),
    (["armory__tool_web_search", "!stronghold__tool_brain_search"],
     ["stronghold__tool_brain_search", "stronghold__tool_brain_write"], ["armory__tool_web_search"]),
    (["x", "!x"], ["x"], []),
])
def test_tool_filter_exceptions(names, allowed, blocked):
    token = tool_filter.bind(names)
    try:
        assert all(not tool_filter.is_blocked(name) for name in allowed)
        assert all(tool_filter.is_blocked(name) for name in blocked)
    finally:
        tool_filter.reset(token)


def test_the_set_still_travels_whole_and_agent_blocking_is_unchanged():
    token = tool_filter.bind(["*", "!a", "agent:writer"])
    try:
        assert tool_filter.blocked() == frozenset({"*", "!a", "agent:writer"})
        assert tool_filter.agent_blocked("writer") is True
        assert tool_filter.agent_blocked("other") is False
    finally:
        tool_filter.reset(token)
