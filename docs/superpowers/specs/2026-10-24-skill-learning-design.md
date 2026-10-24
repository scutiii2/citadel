# Learned skills for garrison agents (design draft)

Status: draft, nothing built. Inspired by the Hermes Agent learning loop (procedural memory).

## Goal
After a successful multi-tool turn, an agent can propose a reusable "skill" (a short how-to: when to use it, the steps, the tools involved). The user approves it. Later turns that match load the skill, so the agent does not rediscover the sequence.

## What already exists
- `armory/src/services/memory_store.py`: per-owner notes in SQLite with FTS5 search. `search()` already takes a query and ranks matches; only `memory_recall.py` calls it with an empty query (newest notes).
- `garrison/src/agents/memory_recall.py`: `with_recall()` prepends notes to the question at the start of a top-level turn. It is wired in `agent_config.py` (`depth == 0 and memory_recall`), opt-in per agent, best effort, 5 s timeout.
- `garrison/src/core/approvals.py` and `questions.py`: the ask-the-user flow, fails closed.
- `reviewer.json` denies `tool_mem_*` so output from other agents cannot be saved as notes.

## What is missing
1. A skill store (separate from notes: title, trigger text, steps, tools, success and failure counts, status `proposed | active | retired`).
2. A post-turn reflection step. `agent_config.py` has no hook after `run_chat` returns; the natural place is right after `result` is built (about line 247), for `depth == 0` only.
3. Query-based skill recall (reuse the FTS5 pattern; pass the question as the query).
4. An approval surface in ember_web (list proposed skills, approve, edit, retire).

## Design
- **Store:** new armory capability `skills` (contract/domain/tool split, see the `mcp-capability-scaffold` skill) with `tool_skill_propose`, `tool_skill_search`, `tool_skill_mark`. Same SQLite and FTS5 approach and owner-uid keying as memory.
- **Reflection:** opt-in agent key `skill_learning` (like `memory_recall`). Runs after a top-level turn that used at least N tools and did not fail. One extra LLM call on the cheap tier (the shared `context-summarizer` agent is a candidate). Output is a proposal only.
- **Approval:** proposals are stored as `proposed` and never loaded until the user approves them in ember_web. No auto-activation.
- **Recall:** `skill_recall` runs beside `with_recall`, searches with the question, injects at most 3 active skills under a label that says they are data, not instructions.
- **Feedback:** after a turn that loaded a skill, record success or failure. A skill with repeated failures is flagged for edit or retirement.

## Safety rules
- Never propose from a turn that read untrusted content (web scrape, email) unless the user confirms the text; the proposal shows the full text before approval.
- Deny `tool_skill_*` to `reviewer` and to any agent without a tool scope, as for `tool_mem_*`.
- Per-account scope only; no sharing between accounts.
- Off by default; each reflection call is billed, like the remote classifier settings.
- Cap: 50 active skills per account, 1,500 characters each.

## Build order
1. armory `skills` capability and store, with tests.
2. garrison skill recall (read side) behind `skill_recall`.
3. ember_api routes and ember_web approval page (follow `ember-feature-scaffold` and `ember-frontend-design`).
4. garrison reflection hook behind `skill_learning`.
5. Success and failure feedback and the retire flow.

Steps 1 to 3 are useful even without step 4, because the user can write skills by hand.

## Open questions
- Skill store in armory SQLite (matches memory) or `treasury` (matches notes)? Leaning armory for FTS5.
- Which agents get it first? Suggest `server-ops` and `pdf-assistant`.
- Should reflection run inside the turn (adds latency) or after the answer is streamed (preferred)?
