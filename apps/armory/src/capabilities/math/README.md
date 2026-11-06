# Mathematics

Deterministic arithmetic, symbolic equations, and controlled numerical solving using SymPy. The assistant
supplies equations and bindings; this capability computes results locally.
See [capability conventions](../README.md) for integration rules.

## Production workflows

All six tools accept exactly two public inputs. MCP injects progress context;
callers never supply identity or a progress callback parameter.

Results carry `structured_conditions` alongside readable conditions. Each fact
includes `source`, `predicate`, and `reusable`. Expression and predicate trees
are allowlisted, bounded to depth 16 and 256 nodes per fact. Unsupported/private
facts become opaque and cannot be used for continuation. `MathValue.expression`
preserves supported exact expressions without evaluating serialized code.
Constant bindings accept finite numbers or restricted finite numeric expressions
such as `"1/3"` and `"sqrt(2)"`; symbolic names are forbidden in constant values.
Set `approximate: true` only for explicitly approximate source values. That flag
propagates through calculations and subsequent continuations.

Use `tool_math_continue` with the complete previous result:

```json
{
  "equation": "z=y+1",
  "data": {"previous": "<previous SolveResult object>", "solution_index": 0, "bindings": []}
}
```

Replace the placeholder with the actual JSON object. `solution_index` selects one
solution family. Overrides can specialize its parameters but cannot change its
selected root or remove original restrictions. For scalar results use
`slot: "value"` and optional `value_name` (default `value`). Units are restored to
canonical magnitudes. Approximate reuse requires `allow_approximate: true`; all
subsequent results retain partial completeness, numeric verification, and no
exact-value claim. Opaque results require resubmitting the original problem.

`tool_math_batch` and `tool_math_table` send best-effort MCP progress notifications
when the client supplies a progress token. The message is JSON containing
`version: 1`, `completed`, `total`, and the complete indexed `record` with its
result. Delivery order follows completion; final records retain input order.
An isolated bounded queue prevents slow progress delivery from stalling math.
Each delivery has a 0.5-second budget; final drain has a 1-second budget.
Final `progress_delivered` and `progress_errors` describe delivery; all completed
records remain in the final response even if a notification failed.

After attaching a numeric CSV/Excel table and obtaining its real `table_id`, call:

```json
{
  "equation": "v=d/t",
  "data": {
    "table_id": "<attached table id>",
    "columns": {"d": "Distance", "t": "Time"},
    "bindings": [], "offset": 0, "limit": 32
  }
}
```

Column names must match exactly and reference numeric columns. Access uses current
request identity and the existing table registry's expiry/ownership rules. Values
come directly from stored cells, preserving their available precision. Shared
bindings are overridden by mapped row cells. Missing cells fail only their row.
Follow `source.next_offset` until null; no rows or history are persisted here.

## Matrices, calculus, and LaTeX

`tool_math_matrix(operation, data)` supports `add`, `subtract`, `multiply`,
`transpose`, `determinant`, `inverse`, `rank`, `rref`, and `solve` (`Ax=b`). Supply
one matrix, or two for binary operations/solve, each at most 8 by 8. Entries are
finite numeric constant expressions. Structural operations require exact algebraic
entries so zero tests are decidable. Singular inverse requests are invalid;
linear solves distinguish inconsistent and parametric systems. Matrix outputs
use `matrix`; rank/reduction include `rank` and `pivots`.

```json
{"operation":"solve", "data":{"matrices":[[[2,0],[0,4]],[[1],[1]]],"precision":30}}
```

`tool_math_calculus(expression, data)` accepts `operation` (`differentiate` or
`integrate`), `variable`, `domain` (default real), `precision` (15–100), optional
derivative `order` (1–8), and optional finite real integration `bounds`.
Indefinite integrals return a primitive in `value` and `integration_constant`;
add that arbitrary constant on each connected valid domain component. Candidate
primitives are verified by differentiation. Original denominator restrictions
survive cancellation. Unproved parameter domains retain conditional verification.
Complex principal log/power branches carry sufficient open-domain restrictions;
complex absolute values and inverse trigonometric branches are unsupported.
Definite integration requires proven continuity across the closed interval,
including original denominator holes; improper integrals/principal values are
unsupported and return unresolved.

```json
{"expression":"x^2", "data":{"operation":"integrate","variable":"x","bounds":[0,3]}}
```

Set `syntax: "latex"` in structured equation controls or matrix/calculus data.
Supported subset: fractions, square roots, approved functions, powers, parentheses,
absolute bars, `\\pi`, `\\cdot`, `\\times`, `\\div`, `\\left`/`\\right`,
roman variable names and simple subscripts. Bare adjacent letters mean products:
`mb` becomes `m*b`; use `\\mathrm{mass}` for a single multi-letter name.
LaTeX applies to root expressions/matrix entries/calculus expressions, not nested
binding equations or units. Unsupported commands, macros, environments, and nth
root syntax are rejected. Limits: 4096 characters, 1024 tokens, parser depth 32;
normalized output still passes the restricted math parser. `normalization`
exposes original text, normalized text, and interpretation notes.

```json
{"equation":{"expression":"y=\\frac{m b}{2}+x","syntax":"latex"},"data":[{"type":"constant","name":"m","value":5},{"type":"constant","name":"b","value":6},{"type":"constant","name":"x","value":5}]}
```

All new operations use the same async isolated workers and resource budgets.
Responses include enforced resource telemetry. Internal `runner.snapshot()` gives
aggregate counts/statuses/reuses, memory/CPU, and queue/total p50/p95/max over a
bounded window of 256 durations. No equations, values, or caller identifiers enter
these metrics. The versioned synthetic representative corpus is
`tests/math/fixtures/workloads.json`; generated equivalences independently check
fractions, equation order, and equivalent units.

Runnable non-blocking application example (from the Armory directory):

```python
import asyncio
from src.capabilities.math.domain import MathDesk
from src.capabilities.math.utils.runner import ProcessRunner

async def main():
    runtime = ProcessRunner()
    desk = MathDesk(runtime)
    try:
        first = await desk.solve("y=1/2", [])
        next_result, matrix, integral = await asyncio.gather(
            desk.continue_from("z=y+1", {"previous": first.model_dump()}),
            desk.matrix("inverse", {"matrices": [[[1, 2], [3, 4]]]}),
            desk.calculus("x^2", {"operation": "integrate", "variable": "x", "bounds": [0, 3]}),
        )
        print(next_result.model_dump_json())
        print(matrix.model_dump_json())
        print(integral.model_dump_json())
        print(runtime.snapshot())
    finally:
        await runtime.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Tools

| Tool | Purpose | Connection |
| --- | --- | --- |
| `tool_math_solve` | Evaluate expressions or solve recursive systems with targets, domains, verification, and optional numerical searches. | Local isolated SymPy workers |
| `tool_math_batch` | Evaluate the same formula over independent ordered records with per-record failures. | Local isolated SymPy workers |
| `tool_math_continue` | Reuse one selected prior solution with exact values, units, and structured restrictions. | Local isolated SymPy workers |
| `tool_math_table` | Apply a formula to a caller-owned attached table page. | Existing table registry and math workers |
| `tool_math_matrix` | Exact bounded matrix arithmetic, reduction, inversion, and linear solving. | Local isolated SymPy workers |
| `tool_math_calculus` | Differentiate or integrate with domain and branch evidence. | Local isolated SymPy workers |

## Slash commands

| Tool | Slash command | Parameters |
| --- | --- | --- |
| `tool_math_solve` | `/math solve` | <ul><li>`equation` (required): expression/equality string or structured controls below.</li><li>`data` (required): JSON list of bindings; `[]` when none.</li></ul> |
| `tool_math_batch` | `/math batch` | <ul><li>`equation` (required): shared string or controls.</li><li>`data` (required): 1–32 records with optional `id` and independent `data` bindings.</li></ul> |
| `tool_math_continue` | `/math continue` | `equation`, `data` containing previous result and selection. |
| `tool_math_table` | `/math table` | `equation`, `data` containing table id, column mapping, and page. |
| `tool_math_matrix` | `/math matrix` | `operation`, `data` containing one or two matrices. |
| `tool_math_calculus` | `/math calculus` | `expression`, `data` containing operation and variable. |

No `system_name` applies: calculations are local and require exactly two inputs.

## Typical workflow

| Sequence | Tool | Explanation |
| --- | --- | --- |
| 1 | `tool_math_solve` | Supply equation and recursive bindings. Read every solution branch and retain conditions and free parameters. |
| 2 (optional) | `tool_math_batch` | Reuse the formula/options across independent records; inspect each record's result. |

## Input

```json
{
  "equation": "y = m * b / 2 + x",
  "data": [
    {"type": "constant", "name": "m", "value": 5},
    {"type": "variable", "name": "x", "value": "m"},
    {"type": "equation", "name": "b", "value": {
      "equation": "b = (p + 4) / q",
      "data": [
        {"type": "constant", "name": "p", "value": 8},
        {"type": "constant", "name": "q", "value": 2}
      ]
    }}
  ]
}
```

This returns `y = 20`, `b = 6`, `m = x = 5`. Numeric inputs are interpreted as
exact decimal values: `0.1 + 0.2` gives `3/10` and an approximate decimal string.

Nested scopes inherit parent names, including unknowns, and can shadow helper
bindings. Only each nested equation's named output is visible in its parent.
Names declared in the same scope are available regardless of input order.
Nested equations must assign their binding name on the left; their data cannot
redefine that output. Every binding is a constraint, even when unused by the
main equation. Conflicting constraints make the whole request inconsistent.

Circular references are solved jointly: change `b` above to `b = (y + 4) / x`
with empty nested data to obtain `y = 14`, `b = 18/5`.

Unknown names remain mathematical unknowns. Root names appear in each solution's
`values`; private helper parameters use qualified names such as `b.p` when free.
`mb` means one variable: write `m * b` for multiplication.

## Optional equation controls

Existing strings remain valid. To configure a calculation, replace only the root
`equation` string with an object; the tool still has exactly two parameters:

```json
{
  "equation": {
    "expression": "cos(x) = x",
    "solve_for": ["x"],
    "domain": "real",
    "precision": 40,
    "method": "auto",
    "numerical": {"bounds": {"x": [0, 1]}},
    "trace": true
  },
  "data": []
}
```

| Field | Default | Meaning |
| --- | --- | --- |
| `expression` | Required | Existing string language, or a list of 1–16 equalities forming a simultaneous system. |
| `solve_for` | Inferred | Root names to solve; undeclared non-target variables remain parameters. |
| `domain` | `complex` | `real` applies to all variables, private helpers, and expression values. |
| `precision` | `15` | Decimal digits for approximations; integer from 15 to 100. |
| `method` | `symbolic` | `numeric` searches; `auto` searches after unresolved symbolic solving; `certified` isolates supported exact real polynomial roots. |
| `numerical` | None | Up to eight `initial_guesses` dictionaries and/or one-variable `bounds`. Required for a numerical search. |
| `trace` | `false` | Return up to 128 performed operations. |
| `assumptions` | `{}` | Root-variable `real`, `positive`, `nonnegative`, `nonzero`, `integer`, inclusive `min`/`max`. |
| `split_cases` / `case_limit` | `false` / `8` | Partition supported parameter-zero branches with 2–8 leaf capacity. |
| `units` / `output_units` | `{}` | Root input units and preferred numeric output units. |
| `result_unit` | None | Preferred unit for a plain expression's numeric result. |

For example, `{"expression":"x^2=y","solve_for":["x"]}` returns both
`x = -sqrt(y)` and `x = sqrt(y)`, with `y` a free parameter. A parameter that may
vanish can change the entire solution family: `m*x=0` solved for `x` stays
unresolved until the `m=0` branch is settled, even though `x=0` is a valid candidate.
Duplicate, reserved, and absent target names are rejected. Nested equation bindings
continue using their original string-and-data shape and inherit the root domain.

### Numerical searches

Use `numerical.initial_guesses`, such as `[{"x":0.5}]`, or complex seeds such as
`[{"x":"I"},{"x":"-I"}]`. String seeds use the same restricted math parser and
must be finite constant expressions. Guesses must cover remaining numerical
unknowns after safe elimination; extra guesses for eliminated root variables are
allowed. Independent parameters need constant bindings in `data`.

`numerical.bounds` uses one root variable and an ordered real interval, such as
`{"x":[3,4]}`. A remaining scalar unknown uses bisection; fully reconstructed
values are checked against their original named bounds. Out-of-interval results
are rejected even when found by a supplied seed. Bounds do not promise that every
root in the interval is enumerated. Up to eight seeded searches use at most 100
iterations each; one bounded search uses at most 512. The worker deadline still
limits total execution.

Every candidate is checked against **all original equations**, original function
and power domains, requested realness, and supplied bounds. Numerical checks use
10 guard digits and tolerance `10^-(precision-5)`. Known nonzero numeric factors
are removed before solving and checking residuals, so multiplying an equation by
`10^-30` cannot turn a non-root into an accepted root. `max_residual` is the
normalized absolute residual; `max_raw_residual` preserves its unnormalized value.
Near-zero normalized denominators or pole factors (within the square root of the
tolerance) are rejected conservatively; increase precision for valid nearby roots.

Numerical results have status `approximate`, verification `numeric`, completeness
`partial`, and `exact: null`. A small residual is numerical evidence, not an exact
existence proof or proof that no other roots exist. Failed searches remain
unresolved and retain available partial symbolic relationships.

## Supported mathematics and output

Use decimal numbers, names, parentheses, `+`, `-`, `*`, `/`, and `^` or `**`.
Approved single-argument functions: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`,
`sinh`, `cosh`, `tanh`, `exp`, `log`, `sqrt`, and `abs`.
`pi`, `E`, `i`, and `I` are reserved constants; approved function names cannot
be rebound. Trigonometric arguments use radians. Complex powers and elementary
functions follow SymPy's principal-branch conventions.

Results contain `status`, `solutions` (with `values[name].exact` and
`values[name].approximate`), optional expression `value`, `free_parameters`,
`solution_set`, `conditions`, and human-readable `message`. Each row preserves
correlations between variables, its own `conditions`, and its expression `value`
when applicable; never combine values or conditions from different rows.
Top-level conditions apply to every returned row. Additional evidence:

- `verification`: `exact`, `numeric`, `certified`, `conditional`, `unverified`, or
  `not_applicable`; includes checked equation/domain counts and numeric residuals
  with tolerance where relevant. Each solution also has its own verification.
- `completeness`: `complete`, `partial`, or `unknown`, independently of candidate
  verification. An exact verified answer alone does not prove all answers were found.
- `diagnostics`: stable codes, details, suggested next actions, and relevant names.
  Missing parameters, unproved branches, invalid hints, nonconvergence, poles, and
  resource failures are distinguished. Inspect these before retrying.
- `trace`: opt-in binding constraints, actual substitutions, attempted solver
  selection, and verification operations. These are engine actions, not AI reasoning.
- `engine`: name and version for reproducibility.
- `timings`: parse, symbolic solve, optional numerical solve, verification, worker,
  queue, startup, initialization, request, and total milliseconds. Worker total and
  request/parent totals include their component phases; do not sum all fields.
- `execution`: whether the worker was reused and its request number.

- `unique` / `multiple`: finite, checked solutions.
- `parametric`: free variables or an infinite symbolic solution set; retain conditions.
- `approximate`: numerically checked candidates from a partial local search.
- `certified`: exact real-polynomial root intervals/counts within the certificate scope below.
- `inconsistent`: no values satisfy the constraints and original denominator exclusions.
- `unresolved`: unsupported or conditional solutions; this does not mean no solution.
- `invalid` / `limited` / `timeout` / `error`: invalid input, exceeded bounds,
  deadline, or worker failure, respectively.

Safe affine substitution first resolves bindings and expresses requested outputs
without dividing by unknown coefficients. Remaining single-variable equations use
`solveset`, linear systems use `linsolve`, and supported nonlinear systems use
`nonlinsolve`. General transcendental equations and parameterizations whose missing
branches cannot be ruled out remain unresolved. General nonlinear parameterizations
can have unknown completeness even when their returned candidates verify exactly.
Arbitrary inequalities, calculus, matrices, LaTeX, and implicit multiplication are
outside this capability's input language.

Original division, logarithm, function-pole, and conditional power restrictions
survive simplification, including inside zero-multiplied terms. As in SymPy,
`0^0` evaluates to `1`; zero bases with negative or non-real exponents are excluded.

## Non-blocking Python usage

From `apps/armory`, save this example as a Python file and run `uv run example.py`:

```python
import asyncio

from src.capabilities.math.domain import MathDesk
from src.capabilities.math.utils.runner import ProcessRunner


async def main() -> None:
    """Run independent calculations concurrently without blocking the event loop."""
    runtime = ProcessRunner()
    desk = MathDesk(runtime)
    try:
        results = await asyncio.gather(
            desk.solve("x^2 = -1", []),
            desk.solve({"expression": "x^2=y", "solve_for": ["x"], "trace": True}, []),
            desk.solve({
                "expression": "cos(x)=x", "domain": "real", "precision": 40,
                "method": "auto", "numerical": {"bounds": {"x": [0, 1]}},
            }, []),
        )
        for result in results:
            print(result.model_dump_json(indent=2))
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
```

## Operation and bounds

No network, secrets, external service, calculation history, or custom settings.
Install locked dependencies with `uv sync --frozen`. Refresh capabilities in
ember_admin, then enable **Mathematics** through the normal controls. Existing
deployments discover new capabilities offline. The loader owns the standard
`configs/config_capabilities.json` entry; do not add live entries by hand.

Each server event loop admits at most 16 requests and executes at most two
workers at once. Reusable workers expire after 30 idle seconds and are recycled
after eight requests. The 15-second deadline includes queue wait and execution;
cleanup finishes before a slot is released. Workers are killed and reaped on
timeout, cancellation, protocol/worker failure, resource-limit responses, and
application shutdown. Workers enforce a 512 MiB memory ceiling and 128-second
lifetime CPU ceiling (eight 16-second budgets): POSIX uses address-space/CPU
rlimits; Windows uses a native Job Object with process-memory/process-CPU limits.
Startup fails closed if enforcement cannot be installed. These resource controls
supplement the 15-second wall deadline; they are not a code-execution sandbox.

Inputs: 64 KiB, depth 8, 64 total bindings, 32 total symbols, 4096 characters per
equation, 512 syntax nodes per expression, 100-digit numeric literals, numeric
exponent magnitude at most 1000. Output: 256 KiB. A restricted AST constructs
symbolic objects without `eval`, string `sympify`, or `parse_expr`.

Turn Mathematics off through capability controls to hide its tools; existing idle
workers still expire. Wrapper reloads preserve worker admission. Restart Armory
after changing `contract.py` or anything under `utils/`, since workers retain their
initialized engine and models. See [storage lifecycle](STATIC-GUIDELINES.md).

## Measured execution cost

Run `uv run python -m src.capabilities.math.utils.benchmark --requests 5` from
`apps/armory`. It compares identical `x^2=-1` calculations with fresh and reused
workers, reports phase medians, and closes every worker afterward.

One local Windows/Python 3.14 run on 2026-11-06 measured 1873 ms median cold latency,
1598 ms first pooled call, and 14.2 ms median warm latency (about 132× faster for
this small repeated example). Cold imports dominate this workload. Larger symbolic
and numerical calculations can be dominated by solving instead; these figures are
not a general speed guarantee. Production keeps the stricter eight-request budget;
the benchmark allows 32 to keep its repeated-run comparison separate from recycling.

## Systems, assumptions, and parameter cases

Use `{"expression":["x+y=5","x-y=1"]}` with empty `data` for `x=3,y=2`.
Lists contain equalities only. Direct and recursive equations are checked together.
Independent parameter-only constraints can resolve parameter values without solving
them from target relations.

For positive roots, use `{"expression":"x^2=4","assumptions":{"x":{"positive":true}}}`.
This returns only `x=2`. Integer assumptions exclude irrational roots; inclusive
`min`/`max` restrict free variables and solutions. Contradictory controls and absent
names are rejected. `nonzero` alone does not force complex variables to be real.
Active assumptions are returned explicitly, including those encoded in symbolic
properties, and apply to constants, finite candidates, and infinite sets.

Use `{"expression":"m*x=0","solve_for":["x"],"split_cases":true}` for explicit
`m=0` (free `x`) and `m!=0` (`x=0`) results. `cases` includes conditions, solutions,
free parameters, verification, completeness, and inconsistent leaves when present.
Flattened solution rows retain their branch conditions. Supported partitions use
finite numeric zeros of parameter polynomials of degree at most four, including
complex zeros, and parameter products. Symbolic Gaussian pivots detect rank changes
in linear systems. Unsupported structures such as infinitely many `sin(m)=0`
parameter zeros and exhausted case budgets stay unresolved. A rejected generic
candidate never proves unresolved exceptional branches impossible.

## Exact real-root certificates

```json
{
  "equation": {
    "expression": "x^2=2",
    "solve_for": ["x"],
    "domain": "real",
    "method": "certified",
    "precision": 30
  },
  "data": []
}
```

This returns a certified count of two distinct admissible roots, rational isolating
intervals, and multiplicities. Interval width is at most `10^-precision`. Printed
approximations use extra digits when needed to remain inside nondegenerate
intervals, after conversion back to canonical units. Exact rational point intervals
use `exact` as the authoritative value: a finite decimal cannot equal every rational.

Supported scope: one selected real variable; rational-coefficient polynomial or
rational system reducible by polynomial gcd; degree at most 32; supplied parameter
values; polynomial original-domain exclusions. Bounds and declared assumptions
filter roots exactly. Distinct counts and multiplicities are separate. Original
denominator roots are removed before certification. A zero root count gives
certified inconsistency within the supported scope.

`certificate.polynomial` is the common admissible polynomial after reduction and
exclusions. Bounds and intervals use canonical coordinates, with `certificate.unit`
when units are active. Certified solution rows report the selected target only;
derived helpers do not inherit an invented certified error bound. Transcendental
equations, unsupported singularities, unresolved parameters, complex-root rectangles,
identities, and plain expression evaluation receive explicit unsupported certificates.
Use symbolic/numeric modes for those requests.

## Physical units

```json
{
  "equation": {"expression":"v=d/t", "output_units":{"v":"km/h"}},
  "data": [
    {"type":"constant","name":"d","value":100,"unit":"m"},
    {"type":"constant","name":"t","value":5,"unit":"s"}
  ]
}
```

This returns `v=72`, `unit="km/h"`. Conversion factors are exact. Constants convert
to canonical SI magnitudes before solving. `units` declares unknown-variable units
and defaults for bindings without their own unit. Dimensions are checked before
simplification, so `length+0*time` is invalid. Unknown dimensions are inferred when
determined; ambiguity is reported instead of guessed. Sine/log require dimensionless
arguments; degrees convert to radians. Constant exponent arithmetic such as
`x^(1/2)` and `x^(1+1)` works.

Catalogue: `m km cm mm um`, `s ms us min h`, `kg g mg`, `A K mol cd`,
`Hz N Pa kPa MPa bar atm J kJ W kW`, `L mL`, `rad deg percent`, and `1`.
Combine using `*`, `/`, and integer powers from -12 to 12. Unit text is limited to
96 characters/64 syntax nodes, cumulative dimensional exponents to magnitude 64,
and cumulative scale cost to 1024 before scale arithmetic. Offset temperatures,
arbitrary definitions, implicit multiplication, and unknown names are rejected.

Guesses/bounds and assumption limits follow declared input `units`, then binding
units when applicable, otherwise canonical units. `output_units` affects display
only. Numeric outputs carry the indicated unit. Symbolic expressions/conditions
and certificate intervals use canonical SI coordinates, so symbolic outputs keep
canonical labels. Integer assumptions with units require an unscaled dimensionless
variable. Plain expressions can request `result_unit`.

## Independent formula batches

`tool_math_batch` has exactly two required parameters:

```json
{
  "equation": "y=2*x",
  "data": [
    {"id":"first", "data":[{"type":"constant","name":"x","value":2}]},
    {"id":"second", "data":[{"type":"constant","name":"x","value":5}]}
  ]
}
```

Results preserve order and include index/id and an independent `SolveResult` for
each record. Malformed records, invalid bindings, incompatible units, unresolved
calculations, and worker failures do not discard neighboring records. Mathematical
inconsistency is a successfully processed answer with no solutions. `success_count`
includes resolved/parametric/approximate/certified and inconsistent computations;
unresolved/input/runtime failures need attention.

Batches accept 1–32 records, run at most two record tasks, reuse worker limits,
cap aggregate input at 256 KiB/output at 1 MiB, and stop after 60 seconds. Completed
rows survive; unfinished rows receive timeouts after active processes are reaped.
Output-budget rows receive limited results. Split larger workloads across calls.

### Complete non-blocking batch example

From `apps/armory`, save as a Python file and run `uv run example.py`:

```python
import asyncio

from src.capabilities.math.domain import MathDesk
from src.capabilities.math.utils.runner import ProcessRunner


async def main() -> None:
    """Evaluate records with bounded workers and explicit lifecycle cleanup."""
    runtime = ProcessRunner()
    desk = MathDesk(runtime)
    try:
        result = await desk.batch("y=2*x", [
            {"id": "first", "data": [{"type": "constant", "name": "x", "value": 2}]},
            {"id": "second", "data": [{"type": "constant", "name": "x", "value": 5}]},
        ])
        print(result.model_dump_json(indent=2))
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
```
