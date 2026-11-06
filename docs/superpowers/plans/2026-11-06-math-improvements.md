# Mathematics Improvements Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Implement all six approved math-tool improvements without breaking callers.

**Architecture:** Extend root input with optional typed controls, preserve safe
symbolic constraints, verify every candidate, and separate numerical solving from
symbolic completeness. Measure and reduce execution overhead without weakening limits.

**Tech Stack:** Existing Python, Pydantic, SymPy/mpmath, asyncio subprocesses, MCP, uv.

**Spec:** `docs/superpowers/specs/2026-11-06-math-improvements-design.md`

## Global constraints

- Exactly two required parameters; existing equation strings and recursive data work.
- Real/complex controls; precision 15–100; explicit numerical hints required.
- Keep original domain restrictions; no eval or arbitrary code from input.
- Preserve bounded worker admission, deadline, termination, and reaping.
- No commit/deploy/live configuration edits; preserve existing uncommitted math work.

## Review focus

- Targeting must not divide away zero-coefficient branches.
- Verification of answers must not imply completeness of all answers.
- Approximate roots must not acquire invented exact values or pass pole checks.
- Hot reload and worker reuse must not discard newly added result fields or state.
- Timeout/cancellation/shutdown must reap retired workers and retain concurrency limits.

### Task 1: Controls and symbolic evidence

Files: `math/contract.py`, `domain.py`, `tool.py`, `utils/solver.py`, new
`utils/evidence.py`, and `tests/math/test_improvements.py`.

Interfaces: root `EquationSpec`; normalized `SolveRequest.options`; structured
verification/diagnostic/trace/timing result models; `solve_request` remains entry.

- [x] Write and run failing tests for target selection, real domain, precision,
      original-equation verification, conservative completeness, diagnostics, traces.
- [x] Implement typed controls, target-aware elimination, evidence collection,
      exact/conditional result verification, and bounded actual traces.
- [x] Run old and new solver/MCP tests; all must pass.

### Task 2: Controlled numerical solving

Files: new `utils/numerical.py`, `tests/math/test_numerical.py`; extend solver orchestration.

Interfaces: `solve_numerically(system, symbolic_result)` returns checked partial
numeric candidates with residual evidence and actionable failure diagnostics.

- [x] Write/run failing tests for real/complex seeds, bounds, precision,
      no-convergence/missing-data diagnostics, original domains, and numeric labeling.
- [x] Implement bounded nsolve attempts, high-precision verification, domain/bounds
      filtering, guarded fallback, and partial symbolic-result preservation.
- [x] Run all solver/numerical tests; expected all pass.

### Task 3: Measure and improve execution

Files: `utils/runner.py`, `worker.py`, new `benchmark.py`; capability lifecycle;
extend `tests/math/test_runner.py` and MCP tests.

Interfaces: transport returns JSON mappings revalidated by the fresh domain model;
runner closes workers explicitly; benchmark prints cold/warm phase measurements.

- [x] Record baseline cold latency. Add failing timing, worker-reuse, isolation,
      expiry, recycling, shutdown, cancellation, and schema compatibility tests.
- [x] Implement phase measurements and, if baseline warrants it, bounded reusable
      workers with framed JSON, ready handshake, recycling, and lifecycle cleanup.
- [x] Run runtime and MCP tests; benchmark before/after with identical examples.

### Task 4: Documentation and complete verification

Files: capability README/help/storage docs, this plan and spec.

- [x] Document controls, evidence, numeric limitations, traces, measured performance,
      resource and lifecycle behavior, and complete async usage examples.
- [x] Obtain independent review; add regression tests and fix actionable findings.
- [x] Run full Armory suite, `uv sync --frozen --dry-run`, and `git diff --check`.

## Progress

Approved by user: all six improvements. Implementation remains inline. Existing
math files are uncommitted work from the preceding task and must be preserved.
Windows asyncio tests require reviewed escalation because sandbox socketpair setup
hangs; workspace-local pytest temp directories are used.

- Baseline: five original cold calls had median 1943.75 ms; one in-process core
  call took 215.05 ms. Startup dominated, warranting bounded worker reuse.
- Post-change identical benchmark: 1873.30 ms median cold, 1598.40 ms first pooled
  call, 14.16 ms median warm, 132.3x warm speedup for `x^2=-1` (five calls/mode).
- Ruling: raw JSON transport is validated by current domain models; retained
  result-class instances could discard new metadata after hot reload.
- Review regressions: parameter-only coefficients can vanish without candidate
  denominators; reconstructed helpers must obey real domains even for infinite
  sets; numerical residuals must remove known nonzero numeric scaling; bounds
  still apply after full elimination. All corrected with failing tests first.
- Lifecycle regressions: full stdout pipes require draining before waiting on an
  unadopted child; one-shot readers must be tracked; shutdown waits for creation
  ownership events instead of racing another stdout reader. Real subprocess
  regressions pass; independent follow-up review tested delayed-spawn shutdown
  and cancellation combinations without hangs or concurrent-reader failures.
- Final verification: 1676 Armory tests passed, one skipped, six existing
  dependency warnings, in 126.35 seconds. Focused solver/control/numerical tests
  (98) and runner/pool tests (18) passed. `uv sync --frozen --dry-run` reports no
  changes; `git diff --check` passes. Independent follow-up reviews found no
  additional actionable defects in scoped fixes. No commit or deployment made.
