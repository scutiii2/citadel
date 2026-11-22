# Plan 26: Remove what Plan 22b left behind (vault agent, brain-destination plumbing, dead paths) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Run the four tasks straight through in the current checkout and report once at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Nothing in the code still refers to the Obsidian vault, the second brain or the brain destination that Plan 22b removed: Legion's `vault-librarian` agent, the `brain_scope` / `X-Brain-Destination` plumbing in Legion, Armory and Portcullis, the second-brain fields in `ember_cli`, and the Stronghold-to-Armory auth paths that no Armory route serves.

**Architecture:** A removal plan with no new behaviour. Each task deletes one group of leftovers and adds one small test that pins the removal. Callers go before callees. No data, schema or public route changes.

**Tech Stack:** Python 3.11+ (Legion, Armory, Portcullis, `ember_cli`, `libs/citadel_auth`), Vue 3 + TypeScript (Armory Admin test text only), `uv`, `pnpm`, pytest, vitest.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md) ("Obsidian is removed for now"). Follows [Plan 22b](2026-11-22-plan-22b-remove-obsidian-chain.md); its "Follow-ups" list is the input. Roadmap row 26.

## Global Constraints

- Remove only what a task names. If a `git grep` shows a live caller the plan did not name, keep that code and list it under "Findings" in the report.
- No new feature, route, setting, dependency or screen. No data deleted.
- Keep: the whole Brain, the extension proxy, `services/connections.py`, the Armory Admin Connections page, `.obsidian` in Armory's `confined_paths.py` deny list (it protects any folder that holds one), `ember_web` (reference only, never edited), and old plan and spec files.
- `libs/citadel_auth` is edited only in `libs/citadel_auth/`, then `python scripts/sync_citadel_auth.py`, then `python scripts/sync_citadel_auth.py --check` must exit 0. Never edit a copied `apps/*/src/citadel_auth/`.
- Never read, print or write `.env*`, `secrets/` or key files. The `.env.example` change in Task 4 is for the user.
- No reduced-motion code anywhere (repo rule). Use `uv` and `pnpm`. Keep each file's line endings; edit with editor tools.
- Work in the current checkout and branch. Do not create a branch, worktree or commit unless the user asks. Do not push.
- Test budget: each task runs only the files it names, once, with the command it gives. No full suites, no Docker. Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` from the app folder (if it fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). A run over about 2 minutes: stop and say so.

## What the checks found (2026-11-22, on `main` `4cf3ad79`)

| Leftover | Where | Why it is dead |
|---|---|---|
| `vault-librarian` agent | `apps/legion/agents/vault-librarian.json` (port 29609); `apps/legion/docs/spec_model_tiers.md` line 184 | Allows `tool_vault_*`; Armory's `vault` capability is gone (22b), so the agent has no tools and a wrong persona |
| `brain_scope` on the requester | Legion `src/runtime/internal_auth.py` (field, `requester_meta`, `outbound_headers`, `mcp_requester`); Armory `src/services/identity_context.py` `_from_request_meta` (no caller); Portcullis `src/services/caller.py` field (no reader); Legion `tests/test_brain_identity.py` | Only the Obsidian auto-save set it; Stronghold's `Caller.brain_scope` and header went in 22b |
| Second-brain fields | `apps/ember_cli/src/api.py` lines ~64 to 96, ~194 to 209; `apps/ember_cli/tests/test_brain_destinations.py` | Portcullis no longer returns or accepts them (chat PATCH refuses them with 422) |
| Dead auth paths | `libs/citadel_auth/citadel_auth/policy.py` line 21: Stronghold may call Armory at `/skills`, `/memory`, `/tickets`, `/ticket-admin` | Armory serves none of those routes since Plans 21 and 22 |
| Test text | `apps/armory_admin/src/views/CapabilitiesAdminView.test.ts` names a `vault` capability | Cosmetic; the capability does not exist |

---

### Task 1: Remove Legion's vault-librarian agent

**Files:**
- Delete: `apps/legion/agents/vault-librarian.json`
- Modify: `apps/legion/docs/spec_model_tiers.md` (line 184), `apps/legion/agents/README.md` if it lists the agent
- Test: `apps/legion/tests/test_agent_tools_exist.py` (create)

**Interfaces:**
- Consumes: the agent JSON files in `apps/legion/agents/` (key `tools.allow`, a list of names or `prefix*` globs).
- Produces: a test that fails when any agent allows a tool prefix for a capability that no longer exists.

- [ ] **Step 1: Find every user.** `git grep -n -i -E "vault-librarian|vault_librarian|Vault Librarian|29609" -- . ':!docs/superpowers' ':!*/node_modules/*' ':!apps/ember_web'`. Expect only the JSON file and the spec table. If a test, roster fixture or compose file names the agent or port 29609, update that file in this task.

- [ ] **Step 2: Write the failing test**

```python
# apps/legion/tests/test_agent_tools_exist.py
"""No agent file may allow tools of a capability that Armory or Stronghold no longer serves."""

import json
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1] / "agents"
GONE = ("tool_vault_", "tool_obsidian_", "tool_mem_", "tool_notes_", "tool_skill_", "tool_ticket_", "tool_usage_")


def allowed(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8")).get("tools", {}).get("allow", [])


@pytest.mark.parametrize("path", sorted(AGENTS.glob("*.json")), ids=lambda p: p.stem)
def test_no_agent_allows_a_removed_armory_tool(path):
    # Stronghold's own tools carry the "stronghold__" prefix and are fine; a bare tool_<x>_ prefix is an Armory tool.
    bad = [name for name in allowed(path) if name.startswith(GONE)]
    assert bad == []


def test_the_vault_librarian_is_gone():
    assert not (AGENTS / "vault-librarian.json").exists()
```

- [ ] **Step 3: Run it; see `vault-librarian` fail.** `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_agent_tools_exist.py` from `apps/legion`. If another agent also fails (an allow entry for a removed Armory tool), remove only that entry from its file and list it under "Findings".

- [ ] **Step 4: Delete the agent and fix the docs.** Delete the JSON file. In `spec_model_tiers.md` remove `vault-librarian, ` from the table row. In `agents/README.md`, remove a line that names the agent, if any.

- [ ] **Step 5: Run the new test and the agent-roster tests.** `git grep -l -E "agents/|AGENT_FILE|roster" -- tests` names them; run `tests/test_agent_tools_exist.py` and the one or two roster or config-loading test files that fail or mention the agent count. Expected: pass.

---

### Task 2: Remove the `brain_scope` / `X-Brain-Destination` plumbing

**Files:**
- Modify: `apps/legion/src/runtime/internal_auth.py`, `apps/armory/src/services/identity_context.py`, `apps/portcullis/src/services/caller.py`
- Modify (test): `apps/legion/tests/test_brain_identity.py` (rewrite), any test that builds `Requester(...)` with a fourth positional argument

**Interfaces:**
- Consumes: Legion's `Requester` dataclass (`internal_auth.py` line ~33), built in `mcp_requester` as `Requester(who.username, who.email, who.uid, scope, token)`.
- Produces: `Requester` without `brain_scope`; `requester_meta()` returns only `requester_token` and `chat_id`; `outbound_headers()` returns only `X-Citadel-Requester`; no `X-Brain-Destination` header or `brain_scope` meta is read or written anywhere.

- [ ] **Step 1: List every constructor and reader.** `git grep -n -E "Requester\(|brain_scope|X-Brain-Destination|_from_request_meta" -- apps ':!apps/ember_web' ':!*/node_modules/*' ':!apps/*/src/citadel_auth'`. The dataclass is positional: removing the field moves `requester_token`. Every `Requester(...)` call must be checked, and calls that pass the token positionally must switch to `requester_token=`.

- [ ] **Step 2: Write the failing test** (replace the body of `apps/legion/tests/test_brain_identity.py`; keep its imports for `internal_auth` and the signed-token helper that file already uses)

```python
def test_a_requester_carries_no_brain_destination():
    import dataclasses

    from src.runtime import internal_auth

    assert "brain_scope" not in {f.name for f in dataclasses.fields(internal_auth.Requester)}


def test_outbound_calls_never_send_a_brain_destination(signed):
    # `signed`: the signed requester token the old test built; copy how it got one from that file.
    from src.runtime import internal_auth

    requester = internal_auth.Requester(uid="alice", requester_token=signed)
    handle = internal_auth.bind_requester(requester)
    try:
        assert "brain_scope" not in (internal_auth.requester_meta() or {})
        assert "X-Brain-Destination" not in internal_auth.outbound_headers()
    finally:
        internal_auth.reset_requester(handle)
```

Use the real names the old test used for the token and for binding and resetting the requester; keep the two behaviour statements.

- [ ] **Step 3: Run it; see it fail** (`brain_scope` still a field).

- [ ] **Step 4: Remove.**
  - Legion `internal_auth.py`: delete the `brain_scope: str = ""` field; in `requester_meta` delete the `scope` lines and the `meta["brain_scope"]` write; in `outbound_headers` delete the `scope` lines and the header; in `mcp_requester` delete the `scope = extras.get("brain_scope") or ...` line and build `Requester(who.username, who.email, who.uid, requester_token=token)`.
  - Armory `identity_context.py`: delete `_from_request_meta` (no caller). Keep everything else in the file.
  - Portcullis `caller.py`: delete the `brain_scope` field; fix any constructor that passes it.

- [ ] **Step 5: Run the touched tests, once.** Legion: `tests/test_brain_identity.py` and the tests that mention `Requester(` (the grep from step 1 lists them). Armory: the identity tests (`git grep -l identity_context -- apps/armory/tests`). Portcullis: `git grep -l "services.caller\|Caller(" -- apps/portcullis/tests`. Expected: pass.

---

### Task 3: Remove the second-brain fields from `ember_cli`

**Files:**
- Modify: `apps/ember_cli/src/api.py` (summary fields at lines ~64 to 65 and ~95 to 96; `start_turn` parameters and body at ~194 to 209)
- Replace: `apps/ember_cli/tests/test_brain_destinations.py` with `apps/ember_cli/tests/test_second_brain_removed.py`

**Interfaces:**
- Consumes: Portcullis' chat summaries (no `save_to_second_brain`, no `second_brain_scope`) and its turn body (those keys are refused).
- Produces: `ChatSummary` without the two fields; `start_turn(...)` without the two parameters; a turn body that never carries them.

- [ ] **Step 1: Find every use.** `git grep -n -E "second_brain|save_to_second" -- apps/ember_cli`. Check the CLI's screens or commands for a flag or menu item that sets them (`git grep -n -i "second.brain\|brain destination" -- apps/ember_cli/src`); remove any.

- [ ] **Step 2: Write the failing test**

```python
# apps/ember_cli/tests/test_second_brain_removed.py
import dataclasses
import inspect

from src import api


def test_the_summary_has_no_second_brain_fields():
    names = {f.name for f in dataclasses.fields(api.ChatSummary)}
    assert not {"save_to_second_brain", "second_brain_scope"} & names


def test_start_turn_takes_no_second_brain_parameters():
    params = set(inspect.signature(api.PortcullisClient.start_turn).parameters)
    assert not {"save_to_second_brain", "second_brain_scope"} & params
```

Use the real class names (`ChatSummary`, the client class, and the `_summary` helper the old test used); `git grep -n "^class \|^    async def start_turn" -- apps/ember_cli/src/api.py` shows them. If the summary is not a dataclass, assert on the attribute names of an instance built by `_summary({})`.

- [ ] **Step 3: Run it; see it fail.** `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_second_brain_removed.py` from `apps/ember_cli`.

- [ ] **Step 4: Remove the fields, parameters, body keys and the validation of the scope value. Delete `tests/test_brain_destinations.py`.**

- [ ] **Step 5: Run the CLI's API tests.** `tests/test_second_brain_removed.py` plus the test files that call `start_turn` or build a summary (`git grep -l "start_turn\|_summary" -- tests`). Expected: pass.

---

### Task 4: Dead auth paths, test text, final check

**Files:**
- Modify: `libs/citadel_auth/citadel_auth/policy.py` (line 21) and `libs/citadel_auth/tests/test_auth.py`; run the sync script
- Modify: `apps/armory_admin/src/views/CapabilitiesAdminView.test.ts`

**Interfaces:**
- Consumes: `POLICY["armory"]["stronghold"]` (what Armory accepts from Stronghold): `("/mcp", "/skills", "/memory", "/tickets", "/ticket-admin", "/upload", "/connections")`.
- Produces: only the paths Armory still serves for Stronghold.

- [ ] **Step 1: Prove each path dead before removing it.** For each of `/skills`, `/memory`, `/tickets`, `/ticket-admin`, `/connections`: `git grep -n -E "\"/<path>|'/<path>|/<path>/" -- apps/armory/src apps/stronghold/src` and confirm (a) no Armory route serves it and (b) no Stronghold call targets Armory with it. Remove from the policy only those that pass both checks. Keep `/mcp` and `/upload`. If `/connections` is still served by Armory's `connection_admin.py` and called by Stronghold's tool-services code, keep it and list it under "Findings".

- [ ] **Step 2: Write the failing test** (append to `libs/citadel_auth/tests/test_auth.py`, using its existing `allowed` import)

```python
@pytest.mark.parametrize("path", ["/skills/x", "/memory/x", "/tickets/x", "/ticket-admin/x"])
def test_stronghold_may_not_call_armory_for_routes_armory_no_longer_has(path):
    assert not allowed("armory", "stronghold", path)


def test_stronghold_may_still_call_armory_for_mcp_and_uploads():
    assert allowed("armory", "stronghold", "/upload/pdf") and allowed("armory", "stronghold", "/mcp")
```

Drop from the first list any path that step 1 kept.

- [ ] **Step 3: Run it; see it fail.** From `libs/citadel_auth`: `python -m pytest -q -p no:cacheprovider tests/test_auth.py` using an interpreter that has the library's test dependencies (the Armory `.venv` python works).

- [ ] **Step 4: Edit `policy.py`, run `python scripts/sync_citadel_auth.py`, then `python scripts/sync_citadel_auth.py --check` (must exit 0).** Run the new tests and any existing policy test that lists those paths (`git grep -n "/ticket-admin\|/skills" -- libs/citadel_auth/tests apps/*/tests`); fix an old test only if it asserted the removed path was allowed.

- [ ] **Step 5: Rename the cosmetic test fixture.** In `CapabilitiesAdminView.test.ts` replace the fake capability `vault` (name, label, `tool_vault_search`, `/vault`, "Search and manage notes in your vault.", `data-name=vault`) with an existing one, `pdf_merger` ("PDF merger", `tool_pdf_inspect`, `/pdf`, "Merge and inspect PDF files."), keeping every assertion's meaning. Run `pnpm exec vitest run src/views/CapabilitiesAdminView.test.ts` from `apps/armory_admin`.

- [ ] **Step 6: Final sweep and report.** `git grep -n -i -E "vault-librarian|tool_vault_|tool_obsidian_|brain_scope|X-Brain-Destination|second_brain|save_to_second" -- apps libs docs scripts ':!docs/superpowers' ':!*/node_modules/*' ':!*/.venv/*' ':!apps/ember_web' ':!apps/portcullis/migrations' ':!apps/portcullis/tests/test_migrations.py' ':!apps/portcullis/tests/test_chats.py'`. Expect no hits. List each remaining hit with its reason (the two Portcullis tests and the migrations pin the removal; `ember_web` is reference only; the two Armory `.excalidraw` and `.html` diagrams under `docs/` are drawings that were not redrawn). Run `git diff --check`.

## Self-review

- **Spec coverage:** Plan 22b's follow-up list is fully covered: vault agent (Task 1), `X-Brain-Destination` handling (Task 2), `ember_cli` fields (Task 3). Dead auth paths and the cosmetic test text are extra items found during the checks (Task 4). The `.env.example` lines are a user step.
- **Order check:** Legion stops sending the header (Task 2) before anything is said about the paths in Task 4; Portcullis' `Caller.brain_scope` has no reader, so its removal cannot break a caller.
- **Placeholders:** the helper names marked "use the real names" (token fixture, client class) are in files this plan did not read; each says where to find them.
- **Risk:** the `Requester` dataclass is positional; Task 2 step 1 lists every constructor so none keeps the old argument order.

## User steps (the executor must not open these files)

1. In `apps/armory/.env.example`, line 6 mentions `OBSIDIAN_*` and `MCP_VAULT_DIR`: change the comment to name only `MCP_WORKSPACE_DIR`. In any local `.env`, delete `OBSIDIAN_*` and `MCP_VAULT_DIR` lines.

## Open questions for the user

1. Should the two Armory diagrams (`docs/armory-architecture.excalidraw`, `docs/armory-catalog.html`) be redrawn, or deleted as out of date? This plan leaves them.
2. Plan 22c (the extension proxy) is still unwritten. It needs a decision on where Ember lists extensions; write it after this plan.
