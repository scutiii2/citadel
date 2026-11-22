# Plan 24b: Outside clients at the Stronghold level (an agent with its own memory) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An outside client whose record allows the service `stronghold` can call `POST /api/outside/stronghold/ask` and get an answer from Legion's entry agent that remembers: it can search, read, list, write and update notes in its own Brain folder, and nothing else. The client never sees another account's data, the global brain, tickets, usage, skills, short-term memory or sharing.

**Architecture:** Plan 24 built the door (client records, key, IP lists, rate limit, token budget, fail-closed guard) and the stateless Legion ask, which refuses every tool with `disabled_tools=["*"]`. This plan adds a second level on the same door. Legion's tool filter gets an exception form (`"!name"` allows one tool through a `"*"` block), so Portcullis can say "block everything except these five Stronghold tools". Stronghold adds its own fail-closed rule: a requester uid that starts with `oc_` may use only those five tools, only on its own folder. Two walls, so a mistake in one does not open the other.

**Tech Stack:** Python 3.11+ (Legion, Stronghold, Portcullis), FastAPI and FastMCP, SQLAlchemy and Alembic (Portcullis; no migration is needed here), pytest, `uv`.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md), section "Outside clients and access levels" (two outside levels; a client calling Stronghold gets its own memory namespace; outside clients cannot reach the model level or share brain fragments). Builds on [Plan 24](2026-11-22-plan-24-outside-clients.md) and the Brain plans 20a to 20c.

## Global Constraints

- Allowed Stronghold tools for an outside client, exact short names: `stronghold__tool_brain_search`, `stronghold__tool_brain_read`, `stronghold__tool_brain_list`, `stronghold__tool_brain_write`, `stronghold__tool_brain_update`. Everything else stays blocked: Armory tools, all other `stronghold__tool_*` (stack, propose, skill, ticket, usage), the plan tool, questions back, extensions.
- An outside client's Brain folder is its own uid (`oc_<12hex>`), created the first time it writes. Per-account quota and record limits apply to it like any account.
- **An outside client never reads the global brain.** Open question 1 asks whether that should change.
- Guards fail closed: if Stronghold cannot tell whether a uid is an outside client, it refuses the tool. If Legion cannot parse the filter, nothing runs.
- The Stronghold level uses the same key, rate limit, token budget, IP lists and audit log as the Legion level. A client record lists the services it may call; `stronghold` is a new value. A client allowed `legion` only cannot call the new route.
- No model call outside Legion. No new dependency. No database migration. No admin screen.
- Question and answer text never appears in a log or an error, as in Plan 24.
- `libs/citadel_auth` needs no change. Never read, print or write `.env*`, `secrets/` or key files.
- Use `uv`. One commit per task, each ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push.

## Baseline (record before the first edit)

Branch `plan-24b-outside-stronghold` from `main` (Plan 24 on `main`, `ba29fde1` or later; if not, stop and report). If Plan 22b or Plan 25 is open at the same time, they touch `api.py`, `app.py`, READMEs and (22b) `src/brain/access.py`; merge one, then `git rebase main` the other. This plan adds `is_outside` and a keyword to `resolve_account` in `src/mcp_tools/scope.py`; it does not touch `src/brain/access.py`.

Run once: Legion, Stronghold, Portcullis (about 13 minutes, 2 known failures: `test_secret_box.py::test_an_invalid_key_in_env_stops_startup`, `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`) with `uv run --no-sync python -u -m pytest -q -p no:cacheprovider` (in a worktree with empty `.venv` folders use the main checkout's interpreter from the app folder). Record counts under "Baseline results".

## Assumptions to check (record each result under "Changes found during work")

- **(a)** `apps/legion/src/runtime/tool_filter.py`: `is_blocked(name)` is `"*" in names or name in names`; `blocked()` returns the set; `agent_blocked` ignores a bare `"*"`. Delegation passes `sorted(tool_filter.blocked())` on to a delegate (`delegation.py` line ~290), and checks `"*" in tool_filter.blocked()` at lines ~309 to 323.
- **(b)** Legion's memory recall calls `mcp_upstream.call_tool("stronghold__tool_brain_search", ...)` (`memory_recall.py` line 21), and the filter is checked on the short name inside `call_tool` (`mcp_upstream.py` lines ~125, 136, 142, 179). So an exception for `stronghold__tool_brain_search` lets recall and the model's own search through. Skill recall (`stronghold__tool_skill_search`) and skill learning (`stronghold__tool_skill_propose`) stay blocked.
- **(c)** The Stronghold MCP tools are registered in `apps/stronghold/src/mcp_tools/server.py` (names listed there: `tool_stack_*`, `tool_brain_search/read/list/write/update/propose`, `tool_skill_*`, `tool_ticket_*`, `tool_usage_summary`). Account-wide tools use `resolve_account(app)` in `src/mcp_tools/scope.py`; chat-bound tools use `resolve_scope(app)` (needs a chat id, which an outside call never has).
- **(d)** Brain search merges own and global results in `apps/stronghold/src/brain/search.py` (or the file `tool_brain_search` calls: follow it from `mcp_tools/brain_tools.py`). Find the one place global results are added.
- **(e)** Portcullis `OutsideClients.SERVICES = ("legion",)` (`src/services/outside_clients.py` line 18) validates a client's `services` list. The guard's `admit(clients, key, service, ip)` already takes the service name.
- **(f)** `LegionAsk.ask(url, client, question, history)` in `src/services/legion_ask.py` builds the `ask` arguments, with `DISABLED_TOOLS = ["*"]`; identity is `identity_headers(f"outside:{client.uid}", "", client.uid)`.
- **(g)** Deleting an outside client is `DELETE /api/admin/outside-clients/{client_id}` in `src/routes/outside_clients_admin.py`. Stronghold has per-account purge routes `DELETE /brain/accounts/{uid}`, `/brain/proposals/accounts/{uid}`, `/stack/accounts/{uid}` (`src/brain/files_routes.py:83`, `proposal_routes.py:35`, `routes.py:59`), and `/brain/shares/accounts/{uid}` (`share_routes.py:95`). The delete-account flow calls them through `request.app.state.stronghold.forward("DELETE", f"/{domain}/accounts/{uid}", admin)` in `src/routes/admin.py` (around line 312).

## File map

| Area | Create | Modify |
|---|---|---|
| Legion | `tests/test_tool_filter_exceptions.py` | `src/runtime/tool_filter.py` |
| Stronghold | `tests/test_outside_scope.py` | `src/mcp_tools/scope.py`, `src/mcp_tools/server.py` (pass `outside_ok=True` for five tools), the search code from assumption (d), README |
| Portcullis | `tests/test_outside_stronghold.py` | `src/services/outside_clients.py` (`SERVICES`), `src/services/legion_ask.py` (`memory` option), `src/routes/outside.py` (new route), `src/routes/outside_clients_admin.py` (purge on delete), README |

---

### Task 1: Legion filter exceptions

**Files:**
- Modify: `apps/legion/src/runtime/tool_filter.py`
- Test: `apps/legion/tests/test_tool_filter_exceptions.py` (create)

**Interfaces:**
- Consumes: `bind`, `reset`, `blocked`, `is_blocked` as they are today.
- Produces: a name in the bound set that starts with `"!"` (for example `"!stronghold__tool_brain_search"`) is an exception: `is_blocked("stronghold__tool_brain_search")` is `False` even when `"*"` is in the set. An exception for a name that is not blocked changes nothing. `blocked()` still returns the whole set (exceptions included), so delegation passes them on unchanged. `agent_blocked` is untouched.

- [ ] **Step 1: Check assumption (a).** Read `delegation.py` lines ~285 to 325 and note how a delegate with `"*"` is treated; the exception names ride in the same set, so a delegate gets the same exceptions.

- [ ] **Step 2: Write the failing test**

```python
# apps/legion/tests/test_tool_filter_exceptions.py
from src.runtime import tool_filter


def test_an_exception_lets_one_tool_through_a_star_block():
    token = tool_filter.bind(["*", "!stronghold__tool_brain_search"])
    try:
        assert tool_filter.is_blocked("stronghold__tool_brain_search") is False
        assert tool_filter.is_blocked("stronghold__tool_brain_write") is True
        assert tool_filter.is_blocked("armory__tool_web_search") is True
    finally:
        tool_filter.reset(token)


def test_without_a_star_nothing_changes():
    token = tool_filter.bind(["armory__tool_web_search", "!stronghold__tool_brain_search"])
    try:
        assert tool_filter.is_blocked("armory__tool_web_search") is True
        assert tool_filter.is_blocked("stronghold__tool_brain_search") is False
        assert tool_filter.is_blocked("stronghold__tool_brain_write") is False
    finally:
        tool_filter.reset(token)


def test_an_exception_beats_an_exact_block_of_the_same_name():
    token = tool_filter.bind(["x", "!x"])
    try:
        assert tool_filter.is_blocked("x") is False
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
```

- [ ] **Step 3: Run it; see it fail.** `uv run --no-sync python -u -m pytest tests/test_tool_filter_exceptions.py -q -p no:cacheprovider` from `apps/legion`. Expected: the first, second and third tests fail on the `is False` assertions.

- [ ] **Step 4: Implement**

```python
def is_blocked(name: str) -> bool:
    names = _blocked.get()
    if "!" + name in names:  # an exception beats "*" and an exact block of the same name
        return False
    return "*" in names or name in names
```

Update the module docstring with one line: `"!name" lets one tool through a "*" block (used for outside clients that may use only some tools).`

- [ ] **Step 5: Run the Legion suite.** Record counts against the baseline. Check that `delegation.py`'s `"*" in tool_filter.blocked()` logic is unchanged and still sees `"*"`; add no code there.

- [ ] **Step 6: Commit.** `git commit -m "feat(legion): a tool filter exception lets one tool through a star block"`

---

### Task 2: Stronghold treats outside uids as a narrow, own-folder-only caller

**Files:**
- Modify: `apps/stronghold/src/mcp_tools/scope.py`, `apps/stronghold/src/mcp_tools/server.py`, the global-merge place found in assumption (d), `apps/stronghold/README.md`
- Test: `apps/stronghold/tests/test_outside_scope.py` (create)

**Interfaces:**
- Consumes: `resolve_account(app)` and `Account` from `scope.py`.
- Produces: `OUTSIDE_PREFIX = "oc_"` and `is_outside(uid: str) -> bool` (true when `uid.startswith(OUTSIDE_PREFIX)`). `resolve_account(app, outside_ok: bool = False)`: when the verified uid is outside and `outside_ok` is false, raise `ScopeError("Not available to outside clients.")`. The five Brain tools pass `outside_ok=True`; every other tool keeps the default and so refuses outside uids. `tool_brain_search`, `tool_brain_list` and `tool_brain_read` never return or read a global file for an outside uid.

- [ ] **Step 1: Check assumptions (c), (d).** List every `resolve_account(` call in `server.py` and the tools it reaches. Find the one place the global brain joins a search or list, and the check in `read` that lets a file id resolve to a global file.

- [ ] **Step 2: Write the failing tests**

```python
# apps/stronghold/tests/test_outside_scope.py
import asyncio

import pytest

from src.mcp_tools import scope


def test_is_outside_by_prefix():
    assert scope.is_outside("oc_0123456789ab") is True
    assert scope.is_outside("u-1") is False
    assert scope.is_outside("") is False


def test_an_outside_uid_is_refused_unless_the_tool_opts_in(app_with_requester):
    # app_with_requester(uid): the helper other mcp_tools tests use to give the app a keyring and a signed
    # requester; copy its real name and signature from tests/test_mcp_*.py
    app = app_with_requester("oc_0123456789ab")

    async def go(outside_ok):
        async with scope.resolve_account(app, outside_ok=outside_ok) as who:
            return who.uid

    with pytest.raises(scope.ScopeError, match="outside clients"):
        asyncio.run(go(False))
    assert asyncio.run(go(True)) == "oc_0123456789ab"


def test_a_member_is_unaffected(app_with_requester):
    app = app_with_requester("u-1")

    async def go():
        async with scope.resolve_account(app) as who:
            return who.uid

    assert asyncio.run(go()) == "u-1"
```

Add three tests against the real tool functions (find how existing tests call them, `git grep -l "tool_brain_search" -- apps/stronghold/tests`):

```python
def test_outside_search_and_list_never_return_global_files(brain_with_global_note, call_tool):
    # brain_with_global_note: a fixture that puts one global file and one file in the outside uid's folder;
    # build it from the global-brain tests (tests/test_brain_global*.py). call_tool: the existing helper.
    result = call_tool("tool_brain_search", {"query": "note"}, uid="oc_0123456789ab")
    assert all(item["scope"] != "global" for item in result["results"])


def test_outside_read_of_a_global_file_id_is_refused(brain_with_global_note, call_tool):
    global_id = brain_with_global_note.global_file_id
    result = call_tool("tool_brain_read", {"file_id": global_id}, uid="oc_0123456789ab")
    assert "not found" in str(result).lower() or "outside" in str(result).lower()


@pytest.mark.parametrize("name,args", [
    ("tool_ticket_listMyTickets", {}), ("tool_usage_summary", {}), ("tool_skill_search", {}),
    ("tool_brain_propose", {"title": "t", "body": "b"}),
])
def test_outside_uids_cannot_use_other_tools(call_tool, name, args):
    assert "outside clients" in str(call_tool(name, args, uid="oc_0123456789ab")).lower()
```

If the result keys differ (`results`, `scope`), use the real ones; keep each test's behaviour statement.

- [ ] **Step 3: Run them; see them fail** (`AttributeError: is_outside`, then the behaviour tests).

- [ ] **Step 4: Implement.** In `scope.py`:

```python
OUTSIDE_PREFIX = "oc_"


def is_outside(uid: str) -> bool:
    """True for an outside client's synthetic uid (Portcullis makes it as oc_<12 hex>)."""
    return uid.startswith(OUTSIDE_PREFIX)
```

Change `resolve_account(app)` to `resolve_account(app, outside_ok: bool = False)`; after `_verified` yields `who`, `if is_outside(who.uid) and not outside_ok: raise ScopeError("Not available to outside clients.")`. In `server.py`, pass `outside_ok=True` only in `tool_brain_search`, `tool_brain_read`, `tool_brain_list`, `tool_brain_write`, `tool_brain_update`. At the global-merge place, skip global results when `is_outside(uid)`; in read, treat a global file id as not found for an outside uid. A uid is never an outside uid by accident: Portcullis account uids are random hex without the `oc_` prefix; record in the README that `oc_` is reserved.

- [ ] **Step 5: Run the Stronghold suite.** Record counts. No existing tool test may change except to pass through the new default.

- [ ] **Step 6: Commit.** `git commit -m "feat(stronghold): outside uids may use only the five Brain tools, on their own folder"`

---

### Task 3: Portcullis route, client service value and purge on delete

**Files:**
- Modify: `apps/portcullis/src/services/outside_clients.py` (`SERVICES = ("legion", "stronghold")`), `src/services/legion_ask.py` (a `memory` option on `ask`), `src/routes/outside.py` (the new route), `src/routes/outside_clients_admin.py` (purge on delete), `apps/portcullis/README.md`
- Test: `apps/portcullis/tests/test_outside_stronghold.py` (create); extend `test_outside_clients.py` for the `services` validation

**Interfaces:**
- Consumes: Task 1 (`"!name"` exceptions) and Task 2 (Stronghold's own wall). Plan 24's guard, `OutsideClients.record`, `spent`, `LegionAsk`.
- Produces: `LegionAsk.ask(url, client, question, history, memory: bool = False)`. With `memory=False` the `disabled_tools` argument is exactly `["*"]` (the Legion level, unchanged). With `memory=True` it is `["*"] + ["!stronghold__tool_brain_search", "!stronghold__tool_brain_read", "!stronghold__tool_brain_list", "!stronghold__tool_brain_write", "!stronghold__tool_brain_update"]`. `STRONGHOLD_ALLOWED` is that tuple of five names in `legion_ask.py`. `POST /api/outside/stronghold/ask` with the same body and response as `/api/outside/legion/ask` and `SERVICE = "stronghold"` in the guard, audit events and budget. Deleting an outside client also asks Stronghold to purge its folder and short-term data.

- [ ] **Step 1: Check assumptions (e), (f), (g).** Read `outside.py` again: the legion route is one function; the new route repeats its shape with `SERVICE` and `memory` as the only differences. Do not copy the whole body by hand: refactor the shared body into one helper `_ask(request, body, service, memory)` that both routes call, keeping every refusal path and the audit writes exactly as they are, and run the existing Plan 24 route tests to prove nothing moved.

- [ ] **Step 2: Write the failing tests**

```python
# apps/portcullis/tests/test_outside_stronghold.py
# Fixtures: copy the names from tests/test_outside_routes.py and tests/test_legion_ask.py (a client with a key,
# a fake Legion that records the `ask` arguments, the app client). The names below are placeholders for them.

def test_a_legion_only_client_is_refused_the_stronghold_route(app_client, make_client):
    key = make_client(services=["legion"])
    response = app_client.post("/api/outside/stronghold/ask", json={"question": "hi"},
                               headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 403


def test_a_stronghold_client_gets_an_answer_and_only_the_five_tools(app_client, make_client, fake_legion):
    key = make_client(services=["stronghold"])
    response = app_client.post("/api/outside/stronghold/ask", json={"question": "remember my cat is Tom"},
                               headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 200
    sent = fake_legion.last_arguments
    assert sent["disabled_tools"][0] == "*"
    assert sorted(sent["disabled_tools"][1:]) == sorted([
        "!stronghold__tool_brain_search", "!stronghold__tool_brain_read", "!stronghold__tool_brain_list",
        "!stronghold__tool_brain_write", "!stronghold__tool_brain_update"])
    assert sent["approval_mode"] == "deny" and sent["enabled_extensions"] == [] and sent["plan"] is False


def test_the_legion_route_is_unchanged(app_client, make_client, fake_legion):
    key = make_client(services=["legion"])
    app_client.post("/api/outside/legion/ask", json={"question": "hi"}, headers={"Authorization": f"Bearer {key}"})
    assert fake_legion.last_arguments["disabled_tools"] == ["*"]


def test_the_stronghold_call_uses_the_same_budget_and_audit(app_client, make_client, fake_legion, events):
    key = make_client(services=["stronghold"], budget_tokens=10)
    fake_legion.next_tokens = 50
    first = app_client.post("/api/outside/stronghold/ask", json={"question": "a"}, headers={"Authorization": f"Bearer {key}"})
    assert first.status_code == 200 and first.json()["usage"]["budget_remaining"] == 0
    second = app_client.post("/api/outside/stronghold/ask", json={"question": "b"}, headers={"Authorization": f"Bearer {key}"})
    assert second.status_code == 429
    assert {e.service for e in events()} == {"stronghold"}


def test_deleting_a_client_asks_stronghold_to_purge_its_data(admin_client, make_client, fake_stronghold):
    created = make_client(services=["stronghold"], return_record=True)
    admin_client.delete(f"/api/admin/outside-clients/{created['id']}")
    purged = fake_stronghold.deleted_paths
    for domain in ("brain", "stack", "brain/proposals", "brain/shares"):
        assert f"/{domain}/accounts/{created['uid']}" in purged
```

Also in `test_outside_clients.py`: creating a client with `services=["stronghold"]` is accepted, `["other"]` is refused. Use the real status the existing validation returns (the existing test for an unknown service shows it).

- [ ] **Step 3: Run them; see them fail.** Expected: 404 for the new route, then assertion errors.

- [ ] **Step 4: Implement.** In `legion_ask.py`:

```python
STRONGHOLD_ALLOWED = (
    "stronghold__tool_brain_search", "stronghold__tool_brain_read", "stronghold__tool_brain_list",
    "stronghold__tool_brain_write", "stronghold__tool_brain_update",
)


def disabled_tools(memory: bool) -> list[str]:
    """Everything blocked; at the Stronghold level five Brain tools are let through ("!name" is Legion's exception form)."""
    return ["*"] + ["!" + name for name in STRONGHOLD_ALLOWED] if memory else ["*"]
```

Use it in `ask(..., memory=False)` in place of `DISABLED_TOOLS`; keep the comment that says why `"*"` is used and add that the exceptions also open memory recall (`memory_recall.py`). In `outside.py`, extract the helper, add the second route `@router.post("/stronghold/ask")` calling it with `service="stronghold", memory=True`. `SERVICES` gains `"stronghold"`. In the admin delete route, after the record is deleted and committed, best-effort purge: for each of `brain`, `stack`, `brain/proposals`, `brain/shares` call `request.app.state.stronghold.forward("DELETE", f"/{domain}/accounts/{uid}", admin)` exactly as the account-delete flow does, log one line per failure with the client id and domain only, and never fail the delete because of it. The delete response stays `204`.

- [ ] **Step 5: Run the Portcullis suite** (the two known failures stay) and the Plan 24 outside tests specifically. Record counts.

- [ ] **Step 6: README.** Document the route, the five tools, the own-folder rule, the global-brain exclusion, the purge on delete and what an outside client can never do. Say plainly that the end-to-end path through a live Legion and Stronghold was not run.

- [ ] **Step 7: Commit.** `git commit -m "feat(portcullis): outside clients at the Stronghold level with their own memory"`

---

### Task 4: Probe, docs and report

**Files:**
- Modify: `apps/legion/README.md` (the filter exception form, one short paragraph), `apps/stronghold/README.md`, `apps/portcullis/README.md` (done in Task 3; check), `docs/deployment.md` if it names outside clients, roadmap row 24b.
- Test: extend `apps/portcullis/tests/legion_filter_probe.py` (the Plan 24 probe that drives Legion's own filter with a fake upstream).

- [ ] **Step 1: Extend the probe.** With the Stronghold-level filter set (`["*", "!stronghold__tool_brain_search", ...]`), drive Legion's own filter and a fake upstream the way the Plan 24 probe does, and assert: the five exceptions reach the upstream; `stronghold__tool_skill_search`, `stronghold__tool_skill_propose`, `stronghold__tool_ticket_createTicket`, `stronghold__tool_usage_summary`, `stronghold__tool_brain_propose` and any `armory__*` tool do not. Keep the probe's existing no-bytecode flag and run it the way Plan 24 documents.

- [ ] **Step 2: Docs.** The Legion README gets the exception form. The Stronghold README says `oc_` is reserved and what an outside uid may call. Add the roadmap row link (row 24b, "Written" then "Built" after the merge).

- [ ] **Step 3: Final suites** for Legion, Stronghold and Portcullis, `git diff --check`. Record counts under "Final results".

- [ ] **Step 4: Commit.** `git commit -m "test: probe the Stronghold-level filter against Legion; docs for Plan 24b"`

## Self-review

- **Spec coverage:** an outside client with its own memory namespace (Tasks 2, 3); no sharing (no share tools exist on the MCP server and the route reaches nothing else; Task 2's default refuses every other tool); no model-level access (Legion only; the key opens nothing else); per-client budget and audit as before (same guard); purge when a client is deleted (Task 3).
- **Two walls:** Legion's filter (Task 1, set by Task 3) and Stronghold's `resolve_account` default (Task 2). The probe in Task 4 tests the first; the Stronghold tests test the second.
- **Placeholders:** the fixture names in tests marked "copy the real name" are helpers this plan did not read; each says which test file to copy from.
- **Risk:** `"!name"` is a new meaning for a string in `disabled_tools`. Portcullis for ordinary accounts only sends real tool names and `agent:<id>`, never a name that starts with `!`, so existing behaviour is unchanged; Task 1's tests pin it.

## Open questions for the user

1. May an outside client read the global brain? This plan says no (own folder only). Say so if it should read it.
2. The five tools include write and update. Should the Stronghold level be read-only by default and writing a per-client switch? This plan allows writing, limited by the account quota.
3. Memory in Legion's recall also runs for these calls. Should recall be switched off for outside clients that only want a stateless answer? They can use the Legion level.

## Manual checklist (pending after the build)

- [ ] Create a client with `stronghold` allowed. Ask "remember that my cat is Tom", then in a second call "what is my cat's name?". The second answer uses the note.
- [ ] Look in Stronghold's Brain folder: a folder named `oc_...` holds the note, and no other account's folder changed.
- [ ] Ask it to open a ticket, show usage, or learn a skill: it cannot, and no ticket or skill appears.
- [ ] Ask it for a global note by name: it finds nothing.
- [ ] Delete the client in the admin route: its folder is gone.
- [ ] Call `/api/outside/stronghold/ask` with a legion-only client: `403`.

## Baseline results

(record here)

## Changes found during work

(record here)

## Final results

(record here)
