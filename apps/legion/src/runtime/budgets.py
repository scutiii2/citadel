"""Token budgets: how much one turn may use, and how much one user or one agent may use per day.

Both are `budgets.<name>` paths of the Tuning page (runtime/tuning_overrides.py, table `tuning` of settings.db), so no
config file holds them. A daily budget of 0 means no limit. Usage is counted per UTC day in stats.db
(runtime/counters.py): `ask` adds the tokens an agent used after each turn and refuses a new turn once the user's or
the agent's budget for the day is used up. The count is of tokens a provider reported, so a turn may overshoot by what
it was already running when the budget ran out.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.runtime import counters, tuning_overrides

PREFIX = "budgets."
DEFAULTS: dict[str, Any] = {"turn_tokens": 100_000, "turn_seconds": 300, "daily_tokens_per_user": 0, "daily_tokens_per_agent": 0}


@dataclass(frozen=True)
class Budgets:
    turn_tokens: int = 100_000
    turn_seconds: int = 300
    daily_tokens_per_user: int = 0
    daily_tokens_per_agent: int = 0


class BudgetUsed(ValueError):
    """A daily budget is used up; the message is safe to show."""


def current(db: Path | None = None) -> Budgets:
    stored = {key[len(PREFIX):]: value for key, value in tuning_overrides.load(db or tuning_overrides.PATH).items()
              if key.startswith(PREFIX)}
    return Budgets(**{**DEFAULTS, **stored})


def user_key(user: str) -> str:
    return f"tokens.user.{counters.safe_name(user)}"


def agent_key(agent_id: str) -> str:
    return f"tokens.agent.{counters.safe_name(agent_id)}"


def check(user: str | None, agent_id: str) -> None:
    """Raise BudgetUsed when the user's or the agent's daily budget is used up."""
    limits = current()
    if user and limits.daily_tokens_per_user and counters.today(user_key(user)) >= limits.daily_tokens_per_user:
        raise BudgetUsed(f"Your daily token budget ({limits.daily_tokens_per_user:,} tokens) is used up. It resets at midnight UTC.")
    if limits.daily_tokens_per_agent and counters.today(agent_key(agent_id)) >= limits.daily_tokens_per_agent:
        raise BudgetUsed(f"This agent's daily token budget ({limits.daily_tokens_per_agent:,} tokens) is used up. It resets at midnight UTC.")


def record(user: str | None, agent_id: str, tokens: int | None) -> None:
    """Count the tokens one turn of `agent_id` used, for the asking user as well."""
    if not tokens or tokens <= 0:
        return
    counters.add(agent_key(agent_id), tokens)
    if user:
        counters.add(user_key(user), tokens)
