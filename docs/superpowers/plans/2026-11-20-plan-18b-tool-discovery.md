# Plan 18b: Agents see tools of Legion's other MCP connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tool of a connection saved in Legion Admin (for example `bard__tool_bard_speak`) is offered to an agent, and callable by it, when the agent's `tools.allow` names it. Today only `main__` tools reach agents.

**Architecture:** Legion's `mcp_upstream.py` filters the registry's tools to the `main__` prefix, in `list_tools`, `_qualified`, `call_tool`, `warn_unmatched_tool_globs` and `agent_routing._live_tool_names`. The change widens those five places to every registry server, with one rule: tools of a connection other than `main` reach an agent only when `tools.allow` names them (an empty allow list does not expose them), and they are not gated by `enabled_extensions`. A Legion connection of the same id replaces Armory's proxied extension of that name while both exist.

**Tech Stack:** Python 3.12+, pytest, uv. No UI and no other service changes.

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md` (Legion owns "all MCP connections to outside servers"; Armory's proxy is dropped in Plan 22). Follows Plan 18 (merged), which left connections invisible to agents. Roadmap: `2026-11-20-scope-roadmap.md`.

## Baseline

On local `main` at `97bb6982`, `uv run pytest -q -p no:cacheprovider -m "not slow"` returned 1,451 passed, 6 deselected, and 2 pre-existing deprecation warnings. The sandbox blocked the uv cache and Windows asyncio loopback, so the successful run used approved local execution.

## Global Constraints

- Agent-facing tool names: `main__` is still stripped (`unprefixed`); a tool of another connection keeps its server id as the prefix, so `bard__tool_bard_speak` is both its registry name and the name `tools.allow` globs match. This is the shape `agents/shared-extensions.json` already uses (`bard__*`).
- An agent sees another connection's tools only when `tools.allow` is non-empty and matches the name and `tools.deny` does not. An empty `allow` list never exposes them (a new connection must not appear in every unscoped agent).
- Another connection's tools are not gated by `enabled_extensions` (that list gates Armory's proxied extensions only) and are not "read-only built-ins": with approvals on they ask, as an Armory extension tool does.
- A model may name a tool without a prefix only for `main` built-ins (existing behaviour); an exact registry name always wins over the `main__` guess.
- A call the scope forbids, or the user switched off, raises `PermissionError` before anything is sent.
- Private (`u_`) tools are unchanged.
- No new settings, no UI, no change to the registry or to Plan 18 code.
- Python through `uv`. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File structure

| File | Responsibility |
|---|---|
| `apps/legion/src/agents/agent_spec.py` (modify) | `ToolScope.allows_explicitly` |
| `apps/legion/src/tools/mcp_client/mcp_upstream.py` (modify) | List, qualify and call tools of every connection; warn on unmatched globs |
| `apps/legion/src/agents/agent_routing.py` (modify) | Roster check sees every connection's tools |
| `apps/legion/tests/test_mcp_upstream_servers.py` (create) | All tests of this plan |
| `apps/legion/README.md`, `apps/legion/agents/README.md`, spec, `aiagent-scaffold` skill (modify) | Document the rule |

### Task 1: Listing

**Files:**
- Modify: `apps/legion/src/agents/agent_spec.py` (`ToolScope`, line ~88), `apps/legion/src/tools/mcp_client/mcp_upstream.py` (`list_tools`)
- Test: `apps/legion/tests/test_mcp_upstream_servers.py` (create)

**Interfaces:**
- Produces: `ToolScope.allows_explicitly(name: str) -> bool` (True only when `allow` is non-empty, matches, and `deny` does not); `mcp_upstream._other_server(name: str) -> bool` (a registry tool that is neither `main__` nor private); `list_tools` now also returns tools of other connections that pass `allows_explicitly` and are not blocked, and skips a `main__<id>__*` tool when a connection `<id>` is connected.

- [x] **Step 1: Write the failing tests**

```python
# apps/legion/tests/test_mcp_upstream_servers.py
"""Tools of Legion's own MCP connections (bard__..., lens__...) reach an agent only through its tools.allow."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from mcp import types

from src.agents import agent_routing
from src.agents.agent_spec import ToolScope
from src.tools.mcp_client import mcp_upstream


def tool(name: str) -> types.Tool:
    return types.Tool(name=name, description="d", inputSchema={"type": "object"})


# main is Armory; bard and lens are Legion connections; main__bard__* is Armory's proxied extension of the same name.
CATALOG = [tool("main__tool_ticket_create"), tool("main__bard__tool_bard_speak"), tool("main__scribe__tool_x"),
           tool("bard__tool_bard_speak"), tool("lens__tool_ocr")]


def agent(allow=(), deny=()):
    return SimpleNamespace(id="a", tools=ToolScope(tuple(allow), tuple(deny)))


@pytest.fixture
def upstream(monkeypatch):
    calls: list[str] = []

    def call(name, arguments, **extra):
        calls.append(name)
        return types.CallToolResult(content=[types.TextContent(type="text", text="ok")])

    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: CATALOG)
    monkeypatch.setattr(mcp_upstream.client, "call_tool", call)
    return calls


def listed(allow=(), deny=(), enabled=()):
    with patch.object(mcp_upstream.agent_spec, "current", return_value=agent(allow, deny)):
        return [t.name for t in mcp_upstream.list_tools(list(enabled))]


def test_allows_explicitly_needs_a_matching_allow_glob():
    assert ToolScope().allows_explicitly("bard__x") is False
    assert ToolScope(("bard__*",)).allows_explicitly("bard__x") is True
    assert ToolScope(("bard__*",)).allows_explicitly("lens__x") is False
    assert ToolScope(("bard__*",), ("*x",)).allows_explicitly("bard__x") is False


def test_an_agent_without_an_allow_list_sees_main_tools_only(upstream):
    assert listed() == ["main__tool_ticket_create"]


def test_an_allow_glob_offers_a_connections_tools_without_an_enabled_extension(upstream):
    assert listed(allow=("bard__*", "lens__*")) == ["bard__tool_bard_speak", "lens__tool_ocr"]


def test_deny_wins_over_allow(upstream):
    assert listed(allow=("bard__*",), deny=("*speak",)) == []


def test_the_connection_replaces_the_proxied_extension_of_the_same_name(upstream):
    # main__bard__tool_bard_speak would match bard__* too; only the Legion connection's tool is offered.
    assert listed(allow=("bard__*",)) == ["bard__tool_bard_speak"]


def test_a_proxied_extension_without_a_connection_is_unchanged(upstream):
    assert listed(enabled=["scribe"]) == ["main__tool_ticket_create", "main__scribe__tool_x"]
    assert listed(enabled=[]) == ["main__tool_ticket_create"]


def test_a_tool_the_user_switched_off_is_not_offered(upstream, monkeypatch):
    monkeypatch.setattr(mcp_upstream.tool_filter, "is_blocked", lambda name: name == "lens__tool_ocr")
    assert listed(allow=("bard__*", "lens__*")) == ["bard__tool_bard_speak"]
```

- [x] **Step 2: Run to verify failure.** From `apps/legion`: `uv run pytest tests/test_mcp_upstream_servers.py -q -p no:cacheprovider`. Expected: FAIL (`AttributeError: 'ToolScope' object has no attribute 'allows_explicitly'`).

- [x] **Step 3: Implement.** In `agent_spec.py`, add to `ToolScope` after `allows`:

```python
    def allows_explicitly(self, name: str) -> bool:
        """True only when `allow` names the tool. Tools of an outside connection need this: an empty allow list,
        which means every `main` tool, must not expose a connection an administrator added later."""
        return bool(self.allow) and self.allows(name)
```

In `mcp_upstream.py` add after `_tool_is_enabled`:

```python
def _other_server(name: str) -> bool:
    """A registry tool of a connection other than `main` (for example `bard__tool_bard_speak`)."""
    return not name.startswith((_PREFIX, private_turn.TOOL_PREFIX))
```

and replace the body of `list_tools` from `tools = client.list_tools()` to the `result.extend` line with:

```python
    tools = client.list_tools()
    _remember_read_only(tools)
    enabled = set(enabled_extensions or [])
    scope = agent_spec.current().tools
    connected = {tool.name.partition("__")[0] for tool in tools} - {_SERVER_ID}
    result = []
    for tool in tools:
        short = unprefixed(tool.name)
        if _other_server(tool.name):
            # An administrator's connection: only an explicit tools.allow offers it, whatever `enabled_extensions` says.
            if scope.allows_explicitly(short) and not tool_filter.is_blocked(short):
                result.append(tool)
            continue
        if "__" in short and short.partition("__")[0] in connected:
            continue  # a Legion connection of this id replaces Armory's proxied extension of the same name
        if not _tool_is_enabled(short, enabled):
            continue
        if not scope.allows(short):
            continue
        if tool_filter.is_blocked(short):
            continue
        result.append(tool)
    turn = private_turn.current()
    if turn:
        # Fetched before the provider started (prefetch_private), so this never waits on a network.
        result.extend(tool for tool in turn.tools() if scope.allows(tool.name) and not tool_filter.is_blocked(tool.name))
    return result
```

Also update the `list_tools` docstring's first line to "Live tool catalog from every connected server".

- [x] **Step 4: Run to verify pass.** `uv run pytest tests/test_mcp_upstream_servers.py tests/test_private_upstream.py -q -p no:cacheprovider`. Expected: PASS (the private tests prove private tools are unchanged).

- [x] **Step 5: Commit** `feat(legion): offer tools of Legion's other MCP connections to agents that name them`.

### Task 2: Calling

**Files:**
- Modify: `apps/legion/src/tools/mcp_client/mcp_upstream.py` (`_qualified`, `call_tool`)
- Test: `apps/legion/tests/test_mcp_upstream_servers.py`

**Interfaces:**
- Consumes: `ToolScope.allows_explicitly`, `_other_server` (Task 1).
- Produces: `_qualified(name)` returns an exact registry name unchanged and otherwise tries the `main__` guess; `call_tool` refuses (`PermissionError`) a tool of another connection that the agent's `allow` does not name, and one the user switched off, before sending anything.

- [x] **Step 1: Write the failing tests** (append)

```python
def call(name, allow=(), deny=()):
    with patch.object(mcp_upstream.agent_spec, "current", return_value=agent(allow, deny)):
        return mcp_upstream.call_tool(name, {})


def test_a_call_by_exact_name_reaches_the_connection_not_the_proxied_extension(upstream):
    assert call("bard__tool_bard_speak", allow=("bard__*",)) == "ok"
    assert upstream == ["bard__tool_bard_speak"]


def test_a_bare_main_tool_name_still_reaches_the_built_in(upstream):
    assert call("tool_ticket_create") == "ok"
    assert upstream == ["main__tool_ticket_create"]


def test_a_connection_tool_the_allow_list_does_not_name_is_refused(upstream):
    with pytest.raises(PermissionError):
        call("lens__tool_ocr", allow=("bard__*",))
    with pytest.raises(PermissionError):
        call("lens__tool_ocr")  # an empty allow list never exposes a connection
    assert upstream == []


def test_a_denied_or_switched_off_connection_tool_is_refused(upstream, monkeypatch):
    with pytest.raises(PermissionError):
        call("bard__tool_bard_speak", allow=("bard__*",), deny=("*speak",))
    monkeypatch.setattr(mcp_upstream.tool_filter, "is_blocked", lambda name: name == "bard__tool_bard_speak")
    with pytest.raises(PermissionError):
        call("bard__tool_bard_speak", allow=("bard__*",))
    assert upstream == []
```

- [x] **Step 2: Run to verify failure.** `uv run pytest tests/test_mcp_upstream_servers.py -q -p no:cacheprovider -k "call or refused or exact or bare"`. Expected: FAIL (the exact-name call is rerouted to `main__bard__...`; the refusals do not raise).

- [x] **Step 3: Implement.** Replace `_qualified` and the head of `call_tool` (everything before `on_progress = tool_progress.current()`):

```python
def _qualified(name: str) -> str:
    """`name` as the registry lists it. A model that drops the "main__" prefix (tool descriptions and
    instructions name tools bare) still reaches the built-in tool it meant. An exact registry name, such as a
    connection's `bard__tool_bard_speak`, always wins over that guess."""
    if name.startswith((_PREFIX, private_turn.TOOL_PREFIX)):
        return name
    listed = {tool.name for tool in client.list_tools()}
    if name in listed:
        return name
    return _PREFIX + name if _PREFIX + name in listed else name


def call_tool(name: str, arguments: dict[str, Any]) -> str:
    name = _qualified(name)
    private = name.startswith(private_turn.TOOL_PREFIX)
    short = name if private else unprefixed(name)
    if tool_filter.is_blocked(short):
        raise PermissionError(f"tool {name!r} is switched off for this user")
    if private:
        return _call_private(name, arguments)
    scope = agent_spec.current().tools
    if not (scope.allows_explicitly(short) if _other_server(name) else scope.allows(short)):
        # The model only sees in-scope tools, but may still name another one.
        raise PermissionError(f"tool {name!r} is not available to this agent")
```

(The old second `is_blocked` check after the scope check is the same test as the first; it goes.)

- [x] **Step 4: Run to verify pass, then the Legion suite.** `uv run pytest tests/test_mcp_upstream_servers.py -q -p no:cacheprovider` then `uv run pytest -q -p no:cacheprovider -m "not slow"`. Expected: PASS; baseline after Plan 18: 1,451 passed, 6 deselected.

- [x] **Step 5: Commit** `feat(legion): call tools of other MCP connections under the agent's scope`.

### Task 3: Roster check and glob warnings

**Files:**
- Modify: `apps/legion/src/agents/agent_routing.py` (`_live_tool_names`, line ~48), `apps/legion/src/tools/mcp_client/mcp_upstream.py` (`warn_unmatched_tool_globs`)
- Test: `apps/legion/tests/test_mcp_upstream_servers.py`

**Interfaces:**
- Produces: `_live_tool_names()` returns the unprefixed names of every connection's tools (so a specialist whose `tools.allow` is `bard__*` is "usable" when `bard` is connected); `warn_unmatched_tool_globs()` warns once per glob that matches no tool of any connection.

- [x] **Step 1: Write the failing tests** (append)

```python
def test_the_roster_check_sees_every_connections_tools(upstream):
    names = agent_routing._live_tool_names()
    assert "tool_ticket_create" in names and "bard__tool_bard_speak" in names and "lens__tool_ocr" in names


def test_a_glob_that_matches_no_tool_of_any_connection_is_warned_about(upstream, caplog):
    with patch.object(mcp_upstream.agent_spec, "current", return_value=agent(allow=("bard__*", "nope__*"))):
        with caplog.at_level(logging.WARNING):
            mcp_upstream.warn_unmatched_tool_globs()
    assert "nope__*" in caplog.text and "bard__*" not in caplog.text
```

- [x] **Step 2: Run to verify failure.** Expected: FAIL (`bard__tool_bard_speak` missing; `bard__*` warned about).

- [x] **Step 3: Implement.** In `agent_routing._live_tool_names` replace the list comprehension with `[mcp_upstream.unprefixed(t.name) for t in mcp_upstream.client.list_tools()]` and update its docstring to "Unprefixed names of the tools every connection offers right now". In `warn_unmatched_tool_globs` replace the `names = ...` line with `names = [unprefixed(t.name) for t in client.list_tools()]` and update its docstring ("matches no tool of any connection").

- [x] **Step 4: Run to verify pass, then the Legion suite.** Expected: PASS, no new failures.

- [x] **Step 5: Commit** `fix(legion): roster and glob checks see every MCP connection`.

### Task 4: Docs and verification

- [x] **Step 1:** In `apps/legion/README.md` (section "Outside MCP connections", added by Plan 18) add: the agent-facing name `<server-id>__<tool>`, the explicit-allow rule (empty `allow` does not expose a connection), not gated by `enabled_extensions`, ask-before-use when approvals are on, and that a connection replaces Armory's proxied extension of the same id. In `apps/legion/agents/README.md` add the same rule where `tools.allow` is described. In the scope spec, under "Tool placement", add one sentence: "Legion offers a connection's tools to an agent only through an explicit `tools.allow` glob `<server-id>__*`." If `.agents/skills/aiagent-scaffold/SKILL.md` describes `tools.allow`, add the same sentence there.
- [x] **Step 2:** Run the Legion suite once more (`uv run pytest -q -p no:cacheprovider -m "not slow"`).
- [x] **Step 3:** Add a "Verification" section to this plan with the command and counts, and any "Changes found during work".
- [x] **Step 4: Commit** `docs: how agents get tools from Legion's MCP connections`.

## Self-review notes
- **Spec coverage:** Legion owns outside MCP connections and agents scope their tools (Tasks 1 to 3); a new connection does not leak into unscoped agents (explicit-allow rule, tests in Tasks 1 and 2); approvals stay fail-closed for connection tools (not read-only builtins, unchanged `_remember_read_only`).
- **Assumptions to check at build time:** `tool_filter.is_blocked` returns False outside a turn context (the tests rely on it); `types.Tool` accepts `name`, `description`, `inputSchema` as in `test_private_upstream.py`; the shared-extensions agent keeps working (its `bard__*` glob now matches the Legion connection when one exists, else Armory's proxied tool as before).
- **Not in this plan:** a trusted "read-only" annotation for Stronghold's own MCP server (Plan 20a decides), `ServiceAuth` for a Citadel-service connection other than `main` (Plan 20a), live apply, and the `memory_recall`/`skill_recall` tool names (they stay `main__tool_mem_search` until Plan 20c).
- **Names match across tasks:** `allows_explicitly`, `_other_server`, `_qualified`, `list_tools`, `call_tool`, `_live_tool_names`, `warn_unmatched_tool_globs`.

## Changes found during work

- `apps/legion/AGENTS.md` is absent. Applied Citadel’s root instructions.
- Task 1 enables the Armory Bard extension in the collision test so both tools would otherwise qualify. The test using the tracked Shared Extensions agent also checks the fallback with no Legion Bard tools. Registry names reserved for private tools are excluded from shared listing and shadow detection.
- The provider tool schemas already use `tool.name` verbatim. `unprefixed()` is the scope and filtering name, so the existing provider-facing `main__` spelling stays intact.

- Task 2 classifies only namespaced tools as shared connections. The first full run exposed the old contract for unknown bare names: let the registry report them. The classifier preserves that path.
- Task 2 keeps Citadel requester metadata on the Armory path. The origin registry already drops it for origin entries, but legacy HTTP or stdio dispatch did not. Tests cover both metadata routing and approval despite an outside read-only hint.

- Task 3 uses Lens in the warning test because Armory’s Bard proxy would match the Bard glob on its own. Duplicate unmatched globs produce one warning even when listed in both allow and deny.
- Task 4 includes the scope spec and repository scaffold skill as the plan explicitly requests.

## Verification

- Task 1 red: 5 failed, 4 passed for missing explicit scope and connection listing. Listing plus the five existing regression files: 98 passed.
- Task 2 red: 3 failed, 3 passed, 9 deselected. Focused regression run: 116 passed. Full non-slow suite: 1,466 passed, 6 deselected, 2 baseline warnings (+15 passed).
- Task 3 red: 2 failed, 15 deselected. Focused roster and scope run: 21 passed. Full non-slow suite: 1,468 passed, 6 deselected, 2 baseline warnings (+17 passed).
- Task 4: `uv run pytest -q -p no:cacheprovider -m "not slow"` returned 1,468 passed, 6 deselected, and the same 2 baseline warnings (+17 passed).

### Assumption checks

- `tool_filter.is_blocked("bard__tool_bard_speak")` returned `False` outside a turn.
- MCP `types.Tool` accepted `name`, `description`, and `inputSchema` in the new fixture and existing private upstream tests.
- The tracked Shared Extensions agent matched Legion Bard in a fixture catalog and Armory Bard after removing Legion Bard from that catalog.

A real agent turn calling a live outside MCP connection and Shared Extensions against live Bard remain unverified.

### Final review

- The reviewer found no outside authorization defect. Task 2 preserves its specified legacy dispatch path for explicitly qualified Armory proxy names and fallback names. Task 1’s shadowing applies to the offered catalog. A stale explicit Armory call can therefore still reach the proxy if the existing scope and user checks allow it.
- Deferred minor: Task 3 checks raw registry names. A proxy-only tool shadowed in the offered catalog can still satisfy a roster or startup glob check. Changing those checks to use the offered catalog would change the plan’s Task 3 behavior.
