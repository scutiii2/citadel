# Mathematics controls, verification, diagnostics, numerical solving, and performance

## Approved scope

The user requested all six proposed improvements to the existing math capability:
explicit solving intent; stronger verification; actionable unresolved results;
controlled numerical solving; auditable calculation traces; measured performance
improvements. Existing `tool_math_solve(equation, data)` and recursive bindings
remain compatible. Units, matrices, calculus, and LaTeX remain separate extensions.

## Input and result

The root `equation` accepts its existing string or an object containing:
`expression` (required), `solve_for` (list of root variable names, default inferred),
`domain` (`complex` default or `real`), `precision` (15–100 decimal digits),
`method` (`symbolic` default, `numeric`, or `auto`), `trace` (false default), and
optional `numerical` with up to eight `initial_guesses` dictionaries and/or a
single-variable real `bounds` dictionary. Guess values can be finite JSON numbers
or restricted constant expressions, including complex numbers. Bounded search
must remain inside its interval. Numerical execution requires supplied hints.
Nested equation values retain the original string-and-data shape.

Explicit targets determine which unknowns are solved; other undeclared variables
remain parameters. Binding outputs and local helpers remain simultaneous unknowns.
Reject absent/reserved/duplicate targets. Real domain applies to all variables and
results, including private helpers, with restrictions retained when realness is
conditional. Precision controls approximations and numerical residual tolerance.

Every result adds verification and completeness metadata, structured diagnostics,
optional actual calculation steps, engine version, and timing measurements. Each
solution retains its own verification evidence and conditions. Numeric candidates
have status `approximate`, no fabricated exact value, and completeness `partial`.
Numeric verification checks every original equation and domain restriction at
guard precision; candidates near singularities or outside supplied bounds are
rejected. Remove known nonzero numeric factors before solving and checking
residuals, without cancelling variable factors. Report normalized absolute
residuals, raw absolute residuals, and tolerance separately. Failure to find a root
remains unresolved, never proof of no solution. Fully eliminated scalar candidates
remain eligible for numerical verification against their original named bounds.

Unresolved diagnostics identify unsupported solving, missing parameter values,
unproved branches, invalid numerical hints, or failed convergence, with concrete
next actions. Partial relationships survive failed numerical fallback.

## Implementation decisions

Preserve safe AST construction and input/output/recursion bounds. Specialized
symbolic algorithms and constant-coefficient elimination remain the baseline.
Use a separate numerical engine around nsolve; never claim local root searches
enumerate all solutions. Explicit one-variable targets use solveset treating
non-target symbols as parameters; symbolic-coefficient degeneracies stay unresolved.
Check vanishing parameter-only leading and overall coefficients before symbolic
solving, including coefficients cancelled from candidates. Reconstructed helper
domains are checked before returning infinite sets as well as finite rows.

Trace only actions performed by the engine: binding constraints, substitutions,
solver selection, original-equation/domain checks. Bound trace length to 128 steps.
Record parse, symbolic/numeric solve, verification, worker initialization, queue,
startup, request, and total times. Measure existing cold execution first.

If startup dominates, reuse at most two local workers, with at most 16 admitted
requests, a 15-second queue/execution deadline, 30-second idle expiry, and eight
requests per worker before recycling. Reuse uses framed JSON pipes and an explicit
ready handshake. Exceptions, cancellation, timeout, bad protocol, and exceeded
limits retire and reap the worker before releasing capacity. No request objects or
calculation history are intentionally retained; clear symbolic caches per request.
Register shutdown cleanup through the capability's existing lifespan hook.
POSIX workers retain a 512 MiB memory ceiling and a bounded lifetime CPU budget;
per-request wall deadline remains enforced by the parent. No external service.

## Validation

Write failing behavioral tests before each implementation slice. Cover old strings
and exact two-parameter MCP schema; explicit target relations and zero-coefficient
branches; real/complex domain filtering; precision; verified/conditional/unknown
completeness; actionable diagnostics; numerical real and complex seeds, bounded
roots, missing guesses, bad seeds, poles and nonconvergence; actual trace actions;
worker reuse, isolation, recycling, idle/shutdown cleanup, cancellation, and recovery.
Run independent review, full Armory suite, lockfile check, and repeatable benchmark.
No commit, deployment, or live capability configuration change is requested.
