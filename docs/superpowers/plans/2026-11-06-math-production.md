# Mathematics Production Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task.

**Goal:** Implement all six approved reliability/integration areas.
**Architecture:** Typed symbolic exchange, shared bounded worker envelopes, existing
caller identity/table registry, ephemeral progress, and independently verified operations.
**Tech Stack:** Existing Python/Pydantic/SymPy/asyncio/MCP/ctypes; no new dependencies.
**Spec:** `docs/superpowers/specs/2026-11-06-math-production-design.md`

## Global constraints

- Preserve existing solve/batch parameters and prior uncommitted work.
- Keep worker input/output/admission/deadline caps and caller-owned table access.
- No unsafe string evaluation, macro execution, persistent history, commit or deployment.
- Predicate trees depth<=16/nodes<=256; matrices<=8x8; derivatives order<=8; table pages<=32.

## Review focus

- Structured restrictions must preserve assumed facts and private/unsupported conditions.
- Continuation cannot silently upgrade approximate data or discard branch restrictions.
- Resource enforcement must be real on Windows/POSIX and isolated from server process.
- Progress/table adapters cannot leak another caller's data or change cell precision.
- Matrix/calculus/LaTeX output must retain domains, uncertainty, and normalization.

### Task 1: Workloads and structured exchange
- [x] Add failing corpus/equivalence/typed-condition and reuse tests.
- [x] Implement bounded AST codec, condition provenance, exact constant expressions,
      precondition checking, and continuation through current worker boundary.
- [x] Verify old and new solver behavior.

### Task 2: Resources and progress
- [x] Add real-child resource/telemetry and callback/progress regressions.
- [x] Implement native limits and bounded metrics; stream completed batch rows via MCP.
- [x] Verify cancellation/reaping and lifecycle behavior.

### Task 3: Table workflow
- [x] Add real registry ownership/precision/pagination/error tests.
- [x] Implement scoped numeric row adapter and table batch tool.
- [x] Verify MCP identity and both batch paths.

### Task 4: Advanced math and LaTeX
- [x] Add failing normalization/matrix/calculus tests.
- [x] Implement strict normalization and isolated typed worker operations.
- [x] Verify mathematical outputs/domains and existing two-parameter solve schema.

### Task 5: Documentation and final validation
- [x] Update complete runnable examples, supported scopes, resources, and help.
- [x] Independent review; fix findings with regressions.
- [x] Full Armory suite, frozen-lock check, diff check; record completion evidence.

## Progress

Authorized all six areas. Using inline implementation and TDD. Windows asyncio
tests need reviewed escalation because sandbox socketpair initialization hangs.

Completed 2026-11-06. LaTeX parser implemented as one isolated delegated task;
three independent reviews covered advanced math, conditions/continuation/resources,
and table/progress integration. Review regressions preserve selected-root facts,
approximation through symbolic continuations, real-domain uncertainty, principal
complex branch cuts and constant coefficients, and progress consumer isolation.
Combined tests exposed a retained table-adapter model across capability reloads;
adapter now exchanges plain mappings and reconstructs fresh boundary models.

Validation: 280 math tests passed. Full Armory suite: 1835 passed, 1 skipped,
6 existing warnings in 126.93 seconds. Native Windows allocation-refusal test
passed with a 64 MiB child budget and attempted 128 MiB allocation. Frozen uv
sync dry-run checked 72 packages and would make no changes. Tracked diff check
and separate new-source whitespace checks passed. POSIX limits implemented but
not executed on this Windows host. Work remains uncommitted and undeployed.
