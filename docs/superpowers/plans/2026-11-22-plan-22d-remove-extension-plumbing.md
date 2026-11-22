# Plan 22d: Remove the inert extension plumbing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Run the two tasks straight through in the current checkout and report once at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Nothing passes a list of "enabled extensions" any more. Plan 22c removed the shared extension proxy, so `extension_ids` (Portcullis to Stronghold) and `enabled_extensions` (Stronghold, `ember_cli`, Portcullis to Legion, and inside Legion) are always an empty list that nothing reads.

**Architecture:** A removal plan with no new behaviour. Callers stop sending the value first (Task 1), then Legion drops the parameter and its dead gate (Task 2). Private extensions (`private_extensions`, `/user-extensions`) are a different feature and stay untouched. No data, schema, route or permission changes.

**Tech Stack:** Python 3.11+ (Legion, Stronghold, Portcullis, `ember_cli`), Vue 3 + TypeScript (Ember), `uv`, `pnpm`, pytest, vitest.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md). Follows [Plan 22c](2026-11-22-plan-22c-remove-extension-proxy.md) (its open question 3). Roadmap row 22d.

## Global Constraints

- Remove only what a task names. If a `git grep` shows a live reader of `enabled_extensions` or `extension_ids` that the plan did not name, keep that code and list it under "Findings" in the report.
- Keep: `private_extensions` everywhere, Stronghold's `/extensions` routes for private extensions, the permissions `extensions.manage` and `extensions.personal.manage`, the Armory `settings.db` tables, `apps/ember_web` (reference only, never edited), old plan and spec files.
- No new feature, route, setting, dependency or screen. No data deleted. No migration.
- `enabled_extensions` is a positional argument in several Legion functions and in many test fakes. Remove it from every signature, every call and every fake in the same step, then check each call by reading it, because a missed positional argument shifts the ones after it.
- Never read, print or write `.env*`, `secrets/` or key files. No reduced-motion code (repo rule). Use `uv` and `pnpm`. Keep each file's line endings; edit with editor tools.
- Work in the current checkout and branch. Do not create a branch, worktree or commit unless the user asks. Do not push.
- Test budget: each task runs only the files it names, once, with the command it gives. No full suites, no Docker. Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` from the app folder (if it fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). Ember: `pnpm exec vitest run <files>` from `apps/ember`. A run over about 2 minutes: stop and say so.

## What the checks found (2026-11-22, on `main` `682f5ac6`)

| Name | Where (non-test) | State |
|---|---|---|
| `extension_ids` | Portcullis `src/routes/chats.py` (~540, ~546: turn body, always `[]`); Stronghold `src/turns/routes.py` (~76 field, ~261 `enabled_extensions=tuple(trusted.extension_ids)`) | Always empty |
| `enabled_extensions` (Stronghold) | `src/turns/engine.py` (`TurnOptions` ~98, ~609, ~779); `src/agents/gateway.py` (~60, ~140, ~159); `src/triage/questions.py` (~202) | Always empty, forwarded to Legion |
| `enabled_extensions` (callers of Legion) | Portcullis `src/services/legion_ask.py` (~50); `apps/ember_cli/src/api.py` (~192) | Literal `[]` |
| `enabledExtensions` | Ember `src/features/chat/services/slashCommands.ts` (~182 to 224: `list`, `forTurn`); `chat.capabilities.test.ts` | Default `[]`, no caller passes a value since 22c |
| `enabled_extensions` (Legion) | `src/server.py` `ask` (~166, ~257); `src/agents/agent_config.py` (~118, ~202 to 292); `src/agents/roles/orchestrator/delegation.py` (~95 to 104, ~284); `src/providers/decision/provider.py` (~144); `src/providers/language/anthropic_provider.py` and `openai_provider.py` (`_tool_schemas`, `run_chat`); `src/tools/mcp_client/mcp_upstream.py` (`list_tools`, `_tool_is_enabled`) | Threaded through, read in one place |
| The one reader | `mcp_upstream.list_tools` + `_tool_is_enabled`: a `main__{ext}__{tool}` name needs `ext` in the enabled set | Armory serves no proxied tools any more, so no such name exists and the gate never fires |
| Docs | `apps/legion/README.md` ~573, `apps/legion/agents/README.md` ~38 ("applies `enabled_extensions` only to Armory's proxied extensions"), `apps/portcullis/README.md` ~652, `apps/stronghold/README.md` (turn body) | Stale |

---

### Task 1: Callers stop sending the empty list

**Files:**
- Modify: `apps/portcullis/src/routes/chats.py`, `apps/portcullis/src/services/legion_ask.py`, `apps/portcullis/README.md`
- Modify: `apps/stronghold/src/turns/routes.py`, `apps/stronghold/src/turns/engine.py`, `apps/stronghold/src/agents/gateway.py`, `apps/stronghold/src/triage/questions.py`, `apps/stronghold/README.md`
- Modify: `apps/ember_cli/src/api.py`
- Modify: `apps/ember/src/features/chat/services/slashCommands.ts`
- Tests to update: `apps/portcullis/tests/test_turn_passthrough.py`, `test_legion_ask.py`, `test_outside_stronghold.py`; `apps/stronghold/tests/test_agent_gateway.py`, `test_turns.py`, `test_turn_extras.py`, `test_triage.py`, `turn_agent.py` (helper); `apps/ember_cli/tests/test_api.py`; `apps/ember/src/features/chat/stores/chat.capabilities.test.ts` and the slash command test that passes the argument, if any
- Test (new): one assertion each in `test_turn_passthrough.py` and `test_legion_ask.py` that the sent body has no extension key

Legion still accepts the argument after this task (Task 2 removes it), so the order is safe on a live stack: callers first.

- [ ] **Step 1: Write the failing assertions**

In `apps/portcullis/tests/test_turn_passthrough.py`, where the body sent to Stronghold is captured, replace the existing check that `extension_ids == []` with:

```python
assert "extension_ids" not in sent_body
```

(Use the real variable name in that test.) In `apps/portcullis/tests/test_legion_ask.py`, in `test_the_call_is_stateless_and_carries_the_clients_identity`, replace `arguments["enabled_extensions"] == []` with `"enabled_extensions" not in arguments`.

- [ ] **Step 2: Run them and see them fail**

From `apps/portcullis`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_turn_passthrough.py tests/test_legion_ask.py`. Expect failures that the key is still present.

- [ ] **Step 3: Portcullis**

In `routes/chats.py` delete the `extension_ids: list[str] = []` local and its entry in the body sent to Stronghold. In `services/legion_ask.py` delete `"enabled_extensions": []` from the `ask` arguments. Fix the README line about `extension_ids` ("always empty since Plan 22c"): say the turn body carries no extension list.

- [ ] **Step 4: Stronghold**

Read `src/turns/routes.py`: check the request model's `model_config` for `extra="forbid"`. Delete the `extension_ids` field and the `enabled_extensions=tuple(trusted.extension_ids)` argument. Delete `enabled_extensions` from `TurnOptions` in `engine.py` and from the two places that read it (~609 call into the gateway, ~779 saved options). In `agents/gateway.py` delete the parameter, its pass-through to the inner call and the `"enabled_extensions"` key sent to Legion. In `triage/questions.py` delete `enabled_extensions=[]` from the call. Update the Stronghold README turn description. Update the five test files and `turn_agent.py` so no fake or call mentions it; read each changed call to confirm no positional argument shifted.

- [ ] **Step 5: ember_cli and Ember**

In `apps/ember_cli/src/api.py` delete `"enabled_extensions": []` from the body and update `tests/test_api.py`. In Ember `slashCommands.ts` delete the `enabledExtensions` parameter of `list` and `forTurn`, the early return `if (!enabledExtensions.length) return builtIns`, and the `enabled` set built from it (read the body: keep what `builtIns` and `enabledCapabilities` still do). Update every caller and test in `apps/ember/src` found by `git grep -n "enabledExtensions" apps/ember/src`.

- [ ] **Step 6: Run the tests**

```
cd apps/portcullis; uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_turn_passthrough.py tests/test_legion_ask.py tests/test_outside_stronghold.py
cd apps/stronghold; uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_agent_gateway.py tests/test_turns.py tests/test_turn_extras.py tests/test_triage.py
cd apps/ember_cli; uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_api.py
cd apps/ember; pnpm exec vitest run src/features/chat/stores/chat.capabilities.test.ts src/features/chat/services
cd apps/ember; pnpm exec vue-tsc -b
```

Expected: all pass. If `vue-tsc -b` takes over 2 minutes, stop it and say so.

---

### Task 2: Legion drops the parameter and its dead gate

**Files:**
- Modify: `apps/legion/src/server.py`, `src/agents/agent_config.py`, `src/agents/roles/orchestrator/delegation.py`, `src/providers/decision/provider.py`, `src/providers/language/anthropic_provider.py`, `src/providers/language/openai_provider.py`, `src/tools/mcp_client/mcp_upstream.py`, `README.md`, `agents/README.md`
- Tests to update: `apps/legion/tests/test_agent_config.py`, `test_delegation.py`, `test_server.py`, `test_tool_filter.py`, `test_private_server.py`, `test_anthropic_provider_prompt_cache.py`, `test_anthropic_provider_streaming.py`, `test_approvals.py`, `test_auto_tier.py`, `test_effort.py`, `test_questions.py`
- Test (new): in `apps/legion/tests/test_server.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_ask_tool_has_no_enabled_extensions_argument():
    import asyncio
    from src import server

    tools = asyncio.run(server.mcp.list_tools())
    ask = next(tool for tool in tools if tool.name == "ask")
    assert "enabled_extensions" not in ask.inputSchema["properties"]
    assert "private_extensions" in ask.inputSchema["properties"]
```

Adjust the import to match how `test_server.py` already reaches the server module.

- [ ] **Step 2: Run it and see it fail**

From `apps/legion`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_server.py -k enabled_extensions`. Expect: the property is still in the schema.

- [ ] **Step 3: Remove the parameter, caller first**

Work from the entry point inward so each call stays consistent:

1. `server.py`: delete the `enabled_extensions` parameter of `ask` and the `enabled_extensions or []` argument of the call (~257).
2. `agent_config.py`: delete the parameter of `run` (~118), the `delegation.bind_enabled_extensions(...)` call and its token (~202), both `enabled_extensions` arguments in the provider calls (~258, ~270) and `delegation.reset_enabled_extensions(...)` (~292).
3. `delegation.py`: delete the `_enabled_extensions` ContextVar, `bind_enabled_extensions`, `reset_enabled_extensions` and the `"enabled_extensions"` key in the sub-agent `ask` arguments (~284).
4. `providers/decision/provider.py`, `anthropic_provider.py`, `openai_provider.py`: delete the parameter from `run_chat` and `_tool_schemas`, and call `list_tools()` with no argument.
5. `mcp_upstream.py`: change `list_tools` to take no argument and delete `enabled`, `_tool_is_enabled` and the `connected` skip ("a Legion connection of this id replaces Armory's proxied extension"). Keep the other-connection branch (explicit `tools.allow`), the `_PREFIX` check, `scope.allows` and `tool_filter.is_blocked`. Update the module docstring line 4 and the `list_tools` docstring.
6. Docs: delete or rewrite the sentence "Legion applies `enabled_extensions` only to Armory's proxied extensions" in `README.md` (~573) and `agents/README.md` (~38).

Update every test fake of `run_chat` and `_fake_run_chat` in the eleven test files: drop the `enabled_extensions` parameter and, where a test asserts the captured argument tuple (for example `captured_args["args"]` in `test_agent_config.py`), drop that item and fix the expected tuple. Read each changed call to confirm no positional argument shifted.

- [ ] **Step 4: Run the tests**

From `apps/legion`:

```
uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_server.py tests/test_agent_config.py tests/test_delegation.py tests/test_tool_filter.py tests/test_private_server.py tests/test_approvals.py tests/test_auto_tier.py tests/test_effort.py tests/test_questions.py tests/test_anthropic_provider_prompt_cache.py tests/test_anthropic_provider_streaming.py
```

Expected: all pass. If the run takes over 2 minutes, stop it and say so.

- [ ] **Step 5: Final grep**

`git grep -nE "enabled_extensions|extension_ids|enabledExtensions" -- apps ':!apps/ember_web' ':!*.md'` returns only: tests that assert the removal, and nothing in `src`. List any remaining hit in the report with its reason.

---

## Out of scope (separate decisions)

- Dropping the permissions `extensions.manage` and `extensions.personal.manage` (needs a Portcullis migration).
- A prune script for the unused `extensions` and `connections` tables in Armory's `settings.db`.
- `apps/ember_web`, which is reference only.

## Report

Report once: per task what changed (files), the test commands run with pass counts, the commands not run, "Findings" (live readers kept), the final grep result, and the vault notes that need an update (Portcullis, Stronghold, Legion/garrison, Ember, `ember_cli`).
