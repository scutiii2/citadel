"""Validated recursive inputs and JSON-safe exact/approximate math results."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator, model_validator

MAX_INPUT_BYTES = 65_536
MAX_OUTPUT_BYTES = 262_144
MAX_DEPTH = 8
MAX_BINDINGS = 64
MAX_BATCH_INPUT_BYTES = 262_144
MAX_BATCH_OUTPUT_BYTES = 1_048_576
FUNCTIONS = frozenset({"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "exp", "log", "sqrt", "abs"})
RESERVED = FUNCTIONS | {"i", "I", "pi", "E"}
Name = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$", max_length=32)]
Equation = Annotated[str, Field(min_length=1, max_length=4096)]
FiniteNumber = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]
Seed = FiniteNumber | Annotated[str, Field(min_length=1, max_length=256)]
UnitText = Annotated[str, Field(min_length=1, max_length=96)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpressionNode(InputModel):
    kind: Literal["integer", "rational", "float", "symbol", "constant", "add", "multiply", "power", "function", "opaque"]
    value: Annotated[str, Field(max_length=2048)] | None = None
    args: list[ExpressionNode] = Field(default_factory=list, max_length=32)


class PredicateNode(InputModel):
    operator: Literal["eq", "ne", "gt", "ge", "lt", "le", "integer", "real", "finite", "and", "or", "not", "true", "false", "opaque"]
    arguments: list[ExpressionNode] = Field(default_factory=list, max_length=3)
    children: list[PredicateNode] = Field(default_factory=list, max_length=32)


class StructuredCondition(InputModel):
    predicate: PredicateNode
    text: Annotated[str, Field(max_length=4096)]
    source: Literal["domain", "assumption", "case", "verification", "solver", "imported"]
    reusable: bool = True


class NumericalOptions(InputModel):
    initial_guesses: list[Annotated[dict[Name, Seed], Field(min_length=1, max_length=32)]] = Field(default_factory=list, max_length=8)
    bounds: dict[Name, tuple[FiniteNumber, FiniteNumber]] = Field(default_factory=dict, max_length=1)

    @model_validator(mode="after")
    def validate_hints(self):
        if not self.initial_guesses and not self.bounds:
            raise ValueError("Numerical solving needs initial_guesses or bounds.")
        if any(lower >= upper for lower, upper in self.bounds.values()):
            raise ValueError("Each numerical lower bound must be less than its upper bound.")
        return self


class VariableAssumptions(InputModel):
    real: bool = False
    positive: bool = False
    nonnegative: bool = False
    nonzero: bool = False
    integer: bool = False
    min: FiniteNumber | None = None
    max: FiniteNumber | None = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Assumption min must not exceed max.")
        if self.positive and self.max is not None and self.max <= 0:
            raise ValueError("Positive assumptions conflict with a nonpositive maximum.")
        if self.nonnegative and self.max is not None and self.max < 0:
            raise ValueError("Nonnegative assumptions conflict with a negative maximum.")
        if self.nonzero and self.min == self.max == 0:
            raise ValueError("Nonzero assumptions conflict with a zero-only range.")
        return self


class EquationSpec(InputModel):
    expression: Equation | Annotated[list[Equation], Field(min_length=1, max_length=16)]
    syntax: Literal["math", "latex"] = "math"
    assumptions: dict[Name, VariableAssumptions] = Field(default_factory=dict, max_length=32)
    split_cases: bool = False
    case_limit: StrictInt = Field(default=8, ge=2, le=8)
    units: dict[Name, UnitText] = Field(default_factory=dict, max_length=32)
    output_units: dict[Name, UnitText] = Field(default_factory=dict, max_length=32)
    result_unit: UnitText | None = None
    solve_for: list[Name] = Field(default_factory=list, max_length=32)
    domain: Literal["complex", "real"] = "complex"
    precision: StrictInt = Field(default=15, ge=15, le=100)
    method: Literal["symbolic", "numeric", "auto", "certified"] = "symbolic"
    numerical: NumericalOptions | None = None
    trace: bool = False

    @model_validator(mode="after")
    def validate_controls(self):
        if len(set(self.solve_for)) != len(self.solve_for) or any(name in RESERVED for name in self.solve_for):
            raise ValueError("Targets must be unique, non-reserved variable names.")
        if self.method == "numeric" and self.numerical is None:
            raise ValueError("Numerical solving needs supplied initial_guesses or bounds.")
        if self.method == "symbolic" and self.numerical is not None:
            raise ValueError("Set method to auto or numeric when supplying numerical hints.")
        if self.method == "certified" and self.numerical is not None and self.numerical.initial_guesses:
            raise ValueError("Certified solving uses exact intervals; supply bounds rather than initial guesses.")
        return self


RootEquation = Equation | EquationSpec


class NamedBinding(InputModel):
    name: Name

    @field_validator("name")
    @classmethod
    def reject_reserved(cls, value: str) -> str:
        if value in RESERVED:
            raise ValueError(f"Reserved math name: {value}.")
        return value


class ConstantBinding(NamedBinding):
    type: Literal["constant"]
    value: Seed
    unit: UnitText | None = None
    approximate: bool = False

    @field_validator("value")
    @classmethod
    def limit_literal_digits(cls, value):
        if not isinstance(value, str) and sum(character.isdigit() for character in str(value)) > 100:
            raise ValueError("Numeric constants exceed 100 digits.")
        return value


class VariableBinding(NamedBinding):
    type: Literal["variable"]
    value: Name


class EquationValue(InputModel):
    equation: Equation
    data: list[Binding] = Field(max_length=MAX_BINDINGS)


class EquationBinding(NamedBinding):
    type: Literal["equation"]
    value: EquationValue


Binding = Annotated[ConstantBinding | VariableBinding | EquationBinding, Field(discriminator="type")]
EquationValue.model_rebuild()
EquationBinding.model_rebuild()


class SolveRequest(InputModel):
    kind: Literal["solve"] = "solve"
    equation: RootEquation
    data: list[Binding] = Field(max_length=MAX_BINDINGS)
    preconditions: list[StructuredCondition] = Field(default_factory=list, max_length=129)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def options(self) -> EquationSpec:
        return EquationSpec(expression=self.equation) if isinstance(self.equation, str) else self.equation

    @model_validator(mode="before")
    @classmethod
    def limit_recursive_input(cls, value):
        """Check the whole tree before recursive Pydantic validation allocates it."""
        if not isinstance(value, dict):
            return value
        count = 0
        pending = [(value.get("data", []), 0)]
        while pending:
            entries, depth = pending.pop()
            if depth > MAX_DEPTH:
                raise ValueError(f"Nested data exceeds depth {MAX_DEPTH}.")
            if not isinstance(entries, list):
                continue
            count += len(entries)
            if count > MAX_BINDINGS:
                raise ValueError(f"Input exceeds {MAX_BINDINGS} total bindings.")
            for entry in entries:
                if isinstance(entry, BaseModel):
                    entry = entry.model_dump()
                if isinstance(entry, dict) and entry.get("type") == "equation":
                    nested = entry.get("value")
                    if isinstance(nested, dict):
                        pending.append((nested.get("data", []), depth + 1))
        try:
            encoded = json.dumps(value, default=lambda item: item.model_dump()).encode("utf-8")
        except (ValueError, TypeError, AttributeError, RecursionError) as error:
            raise ValueError("Input must be a finite JSON tree.") from error
        if len(encoded) > MAX_INPUT_BYTES:
            raise ValueError(f"Input exceeds {MAX_INPUT_BYTES} bytes.")
        return value


class MathValue(BaseModel):
    exact: str | None = None
    approximate: str | None = None
    unit: str | None = None
    expression: ExpressionNode | None = None


class Verification(BaseModel):
    status: Literal["exact", "numeric", "certified", "conditional", "unverified", "not_applicable"] = "not_applicable"
    equations_checked: int = 0
    restrictions_checked: int = 0
    max_residual: str | None = None
    max_raw_residual: str | None = None
    residual_kind: Literal["absolute", "normalized_absolute"] = "absolute"
    tolerance: str | None = None


class Diagnostic(BaseModel):
    code: str
    detail: str
    suggestion: str
    variables: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    action: str
    detail: str


class EngineInfo(BaseModel):
    name: str = "sympy"
    version: str


class ExecutionInfo(BaseModel):
    worker_reused: bool = False
    worker_request: int = 1


class ResourceUsage(BaseModel):
    hard_limits: bool
    enforcement: Literal["windows_job", "posix_rlimit"]
    memory_limit_bytes: int
    cpu_limit_seconds: float
    peak_memory_bytes: int
    cpu_seconds: float
    cpu_total_seconds: float


class NormalizationInfo(BaseModel):
    syntax: Literal["latex"] = "latex"
    original: list[str]
    normalized: list[str]
    notes: list[str] = Field(default_factory=list)


class Solution(BaseModel):
    values: dict[str, MathValue]
    value: MathValue | None = None
    conditions: list[str] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)
    structured_conditions: list[StructuredCondition] = Field(default_factory=list, max_length=129)


class ParameterCase(BaseModel):
    conditions: list[str]
    status: str
    completeness: Literal["complete", "partial", "unknown"]
    solutions: list[Solution] = Field(default_factory=list)
    free_parameters: list[str] = Field(default_factory=list)
    solution_set: str | None = None
    verification: Verification = Field(default_factory=Verification)
    structured_conditions: list[StructuredCondition] = Field(default_factory=list, max_length=129)


class RootInterval(BaseModel):
    lower: str
    upper: str
    multiplicity: int


class RootCertificate(BaseModel):
    status: Literal["certified", "unsupported"]
    variable: str | None = None
    polynomial: str | None = None
    distinct_roots: int | None = None
    intervals: list[RootInterval] = Field(default_factory=list)
    lower_bound: str | None = None
    upper_bound: str | None = None
    unit: str | None = None
    method: str = "exact rational-polynomial real-root isolation"


class SolveResult(BaseModel):
    status: Literal["unique", "multiple", "parametric", "approximate", "certified", "inconsistent", "unresolved", "invalid", "limited", "timeout", "error"]
    solutions: list[Solution] = Field(default_factory=list)
    value: MathValue | None = None
    free_parameters: list[str] = Field(default_factory=list)
    solution_set: str | None = None
    conditions: list[str] = Field(default_factory=list)
    completeness: Literal["complete", "partial", "unknown"] = "unknown"
    verification: Verification = Field(default_factory=Verification)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    engine: EngineInfo | None = None
    timings: dict[str, float] = Field(default_factory=dict)
    execution: ExecutionInfo | None = None
    assumptions: dict[str, VariableAssumptions] = Field(default_factory=dict)
    cases: list[ParameterCase] = Field(default_factory=list, max_length=8)
    certificate: RootCertificate | None = None
    unit_convention: str | None = None
    structured_conditions: list[StructuredCondition] = Field(default_factory=list, max_length=129)
    provenance: dict[str, Any] = Field(default_factory=dict)
    symbol_units: dict[str, str] = Field(default_factory=dict)
    resources: ResourceUsage | None = None
    normalization: NormalizationInfo | None = None
    matrix: list[list[MathValue]] | None = None
    rank: int | None = None
    pivots: list[int] = Field(default_factory=list)
    integration_constant: str | None = None
    message: str


class MatrixOptions(InputModel):
    matrices: Annotated[list[Annotated[list[Annotated[list[Seed], Field(min_length=1, max_length=8)]], Field(min_length=1, max_length=8)]], Field(min_length=1, max_length=2)]
    precision: StrictInt = Field(default=15, ge=15, le=100)
    syntax: Literal["math", "latex"] = "math"


class MatrixRequest(InputModel):
    kind: Literal["matrix"] = "matrix"
    operation: Literal["add", "subtract", "multiply", "transpose", "determinant", "inverse", "rank", "rref", "solve"]
    data: MatrixOptions


class CalculusOptions(InputModel):
    operation: Literal["differentiate", "integrate"]
    variable: Name
    order: StrictInt = Field(default=1, ge=1, le=8)
    bounds: tuple[Seed, Seed] | None = None
    domain: Literal["real", "complex"] = "real"
    precision: StrictInt = Field(default=15, ge=15, le=100)
    syntax: Literal["math", "latex"] = "math"

    @model_validator(mode="after")
    def validate_operation(self):
        if self.variable in RESERVED:
            raise ValueError("Calculus variable must not be reserved.")
        if self.operation == "differentiate" and self.bounds is not None:
            raise ValueError("Derivative does not accept integration bounds.")
        if self.operation == "integrate" and self.order != 1:
            raise ValueError("Integration order must be one.")
        if self.bounds is not None and self.domain != "real":
            raise ValueError("Definite integration requires a real domain.")
        return self


class CalculusRequest(InputModel):
    kind: Literal["calculus"] = "calculus"
    expression: Equation
    data: CalculusOptions


class ContinuationInput(InputModel):
    previous: SolveResult
    solution_index: StrictInt = Field(default=0, ge=0, le=255)
    slot: Literal["solution", "value"] = "solution"
    value_name: Name = "value"
    bindings: list[Binding] = Field(default_factory=list, max_length=MAX_BINDINGS)
    allow_approximate: bool = False


class ContinuationRequest(InputModel):
    kind: Literal["continue"] = "continue"
    equation: RootEquation
    data: ContinuationInput


class BatchRecord(InputModel):
    id: Annotated[str, Field(max_length=64)] | None = None
    data: list[Binding] = Field(max_length=MAX_BINDINGS)


class BatchRow(BaseModel):
    index: int
    id: str
    result: SolveResult


class BatchProgress(BaseModel):
    version: Literal[1] = 1
    completed: int
    total: int
    record: BatchRow


class TableFormulaInput(InputModel):
    table_id: Annotated[str, Field(min_length=1, max_length=128)]
    columns: dict[Name, Annotated[str, Field(min_length=1, max_length=256)]] = Field(min_length=1, max_length=16)
    bindings: list[Binding] = Field(default_factory=list, max_length=32)
    offset: StrictInt = Field(default=0, ge=0, le=200000)
    limit: StrictInt = Field(default=32, ge=1, le=32)


class TablePageInfo(BaseModel):
    table_id: str
    offset: int
    rows: int
    total_rows: int
    next_offset: int | None = None


class BatchResult(BaseModel):
    status: Literal["completed", "partial", "invalid", "limited"]
    records: list[BatchRow] = Field(default_factory=list, max_length=32)
    success_count: int = 0
    failure_count: int = 0
    progress_delivered: int = 0
    progress_errors: int = 0
    source: TablePageInfo | None = None
    message: str
