# Armory Math Capability Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delegate calculations and recursive equation systems to a dedicated tool.

**Architecture:** A typed Armory capability compiles scoped input into SymPy
constraints. An async desk runs each calculation in a bounded, terminable worker.

**Tech Stack:** Python 3.11+, Pydantic 2, SymPy, asyncio subprocesses, MCP, uv, pytest.

**Spec:** `docs/superpowers/specs/2026-11-06-math-capability-design.md`

## Global Constraints

- Exactly two required tool parameters: `equation` and `data`.
- Complex domain, lexical nested scopes, simultaneous constraint solving.
- No evaluation of input as Python; no secrets, external services, or stored state.
- Two workers, 15-second deadline, 64 KiB input, depth 8, 64 bindings, 32 symbols,
  512 AST nodes/expression, 100-digit literals, exponent magnitude 1000, 256 KiB output.
- Work in current clean checkout; do not commit, deploy, or edit live configuration.

## Review Focus

- Nested output bindings must refer to outer symbols even when helpers shadow names.
- Simplification must not admit roots excluded by original denominators.
- Infinite/conditional solution sets must not become misleading finite results.
- Timeout and cancellation must reap children and preserve concurrency capacity.
- MCP recursive schemas must remain valid and expose exactly two required parameters.

### Task 1: Safe recursive solver

**Files:** Create `apps/armory/src/capabilities/math/{__init__,contract,domain}.py`,
`utils/{__init__,parser,solver}.py`, `apps/armory/tests/math/test_solver.py`;
update `apps/armory/pyproject.toml` and `uv.lock`.

**Interfaces:** `SolveRequest(equation, data)`, `SolveResult`,
`solve_request(request: SolveRequest) -> SolveResult`.

- [x] Write failing tests for evaluation, nested/cyclic constraints, shadowing,
      complex/multiple/parametric/inconsistent results, denominator restrictions,
      unsafe syntax, duplicate/reserved bindings, and input bounds.
- [x] Run `uv run --no-sync pytest tests/math/test_solver.py -q`; confirm missing capability.
- [x] Add SymPy with uv; implement typed validation, allowlisted AST construction,
      lexical scopes, specialized solvers, checked output classification.
- [x] Run solver tests; expected all pass.

### Task 2: Bounded asynchronous execution

**Files:** Create `utils/{runner,worker}.py`,
`apps/armory/tests/math/test_runner.py`; complete `domain.py`.

**Interfaces:** `MathDesk.solve(equation: str, data: list[Binding]) -> SolveResult`
is async; worker reads one request and writes one result as JSON.

- [x] Write failing tests for real worker round trip, concurrent requests, deadlines,
      cancellation cleanup, admission bounds, and recovery after timeout.
- [x] Run runner tests; confirm feature failures.
- [x] Implement subprocess execution and structured failure results; kill/reap on
      timeout/cancellation; enforce bounded input/output and worker resource limits.
- [x] Run solver and runner tests; expected all pass.

### Task 3: MCP integration and documentation

**Files:** Create `tool.py`, `help.json`, `README.md`, `STATIC-GUIDELINES.md`,
`apps/armory/tests/math/test_tool.py`; update capability index and read-only test list.

**Interfaces:** `tool_math_solve(equation, data) -> SolveResult` async MCP tool,
capability id `math`, slash command `/math solve`.

- [x] Write failing schema/dispatch tests and update read-only expectation.
- [x] Run integration tests; confirm missing tool.
- [x] Register tool, metadata, command, help, and runnable async usage example.
- [x] Run `uv run --no-sync pytest -q` for Armory, inspect every failure, and
      run `git diff --check`. Obtain independent review and fix actionable issues.

## Progress

Design and implementation plan recorded after user approved recommended approach.
No commits requested. Local implementation proceeds without another approval gate.

- Task 1 complete: failing solver tests observed before implementation; 54 direct
  solver tests now pass, including independent-review regressions. Ruling: safe
  constant-coefficient affine elimination precedes specialized solvers because
  generic nonlinear parameterization can discard zero-valued branches. Domain
  conditions stay attached to individual branches; completeness is conservative.
- Task 2 complete: runner tests failed before implementation; nine tests pass for
  real subprocess math, concurrency, admission, timeout/cancellation cleanup,
  output limits, failed workers, and validation before spawning.
- Task 3 complete: two-required-parameter recursive MCP schema, actual dispatch,
  slash help, read-only declaration, and disable/reload tests pass. Independent
  code review found domain/completeness issues; regression tests and fixes added.
- Verification after all review fixes: full Armory suite passed 1622 tests, skipped
  one, with six existing dependency warnings (111.05 seconds). `uv sync --frozen
  --dry-run` reports no changes. `git diff --check` passes. Independent follow-up
  review found no additional concrete correctness defects in scoped fixes.
- Environment ruling: Windows sandbox hangs in asyncio's socketpair initialization;
  async tests run with reviewed escalation. Workspace-local pytest basetemp avoids
  sandbox temporary-directory creation failures. No production code workaround.
