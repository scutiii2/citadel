# Mathematics coverage expansion

The user approved all six next improvements: parameter cases, per-variable
assumptions, certified roots, direct equation systems, dimensional units, and batch
evaluation. Existing solve calls remain compatible. Matrices/calculus/LaTeX remain
separate extensions, as stated at execution start.

## Input and behavior

Structured `equation.expression` accepts one string or up to 16 equality strings.
Existing strings and recursive bindings retain their meanings. New controls:

- `assumptions`: root-name mappings with `real`, `positive`, `nonnegative`,
  `nonzero`, `integer`, and inclusive `min`/`max`. Reject contradictory controls;
  check assumptions against original candidate values and symbolic sets. Report
  active assumptions so hidden Symbol properties do not conceal restrictions.
- `split_cases`: opt-in bounded symbolic partitioning, up to eight leaves. Split
  supported parameter-zero/nonzero cases; return explicit case conditions and
  leaf results. Unsupported or exhausted partitions remain unresolved. Never
  claim generic division covers zero coefficients.
- `method: certified`: exact real-root isolation for one rational-coefficient
  polynomial (or rational system reducible by polynomial gcd), degree <=32.
  Remove excluded denominator roots exactly, respect rational bounds and supported
  assumptions, report rational isolating intervals and multiplicities. Unsupported
  functions/coefficients/domains get an explicit unsupported certificate.
- `units` and `output_units`: optional root-name unit strings. Constant bindings
  can also declare `unit`. Convert constants to canonical SI magnitudes, check
  unsimplified equation dimensions, infer unknown dimensions where determined, and
  convert output magnitudes. Support curated SI/engineering units with an
  allowlisted multiplication/division/integer-power grammar, no offset units or
  arbitrary unit definitions. Numerical guesses/bounds and assumption limits use
  declared input units; certified interval metadata states canonical units.

Case results expose their assumptions, conditions, completeness, and solution
families, including inconsistent leaves. Certified intervals guarantee roots of the
admissible exact polynomial, not arbitrary local searches. Derived quantities are
not falsely assigned a certified error bound. Unit inference that is ambiguous
remains explicit rather than inventing dimensions. Integer assumptions are limited
to dimensionless variables when units are active.

## Batch capability

Add `tool_math_batch(equation, data)` and `/math batch` alongside existing solve.
`data` contains up to 32 `{id?, data:[bindings...]}` records. Evaluate identical
formula/options with independent data, at most two active record tasks, using
existing worker admission. Preserve order and per-record validation/math errors.
Cap aggregate input at 256 KiB, output at 1 MiB, and batch wall time at 60 seconds.
Cancel/reap active work at deadline and return completed records plus explicit
timeouts for unfinished rows. No new external service, storage, or dependency.

## Architecture and proof

Keep specialized modules under capability utils: assumptions, parameter cases,
certification, and units. Safe parser and process isolation remain unchanged.
Dimensional checks use original unevaluated expressions so simplification cannot
erase invalid additions. Exact conversions and root intervals use SymPy rationals.
All six features receive failing behavioral tests first, integration through the
two-parameter MCP surface, independent review, and full Armory regression suite.
No commit, deployment, or live configuration change is requested.
