# Mathematics production reliability and workflow integration

User approved all six proposed areas: workload regressions, structured conditions,
worker enforcement/metrics, progress with partial results, table/result workflows,
and additional matrix/calculus/LaTeX capabilities. Existing solve and batch calls
remain compatible. No deployment, commit, or live configuration change requested.

## Interfaces and bounded scope

- Add a versioned JSON workload corpus and generated equivalence/unit/branch tests.
- Add typed expression/predicate trees alongside readable conditions, with source
  provenance and explicit non-reusable opaque nodes. Preserve domain, assumption,
  branch, and residual restrictions. Decoding constructs allowlisted objects only.
- Enforce worker memory/CPU budgets using Windows Job Objects or POSIX rlimits,
  fail closed on unsupported enforcement, and return resource telemetry. Aggregate
  bounded latency/status/resource metrics without storing equations or cell data.
- Batch domain accepts an optional async progress callback emitting indexed complete
  rows. MCP sends progress notifications with those rows before the final result;
  cancellation and the existing 60-second deadline preserve cleanup. Do not create
  a persistent job/history service.
- Add caller-scoped table-to-batch adapter with explicit column/variable mapping,
  row offset, and page limit <=32, using existing table registry ownership checks.
  Copy only requested rows and numeric cells; no display rounding. Return row
  provenance and continuation offset. Registry reads run outside the event loop.
- Add exact prior-result continuation for a selected solution family, preserving
  typed conditions, units, and scope. Approximate reuse requires explicit opt-in,
  returns partial/numeric evidence, and cannot obtain an original exact certificate.
  Unsupported legacy/private/opaque conditions fail explicitly, never disappear.
- Add isolated matrix operations on up to two 8x8 finite constant matrices:
  add/subtract/multiply/transpose/determinant/inverse/rank/rref/Ax=b. Structural
  operations require decidable exact algebraic entries. Singular/underdetermined
  systems return explicit statuses; verify inverse/linear solutions exactly.
- Add isolated differentiation (orders 1–8) and indefinite/finite-interval
  integration with allowlisted scalar expressions. Definite integrals require
  provable continuity and no original-domain singularities on the closed path;
  improper/conditional/unevaluated integrals remain unresolved. Preserve domain
  restrictions and state integration constants; do not invent elementary forms.
- Add strict LaTeX expression subset: fractions, roots, powers, grouped expressions,
  approved elementary functions, constants, subscripts, explicit/implicit products.
  No arbitrary macros/environments. Return normalized math and interpretation
  notes; multi-letter variable names require explicit roman-name notation.

New advanced requests use a small discriminated worker envelope. All CPU work uses
existing worker deadlines, memory limits, admission, recycling, and output caps.
No external service or additional dependency is required. New tools follow Armory
registration, read-only declaration, help, and current-account identity conventions.

## Verification

Behavioral failing tests precede each slice. Include exact predicate round trips,
hostile/deep AST rejection, reuse preserving preconditions, numeric provenance,
Windows/POSIX enforcement in isolated children, resource metrics, real progress
ordering, table ownership/expiry/precision, matrix verification, calculus poles,
LaTeX ambiguity/normalization, MCP schemas, independent reviews, and full suite.
