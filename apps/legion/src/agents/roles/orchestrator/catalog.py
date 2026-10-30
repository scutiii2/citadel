"""A bounded snapshot of the live architects and their worker capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anyio.to_thread

from src.agents import agent_registry
from src.runtime import tool_filter

MAX_CHARS = 8192


@dataclass(frozen=True)
class Catalog:
    text: str
    architect_ids: frozenset[str]


def _line(value: Any) -> str:
    return " ".join(str(value or "").split())


def build(agents: list[dict[str, Any]], max_chars: int = MAX_CHARS) -> Catalog:
    by_id = {agent["id"]: agent for agent in agents}
    architects = [a for a in agents if a.get("role") == "architect" and a.get("delegable", True)
                  and not tool_filter.agent_blocked(a["id"])]
    lines, included = [], []
    for agent in architects:
        line = f"- {_line(agent['id'])} ({_line(agent.get('kind'))}): {_line(agent.get('focus'))}"
        if len("\n".join([*lines, line])) <= max_chars:
            lines.append(line)
            included.append(agent)
    for agent in included:
        for worker_id in agent.get("workers") or ():
            worker = by_id.get(worker_id)
            if not worker or worker.get("role") != "specialist" or tool_filter.agent_blocked(worker_id):
                continue
            line = f"  {_line(agent['id'])} worker {_line(worker_id)}: {_line(worker.get('focus'))}"
            if len("\n".join([*lines, line])) <= max_chars:
                lines.append(line)
    return Catalog("\n".join(lines), frozenset(agent["id"] for agent in included))


def _live() -> Catalog:
    agent_registry.reload()
    return build(agent_registry.all_agents())


async def for_turn() -> Catalog:
    return await anyio.to_thread.run_sync(_live)
