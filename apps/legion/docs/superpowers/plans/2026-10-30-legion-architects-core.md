# Legion Architects Core Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement phase 1 of Legion Architects without enabling any architects.

**Architecture:** Extend agent-file validation and registry metadata first. Add shared DAG types and an executor with an injected async runner. Integrate a per-turn submit_plan session into both existing provider loops so their existing usage, streaming and tool-result history also cover plan repair and final synthesis.

**Tech Stack:** Python, asyncio, anyio, pytest; existing dependencies only.

**Spec:** `../../Brain/Projects/Legion Architects Spec.md` from the repository root, corrected section 3 on 2026-10-30; user request defines phase-1 scope.

## Global Constraints

- Branch `feat/legion-architects-core` from main; commit A, B, C separately; no push or PR.
- No architect JSON files, pipelines, approvals, router integration, Ember, Armory or gateway changes.
- Automatic recall stays; plan-mode skill text omits marking; legacy text unchanged.
- Model output is untrusted; validate before execution. Keep delegation depth unchanged.
- No new dependencies. No runtime skill marking.

## Review Focus

- Unoffered model tool calls must be rejected, even if hallucinated.
- Cancellation and timeouts must reach child requests without retrying writes.
- A capped catalog must authorize only architects whose complete lines are present.
- Multiple submit_plan calls in one round must not execute multiple plans.
- Usage and agent events must be recorded once, including retries.

## Task 1: A — agent schema and startup

**Files:** agent_spec.py, agent_registry.py, server.py, README.md; tests/test_architect_spec.py.

**Interfaces:** AgentSpec gains mode, kind, workers, prefetch and ArchitectLimits (12, 3, 120 seconds, 1 retry). Registry publishes kind/workers for architects.

- [x] Write and run failing tests for every architect rule, mode ownership, cross-file references, duplicate kinds, entry/port invariants, and registry metadata.
- [x] Implement validation with file/field errors; preserve legacy defaults. Existing supervisor uses load_dir and starts any enabled spec, so exercise it without adding a new role switch.
- [x] Run schema, registry and supervisor tests; commit A.

## Task 2: B — shared DAG

**Files:** roles/architect/{__init__,types,executor}.py; tests/test_dag_executor.py.

**Interfaces:** Step and Unit share id/depends_on/effect/tier; Plan holds steps; NodeResult carries status/output/error/usage. DagExecutor.run(nodes, runner, request_id) returns a map. runner(node, tier, dependency_results) is async. The real runner calls delegation.call in an anyio worker thread.

- [x] Write and run failing tests for validation, waves, parallel cap, retries/escalation, write safety, skip propagation, timeout and cancellation; include usage/events exactly once.
- [x] Implement validation before starting, bounded waves, cooperative cancellation and per-attempt limits. Reuse delegation's existing events and usage for real calls.
- [x] Run executor and existing delegation/cancellation tests; commit B.

## Task 3: C — plan-mode orchestration

**Files:** roles/orchestrator/{catalog,submit_plan,plan_runner,skill_recall}.py, agent_roles.py, agent_config.py, both language providers; tests/test_submit_plan.py and tests/test_plan_mode.py.

**Interfaces:** Catalog snapshot supplies text and authorized architect ids. submit_plan owns tool schema and validation. Per-turn session owns one repair allowance and executes one accepted plan through DagExecutor, returning JSON step results to the provider loop for final synthesis.

- [x] Write and run failing tests for catalog cap, untrusted plans, one repair then direct fallback, final synthesis, tool restrictions in both providers, runtime recall, and unchanged legacy skill text.
- [x] Inject catalog in place of roster, offer only ask_user/submit_plan, reject unoffered calls, disable further plan submission after acceptance or two failures. Bypass entry routing in plan mode without changing router code. Do not run architect provider loops before phase 2 exists.
- [x] Fill checklist from validated steps if it fits existing Checklist API; never offer update_plan in plan mode.
- [x] Run full `.venv_legion\Scripts\python -m pytest` from apps/legion; review diff and commit C.

## Open questions retained

Runtime skill marking, two-level Ember event display, and single-step final-call omission remain open. Always perform final synthesis. Duplicate-kind enforcement and agent-file mode placement are explicitly required by the user despite (?) in the spec. Router and approval questions belong to later phases.

## Execution record

- A: `c31d41a1`. Schema/startup regression run: 191 passed; expanded architect-only check: 41 passed.
- B: `af482d3b`. Executor/delegation/cancellation regression run: 49 passed.
- C: Full command from apps/legion: `.venv_legion\Scripts\python -m pytest` → `1388 passed, 8 warnings in 31.57s`. Legacy tests were run without edits. Warnings come from MCP's deprecated `streamablehttp_client`.
- Review: fresh read-only reviewer found no concrete in-scope findings. Its test attempt was sandbox-blocked; the main agent ran verification with elevated execution.
- Additional cancellation audit: paired end-event assertions failed for both Stop and timeout, then passed after call_worker closed the lifecycle when the cancelled thread bridge dropped late events. Focused executor/plan-mode/delegation run: 63 passed before the final full suite.
- Implementation choices where the spec gives no numeric value: catalog cap 8,192 characters; brief length 20–16,000 characters; step ids 1–64 characters. Complete architect lines take priority over worker lines; lines that cannot fit are omitted from both text and authorized ids.
- Conservative retry policy: orchestrator steps default to write because their brief may contain side effects; the future architect pipeline classifies individual units. Read units retry with escalating tiers; writes do not retry.
- Architect startup is verified with temporary definitions and mocked serving, not a live model/gateway. Calls fail explicitly until phase-2/3 pipelines exist. No tracked architect files were created; Ember stays legacy.
- Not verified: live LLM/architect pipeline, two-level Ember display, real remote cancellation latency or a running supervisor deployment. Router integration, approval gates and runtime skill marking remain out of scope.
