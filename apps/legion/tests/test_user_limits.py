# apps/legion/tests/test_user_limits.py
"""A user's own limits lower, never raise, what the admin allows."""

from types import SimpleNamespace
from unittest.mock import patch

from src import server
from src.providers import token_limits
from src.providers.llm_options import LlmOptions


def _options(max_tokens=None, max_tool_rounds=None):
    return LlmOptions("anthropic", "agent", SimpleNamespace(max_tokens=max_tokens, max_tool_rounds=max_tool_rounds))


def test_user_limit_lowers_the_effective_value():
    token = token_limits.bind_user_limits({"max_output_tokens": 500, "max_tool_rounds": 3})
    try:
        assert _options().max_tokens(2048) == 500
        assert _options().max_tool_rounds(15) == 3
    finally:
        token_limits.reset_user_limits(token)


def test_user_limit_never_raises_it():
    token = token_limits.bind_user_limits({"max_output_tokens": 9000})
    try:
        assert _options().max_tokens(2048) == 2048
    finally:
        token_limits.reset_user_limits(token)


def test_an_agent_files_own_cap_is_clamped_too():
    token = token_limits.bind_user_limits({"max_output_tokens": 500})
    try:
        assert _options(max_tokens=4096).max_tokens(2048) == 500
    finally:
        token_limits.reset_user_limits(token)


def test_without_limits_nothing_changes():
    assert _options().max_tokens(2048) == 2048
    assert _options().max_tool_rounds(15) == 15


def test_junk_limits_are_ignored():
    token = token_limits.bind_user_limits({"max_output_tokens": True, "max_tool_rounds": -1, "max_context_tokens": 5, "x": 1})
    try:
        assert token_limits.apply_user_limit("max_output_tokens", 2048) == 2048
        assert token_limits.apply_user_limit("max_tool_rounds", 15) == 15
        assert token_limits.apply_user_limit("max_context_tokens", 100) == 100
    finally:
        token_limits.reset_user_limits(token)


def test_limits_are_unset_after_the_turn():
    token = token_limits.bind_user_limits({"max_tool_rounds": 2})
    token_limits.reset_user_limits(token)
    assert token_limits.apply_user_limit("max_tool_rounds", 15) == 15


def test_status_says_ask_understands_limits():
    with patch.object(server.agent_config, "status", return_value={}):
        assert server.status()["user_limits"] is True


def test_ask_forwards_limits_to_run_chat():
    import asyncio
    from unittest.mock import AsyncMock
    from src.providers.base_provider import ChatResult

    with patch.object(server.agent_config, "run_chat", new_callable=AsyncMock, return_value=ChatResult(response="hi")) as run_chat, patch.object(server.agent_config, "status", return_value={"model": "m", "context_window": 1}):
        asyncio.run(server.ask("hi", limits={"max_output_tokens": 500}))
        assert run_chat.call_args.kwargs["limits"] == {"max_output_tokens": 500}
        asyncio.run(server.ask("hi"))
        assert "limits" not in run_chat.call_args.kwargs


def test_stored_user_limits_follow_a_lowered_admin_cap_despite_agent_overrides():
    token = token_limits.bind_user_limits({"max_output_tokens": 3000, "max_tool_rounds": 7})
    try:
        assert _options(max_tokens=4096, max_tool_rounds=8).max_tokens(2048) == 2048
        assert _options(max_tokens=4096, max_tool_rounds=8).max_tool_rounds(3) == 3
    finally:
        token_limits.reset_user_limits(token)
    assert _options(max_tokens=4096, max_tool_rounds=8).max_tokens(2048) == 4096
    assert _options(max_tokens=4096, max_tool_rounds=8).max_tool_rounds(3) == 8
