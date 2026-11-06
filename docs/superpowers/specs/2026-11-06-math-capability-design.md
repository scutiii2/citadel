# Armory math capability

## Intent and approved approach

The assistant delegates arithmetic and equation solving to a deterministic tool.
The user approved an Armory capability backed by SymPy, recursive bindings,
simultaneous equations, and complex solutions. A separate MCP math service was
considered but adds deployment and configuration without a present requirement.

## Contract

`tool_math_solve(equation, data)` has exactly two required parameters.
`equation` is an expression or equality. `data` is a list of tagged objects:

- `{"type":"constant","name":"m","value":5}`
- `{"type":"variable","name":"x","value":"m"}`
- `{"type":"equation","name":"b","value":{"equation":"b = (p + 4) / q","data":[...]}}`

Constant values are finite JSON numbers. Variable values are symbol references.
Equation values reuse this contract recursively. Nested scopes inherit parent
bindings; local names shadow parents, except that the equation's output name
always refers to its enclosing binding. Local helpers never leak to their parent.
An absent symbol is an unknown, not an input validation error. Duplicate bindings
within a scope and reserved math names are rejected.

The main equality's left side identifies requested variables; when it is numeric,
all unknowns in that equality are requested. Expressions request their evaluated
value and any unresolved symbols. All binding equations are constraints, including
cyclic dependencies. Root binding values are included in solution rows.

Results distinguish unique, multiple, parametric, inconsistent, unresolved,
invalid, limited, timeout, and internal errors. Finite solutions contain exact
strings and 15-digit approximations when numeric. Each solution row keeps its own
domain conditions and expression value; top-level conditions are their intersection.
Infinite sets remain symbolic;
conditional/unsupported sets are never reported as complete solutions. Domain is
complex. Preserve denominator exclusions before simplification and verify candidate
solutions against original constraints.

## Execution and limits (implementation choices)

Use a restricted Python AST visitor to construct SymPy objects directly: numbers,
identifiers, arithmetic, `^`/`**`, and approved elementary function calls. No eval,
string sympification, attributes, indexing, comprehensions, or arbitrary calls.
Explicit multiplication is required; `mb` is a single symbol. `i`/`I`, `pi`, and
`E` are reserved constants. No inequalities, calculus, units, matrices, or LaTeX
in this first capability.

The async desk starts a fresh Python worker through stdin/stdout JSON, bounded to
two workers per server event loop and a 15-second deadline including queue time.
Timeout and caller cancellation kill and reap the worker before releasing its
slot. Limit total input to 64 KiB, nested depth to 8, total bindings to 64, symbols
to 32, AST nodes to 512 per expression, numeric literals to 100 digits, literal
exponents to absolute value 1000, and serialized output to 256 KiB. On POSIX the
worker also applies a 512 MiB address-space limit and CPU limit where available.
These limits bound common workloads; subprocesses are not a security sandbox.

First eliminate affine variables only when their coefficient is a nonzero numeric
constant, retaining all zero-valued branches of unknown coefficients. Then use
solveset for one unknown, linsolve for linear systems, and nonlinsolve for supported
nonlinear systems. Preserve log/function poles and conditional zero-base power
domains before simplification. Nonpolynomial EmptySet results and parameterizations
with unproved missing denominator-zero branches remain unresolved.
Unsupported general transcendental systems return
unresolved rather than guessed roots. No incomplete numerical-root search is
presented as all solutions.

## Integration and proof

Follow Armory's capability shape: typed contract, MathDesk domain service, thin
async MCP wrapper, capability identity `math`, help, and README. Declare read-only,
closed-world behavior and searchable metadata. Existing capability discovery and
formatting require no frontend changes. New capability starts offline on existing
deployments until enabled through normal capability controls.

Tests cover nested scope/shadowing, circular systems, rational and complex roots,
infinite/conditional sets, excluded denominators, inconsistent equations, hostile
syntax, bounded inputs, timeout/cancellation cleanup, concurrent calls, and actual
MCP input schema/dispatch. No network or persistent calculation state is needed.
