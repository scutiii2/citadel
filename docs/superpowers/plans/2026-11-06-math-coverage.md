# Mathematics Coverage Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task.

**Goal:** Deliver all six approved coverage improvements, keeping solve compatible.
**Architecture:** Typed controls feed bounded specialized engines; original-domain
verification, worker isolation, and two-parameter tools remain the shared boundary.
**Tech Stack:** Existing Python/Pydantic/SymPy/asyncio/MCP/uv; no new dependencies.
**Spec:** `docs/superpowers/specs/2026-11-06-math-coverage-design.md`

## Global constraints

- Preserve existing strings, recursive bindings, two solve inputs, and prior work.
- 16 equations, 32 symbols, eight case leaves, degree-32 certification, bounded units.
- 32 batch records, two active records, 60-second batch deadline, 256 KiB input/1 MiB output.
- No eval, external services, live config edits, commits, or deployment.

## Review focus

- Assumption filtering cannot hide valid zero-parameter branches or reject valid roots.
- Case partitions must be exhaustive before claiming completeness.
- Certificates must exclude original singularities and accurately count multiplicities.
- Units must be checked before cancellation and conversion must preserve exactness.
- Batch validation, cancellation, order, and output limits must isolate each record.

### Task 1: Systems and assumptions

Files: contract.py, solver.py, numerical.py, new utils/assumptions.py and tests.
Interfaces: expression string/list; root VariableAssumptions; candidate/domain checks.
- [x] Write/run failing systems and assumption tests.
- [x] Implement typed controls and assumption-aware symbols, domains, and checking.
- [x] Run new plus existing solver/numerical tests.

### Task 2: Parameter cases

Files: new utils/cases.py and tests; integrate symbolic orchestration.
Interfaces: bounded explicit case results with conditions and leaf completeness.
- [x] Write/run failing zero/nonzero/unsupported/budget tests.
- [x] Partition supported cases, preserve original constraints and domain checks.
- [x] Verify case coverage and all old default behaviors.

### Task 3: Certified roots

Files: new utils/certification.py and tests; typed certificate models.
Interfaces: rational real isolating intervals, multiplicities, explicit unsupported status.
- [x] Write/run failing interval/count/denominator/bounds/unsupported tests.
- [x] Implement exact polynomial reduction and isolation; expose certificate scope.
- [x] Verify root counts and original exclusions using exact arithmetic.

### Task 4: Units

Files: new utils/units.py and tests; bindings/parser/solver/numerical integration.
Interfaces: safe unit registry, canonical scaling, dimensional constraints, output units.
- [x] Write/run failing conversion/dimension/inference/hostile-unit tests.
- [x] Implement exact curated units and original-expression dimensional analysis.
- [x] Verify assumptions, numeric hints, and certificates with unitful inputs.

### Task 5: Batch and documentation

Files: domain.py, tool.py, contract.py, help/README/storage docs, read-only declaration tests.
Interfaces: tool_math_batch(equation,data), ordered bounded BatchResult.
- [x] Write/run failing real-worker batch/error/order/deadline/MCP tests.
- [x] Implement bounded producers and result/input caps; preserve ordinary solve.
- [x] Document complete runnable examples, supported limits, and activation.

### Task 6: Final validation

- [x] Obtain independent mathematical and integration reviews; fix findings with tests.
- [x] Run full Armory suite, frozen lockfile check, and diff check.

## Progress

User approved all six items. Existing uncommitted math work belongs to prior steps
of this conversation and will be preserved. Tests needing Windows asyncio run with
reviewed escalation because sandbox socketpair initialization hangs.

- All six features implemented without additional dependencies or deployment.
- Ruling: independent parameter-only affine constraints may resolve parameter
  values, reducing redundant zero-case leaves without dividing by unknown factors.
- Review fixes: Gaussian pivot rank-change conditions, unresolved exceptional
  branches after generic rejection, plain-expression certification scope, decimal
  enclosure, constant exponent arithmetic, cumulative unit scale/dimension limits,
  and raw MCP record boundaries preserving per-row validation. Failing regressions
  were observed before fixes; all three follow-up reviews confirmed scoped fixes.
- Final full Armory suite: 1743 passed, one skipped, six existing dependency
  warnings, 135.45 seconds. Focused CPU suite: 156 passed. Frozen lockfile dry run
  reports no changes; git diff --check passes. Existing uncommitted work preserved.
