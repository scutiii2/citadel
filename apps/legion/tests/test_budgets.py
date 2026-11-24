"""Token budgets and the daily counters."""

import pytest

from src.runtime import budgets, counters, tuning_overrides


def test_counters_add_up_per_day_and_come_back_in_the_history(tmp_path):
    db = tmp_path / "c.db"
    counters.add("a", 2, db)
    counters.add("a", 3, db)
    counters.add("b", 1, db)
    counters.add("zero", 0, db)
    assert counters.today("a", db) == 5 and counters.today("missing", db) == 0
    assert list(counters.history(3, db).values()) == [{"a": 5, "b": 1}]
    assert counters.safe_name("Ann@Example.com/../x|y") == "ann@example.com_.._x_y"


def test_a_daily_budget_of_zero_is_no_limit_and_a_set_one_refuses_when_used_up():
    budgets.check("ann@example.com", "ember")  # no limit set
    tuning_overrides.save({"budgets.daily_tokens_per_user": 1000, "budgets.daily_tokens_per_agent": 5000})
    budgets.record("ann@example.com", "ember", 600)
    budgets.check("ann@example.com", "ember")
    budgets.record("ann@example.com", "ember", 400)
    with pytest.raises(budgets.BudgetUsed, match="Your daily token budget"):
        budgets.check("ann@example.com", "ember")
    budgets.check("bob@example.com", "ember")  # another user is not affected
    budgets.check(None, "ember")  # a direct call with no signed-in user: only the agent limit applies
    budgets.record(None, "ember", 4000)  # the agent's total is now 5,000
    with pytest.raises(budgets.BudgetUsed, match="agent's daily token budget"):
        budgets.check("bob@example.com", "ember")


def test_the_turn_limits_come_from_tuning_unless_the_agent_file_sets_its_own():
    from types import SimpleNamespace

    from src.providers.llm_options import LlmOptions

    spec = SimpleNamespace(max_turn_tokens=None, max_turn_seconds=40)
    options = LlmOptions("anthropic", "x", spec)
    assert (options.turn_guard().max_tokens, options.turn_guard().max_seconds) == (100_000, 40)
    tuning_overrides.save({"budgets.turn_tokens": 5000, "budgets.turn_seconds": 90})
    guard = options.turn_guard()
    assert (guard.max_tokens, guard.max_seconds) == (5000, 40)


def test_ask_refuses_a_used_up_user_budget_only_on_the_turn_the_user_asked():
    import asyncio
    from dataclasses import replace
    from unittest.mock import patch

    from src import server
    from src.providers.base_provider import ChatResult
    from src.runtime import internal_auth

    tuning_overrides.save({"budgets.daily_tokens_per_user": 100})
    counters.add(budgets.user_key("ann@example.com"), 500)

    async def fake_run_chat(question, history, request_id, depth, **kwargs):
        return ChatResult(response="done")

    async def ask(depth):
        with patch("src.server.agent_config.run_chat", new=fake_run_chat), \
             patch("src.server.agent_config.status", return_value={"model": "m", "context_window": 1000}):
            token = internal_auth.bind_requester(replace(internal_auth.current_requester(), email="ann@example.com"))
            try:
                return await server.ask("q", depth=depth)
            finally:
                internal_auth.reset_requester(token)

    with pytest.raises(budgets.BudgetUsed):
        asyncio.run(ask(0))
    assert asyncio.run(ask(1))["response"] == "done"  # a specialist of a plan that already started
