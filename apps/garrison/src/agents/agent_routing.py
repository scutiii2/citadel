"""Which specialists an orchestrator offers the model this turn.

The roster is re-read from the registry every turn (specialists start and
stop independently). A specialist whose tools mcp_server does not currently
offer (its capability is switched off), or that the asking user switched off
for their own chats, is left out, so the orchestrator never promises work
nobody can do.
"""

from __future__ import annotations

import logging
from fnmatch import fnmatchcase
from typing import Iterable

import anyio.to_thread

from src.agents import agent_registry, agent_spec
from src.agents.agent_spec import RosterEntry
from src.runtime import tool_filter
from src.providers import model_tiers, reasoning_effort


_log = logging.getLogger(__name__)

# Tools every specialist gets for reporting problems; they do not make a specialist useful.
SUPPORT_TOOLS = ("tool_ticket_*",)


def own_tools(entry: RosterEntry) -> list[str]:
    """The tool globs `entry` works with: its tools.allow minus the support tools."""
    return [g for g in entry.tool_allow if not any(fnmatchcase(g, support) for support in SUPPORT_TOOLS)]


def is_usable(entry: RosterEntry, tool_names: Iterable[str]) -> bool:
    """False when `entry` has tools of its own (tools.allow minus the support
    tools) and none of them exists in `tool_names`. No tools.allow, or only
    support tools, means it works without mcp_server tools: usable."""
    own = own_tools(entry)
    if not own:
        return True
    names = list(tool_names)
    return any(fnmatchcase(name, glob) for glob in own for name in names)


def _live_tool_names() -> list[str] | None:
    """Unprefixed names of the tools mcp_server offers right now; None when
    they cannot be read (then nothing is left out). Blocking."""
    try:
        from src.tools.mcp_client import mcp_upstream

        return [mcp_upstream.unprefixed(t.name) for t in mcp_upstream.client.list_tools() if t.name.startswith("main__")]
    except Exception:  # noqa: BLE001 - an unreadable catalog must not empty the roster
        _log.debug("could not read the tool catalog; offering every specialist", exc_info=True)
        return None


def specialists() -> list[RosterEntry]:
    """Every registered non-orchestrator agent except this one. Blocking
    (re-reads the registry file) - call from a worker thread."""
    agent_registry.reload()
    me = agent_spec.current().id
    return [
        RosterEntry(
            a["id"], a.get("label") or a["id"], a.get("focus") or "",
            model_tiers.from_records(a.get("tiers")), reasoning_effort.from_record(a.get("efforts")),
            tuple(g for g in a.get("tool_allow") or () if isinstance(g, str)),
        )
        for a in agent_registry.all_agents()
        if not a.get("orchestrator") and not a.get("internal_role") and a.get("delegable", True) and a["id"] != me
    ]


async def roster_for() -> list[RosterEntry]:
    """This turn's roster: [] unless this agent is an orchestrator."""
    if not agent_spec.current().orchestrator:
        return []
    return await anyio.to_thread.run_sync(_usable_specialists)


def _usable_specialists() -> list[RosterEntry]:
    # A specialist the user switched off is gone whatever the catalog says.
    found = [entry for entry in specialists() if not tool_filter.agent_blocked(entry.id)]
    live = _live_tool_names()
    if not live:
        # Unreadable or empty catalog: nothing can be judged, so nobody is left out.
        return found
    # The user's own switches (core/tool_filter.py) count too: a specialist whose tools they
    # turned off would only run empty-handed. Checked after the catalog test above, so
    # blocking every tool hides specialists instead of offering all of them.
    names = [name for name in live if not tool_filter.is_blocked(name)]
    return [entry for entry in found if is_usable(entry, names)]
