# Shared Context Summarizer Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. The user authorized implementation in the current chat; proceed inline without another approval round.

**Goal:** Add one dedicated agent for Router context briefs, manual `/compact`, and automatic chat compaction.

**Architecture:** A supervised, non-delegable `context-summarizer` uses the existing Anthropic/OpenRouter light tier. Garrison calls its tool-free `interpret` operation for a bounded routing brief; Ember API directs existing compaction prompts to the same agent. Existing compaction owns transcript preservation, recompression, and accounting.

**Tech Stack:** Python, existing MCP clients, FastAPI, pytest. No new packages or UI.

**Spec:** Approved conversation design: short routing brief versus fuller continuation summary; latest user message remains verbatim; routing failure falls back; compaction failure preserves chat; separate usage attribution.

## Global Constraints

- No secrets, environment files, runtime registries, deployment overrides, model downloads, or external service mutations.
- The helper has no tools, memory recall, plan capability, orchestration, entry role, or delegation eligibility.
- Reuse configured light tier (`openrouter/free` in tracked defaults); no new provider.
- No additional persistent summary/cache: existing compacted history is available as input.
- Work on `codex/context-summarizer` in the shared workspace; no commit or push requested.

## Review Focus

- Failed/disabled helper: routing uses original subject; manual compaction leaves transcript intact; automatic compaction still answers.
- Cancelled routing: ignore late summaries and never dispatch work.
- Overlong/empty summaries: bounded, validated routing input with latest user message unchanged.
- Usage: helper work is attributed once, independently of Router voters and answer generation.
- First message, existing compacted summary, and follow-up: no invented context or cross-chat state; sufficient context permits tier selection for short follow-ups.

### Task 1: Agent and routing integration

Files: `apps/garrison/agents/context-summarizer.json`, `apps/garrison/src/agents/context_summarizer.py`, `apps/garrison/src/agents/router_routing.py`, `apps/garrison/tests/test_context_summarizer.py`, `apps/garrison/tests/test_router_integration.py`.

Interface: `async routing_brief(question: str, history: list[dict], request_id: str) -> str | None`; records returned agent usage in existing turn sink. Discover fixed helper ID through trusted registry, call existing MCP transport with internal identity, limit elapsed time, and fall back on missing/invalid response.

- [x] Write tests for historical context, compacted history, bounded input/output, fallback, cancellation, raw latest message, and usage attribution; run and observe failure.
- [x] Implement helper agent and client. Integrate summary as labeled context in Router subject. Keep current fallback, explicit tiers, approvals, and roster rules.
- [x] Run focused Garrison tests and agent configuration regressions.

### Task 2: Shared manual/automatic compaction

Files: `apps/Ember/ember_api/src/routes/chats.py`, `apps/Ember/ember_api/src/services/turns.py`, `apps/Ember/ember_api/src/app.py`, `apps/Ember/ember_api/src/services/summarization.py`, `apps/Ember/ember_api/tests/test_turns.py` and related summarization tests.

Interface: Resolve `context-summarizer` through existing `AgentDirectory`; retain existing `summarize(gateway, url, caller, messages)` interface and result/usage contract. Pass directory to `TurnRegistry` for automatic compaction.

- [x] Add tests demonstrating both manual and automatic compaction use helper URL and usage; helper absence/failure leaves stored messages intact or continues answering.
- [x] Implement directory discovery, bounded calls, and mode-specific prompt; preserve prior summaries, raw logs, exact values, tool digests, and recompression behavior.
- [x] Run focused Ember API compaction and turn tests.

### Task 3: Documentation and verification

- [x] Update Garrison and Ember API docs to explain shared agent, prompts, fallback, usage, and existing compacted-history reuse.
- [x] Run appropriate agent, routing, compaction, and turn regressions; inspect diff and whitespace.
- [x] Obtain an independent final review, address actionable findings, and report actual verification limits.

## Execution notes

- Catalog checked: cache absent and localhost:8020 unreachable. Reuse existing registry discovery, `delegation._call_tool`, and `delegation.record_usage`; tag new reusable helper with `@catalog`.
- Branch creation required sandbox escalation and succeeded; no automatic approval rejection.
- Ruling: implement in the visible shared checkout on a feature branch, avoiding a worktree relocation after the user explicitly authorized implementation here.
- Review fixes: both generation providers now honor per-agent `max_tokens` for `interpret`; completed synchronous interpretations persist usage before returning, correlated with routing request IDs when provided. Late remote inference may complete after caller timeout; its usage remains in the helper log rather than the finished account turn.
- Verification: final full Garrison suite: 1,232 passed (eight existing MCP deprecation warnings). Focused Ember API turn and compaction suite: 70 passed. The unrelated full API sweep was stopped after the focused checks passed; no full API success claim. No real provider call, credential inspection, deployment restart, commit, or push performed.
