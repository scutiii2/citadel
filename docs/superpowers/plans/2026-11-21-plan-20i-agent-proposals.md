# Plan 20i: Agent Proposals From Short-Term To Long-Term Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agent can propose that something worth keeping moves from a chat's short-term memory into the user's long-term files; nothing is saved until the user accepts it in Ember.

**Architecture:** Stronghold keeps proposals as Treasury documents (collection `brain_proposals`, one per proposal, like shares). One new MCP tool `tool_brain_propose` creates a pending proposal. New `/brain/proposals` routes list, read, accept and decline it; Portcullis passes them on as `/api/brain/proposals`. Accept creates a long-term file through the existing `BrainFiles.create` (so every quota and check applies) and can remove the proposed items from the stack. Ember gets a "Suggestions" button on the Notes page that opens a review dialog. Legion's Ember agent gets one instruction sentence so it uses the tool.

**Tech Stack:** Python 3.12, FastAPI, FastMCP (Stronghold, Portcullis, Legion tests), pytest; Vue 3, TypeScript, Pinia, Vitest (Ember).

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md) (line "Agents propose moving short-term items to long-term; the user accepts"), [roadmap](2026-11-20-scope-roadmap.md) row 20i. Builds on Plans 20a (stack), 20b (files), 20e and 20f (Ember), 20d (the share pattern this copies).

## Global Constraints

- Nothing reaches long-term memory without the user pressing Keep. An agent never writes through this tool, and the tool does not read or change files or stacks except to check that named item ids exist.
- The proposal text is agent output. Ember shows it as plain text, never as markup, with the server's sentence that an agent wrote it. Text, titles and folders never reach a log, an action log or an error message; every refusal says what is wrong, never what was written.
- Keep the long-term rules: a proposal is checked at proposal time with `BrainFiles._check` (title, body size from `limits.max_record_chars`, tags, folder) and again at accept time by `BrainFiles.create` (file count, total bytes). A refused accept leaves the proposal pending.
- An accepted file is created with `actor="agent"` (source `automatic`: agents may refine it, the user can revert to the original). Folder defaults to the proposal's folder, and the user may change title and folder before keeping.
- At most 20 proposals wait per account (constant in `proposals.py`, not an admin setting). A proposal with the same fingerprint (title, body, folder, tags) as a pending one is not stored twice; one the user already declined or kept is refused with a message that tells the agent not to propose it again.
- The only Ember change is `features/proposals/` plus the Notes page button and dialog. No new route or nav entry, so the nav tests do not change. Ember rules apply: `apiRequest` only, tokens only (`radiusScale.test.ts`), shared components (`BaseModal`, `StateMessage`), 44px touch targets, status by words plus an icon, no reduced motion (never add a reduced-motion rule, media query or test), `architecture.test.ts` (shared code must not import features; feature to feature is allowed).
- Store pattern: Pinia setup store, run counters so late replies are dropped, `epoch` raised by `forget()`, watch `auth.account?.id` with `flush: "sync"`, private data cleared on unmount and sign-out.
- Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider`. Ember: `pnpm exec vue-tsc -b` and `pnpm test` from `apps/ember`. Use `uv` and `pnpm`, add no dependency. Never read `.env*` or `secrets/`.
- Out of scope: removing `tool_brain_write` (it stays for what the user explicitly asks to save; this is reported as an open question), an admin setting for the cap, editing the proposal text before Keep, proposals for skills or global files, a count badge outside the Notes page, Armory memory removal (Plan 22), removal of old Stronghold notes and `/memory` (Plan 20j).

## Assumptions to check while working

Record each result in "Changes found during work" at the end of this file.

- (a) `BrainFiles._check(title, body, tags, folder)` returns `(title, body, tags_tuple, folder)` and raises `BrainError(422, ...)` for a bad value, and `FakeDbGateway.query(collection, filters, limit, offset)` filters by equality. Confirm in `src/brain/files.py` and `tests/conftest.py`.
- (b) Legion's Ember agent allows `stronghold__tool_brain_*` by glob, so the new tool needs no allow-list change (`legion/agents/ember.json`). If the glob is missing, add the tool name.
- (c) The Portcullis outside-client allow list (client records and `brain_sharing.py` docstring: "Outside clients must never be given these routes") does not need a change. Grep Portcullis for where routes are denied to outside clients; if routes are listed by prefix, add `/api/brain/proposals` the same way `/api/brain/shares` is handled.
- (d) The sync route tests in Stronghold seed async state somehow (see how `test_stack_routes.py` creates agent items). Copy that way in the `seed` helper of Task 3.
- (e) `BaseModal` takes `open`, `title`, `wide` and emits `close`; its default slot holds the body and buttons (see `ShareReview.vue`). The jsdom `<dialog>` stubs used in `ShareReview.test.ts` are needed in the dialog test.

## Baseline

Fill in before changing anything (type check and tests, each service):

- Stronghold (`apps/stronghold`): 1,055 passed.
- Portcullis (`apps/portcullis`): 1,103 passed, 2 known failures. test_secret_box.py::test_an_invalid_key_in_env_stops_startup and test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown both reject http://127.0.0.1:0.
- Legion (`apps/legion`): 1,488 passed, 6 deselected.
- Ember (`apps/ember`): Type check passed. Vitest passed 2,339 tests across 194 files.

## File Map

| File | Change |
|---|---|
| `apps/stronghold/src/brain/proposals.py` | Create: `BrainProposals` store (propose, pending, get, accept, decline, purge) |
| `apps/stronghold/tests/test_brain_proposals.py` | Create |
| `apps/stronghold/src/mcp_tools/proposal_tools.py` | Create: `ProposalTools.propose` |
| `apps/stronghold/src/mcp_tools/server.py` | Modify: register `tool_brain_propose` |
| `apps/stronghold/tests/test_mcp_proposal_tools.py` | Create |
| `apps/stronghold/tests/test_mcp_mount.py` | Modify: expected tool list |
| `apps/stronghold/src/brain/proposal_routes.py` | Create: `/brain/proposals` |
| `apps/stronghold/src/api.py` | Modify: build `app.state.brain_proposals`, include the router |
| `apps/stronghold/tests/test_brain_proposal_routes.py` | Create |
| `apps/stronghold/README.md` | Modify: tool list and routes |
| `apps/portcullis/src/routes/brain_proposals.py` | Create: `/api/brain/proposals` passes |
| `apps/portcullis/src/app.py` | Modify: include the router |
| `apps/portcullis/src/routes/admin.py` | Modify: purge list entry and error log line |
| `apps/portcullis/tests/test_brain_proposal_routes.py` | Create |
| `apps/legion/agents/ember.json` | Modify: one instruction sentence |
| `apps/legion/tests/test_agent_spec.py` | Modify: assert the sentence |
| `apps/ember/src/features/proposals/api/ProposalsClient.ts` (+ test) | Create |
| `apps/ember/src/features/proposals/stores/proposals.ts` (+ test) | Create |
| `apps/ember/src/features/proposals/components/ProposalsDialog.vue` (+ test) | Create |
| `apps/ember/src/features/notes/NotesView.vue` (+ test) | Modify: Suggestions button, dialog, reload on keep |

---

### Task 1: Stronghold proposal store

**Files:**
- Create: `apps/stronghold/src/brain/proposals.py`
- Test: `apps/stronghold/tests/test_brain_proposals.py`

**Interfaces:**
- Consumes: `DocumentStore` (`get`, `put`, `delete`, `query`), `BrainFiles` (`_check`, `create`, `limits`), `StackStore` (`view`, `remove`), `BrainError`, `StackError`.
- Produces: `PROPOSALS = "brain_proposals"`, `MAX_PENDING = 20`, `MAX_ITEMS = 20`, `UNTRUSTED` (text), `view(doc, detail=False)`, and `BrainProposals` with
  `await propose(uid, chat_id, title, body, item_ids, folder="", tags=()) -> tuple[dict, bool]` (view, already_waiting),
  `await pending(uid) -> list[dict]` (newest first, no body),
  `await get(uid, proposal_id) -> dict` (with body and notice),
  `await accept(uid, proposal_id, title=None, folder=None, remove_items=False) -> dict` (view plus `removed: int`),
  `await decline(uid, proposal_id) -> dict`,
  `await purge(uid) -> None`.
  Errors are `BrainError(status, message)`.

- [ ] **Step 1: Write the failing tests**

Create `apps/stronghold/tests/test_brain_proposals.py`:

```python
import pytest

from src.brain.files import BrainError, BrainFiles
from src.brain.limits import LongTermLimits, StackLimits
from src.brain.proposals import MAX_PENDING, BrainProposals
from src.brain.stack import StackStore

OWNER, OTHER, CHAT = "u-1", "u-2", "chat-1"


@pytest.fixture
def world(tmp_path, db_gateway):
    files = BrainFiles(tmp_path / "brain", LongTermLimits(max_record_chars=300, max_files=2), refresh_seconds=0.0)
    stacks = StackStore(db_gateway, StackLimits())
    return BrainProposals(db_gateway, files, stacks), files, stacks


async def test_propose_stores_a_pending_proposal_without_touching_files(world):
    proposals, files, stacks = world
    item = await stacks.add(OWNER, CHAT, "likes green tea")
    made, waiting = await proposals.propose(OWNER, CHAT, " Tea  habits ", "The user likes green tea.", [item["id"]], "drinks", ["Tea"])
    assert waiting is False
    assert (made["title"], made["folder"], made["tags"], made["status"]) == ("Tea habits", "drinks", ["tea"], "pending")
    assert made["item_ids"] == [item["id"]] and made["chat_id"] == CHAT and "body" not in made
    assert await files.list(OWNER) == []
    assert [p["id"] for p in await proposals.pending(OWNER)] == [made["id"]]
    assert await proposals.pending(OTHER) == []


async def test_the_detail_has_the_text_and_the_untrusted_notice(world):
    proposals, _, _ = world
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "The user likes green tea.", [])
    detail = await proposals.get(OWNER, made["id"])
    assert detail["body"] == "The user likes green tea." and "agent wrote" in detail["notice"].lower()
    with pytest.raises(BrainError) as gone:
        await proposals.get(OTHER, made["id"])
    assert gone.value.status == 404


async def test_a_bad_proposal_is_refused_without_echoing_the_text(world):
    proposals, _, stacks = world
    for args in [(" ", "body", []), ("Title", " ", []), ("Title", "x" * 301, []), ("Title", "body", [99]),
                 ("Title", "body", list(range(1, 22)))]:
        with pytest.raises(BrainError) as refused:
            await proposals.propose(OWNER, CHAT, *args)
        assert refused.value.status == 422 and "x" * 20 not in str(refused.value)
    with pytest.raises(BrainError):
        await proposals.propose(OWNER, CHAT, "Title", "body", [], folder="../etc")


async def test_the_same_proposal_is_not_stored_twice(world):
    proposals, _, _ = world
    first, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    again, waiting = await proposals.propose(OWNER, CHAT, "tea", "likes tea", [])
    assert waiting is False  # the title differs in case, so the fingerprint differs
    same, waiting = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    assert waiting is True and same["id"] == first["id"]
    assert len(await proposals.pending(OWNER)) == 2


async def test_the_pending_cap(world):
    proposals, _, _ = world
    for number in range(MAX_PENDING):
        await proposals.propose(OWNER, CHAT, f"Title {number}", "body", [])
    with pytest.raises(BrainError) as full:
        await proposals.propose(OWNER, CHAT, "One more", "body", [])
    assert full.value.status == 409 and str(MAX_PENDING) in str(full.value)
    assert (await proposals.propose(OTHER, CHAT, "Mine", "body", []))[1] is False


async def test_accept_creates_an_agent_file_and_can_remove_the_items(world):
    proposals, files, stacks = world
    first = await stacks.add(OWNER, CHAT, "likes green tea")
    keep = await stacks.add(OWNER, CHAT, "uses metric units")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "The user likes green tea.", [first["id"]], "drinks")
    done = await proposals.accept(OWNER, made["id"], title="Green tea", folder="likes", remove_items=True)
    assert done["status"] == "accepted" and done["removed"] == 1
    record = await files.get(OWNER, done["result_id"])
    assert (record.title, record.folder, record.body, record.source, record.last_editor) == (
        "Green tea", "likes", "The user likes green tea.", "automatic", "agent")
    assert [i["id"] for i in (await stacks.view(OWNER, CHAT))["items"]] == [keep["id"]]
    assert await proposals.pending(OWNER) == []
    with pytest.raises(BrainError) as decided:
        await proposals.accept(OWNER, made["id"])
    assert decided.value.status == 409 and "already decided" in str(decided.value)


async def test_accept_keeps_the_items_unless_asked(world):
    proposals, files, stacks = world
    item = await stacks.add(OWNER, CHAT, "likes green tea")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [item["id"]])
    done = await proposals.accept(OWNER, made["id"])
    assert done["removed"] == 0 and (await stacks.view(OWNER, CHAT))["used"] == 1
    assert (await files.get(OWNER, done["result_id"])).folder == ""


async def test_a_refused_accept_leaves_the_proposal_pending(world):
    proposals, files, _ = world
    await files.create(OWNER, title="a", body="a")
    await files.create(OWNER, title="b", body="b")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    with pytest.raises(BrainError) as full:
        await proposals.accept(OWNER, made["id"])
    assert full.value.status == 409
    assert [p["id"] for p in await proposals.pending(OWNER)] == [made["id"]]


async def test_a_gone_stack_does_not_stop_a_kept_proposal(world):
    proposals, files, stacks = world
    item = await stacks.add(OWNER, CHAT, "likes tea")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [item["id"]])
    await stacks.remove(OWNER, CHAT, item["id"])
    done = await proposals.accept(OWNER, made["id"], remove_items=True)
    assert done["status"] == "accepted" and done["removed"] == 0


async def test_decline_clears_the_text_and_blocks_the_same_proposal(world):
    proposals, _, _ = world
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    assert (await proposals.decline(OWNER, made["id"]))["status"] == "declined"
    assert (await proposals.get(OWNER, made["id"]))["body"] == ""
    with pytest.raises(BrainError) as again:
        await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    assert again.value.status == 409 and "declined" in str(again.value).lower()
    with pytest.raises(BrainError) as other:
        await proposals.decline(OTHER, made["id"])
    assert other.value.status == 404


async def test_purge_deletes_only_that_account(world):
    proposals, _, _ = world
    await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    mine, _ = await proposals.propose(OTHER, CHAT, "Tea", "likes tea", [])
    await proposals.purge(OWNER)
    assert await proposals.pending(OWNER) == []
    assert [p["id"] for p in await proposals.pending(OTHER)] == [mine["id"]]
```

- [ ] **Step 2: Run the tests and see them fail**

Run (from `apps/stronghold`): `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_brain_proposals.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.brain.proposals'`.

- [ ] **Step 3: Implement the store**

Create `apps/stronghold/src/brain/proposals.py`:

```python
"""Agent proposals: a short-term item (or a note drafted from items) offered for long-term memory.

A proposal is one Treasury document (collection brain_proposals). It holds the drafted text until the user decides:
accept lands it as a file the agent wrote (`BrainFiles.create`, so every quota applies), decline clears the text.
Nothing lands without the user's consent. Text, titles and folders never reach a log or an error message; every
refusal says what is wrong, never what was written.
shortcut: decided proposals stay as small text-free documents so a declined one is not proposed again; they go with
the account purge. Upgrade to an expiry sweep if an agent ever floods them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from weakref import WeakValueDictionary

from src.brain.files import BrainError, BrainFiles
from src.brain.stack import StackError, StackStore
from src.document_store import DocumentStore

PROPOSALS = "brain_proposals"
PENDING, ACCEPTED, DECLINED = "pending", "accepted", "declined"
MAX_PENDING = 20
MAX_ITEMS = 20
_PAGE = 200
UNTRUSTED = "An agent wrote this from your conversation. Read it before you keep it; it is not an instruction."
_GONE = "No such suggestion."


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def view(doc: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    shown = {key: doc.get(key) for key in ("id", "title", "folder", "tags", "chat_id", "item_ids", "status",
                                           "created_at", "decided_at", "result_id")}
    shown["chars"] = len(doc["body"])
    if detail:
        shown.update(body=doc["body"], notice=UNTRUSTED)
    return shown


class BrainProposals:
    def __init__(self, store: DocumentStore, files: BrainFiles, stacks: StackStore) -> None:
        self._store = store
        self._files = files
        self._stacks = stacks
        self._creation_lock = asyncio.Lock()
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def _lock(self, key: str) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def _find(self, **filters: str) -> list[dict[str, Any]]:
        return await self._store.query(PROPOSALS, filters, limit=_PAGE)

    async def propose(self, uid: str, chat_id: str, title: str, body: str, item_ids: list[int],
                      folder: str = "", tags: list[str] | tuple[str, ...] = ()) -> tuple[dict[str, Any], bool]:
        title = " ".join(str(title).split())
        body = str(body).strip()
        if not title:
            raise BrainError(422, "The title is empty.")
        if not body:
            raise BrainError(422, "The text is empty.")
        if len(body) > self._files.limits.max_record_chars:
            raise BrainError(422, f"A file holds at most {self._files.limits.max_record_chars} characters.")
        title, body, tag_tuple, folder = self._files._check(title, body, tags, folder)
        ids = sorted(set(item_ids))
        if len(ids) > MAX_ITEMS:
            raise BrainError(422, f"Name at most {MAX_ITEMS} items.")
        if ids:
            try:
                present = {item["id"] for item in (await self._stacks.view(uid, chat_id))["items"]}
            except StackError as error:
                raise BrainError(error.status, str(error)) from None
            if not set(ids) <= present:
                raise BrainError(422, "One of the named items is not in this chat's short-term memory.")
        fingerprint = hashlib.sha256(json.dumps([title, body, folder, list(tag_tuple)]).encode()).hexdigest()
        async with self._creation_lock:
            mine = await self._find(owner=uid)
            same = next((doc for doc in mine if doc.get("fingerprint") == fingerprint), None)
            if same is not None:
                if same["status"] == PENDING:
                    return view(same), True
                if same["status"] == DECLINED:
                    raise BrainError(409, "The user declined this suggestion. Do not propose it again.")
                raise BrainError(409, "The user already saved this suggestion.")
            if sum(1 for doc in mine if doc["status"] == PENDING) >= MAX_PENDING:
                raise BrainError(409, f"You already have {MAX_PENDING} suggestions waiting. Ask the user to review them first.")
            doc = {"id": uuid.uuid4().hex, "owner": uid, "chat_id": chat_id, "item_ids": ids, "title": title, "body": body,
                   "folder": folder, "tags": list(tag_tuple), "fingerprint": fingerprint, "status": PENDING,
                   "created_at": _now(), "decided_at": None, "result_id": None}
            await self._store.put(PROPOSALS, doc["id"], doc)
            return view(doc), False

    async def pending(self, uid: str) -> list[dict[str, Any]]:
        docs = [doc for doc in await self._find(owner=uid) if doc["status"] == PENDING]
        return [view(doc) for doc in sorted(docs, key=lambda doc: doc["created_at"], reverse=True)]

    async def _doc(self, uid: str, proposal_id: str) -> dict[str, Any]:
        doc = await self._store.get(PROPOSALS, proposal_id)
        if doc is None or doc["owner"] != uid:
            raise BrainError(404, _GONE)
        return doc

    async def get(self, uid: str, proposal_id: str) -> dict[str, Any]:
        return view(await self._doc(uid, proposal_id), detail=True)

    async def _pending_doc(self, uid: str, proposal_id: str) -> dict[str, Any]:
        doc = await self._doc(uid, proposal_id)
        if doc["status"] != PENDING:
            raise BrainError(409, "That suggestion is already decided.")
        return doc

    async def _close(self, doc: dict[str, Any], status: str, result_id: str | None = None) -> dict[str, Any]:
        doc["status"], doc["decided_at"], doc["result_id"], doc["body"] = status, _now(), result_id, ""
        await self._store.put(PROPOSALS, doc["id"], doc)
        return view(doc)

    async def accept(self, uid: str, proposal_id: str, title: str | None = None, folder: str | None = None,
                     remove_items: bool = False) -> dict[str, Any]:
        async with self._lock(proposal_id):
            doc = await self._pending_doc(uid, proposal_id)
            record = await self._files.create(uid, title=title or doc["title"], body=doc["body"], tags=doc["tags"],
                                              folder=doc["folder"] if folder is None else folder, actor="agent")
            done = await self._close(doc, ACCEPTED, record.id)
        removed = 0
        if remove_items:
            for item_id in doc["item_ids"]:
                try:
                    await self._stacks.remove(uid, doc["chat_id"], item_id)
                    removed += 1
                except StackError:
                    pass  # the item or the chat is already gone
        return {**done, "removed": removed}

    async def decline(self, uid: str, proposal_id: str) -> dict[str, Any]:
        async with self._lock(proposal_id):
            return await self._close(await self._pending_doc(uid, proposal_id), DECLINED)

    async def purge(self, uid: str) -> None:
        while docs := await self._find(owner=uid):
            for doc in docs:
                async with self._lock(doc["id"]):
                    await self._store.delete(PROPOSALS, doc["id"])
```

- [ ] **Step 4: Run the tests**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_brain_proposals.py`
Expected: all pass. If `BrainFiles._check` has another signature (assumption a), adapt the call and record it.

- [ ] **Step 5: Commit**

```bash
git add apps/stronghold/src/brain/proposals.py apps/stronghold/tests/test_brain_proposals.py
git commit -m "feat(stronghold): store for agent proposals to long-term memory"
```

---

### Task 2: MCP tool `tool_brain_propose` and the Ember agent sentence

**Files:**
- Create: `apps/stronghold/src/mcp_tools/proposal_tools.py`
- Modify: `apps/stronghold/src/mcp_tools/server.py`, `apps/stronghold/src/api.py` (state only, router comes in Task 3)
- Modify: `apps/stronghold/tests/test_mcp_mount.py`
- Test: `apps/stronghold/tests/test_mcp_proposal_tools.py`
- Modify: `apps/legion/agents/ember.json`, `apps/legion/tests/test_agent_spec.py`

**Interfaces:**
- Consumes: `BrainProposals.propose`, `Scope(uid, chat_id)`.
- Produces: `ProposalTools(proposals).propose(scope, title, body, item_ids, folder, tags) -> dict` with `{"ok": bool, "message": str, "proposal"?: {"id","title"}}`; MCP tool `tool_brain_propose(title, body, item_ids=None, folder="", tags=None)`. `app.state.brain_proposals` exists after startup.

- [ ] **Step 1: Write the failing tests**

Create `apps/stronghold/tests/test_mcp_proposal_tools.py`:

```python
import pytest

from src.brain.files import BrainFiles
from src.brain.limits import LongTermLimits, StackLimits
from src.brain.proposals import BrainProposals
from src.brain.stack import StackStore
from src.mcp_tools.proposal_tools import ProposalTools
from src.mcp_tools.scope import Scope

SCOPE = Scope("u-1", "chat-1")


@pytest.fixture
def world(tmp_path, db_gateway):
    files = BrainFiles(tmp_path / "brain", LongTermLimits(max_record_chars=300), refresh_seconds=0.0)
    stacks = StackStore(db_gateway, StackLimits())
    proposals = BrainProposals(db_gateway, files, stacks)
    return ProposalTools(proposals), proposals, files, stacks


async def test_a_proposal_waits_for_the_user_and_saves_nothing(world):
    tools, proposals, files, stacks = world
    item = await stacks.add("u-1", "chat-1", "likes green tea")
    answer = await tools.propose(SCOPE, "Tea habits", "The user likes green tea.", [item["id"]], "drinks", ["tea"])
    assert answer["ok"] is True and answer["proposal"]["title"] == "Tea habits"
    assert "nothing is saved" in answer["message"].lower() and "Tea habits" not in answer["message"]
    assert await files.list("u-1") == []
    assert len(await proposals.pending("u-1")) == 1


async def test_the_same_proposal_says_it_is_already_waiting(world):
    tools, _, _, _ = world
    await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    again = await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    assert again["ok"] is True and "already waiting" in again["message"].lower()


async def test_refusals_are_results_not_errors(world):
    tools, proposals, _, _ = world
    for args in [(" ", "x", None, "", None), ("T", "x" * 301, None, "", None), ("T", "x", [99], "", None), ("T", "x", None, "../etc", None)]:
        refused = await tools.propose(SCOPE, *args)
        assert refused["ok"] is False and refused["message"] and "xxxxxxxxxx" not in refused["message"]
    await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    await proposals.decline("u-1", (await proposals.pending("u-1"))[0]["id"])
    declined = await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    assert declined["ok"] is False and "do not propose it again" in declined["message"].lower()
```

In `apps/stronghold/tests/test_mcp_mount.py`, add `"tool_brain_propose"` to the expected tool-name list (line 24 area) and to any count assertion next to it. The existing test shows how the list is compared; keep its order rules.

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_mcp_proposal_tools.py tests/test_mcp_mount.py`
Expected: FAIL (`ModuleNotFoundError: src.mcp_tools.proposal_tools`; the mount test lists a tool that is missing).

- [ ] **Step 3: Implement**

Create `apps/stronghold/src/mcp_tools/proposal_tools.py`:

```python
"""Proposal tool. Every refusal is a result the model can read; nothing here raises to the model."""

from __future__ import annotations

from typing import Any

from src.brain.files import BrainError
from src.brain.proposals import BrainProposals
from src.mcp_tools.scope import Scope


class ProposalTools:
    def __init__(self, proposals: BrainProposals) -> None:
        self._proposals = proposals

    async def propose(self, scope: Scope, title: str, body: str, item_ids: list[int] | None,
                      folder: str, tags: list[str] | None) -> dict[str, Any]:
        try:
            made, waiting = await self._proposals.propose(scope.uid, scope.chat_id, title, body, item_ids or [], folder, tags or [])
        except BrainError as error:
            return {"ok": False, "message": str(error)}
        said = "That suggestion is already waiting for the user." if waiting else "Suggested."
        return {"ok": True, "proposal": {"id": made["id"], "title": made["title"]},
                "message": f"{said} The user decides in Ember; nothing is saved to long-term memory until they keep it."}
```

In `apps/stronghold/src/api.py`, after the `app.state.brain_shares = ...` block add (and import `BrainProposals` beside `BrainShares`):

```python
        app.state.brain_proposals = BrainProposals(
            app.state.store, app.state.brain_files, app.state.stacks,
        )
```

In `apps/stronghold/src/mcp_tools/server.py`: import `ProposalTools`, build `proposals = ProposalTools(app.state.brain_proposals)` next to `skills = ...`, and register the tool before the `tool_skill_search` tool:

```python
    @server.tool(description=("Propose that something worth keeping moves into the user's long-term memory as a Markdown file. Use it when this chat's "
                              "short-term memory holds a fact, preference or instruction that will matter after the chat ends and the user did not ask "
                              "you to save it. " + _NEVER_SAVE + " Write the note in your own words, one topic per proposal, and name the short-term "
                              "item ids it comes from. The user reviews it in Ember and may keep or decline it; nothing is saved until they keep it, so "
                              "tell them you suggested it. A proposal the user declined is refused; do not propose it again."),
                 meta={"keywords": ["memory", "notes", "propose", "suggest", "long-term"], "display_label": "Suggesting a long-term note"},
                 annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def tool_brain_propose(
        title: Title, body: Annotated[str, Field(description="The note as Markdown.", min_length=1, max_length=100_000)],
        item_ids: Annotated[list[int] | None, Field(description="Ids of the short-term items this note comes from, as shown by tool_stack_list (at most 20).", max_length=20)] = None,
        folder: Folder = "",
        tags: Annotated[list[str] | None, Field(description="Up to 10 lowercase tags: letters, digits, - and _.")] = None,
    ) -> dict[str, Any]:
        return await run(proposals.propose, title, body, item_ids, folder, tags)
```

`run` is the chat-scoped helper (it needs the chat for the item ids). `item_ids` entries below 1 are refused by the store ("not in this chat's short-term memory").

Legion: in `apps/legion/agents/ember.json`, in the `instructions` string, directly after the sentence that ends `with stronghold__tool_brain_write.` add: ` When something from this chat looks worth keeping for good but the user did not ask you to save it, call stronghold__tool_brain_propose with a short note in your own words and the short-term item ids it comes from; the user decides in Ember, so say you suggested it and do not claim it is saved.` Keep the JSON valid (escape nothing new). In `apps/legion/tests/test_agent_spec.py` near line 363 add one assertion in the test that already reads the Ember spec: the instructions contain `stronghold__tool_brain_propose`. Follow how that test loads `ember.json`.

- [ ] **Step 4: Run the tests**

Run in `apps/stronghold`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_mcp_proposal_tools.py tests/test_mcp_mount.py tests/test_mcp_brain_tools.py`
Run in `apps/legion`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_agent_spec.py tests/test_skill_reflection.py`
Expected: pass. Check assumption (b): the Ember spec already allows `stronghold__tool_brain_*`.

- [ ] **Step 5: Commit**

```bash
git add apps/stronghold/src apps/stronghold/tests apps/legion/agents/ember.json apps/legion/tests/test_agent_spec.py
git commit -m "feat(stronghold): tool_brain_propose and the Ember agent instruction"
```

---

### Task 3: Stronghold routes, Portcullis passes, docs

**Files:**
- Create: `apps/stronghold/src/brain/proposal_routes.py`
- Modify: `apps/stronghold/src/api.py` (include router), `apps/stronghold/README.md`
- Test: `apps/stronghold/tests/test_brain_proposal_routes.py`
- Create: `apps/portcullis/src/routes/brain_proposals.py`
- Modify: `apps/portcullis/src/app.py`, `apps/portcullis/src/routes/admin.py`
- Test: `apps/portcullis/tests/test_brain_proposal_routes.py`

**Interfaces:**
- Consumes: `BrainProposals`, `BrainRoute`, `Requester`, `current_requester`, `request.app.state.platform.log_action(uid, action, message)`.
- Produces (Stronghold): `GET /brain/proposals` -> `{"proposals": [view...]}` (pending, newest first, no text); `GET /brain/proposals/{id}` -> detail with `body` and `notice`; `POST /brain/proposals/{id}/accept` body `{title?, folder?, remove_items?}` -> view plus `removed`; `POST /brain/proposals/{id}/decline` -> view; `DELETE /brain/proposals/accounts/{uid}` -> 204 (purge). Action log entries `brain.proposal_accept` ("Kept a suggestion") and `brain.proposal_decline` ("Declined a suggestion") never hold text.
- Produces (Portcullis): the same five routes under `/api/brain/proposals`, chat.use, forwarded with `pass_on`.

- [ ] **Step 1: Write the failing Stronghold tests**

Create `apps/stronghold/tests/test_brain_proposal_routes.py`:

```python
import asyncio

from tests.auth_helpers import IdentityHeaders
from tests.conftest import IDENTITY

BO = IdentityHeaders(uid="u-2", username="bob", email="bob@example.com")
CHAT = "chat-1"


def seed(client, uid=None, title="Tea habits", body="The user likes green tea.", **extra):
    """Create a pending proposal the way the MCP tool does, in-process (assumption d: copy the way test_stack_routes seeds)."""
    proposals = client.app.state.brain_proposals
    made, _ = asyncio.run(proposals.propose(uid or IDENTITY.uid, CHAT, title, body, [], **extra))
    return made


def test_list_detail_accept_and_logs(client, platform):
    made = seed(client, folder="drinks")
    listed = client.get("/brain/proposals").json()["proposals"]
    assert [p["id"] for p in listed] == [made["id"]] and "body" not in listed[0]
    assert client.get("/brain/proposals", headers=BO).json()["proposals"] == []
    seen = client.get(f"/brain/proposals/{made['id']}").json()
    assert seen["body"] == "The user likes green tea." and "agent wrote" in seen["notice"].lower()
    assert client.get(f"/brain/proposals/{made['id']}", headers=BO).status_code == 404
    done = client.post(f"/brain/proposals/{made['id']}/accept", json={"title": "Green tea", "folder": "likes"})
    assert done.status_code == 200 and done.json()["status"] == "accepted" and done.json()["removed"] == 0
    mine = client.get("/brain/files").json()["files"]
    assert [(f["title"], f["folder"], f["source"]) for f in mine] == [("Green tea", "likes", "automatic")]
    assert client.get("/brain/proposals").json()["proposals"] == []
    assert [a for _, a, _ in platform.actions if a.startswith("brain.proposal")] == ["brain.proposal_accept"]
    assert all("tea" not in m.lower() for _, _, m in platform.actions)


def test_decline_and_a_decided_proposal(client, platform):
    made = seed(client)
    assert client.post(f"/brain/proposals/{made['id']}/decline", headers=BO).status_code == 404
    assert client.post(f"/brain/proposals/{made['id']}/decline").json()["status"] == "declined"
    again = client.post(f"/brain/proposals/{made['id']}/accept")
    assert again.status_code == 409 and "already decided" in again.json()["detail"]
    assert "brain.proposal_decline" in [a for _, a, _ in platform.actions]


def test_a_full_long_term_memory_refuses_the_accept_and_keeps_it_pending(client):
    made = seed(client)
    state = client.app.state.brain_files
    original = state.limits
    from dataclasses import replace
    state.limits = replace(original, max_files=0)
    try:
        refused = client.post(f"/brain/proposals/{made['id']}/accept")
    finally:
        state.limits = original
    assert refused.status_code == 409
    assert len(client.get("/brain/proposals").json()["proposals"]) == 1


def test_validation_and_purge(client):
    assert client.get("/brain/proposals/not-hex").status_code == 422
    made = seed(client)
    assert client.post(f"/brain/proposals/{made['id']}/accept", json={"folder": "../etc"}).status_code == 422
    assert client.delete(f"/brain/proposals/accounts/{IDENTITY.uid}").status_code == 204
    assert client.get("/brain/proposals").json()["proposals"] == []
```

Adjust `IDENTITY.uid` and the `limits` swap to the real helpers if they differ (assumption d; `BrainFiles.limits` may be frozen: if `replace` onto the attribute fails, create the 409 by filling the account's file quota with `max_files` files instead).

- [ ] **Step 2: Run and see it fail**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_brain_proposal_routes.py`
Expected: FAIL (404 on `/brain/proposals`, route missing).

- [ ] **Step 3: Implement the Stronghold routes**

Create `apps/stronghold/src/brain/proposal_routes.py`:

```python
"""/brain/proposals: the user's door to what agents suggest for long-term memory. Portcullis serves it as /api/brain/proposals.
Only a signed-in person reaches it; the agent's only way in is the MCP tool, which can only create a pending suggestion."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, Field

from src.brain.files_routes import BrainRoute
from src.brain.proposals import BrainProposals
from src.requester import Requester, current_requester

router = APIRouter(prefix="/brain/proposals", tags=["brain-proposals"], route_class=BrainRoute)
ProposalId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
Uid = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class Landing(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    folder: str | None = Field(default=None, max_length=130)
    remove_items: bool = False


def proposals_of(request: Request) -> BrainProposals:
    return request.app.state.brain_proposals


@router.get("")
async def pending(request: Request, who: Requester = Depends(current_requester)):
    return {"proposals": await proposals_of(request).pending(who.uid)}


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(request: Request, uid: Uid) -> Response:
    await proposals_of(request).purge(uid)
    return Response(status_code=204)


@router.get("/{proposal_id}")
async def one(proposal_id: ProposalId, request: Request, who: Requester = Depends(current_requester)):
    return await proposals_of(request).get(who.uid, proposal_id)


@router.post("/{proposal_id}/accept")
async def accept(proposal_id: ProposalId, request: Request, body: Landing | None = None, who: Requester = Depends(current_requester)):
    given = body or Landing()
    done = await proposals_of(request).accept(who.uid, proposal_id, given.title, given.folder, given.remove_items)
    # The action only, never the title or text.
    await request.app.state.platform.log_action(who.uid, "brain.proposal_accept", "Kept a suggestion")
    return done


@router.post("/{proposal_id}/decline")
async def decline(proposal_id: ProposalId, request: Request, who: Requester = Depends(current_requester)):
    done = await proposals_of(request).decline(who.uid, proposal_id)
    await request.app.state.platform.log_action(who.uid, "brain.proposal_decline", "Declined a suggestion")
    return done
```

In `apps/stronghold/src/api.py` import `from src.brain import proposal_routes as brain_proposal_routes` beside the other brain routers and add `app.include_router(brain_proposal_routes.router)` after the `brain_share_routes` lines.

In `apps/stronghold/README.md`, next to the line that lists the `tool_brain_*` tools (line about `tool_brain_search ... tool_brain_update`), add `tool_brain_propose` and one sentence: it creates a suggestion the user keeps or declines on the Notes page in Ember (`/brain/proposals`, Portcullis `/api/brain/proposals`); nothing is saved until the user keeps it.

- [ ] **Step 4: Write the Portcullis tests**

Create `apps/portcullis/tests/test_brain_proposal_routes.py`, copying the imports and the `as_admin`, `upstream`, `client` pattern of `test_brain_sharing_routes.py` (same helpers):

```python
import httpx
import pytest

from tests.auth_helpers import assertion, requester
from tests.test_registration import as_admin

JSON = {"Content-Type": "application/json"}
ID = "a" * 32

CASES = [
    ("GET", "/api/brain/proposals", "/brain/proposals"),
    ("GET", f"/api/brain/proposals/{ID}", f"/brain/proposals/{ID}"),
    ("POST", f"/api/brain/proposals/{ID}/accept", f"/brain/proposals/{ID}/accept"),
    ("POST", f"/api/brain/proposals/{ID}/decline", f"/brain/proposals/{ID}/decline"),
]


@pytest.mark.parametrize("method, url, target", CASES)
def test_a_signed_in_person_reaches_every_route(client, upstream, method, url, target):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(200, json={"forwarded": True})
    upstream.requests.clear()
    answer = client.request(method, url, json={"x": 1} if method == "POST" else None, headers=JSON)
    assert answer.status_code == 200 and answer.json() == {"forwarded": True}
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path) == (method, target)
    assert assertion(sent, "stronghold")["iss"] == "portcullis"
    assert requester(sent)["username"] == "root"


@pytest.mark.parametrize("method, url, _target", CASES)
def test_no_login_means_no_forward(client, upstream, method, url, _target):
    upstream.requests.clear()
    assert client.request(method, url, headers=JSON).status_code == 401
    assert not upstream.requests


def test_a_bad_id_is_refused_before_it_is_forwarded(client, upstream):
    as_admin(client)
    upstream.requests.clear()
    assert client.get("/api/brain/proposals/not-hex").status_code == 422
    assert not upstream.requests
```

Make the imports match the real `test_brain_sharing_routes.py` header (it also imports `uids`, `login` and so on; only import what is used). The purge entry is tested by adding the new domain to the existing deleted-account test if `test_admin*.py` asserts the domain list (grep `brain/shares` in the Portcullis tests and extend that assertion with `brain/proposals`).

- [ ] **Step 5: Implement the Portcullis routes**

Create `apps/portcullis/src/routes/brain_proposals.py`:

```python
"""/api/brain/proposals: what agents suggest for long-term memory, answered by Stronghold.
Only a signed-in session reaches it (chat.use). Outside clients must never be given these routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold
from src.models import Account
from src.routes.chats import require_chat
from src.routes.stronghold import pass_on
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/brain/proposals", tags=["brain-proposals"])
Hex = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


@router.get("")
async def list_proposals(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/proposals")


@router.get("/{proposal_id}")
async def read_proposal(
    proposal_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/proposals/{proposal_id}")


@router.post("/{proposal_id}/accept")
async def accept_proposal(
    proposal_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/proposals/{proposal_id}/accept")


@router.post("/{proposal_id}/decline")
async def decline_proposal(
    proposal_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/proposals/{proposal_id}/decline")
```

In `apps/portcullis/src/app.py`: import `brain_proposals` with `brain_sharing` and add `app.include_router(brain_proposals.router)` after `brain_sharing`. In `apps/portcullis/src/routes/admin.py` extend the purge list with `("brain/proposals", "Memory suggestions")` after `("brain/shares", ...)`, and generalise the special log line so the action name stays valid:

```python
        if not confirmed and domain in ("brain/shares", "brain/proposals"):
            await logs.error(admin.id, f"admin.{domain.replace('/', '_')}_purge", f"{what} were not purged")
```

For `brain/shares` this produces the same action name and text as before (`admin.brain_shares_purge`, "Shared items and blocks were not purged"); `what` for proposals is "Memory suggestions". Check assumption (c) and record it.

- [ ] **Step 6: Run the tests**

Run in `apps/stronghold`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_brain_proposal_routes.py tests/test_brain_proposals.py tests/test_mcp_proposal_tools.py` then the whole suite `... -m pytest -q -p no:cacheprovider`.
Run in `apps/portcullis`: `... -m pytest -q -p no:cacheprovider tests/test_brain_proposal_routes.py tests/test_brain_sharing_routes.py` then the whole suite (two known failures stay).
Expected: new tests pass; counts rise by the new tests; no other change.

- [ ] **Step 7: Commit**

```bash
git add apps/stronghold apps/portcullis
git commit -m "feat(stronghold,portcullis): routes to review agent proposals"
```

---

### Task 4: Ember client and store

**Files:**
- Create: `apps/ember/src/features/proposals/api/ProposalsClient.ts`, `ProposalsClient.test.ts`
- Create: `apps/ember/src/features/proposals/stores/proposals.ts`, `proposals.test.ts`

**Interfaces:**
- Consumes: `apiRequest`, `ApiError`, `useAuthStore`, `errorMessage`.
- Produces: types `Proposal`, `ProposalDetail`, `Landing`, `AcceptedProposal`; `proposalsClient.{list, get, accept, decline}`; `useProposalsStore()` with `status`, `error`, `items`, `load()`, `accept(id, landing?)`, `decline(id)`, `forget()`, and `isDecidedProposalError(err)`.

- [ ] **Step 1: Write the failing tests**

Create `apps/ember/src/features/proposals/api/ProposalsClient.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { proposalsClient } from "./ProposalsClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));
const request = vi.mocked(apiRequest);

beforeEach(() => vi.clearAllMocks());

describe("proposalsClient", () => {
  it("lists the waiting suggestions", async () => {
    request.mockResolvedValue({ proposals: [{ id: "p1" }] });
    expect(await proposalsClient.list()).toEqual([{ id: "p1" }]);
    expect(request).toHaveBeenCalledWith("GET", "/api/brain/proposals");
  });

  it("reads one, keeps one and declines one", async () => {
    request.mockResolvedValue({ id: "p1" });
    await proposalsClient.get("p1");
    await proposalsClient.accept("p1", { title: "T", folder: "f", remove_items: true });
    await proposalsClient.decline("p1");
    expect(request.mock.calls).toEqual([
      ["GET", "/api/brain/proposals/p1"],
      ["POST", "/api/brain/proposals/p1/accept", { title: "T", folder: "f", remove_items: true }],
      ["POST", "/api/brain/proposals/p1/decline"],
    ]);
  });
});
```

Create `apps/ember/src/features/proposals/stores/proposals.test.ts` (same shape as `sharing.test.ts`):

```ts
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { proposalsClient, type Proposal } from "../api/ProposalsClient";
import { useProposalsStore } from "./proposals";

vi.mock("../api/ProposalsClient", () => ({
  proposalsClient: { list: vi.fn(), get: vi.fn(), accept: vi.fn(), decline: vi.fn() },
}));
const client = vi.mocked(proposalsClient);

const proposal = (id: string): Proposal => ({
  id, title: `suggestion ${id}`, folder: "", tags: [], chat_id: "c1", item_ids: [1], status: "pending",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 5,
});

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useProposalsStore() };
}
const later = <T>() => {
  let done!: (value: T) => void;
  const promise = new Promise<T>((resolve) => { done = resolve; });
  return { promise, done };
};

beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue([proposal("a"), proposal("b")]);
});

describe("load", () => {
  it("shows the waiting suggestions", async () => {
    const { store } = setup();
    expect(store.status).toBe("idle");
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.items.map((p) => p.id)).toEqual(["a", "b"]);
  });

  it("does nothing without an account", async () => {
    const { auth, store } = setup();
    auth.account = null;
    await store.load();
    expect(client.list).not.toHaveBeenCalled();
  });

  it("keeps the list when a refresh fails, and shows the error when the first load fails", async () => {
    const { store } = setup();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect([store.status, store.error]).toEqual(["error", "Storage is unavailable"]);
    await store.load();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.items).toHaveLength(2);
  });

  it("ignores an older reply that arrives after a newer one", async () => {
    const { store } = setup();
    const first = later<Proposal[]>();
    client.list.mockReturnValueOnce(first.promise);
    const slow = store.load();
    client.list.mockResolvedValueOnce([proposal("new")]);
    await store.load();
    first.done([proposal("old")]);
    await slow;
    expect(store.items.map((p) => p.id)).toEqual(["new"]);
  });
});

describe("changes", () => {
  it("refreshes the list after a keep or a decline", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockResolvedValue({ ...proposal("a"), status: "accepted", removed: 1 });
    client.list.mockResolvedValue([proposal("b")]);
    const done = await store.accept("a", { remove_items: true });
    expect(done.removed).toBe(1);
    expect(client.accept).toHaveBeenCalledWith("a", { remove_items: true });
    expect(store.items.map((p) => p.id)).toEqual(["b"]);
    client.decline.mockResolvedValue({ ...proposal("b"), status: "declined" });
    client.list.mockResolvedValue([]);
    await store.decline("b");
    expect(store.items).toEqual([]);
  });

  it("refreshes when the suggestion was already decided, and still throws", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockRejectedValue(new ApiError(409, "That suggestion is already decided."));
    client.list.mockResolvedValue([proposal("b")]);
    await expect(store.accept("a")).rejects.toThrow("already decided");
    expect(store.items.map((p) => p.id)).toEqual(["b"]);
  });
});

describe("private data", () => {
  it("is dropped by forget and by a change of account, and a late reply is ignored", async () => {
    const { auth, store } = setup();
    await store.load();
    store.forget();
    expect([store.status, store.items]).toEqual(["idle", []]);
    const late = later<Proposal[]>();
    client.list.mockReturnValueOnce(late.promise);
    const loading = store.load();
    auth.account = makeAccount({ id: 99, username: "other", email: "o@example.com" });
    late.done([proposal("x")]);
    await loading;
    expect(store.items).toEqual([]);
  });
});
```

- [ ] **Step 2: Run and see them fail**

Run (from `apps/ember`): `pnpm exec vitest run src/features/proposals`
Expected: FAIL (modules do not exist).

- [ ] **Step 3: Implement**

Create `apps/ember/src/features/proposals/api/ProposalsClient.ts`:

```ts
import { apiRequest } from "../../../api/http";

export type ProposalStatus = "pending" | "accepted" | "declined";

/** One suggestion as the list shows it. The text is not in it. Times are `...Z` strings. */
export interface Proposal {
  id: string;
  title: string;
  folder: string;
  tags: string[];
  /** The chat whose short-term memory the suggestion comes from. */
  chat_id: string;
  /** The short-term items it comes from; may be empty. */
  item_ids: number[];
  status: ProposalStatus;
  created_at: string;
  decided_at: string | null;
  /** The file id once kept. */
  result_id: string | null;
  chars: number;
}

/** One suggestion with its text. An agent wrote it: show it as plain text. */
export interface ProposalDetail extends Proposal {
  body: string;
  /** The server's sentence about who wrote it. */
  notice: string;
}

/** What the person changes when keeping. `remove_items` also removes the source items from short-term memory. */
export interface Landing {
  title?: string;
  folder?: string;
  remove_items?: boolean;
}

export interface AcceptedProposal extends Proposal {
  /** How many short-term items were removed. */
  removed: number;
}

const path = (id: string) => `/api/brain/proposals/${encodeURIComponent(id)}`;

/** Portcullis's /api/brain/proposals routes (chat.use), passed on to Stronghold. */
export const proposalsClient = {
  /** Waiting for the person's answer, newest first. */
  list: async () => (await apiRequest<{ proposals: Proposal[] }>("GET", "/api/brain/proposals")).proposals,
  get: (id: string) => apiRequest<ProposalDetail>("GET", path(id)),
  accept: (id: string, landing: Landing = {}) => apiRequest<AcceptedProposal>("POST", `${path(id)}/accept`, landing),
  decline: (id: string) => apiRequest<Proposal>("POST", `${path(id)}/decline`),
};
```

Create `apps/ember/src/features/proposals/stores/proposals.ts`:

```ts
import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { proposalsClient, type Landing, type Proposal } from "../api/ProposalsClient";

export function isDecidedProposalError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409 && err.message === "That suggestion is already decided.";
}

/** The suggestions agents made that wait for the person's answer, as the server holds them. The text is not kept
 * here (the dialog asks for it). Everything is private: `forget()` and a change of account drop it, and a reply that
 * arrives after that, or after a newer load, is ignored. Changes show only after the server answered. */
export const useProposalsStore = defineStore("proposals", () => {
  const auth = useAuthStore();
  const status = ref<"idle" | "loading" | "ready" | "error">("idle");
  const error = ref("");
  const items = ref<Proposal[]>([]);
  let loads = 0;
  let epoch = 0; // raised by forget(): a change that started before it must not write after it

  async function load(): Promise<void> {
    if (!auth.account) return;
    const run = ++loads;
    if (status.value !== "ready") status.value = "loading";
    try {
      const waiting = await proposalsClient.list();
      if (run !== loads) return;
      items.value = waiting;
      status.value = "ready";
      error.value = "";
    } catch (err) {
      if (run !== loads) return;
      error.value = errorMessage(err);
      status.value = status.value === "ready" ? "ready" : "error";
    }
  }

  /** Runs a change. Errors go to the caller, who shows the server's reason. */
  async function change<T>(work: () => Promise<T>): Promise<T> {
    const started = epoch;
    const refresh = () => (started === epoch && status.value !== "idle" ? load() : undefined);
    try {
      const result = await work();
      await refresh();
      return result;
    } catch (err) {
      if (isDecidedProposalError(err)) await refresh();
      throw err;
    }
  }

  const accept = (id: string, landing?: Landing) => change(() => proposalsClient.accept(id, landing));
  const decline = (id: string) => change(() => proposalsClient.decline(id));

  function forget(): void {
    epoch++;
    loads++;
    status.value = "idle";
    error.value = "";
    items.value = [];
  }

  watch(() => auth.account?.id, forget, { flush: "sync" });

  return { status, error, items, load, accept, decline, forget };
});
```

- [ ] **Step 4: Run the tests**

Run: `pnpm exec vitest run src/features/proposals` and `pnpm exec vue-tsc -b`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add apps/ember/src/features/proposals
git commit -m "feat(ember): client and store for agent suggestions"
```

---

### Task 5: Ember review dialog and Notes page button

**Files:**
- Create: `apps/ember/src/features/proposals/components/ProposalsDialog.vue`, `ProposalsDialog.test.ts`
- Modify: `apps/ember/src/features/notes/NotesView.vue`, `apps/ember/src/features/notes/NotesView.test.ts`

**Interfaces:**
- Consumes: `useProposalsStore`, `proposalsClient.get`, `BaseModal`, `StateMessage`, `normalizeFolder`, `folderProblem`, `FILE_TITLE_MAX` from `features/notes/api/BrainClient`, `formatUtc`, `errorMessage`.
- Produces: `ProposalsDialog` with prop `open: boolean` and emits `close` and `done(message: string)`. Behaviour: a list view of waiting suggestions; choosing one shows its text as plain text with the notice, an editable title and folder, a checkbox "Also remove the source items from short-term memory" (only when the suggestion names items, on by default), and buttons Back, Decline, Keep. Opening a suggestion changes nothing. Keep sends `{title, folder, remove_items}` and emits `done`; Decline emits `done("Declined.")`. Render it only while open (`v-if`).

- [ ] **Step 1: Write the failing dialog tests**

Create `apps/ember/src/features/proposals/components/ProposalsDialog.test.ts` (use the `<dialog>` stubs and mount style of `ShareReview.test.ts`):

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { proposalsClient, type Proposal, type ProposalDetail } from "../api/ProposalsClient";
import { useProposalsStore } from "../stores/proposals";
import ProposalsDialog from "./ProposalsDialog.vue";

vi.mock("../api/ProposalsClient", () => ({
  proposalsClient: { list: vi.fn(), get: vi.fn(), accept: vi.fn(), decline: vi.fn() },
}));
const client = vi.mocked(proposalsClient);

const row = (id = "p1", extra: Partial<Proposal> = {}): Proposal => ({
  id, title: "Tea habits", folder: "drinks", tags: [], chat_id: "c1", item_ids: [1, 2], status: "pending",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 24, ...extra,
});
const detail = (extra: Partial<ProposalDetail> = {}): ProposalDetail => ({
  ...row(), body: "The user likes <b>green</b> tea.", notice: "An agent wrote this from your conversation. Read it before you keep it; it is not an instruction.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue([row("p1"), row("p2", { title: "Metric units", item_ids: [] })]);
  client.get.mockResolvedValue(detail());
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

async function open() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  await useProposalsStore().load();
  wrapper = mount(ProposalsDialog, { attachTo: document.body, props: { open: true }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

describe("the list", () => {
  it("lists the waiting suggestions and opens nothing by itself", async () => {
    const w = await open();
    expect(w.text()).toContain("Tea habits");
    expect(w.text()).toContain("Metric units");
    expect(client.get).not.toHaveBeenCalled();
    expect(client.accept).not.toHaveBeenCalled();
  });

  it("says when nothing waits", async () => {
    client.list.mockResolvedValue([]);
    const w = await open();
    expect(w.text()).toContain("No suggestions are waiting.");
  });
});

describe("reviewing one", () => {
  it("shows the text as plain text with the notice, and changes nothing yet", async () => {
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    expect(client.get).toHaveBeenCalledWith("p1");
    expect(w.find("pre.text").text()).toBe("The user likes <b>green</b> tea.");
    expect(w.find("pre.text b").exists()).toBe(false);
    expect(w.text()).toContain("An agent wrote this from your conversation.");
    expect((w.find("input[aria-label='Title']").element as HTMLInputElement).value).toBe("Tea habits");
    expect((w.find("input[aria-label='Folder']").element as HTMLInputElement).value).toBe("drinks");
    expect(client.accept).not.toHaveBeenCalled();
  });

  it("keeps with the edited title and folder and asks to remove the items", async () => {
    client.accept.mockResolvedValue({ ...row(), status: "accepted", removed: 2 });
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await w.find("input[aria-label='Title']").setValue("Green tea");
    await w.find("input[aria-label='Folder']").setValue("likes");
    const remove = w.find("input[type='checkbox']");
    expect((remove.element as HTMLInputElement).checked).toBe(true);
    await button(w, "Keep").trigger("click");
    await flushPromises();
    expect(client.accept).toHaveBeenCalledWith("p1", { title: "Green tea", folder: "likes", remove_items: true });
    const done = w.emitted("done");
    expect(done?.[0][0]).toContain("Kept");
    expect(done?.[0][0]).toContain("2");
  });

  it("does not offer to remove items when the suggestion names none", async () => {
    client.get.mockResolvedValue(detail({ item_ids: [] }));
    const w = await open();
    await button(w, "Metric units").trigger("click");
    await flushPromises();
    expect(w.find("input[type='checkbox']").exists()).toBe(false);
  });

  it("explains a bad folder in words and keeps Keep off", async () => {
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await w.find("input[aria-label='Folder']").setValue("../etc");
    expect(w.find("[role='alert']").text()).not.toBe("");
    expect(button(w, "Keep").attributes("disabled")).toBeDefined();
  });

  it("declines", async () => {
    client.decline.mockResolvedValue({ ...row(), status: "declined" });
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await button(w, "Decline").trigger("click");
    await flushPromises();
    expect(client.decline).toHaveBeenCalledWith("p1");
    expect(w.emitted("done")?.[0]).toEqual(["Declined."]);
  });

  it("shows the server's reason when keeping is refused and stays open", async () => {
    client.accept.mockRejectedValue(new ApiError(409, "Your long-term memory is full."));
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await button(w, "Keep").trigger("click");
    await flushPromises();
    expect(w.find("[role='alert']").text()).toBe("Your long-term memory is full.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("goes back to the list and drops the text", async () => {
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await button(w, "Back").trigger("click");
    expect(w.find("pre.text").exists()).toBe(false);
    expect(w.text()).toContain("Metric units");
  });
});
```

- [ ] **Step 2: Run and see it fail**

Run: `pnpm exec vitest run src/features/proposals/components`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement the dialog**

Create `apps/ember/src/features/proposals/components/ProposalsDialog.vue`:

```vue
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import { FILE_TITLE_MAX, folderProblem, normalizeFolder } from "../../notes/api/BrainClient";
import { proposalsClient, type Proposal, type ProposalDetail } from "../api/ProposalsClient";
import { isDecidedProposalError, useProposalsStore } from "../stores/proposals";

/** What agents suggested for long-term memory. A list, then one suggestion at a time: its text as plain text, an editable
 * title and folder, and Keep or Decline. Opening one changes nothing. The text is an agent's, so it is never shown as
 * markup and is dropped when the person goes back or this closes. Render it only while open (`v-if`). */
defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; done: [message: string] }>();

const store = useProposalsStore();
const auth = useAuthStore();
const chosen = ref<Proposal | null>(null);
const detail = ref<ProposalDetail | null>(null);
const loadError = ref("");
const title = ref("");
const folder = ref("");
const removeItems = ref(true);
const busy = ref(false);
const error = ref("");
let run = 0; // a late answer for a suggestion the person has left is dropped

const cleanFolder = computed(() => normalizeFolder(folder.value));
const problem = computed(() => folderProblem(cleanFolder.value));
const canKeep = computed(() => detail.value !== null && title.value.trim() !== "" && problem.value === "" && !busy.value);

function reset(): void {
  run++;
  chosen.value = null;
  detail.value = null;
  title.value = folder.value = error.value = loadError.value = "";
  removeItems.value = true;
  busy.value = false;
}
onBeforeUnmount(reset);
watch(() => auth.account?.id, () => { reset(); emit("close"); }, { flush: "sync" });

async function choose(proposal: Proposal): Promise<void> {
  reset();
  const mine = run;
  chosen.value = proposal;
  title.value = proposal.title;
  folder.value = proposal.folder;
  try {
    const found = await proposalsClient.get(proposal.id);
    if (mine !== run) return;
    detail.value = found;
    title.value = found.title;
    folder.value = found.folder;
  } catch (err) {
    if (mine === run) loadError.value = errorMessage(err);
  }
}

async function answer(work: () => Promise<string>): Promise<void> {
  if (busy.value || !detail.value) return;
  const mine = run;
  busy.value = true;
  error.value = "";
  try {
    const message = await work();
    if (mine === run) {
      reset();
      emit("done", message);
    }
  } catch (err) {
    if (mine === run) {
      error.value = errorMessage(err);
      if (isDecidedProposalError(err)) detail.value = null;
    }
  } finally {
    if (mine === run) busy.value = false;
  }
}

function keep(): void {
  if (!canKeep.value || !chosen.value) return;
  const proposal = chosen.value;
  void answer(async () => {
    const wanted = proposal.item_ids.length > 0 && removeItems.value;
    const done = await store.accept(proposal.id, { title: title.value.trim(), folder: cleanFolder.value, remove_items: wanted });
    const moved = done.removed > 0 ? ` ${done.removed} ${done.removed === 1 ? "item was" : "items were"} removed from short-term memory.` : "";
    return `Kept as a file${cleanFolder.value ? ` in ${cleanFolder.value}` : ""}.${moved}`;
  });
}
function decline(): void {
  if (!chosen.value) return;
  const id = chosen.value.id;
  void answer(async () => { await store.decline(id); return "Declined."; });
}
</script>

<template>
  <BaseModal :open="open" title="Suggestions from your agents" wide @close="emit('close')">
    <div v-if="open" class="suggestions">
      <template v-if="!chosen">
        <StateMessage v-if="store.status === 'idle' || store.status === 'loading'" kind="loading">Loading …</StateMessage>
        <StateMessage v-else-if="store.status === 'error'" kind="error" @retry="store.load()">Could not load suggestions: {{ store.error }}</StateMessage>
        <p v-else-if="store.items.length === 0" class="muted" role="status">No suggestions are waiting.</p>
        <ul v-else class="list">
          <li v-for="item in store.items" :key="item.id">
            <button type="button" class="row" @click="choose(item)">
              <span class="name">{{ item.title }}</span>
              <span class="meta">{{ formatUtc(item.created_at) }} · {{ item.chars }} characters</span>
            </button>
          </li>
        </ul>
      </template>
      <template v-else>
        <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
        <p v-else-if="!detail && !error" class="muted" role="status">Loading …</p>
        <template v-else-if="detail">
          <p class="untrusted" role="note">
            <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
            {{ detail.notice }}
          </p>
          <pre class="text">{{ detail.body }}</pre>
          <label class="field"><span class="label">Title</span><input v-model="title" type="text" aria-label="Title" :maxlength="FILE_TITLE_MAX" :disabled="busy" /></label>
          <label class="field"><span class="label">Keep it in folder</span><input v-model="folder" type="text" aria-label="Folder" maxlength="130" :disabled="busy" /></label>
          <p v-if="problem" class="error" role="alert">{{ problem }}</p>
          <label v-if="chosen.item_ids.length > 0" class="check">
            <input v-model="removeItems" type="checkbox" :disabled="busy" />
            <span>Also remove the source items from short-term memory</span>
          </label>
        </template>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
      </template>
      <div class="buttons">
        <button v-if="chosen" type="button" class="pill-btn ghost" :disabled="busy" @click="reset">Back</button>
        <button type="button" class="pill-btn ghost" :disabled="busy" @click="emit('close')">Close</button>
        <template v-if="chosen">
          <button type="button" class="pill-btn ghost" :disabled="busy || !detail" @click="decline">Decline</button>
          <button type="button" class="pill-btn primary" :disabled="!canKeep" :aria-busy="busy" @click="keep">Keep</button>
        </template>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
/* Copy the rules of `.review`, `.field`, `.label`, `.text`, `.untrusted`, `.error`, `.muted` and `.buttons` from
   ShareReview.vue (same tokens, same 44px inputs), rename `.review` to `.suggestions`, and add: */
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
.row { width: 100%; min-height: 44px; display: grid; gap: 2px; text-align: left; padding: var(--space-2) var(--space-3); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); cursor: pointer; }
.row .name { font-weight: 600; }
.row .meta { color: var(--text-muted); font-size: var(--text-sm); }
.check { display: flex; align-items: center; gap: var(--space-2); min-height: 44px; }
</style>
```

The `<style scoped>` block must use only tokens that exist in `style.css` and the radius tokens the radius test allows: replace every token name above with the real one used by `ShareReview.vue` and `FileList.vue` (check `--space-*`, `--surface-2`, `--border`, `--text-muted`, `--text-sm`, `--radius-md`), and keep `radiusScale.test.ts` green. Read `ShareReview.vue` lines 140 to 162 and copy its style rules instead of inventing new ones.

- [ ] **Step 4: Wire the Notes page**

In `apps/ember/src/features/notes/NotesView.vue`:
- Import `ProposalsDialog from "../proposals/components/ProposalsDialog.vue"` and `useProposalsStore from "../proposals/stores/proposals"`.
- `const proposals = useProposalsStore(); const suggesting = ref(false);`
- In the existing `onMounted(() => void store.load());` also call `void proposals.load();`. In the existing `onBeforeUnmount` also call `proposals.forget()` and set `suggesting.value = false`.
- Add a function:

```ts
function suggested(message: string): void {
  suggesting.value = false;
  notice.value = message;
  void store.load();
}
```

- In the `#actions` slot, before the "New file" button:

```vue
<button v-if="proposals.items.length > 0" type="button" class="suggestions-btn" :disabled="busy" @click="suggesting = true">
  Suggestions ({{ proposals.items.length }})
</button>
```

- At the end of the template (next to `ShareDialog`): `<ProposalsDialog v-if="suggesting" :open="suggesting" @close="suggesting = false" @done="suggested" />`.
- Give `.suggestions-btn` the same classes and style as the neighbouring ghost button in that slot (`pill-btn ghost` with a 44px height) instead of a new look; if the file uses a `ghost` class pattern already, reuse it.

In `apps/ember/src/features/notes/NotesView.test.ts` add, with the other mocks:

```ts
vi.mock("../proposals/api/ProposalsClient", () => ({
  proposalsClient: { list: vi.fn(), get: vi.fn(), accept: vi.fn(), decline: vi.fn() },
}));
vi.mock("../proposals/components/ProposalsDialog.vue", () => ({
  default: { props: ["open"], emits: ["close", "done"], template: '<button data-test="proposals-dialog" @click="$emit(\'done\', \'Kept as a file.\')">dialog</button>' },
}));
```

import `proposalsClient`, set `vi.mocked(proposalsClient).list.mockResolvedValue([])` in `beforeEach`, and add tests:

```ts
it("shows no Suggestions button when nothing waits", async () => {
  const w = await setup();
  expect(w.text()).not.toContain("Suggestions (");
});

it("shows the count, opens the dialog, and reloads the files after a keep", async () => {
  vi.mocked(proposalsClient).list.mockResolvedValue([{ id: "p1" } as never, { id: "p2" } as never]);
  const w = await setup();
  const open = w.findAll("button").find((b) => b.text() === "Suggestions (2)")!;
  expect(open).toBeDefined();
  client.list.mockClear();
  await open.trigger("click");
  await w.get("[data-test='proposals-dialog']").trigger("click");
  await flushPromises();
  expect(w.find("[data-test='proposals-dialog']").exists()).toBe(false);
  expect(w.text()).toContain("Kept as a file.");
  expect(client.list).toHaveBeenCalled();
});
```

Adjust selectors and the `notice` rendering check to what `NotesView.vue` actually shows (the page already has a `notice` ref; confirm where it renders).

- [ ] **Step 5: Run the tests**

Run in `apps/ember`: `pnpm exec vitest run src/features/proposals src/features/notes src/radiusScale.test.ts src/architecture.test.ts`, then `pnpm exec vue-tsc -b` and `pnpm test`.
Expected: all pass; the suite grows by the new tests only; no nav test changes.

- [ ] **Step 6: Commit**

```bash
git add apps/ember/src/features
git commit -m "feat(ember): review agent suggestions on the Notes page"
```

---

## Final checks

- [ ] Run each suite once more and record the counts against the baseline: Stronghold, Portcullis, Legion (touched tests), Ember (`pnpm exec vue-tsc -b`, `pnpm test`).
- [ ] Grep the repo for other places that list Stronghold's MCP tools or the Portcullis brain routes (`tool_brain_write` in docs, `brain/shares` in docs and tests) and update only statements this plan makes false.
- [ ] Add a line to `docs/superpowers/plans/2026-11-20-scope-roadmap.md`: row 20i links to this plan as `[Written](2026-11-21-plan-20i-agent-proposals.md)`.

## Manual checklist (the user runs these; do not claim them done)

- [ ] Start Stronghold, Legion, Portcullis and Ember. In a chat, tell the agent a lasting preference and add a short-term item. Ask it to keep it for good, or wait for it to suggest. The Notes page shows "Suggestions (1)".
- [ ] Open it: the text is plain text with the "An agent wrote this" notice. Nothing is in Notes yet. Keep with a changed title and folder: the file appears, `source` shows as written by an agent, and the chosen short-term items are gone only when the box was ticked.
- [ ] Decline one: it disappears; ask the agent to suggest the same thing again and it is told not to.
- [ ] Fill long-term memory to its file limit, then Keep: the page shows "You have reached the limit of N files." and the suggestion stays.
- [ ] Open the action log: "Kept a suggestion" and "Declined a suggestion" appear with no text.
- [ ] Sign out and in as another account: no suggestions of the first account show. Delete an account and check its suggestions are purged.
- [ ] At 375px the dialog fits, inputs are 44px high, light and dark themes read clearly.

## Self-review (writer)

- Spec line "Agents propose moving short-term items to long-term; the user accepts": Task 2 (tool), Task 1 and 3 (accept path), Task 5 (inbox). Covered.
- Placeholders: none left except the Baseline blanks the executor fills and the style block that must copy `ShareReview.vue` rules (stated with exact lines to copy).
- Type names match across tasks: `Proposal`, `ProposalDetail`, `Landing`, `AcceptedProposal`, `proposalsClient`, `useProposalsStore`, `isDecidedProposalError`, `BrainProposals`, `ProposalTools`, `brain_proposals`.

## Changes found during work

- Codex built Tasks 1 to 4 and committed them (`a8058653`, `05600d74`, `71b66aa8`, `5e84c2cf`), wrote Task 5 and stopped before committing it and before filling this section. Claude finished Task 5.
- Changes beyond the plan, found in the commits: `BrainFiles.create` takes an optional `record_id`; a proposal uses its own id as the file id, so a retry after a partial Keep reuses the file instead of making a second one. `apps/stronghold/src/schema/catalog.py` lists the new `brain_proposals` collection with its purge route. `test_mcp_mount.py` changed (new tool in the expected list).
- Dialog test fix: the "bad folder" test used `../etc`, which `normalizeFolder` turns into the valid folder `etc`. It now uses `a/b/c/d` (four levels, over the three-level limit).
- Assumption (c): no change needed in Portcullis for outside clients; no route list names `/api/brain/shares`, so none names `/api/brain/proposals`.
- Assumptions (a), (b), (d), (e): Codex did not record the results. The tests pass with the plan's snippets adapted where needed, so the assumptions held in effect (not separately written down).
- Final counts after finishing Task 5 (Claude reran all four; Stronghold, Portcullis and Legion ran in the Plan 20i worktree with the main checkout's Python environment, because the worktree's `.venv` folders are empty): Stronghold 1,076 passed (1,055 before); Portcullis 1,113 passed (1,103 before) with the same two known failures; Legion 1,488 passed, 6 deselected (same); Ember type check clean, 2,360 passed in 197 files (2,339 before).
- Not verified: a real chat where an agent calls the tool, a real Keep against a live Stronghold, the delete-account purge against a live Portcullis, phone-width layout. The manual checklist above is pending.
