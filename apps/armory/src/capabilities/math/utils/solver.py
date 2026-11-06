"""Compile lexical bindings into constraints and preserve solution completeness."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

import sympy as sp
from sympy.solvers.solveset import NonlinearError

from src.capabilities.math.contract import (
    MAX_OUTPUT_BYTES, Binding, ConstantBinding, EngineInfo, EquationBinding, MathValue,
    Solution, SolveRequest, SolveResult, Verification,
)
from src.capabilities.math.utils.evidence import EvidenceCollector
from src.capabilities.math.utils.assumptions import AssumptionEngine, symbol_properties
from src.capabilities.math.utils.units import UnitSystem
from src.capabilities.math.utils.conditions import ConditionEngine, encode_expression, source_conditions
from src.capabilities.math.utils.parser import MathInputError, MathParser


@dataclass
class Scope:
    bindings: list[Binding]
    parent: Scope | None = None
    path: str = ""
    output: tuple[str, sp.Symbol] | None = None
    real: bool = False
    assumption_specs: dict = field(default_factory=dict)
    symbols: dict[str, sp.Symbol] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for binding in self.bindings:
            if binding.name in self.symbols or (self.output and binding.name == self.output[0]):
                raise MathInputError(f"Duplicate or redefined output binding: {binding.name}.")
            self.symbols[binding.name] = self._symbol(f"{self.path}{binding.name}")

    def _symbol(self, name: str) -> sp.Symbol:
        return sp.Symbol(name, **symbol_properties(self.assumption_specs.get(name), real=self.real))

    def resolve(self, name: str) -> sp.Symbol:
        if self.output and name == self.output[0]:
            return self.output[1]
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.resolve(name)
        self.symbols[name] = self._symbol(name)
        return self.symbols[name]


class ConstraintSystem:
    """All scopes share constraints but only root names appear as public values."""

    def __init__(self, request: SolveRequest, evidence: EvidenceCollector | None = None) -> None:
        self.options = request.options
        self.preconditions = request.preconditions
        self.case_predicates = []
        self.approximate_inputs = bool(request.provenance.get("approximate_inputs"))
        self.evidence = evidence or EvidenceCollector(self.options.trace)
        self.root = Scope(request.data, real=self.options.domain == "real", assumption_specs=self.options.assumptions)
        self.unit_equations: list[tuple] = []
        self.units = UnitSystem(self)
        self.constraints: list[sp.Expr] = []
        self.denominators: list[sp.Expr] = []
        self.power_domains: list[tuple[sp.Expr, sp.Expr]] = []
        self.symbols: set[sp.Symbol] = set()
        self.bound_symbols: set[sp.Symbol] = set()
        self.targets: list[sp.Symbol] = []
        self.expression: sp.Expr | None = None
        self.evidence.record("parse", f"Read {self.options.expression} over {self.options.domain} numbers.")
        if isinstance(self.options.expression, list):
            for equation in self.options.expression:
                if "=" not in equation:
                    raise MathInputError("Every entry in a direct equation system must be an equality.")
                self._compile(equation, self.root, expression_allowed=True)
        else:
            self._compile(self.options.expression, self.root, expression_allowed=True)
        self._bindings(self.root)
        if len(self.symbols) > 32:
            raise MathInputError("Input exceeds 32 symbols.", "limited")
        self.parameters: set[sp.Symbol] = set()
        self.incomplete_parameters = False
        self.case_coefficients: list[sp.Expr] = []
        if self.options.solve_for:
            missing = set(self.options.solve_for) - self.root.symbols.keys()
            if missing:
                raise MathInputError(f"Requested targets are absent from this system: {', '.join(sorted(missing))}.")
            self.targets = [self.root.symbols[name] for name in self.options.solve_for]
            self.parameters = self.symbols - set(self.targets) - self.bound_symbols
        self.assumptions = AssumptionEngine(self)
        self.units.analyze()
        self.conditions = ConditionEngine(self, self.preconditions)
        for predicate in self.conditions.predicates:
            if isinstance(predicate, sp.Equality):
                expression = sp.simplify(predicate.lhs - predicate.rhs)
                if expression not in self.constraints:
                    self.constraints.append(expression)

    def _parse(self, source: str, scope: Scope) -> sp.Expr:
        parser = MathParser(scope.resolve)
        value = parser.parse(source)
        self.denominators.extend(parser.denominators)
        self.power_domains.extend(parser.power_domains)
        self.symbols.update(parser.symbols)
        return value

    def _compile(self, equation: str, scope: Scope, *, expression_allowed: bool = False) -> None:
        parts = equation.split("=")
        if len(parts) == 1 and expression_allowed:
            self.expression = self._parse(equation, scope)
        elif len(parts) == 2 and all(part.strip() for part in parts):
            if scope.output and parts[0].strip() != scope.output[0]:
                raise MathInputError(f"Nested equation must assign {scope.output[0]} on its left side.")
            left, right = (self._parse(part, scope) for part in parts)
            if expression_allowed:
                self.targets = sorted(set(self.targets) | left.free_symbols, key=str)
            self.constraints.append(sp.Add(left, -right, evaluate=False))
            self.unit_equations.append((left, right))
        else:
            raise MathInputError("Use one equality sign, or a plain expression at the top level.")

    def _bindings(self, scope: Scope) -> None:
        for binding in scope.bindings:
            symbol = scope.resolve(binding.name)
            self.symbols.add(symbol)
            self.bound_symbols.add(symbol)
            self.evidence.record("binding", f"Bind {symbol} as {binding.type}.")
            if isinstance(binding, ConstantBinding):
                if isinstance(binding.value, str):
                    def reject_constant_symbol(name):
                        raise MathInputError(f"Constant expression contains variable {name}.")
                    magnitude = sp.simplify(MathParser(reject_constant_symbol).parse(binding.value))
                else:
                    magnitude = sp.Rational(str(binding.value))
                if magnitude.is_number is not True or magnitude.is_finite is not True:
                    raise MathInputError("Constant expressions must evaluate to finite numbers.")
                self.approximate_inputs |= binding.approximate
                self.constraints.append(symbol - magnitude * self.units.constant(symbol, binding.unit, magnitude))
            elif isinstance(binding, EquationBinding):
                child = Scope(binding.value.data, scope, f"{scope.path}{binding.name}.", (binding.name, symbol), real=scope.real,
                              assumption_specs=scope.assumption_specs)
                self._compile(binding.value.equation, child)
                self._bindings(child)
            else:
                reference = self._parse(binding.value, scope)
                self.constraints.append(symbol - reference)
                self.unit_equations.append((symbol, reference))


def _value(expression: sp.Expr, precision: int = 15, *, system=None, symbol=None) -> MathValue:
    expression = sp.simplify(expression)
    if expression.has(sp.zoo, sp.oo, -sp.oo, sp.nan):
        raise MathInputError("Expression is undefined or non-finite.")
    expression, unit = system.units.output(expression, symbol) if system is not None else (expression, None)
    return MathValue(exact=str(expression), approximate=str(expression.evalf(precision)) if expression.is_number else None, unit=unit,
                     expression=encode_expression(expression))


def _power_condition(base: sp.Expr, exponent: sp.Expr):
    # SymPy defines 0**0 as 1. At zero, other finite powers require a
    # nonnegative real exponent; nonzero bases accept complex exponents.
    return sp.Or(sp.Ne(base, 0), sp.And(sp.Eq(sp.im(exponent), 0), sp.Ge(sp.re(exponent), 0)))


def _condition_text(condition) -> str:
    if isinstance(condition, sp.Unequality):
        return f"{condition.lhs} != {condition.rhs}"
    return str(condition)


def _eliminate(constraints: list[sp.Expr], symbols: list[sp.Symbol], evidence: EvidenceCollector | None = None,
               *, parameters=None, protected=None):
    """Substitute only affine variables with constant nonzero coefficients.

    Dividing by unknown coefficients would lose their zero-valued branches.
    Reverse-order reconstruction preserves every eliminated variable exactly.
    """
    remaining = list(symbols)
    parameters = parameters or set()
    protected = protected or set()
    definitions: list[tuple[sp.Symbol, sp.Expr]] = []
    while True:
        chosen = None
        for symbol in remaining:
            for index, expression in enumerate(constraints):
                if not expression.has(symbol):
                    continue
                if symbol in parameters and expression.free_symbols & protected:
                    continue  # Independent parameters are not solved from target relations.
                try:
                    polynomial = sp.Poly(expression, symbol)
                except sp.PolynomialError:
                    continue
                coefficient = polynomial.coeff_monomial(symbol)
                if polynomial.degree() == 1 and coefficient.is_number and coefficient.is_zero is False:
                    chosen = symbol, index, -polynomial.coeff_monomial(1) / coefficient
                    break
            if chosen:
                break
        if chosen is None:
            break
        symbol, index, definition = chosen
        definitions.append((symbol, definition))
        if evidence:
            evidence.record("eliminate", f"Substitute {symbol} = {definition}; coefficient is constant and nonzero.")
        remaining.remove(symbol)
        constraints = [sp.simplify(expression.subs(symbol, definition)) for offset, expression in enumerate(constraints) if offset != index]
        constraints = [expression for expression in constraints if expression != 0]
    return constraints, remaining, definitions


def _reconstruct(symbols, remaining, definitions, row):
    substitutions = dict(zip(remaining, row))
    for symbol, expression in reversed(definitions):
        substitutions[symbol] = expression.subs(substitutions, simultaneous=True)
    return tuple(substitutions.get(symbol, symbol) for symbol in symbols)


def _zero_branch_excluded(denominator: sp.Expr, system: ConstraintSystem) -> bool:
    """Prove simple excluded parameter branches; otherwise preserve uncertainty."""
    if any(sp.simplify(denominator - value) == 0 or sp.simplify(denominator + value) == 0 for value in system.denominators):
        return True
    if not isinstance(denominator, sp.Symbol):
        if len(denominator.free_symbols) != 1:
            return False
        from src.capabilities.math.utils.cases import polynomial_zeros

        symbol = next(iter(denominator.free_symbols))
        roots = polynomial_zeros(denominator, symbol)
        if roots is None:
            return False
        return all(any(sp.simplify(value.subs(symbol, root)).is_zero is True for value in system.denominators) or any(
            not value.free_symbols and value.is_zero is False
            for value in (sp.simplify(expression.subs(symbol, root)) for expression in system.constraints)
        ) for root in roots)
    if any(sp.simplify(value.subs(denominator, 0)).is_zero is True for value in system.denominators):
        return True
    return any(
        not value.free_symbols and value.is_zero is False
        for value in (sp.simplify(expression.subs(denominator, 0)) for expression in system.constraints)
    )


def _parameter_degeneracy(system: ConstraintSystem, constraints, remaining) -> None:
    """Generic symbolic solving can cancel parameters even without a denominator."""
    if not system.parameters:
        return
    uncertain = set()
    pivot_coefficients = []
    if len(remaining) > 1:
        try:
            matrix, vector = sp.linear_eq_to_matrix(constraints, remaining)
        except NonlinearError:
            pass
        else:
            # Pivots expose parameter-dependent rank changes that original
            # leading coefficients miss. Record them before generic division.
            augmented = matrix.row_join(vector)
            pivot_row = 0
            for column in range(augmented.cols):
                selected = next((index for index in range(pivot_row, augmented.rows) if augmented[index, column] != 0), None)
                if selected is None:
                    continue
                augmented.row_swap(selected, pivot_row)
                pivot = sp.cancel(augmented[pivot_row, column])
                pivot_coefficients.append(sp.together(pivot).as_numer_denom()[0])
                for index in range(pivot_row + 1, augmented.rows):
                    factor = sp.cancel(augmented[index, column] / pivot)
                    for offset in range(column + 1, augmented.cols):
                        augmented[index, offset] = sp.cancel(augmented[index, offset] - factor * augmented[pivot_row, offset])
                    augmented[index, column] = 0
                pivot_row += 1
                if pivot_row == augmented.rows:
                    break
    for expression in constraints:
        coefficients = list(pivot_coefficients)
        independent, _ = sp.factor_terms(expression).as_independent(*remaining, as_Add=False)
        coefficients.append(independent)
        for symbol in remaining:
            try:
                polynomial = sp.Poly(expression, symbol)
            except sp.PolynomialError:
                continue
            if polynomial.degree() > 0:
                coefficients.append(polynomial.LC())
        for coefficient in coefficients:
            if coefficient.free_symbols and coefficient.free_symbols <= system.parameters and coefficient.is_zero is None:
                if not _zero_branch_excluded(coefficient, system):
                    uncertain.update(map(str, coefficient.free_symbols))
                    if coefficient not in system.case_coefficients and len(system.case_coefficients) < 32:
                        system.case_coefficients.append(coefficient)
    if uncertain:
        system.incomplete_parameters = True
        system.evidence.completeness = "unknown"
        system.evidence.diagnose("unproved_branches", "Parameter coefficients may vanish and change the solution family.",
                                 "Supply parameter values in data or solve the zero-coefficient cases separately.", sorted(uncertain))


def _solve(system: ConstraintSystem) -> SolveResult:
    symbols = system.targets + sorted(system.symbols - set(system.targets), key=str)
    constraints = [sp.simplify(expression) for expression in system.constraints]
    if any(expression.is_zero is False and not expression.free_symbols for expression in constraints):
        return SolveResult(status="inconsistent", message="Constraints have no simultaneous solution.")
    constraints = [expression for expression in constraints if expression != 0]
    if not symbols:
        if any(sp.simplify(value).is_zero is True for value in system.denominators) or any(
            sp.simplify(_power_condition(base, exponent)) is sp.S.false for base, exponent in system.power_domains
        ):
            raise MathInputError("Expression is undefined at a function or power singularity.")
        if system.options.domain == "real" and system.expression is not None and sp.simplify(system.expression).is_real is False:
            return SolveResult(status="inconsistent", completeness="complete", message="Expression has no value in the requested real domain.")
        system.evidence.record("verify", "Checked constant equality/expression and original domain restrictions.")
        return SolveResult(status="unique", value=_value(system.expression, system.options.precision, system=system) if system.expression is not None else None,
                           verification=Verification(status="exact", equations_checked=len(system.constraints),
                                                     restrictions_checked=len(system.denominators) + len(system.power_domains), max_residual="0"),
                           message="Expression evaluated." if system.expression is not None else "Equality is true.")

    eligible = [symbol for symbol in symbols if symbol not in system.parameters]
    constraints, remaining, definitions = _eliminate(constraints, symbols, system.evidence,
                                                      parameters=system.parameters, protected=set(system.targets or eligible))
    system.parameters.intersection_update(remaining)
    remaining = [symbol for symbol in remaining if symbol not in system.parameters]
    if any(expression.is_zero is False and not expression.free_symbols for expression in constraints):
        return SolveResult(status="inconsistent", message="Constraints have no simultaneous solution.")
    resolved = dict(zip(symbols, _reconstruct(symbols, remaining, definitions, tuple(remaining))))
    assumptions_valid, assumption_conditions = system.assumptions.check(resolved)
    if not assumptions_valid:
        return SolveResult(status="inconsistent", completeness="complete", message="Reconstructed values violate declared variable assumptions.")
    conditions_valid, inherited_conditions = system.conditions.check(resolved)
    if not conditions_valid:
        return SolveResult(status="inconsistent", completeness="complete", message="Reconstructed values violate inherited conditions.")
    if any(value.has(sp.zoo, sp.oo, -sp.oo, sp.nan) for value in resolved.values()) or (
        system.options.domain == "real" and any(value.is_real is False for value in resolved.values())
    ):
        return SolveResult(status="inconsistent", completeness="complete", message="Reconstructed values violate the requested domain.")
    resolved_restrictions = [sp.simplify(value.subs(resolved, simultaneous=True)) for value in system.denominators]
    resolved_powers = [sp.simplify(_power_condition(base.subs(resolved, simultaneous=True), exponent.subs(resolved, simultaneous=True)))
                       for base, exponent in system.power_domains]
    if any(value.is_zero is True for value in resolved_restrictions) or any(condition is sp.S.false for condition in resolved_powers):
        return SolveResult(status="inconsistent", completeness="complete", message="Reconstructed values violate original domain restrictions.")
    _parameter_degeneracy(system, constraints, remaining)
    if not remaining:
        rows = [()]
    elif len(remaining) == 1:
        symbol = remaining[0]
        system.evidence.record("solver", f"Use solveset for {symbol} over {system.options.domain} numbers.")
        domain = system.assumptions.domain_for(symbol, sp.S.Reals if system.options.domain == "real" else sp.S.Complexes)
        result_set = domain
        for expression in constraints:
            result_set = sp.Intersection(result_set, sp.solveset(expression, symbol, domain=domain))
        for denominator in system.denominators:
            excluded = sp.solveset(denominator.subs(resolved, simultaneous=True), symbol, domain=domain)
            result_set = sp.Complement(result_set, excluded)
        if result_set.has(sp.ConditionSet):
            return SolveResult(status="unresolved", solution_set=str(result_set), message="Solver could not determine a complete solution set.")
        if result_set == sp.S.EmptySet:
            if system.incomplete_parameters:
                return SolveResult(status="unresolved", message="Generic parameter case has no roots; zero-coefficient branches remain unresolved.")
            return SolveResult(status="inconsistent", message="Constraints have no simultaneous solution.")
        if isinstance(result_set, sp.Intersection):
            finite = [part for part in result_set.args if isinstance(part, sp.FiniteSet)]
            if finite and all(part == domain or isinstance(part, sp.FiniteSet) for part in result_set.args):
                # Finite candidates may retain a domain intersection because
                # parameter denominators or realness are conditional. Original
                # equations and explicit branch restrictions check them below.
                result_set = finite[0]
        if not isinstance(result_set, sp.FiniteSet):
            conditions = [f"{value} != 0" for value in resolved_restrictions if value.is_zero is None]
            conditions.extend(assumption_conditions)
            conditions.extend(inherited_conditions)
            conditions.extend(_condition_text(condition) for condition in resolved_powers if condition is not sp.S.true)
            if system.options.domain == "real":
                conditions.extend(f"im({value}) = 0" for value in resolved.values() if value.is_real is None)
            # Identity/free-symbol cases benefit from explicit symbolic rows.
            if not constraints:
                row = _reconstruct(symbols, remaining, definitions, tuple(remaining))
                return _rows(system, symbols, [row], [])
            conditions.extend(f"{name} = {value}" for name, value in resolved.items() if name != value)
            system.evidence.record("verify", "Checked reconstructed values and original domains before returning a symbolic solution set.")
            return SolveResult(status="unresolved" if system.incomplete_parameters else "parametric", solution_set=f"{symbol} in {result_set}", conditions=conditions,
                               completeness=system.evidence.completeness, free_parameters=sorted(map(str, {symbol} | system.parameters)),
                               message="Generic symbolic set omits unresolved parameter-zero branches." if system.incomplete_parameters else "Solution set is infinite or parametrized.")
        rows = [(value,) for value in result_set]
    elif not constraints:
        rows = [tuple(remaining)]
    else:
        try:
            system.evidence.record("solver", f"Try linsolve for {', '.join(map(str, remaining))}.")
            result_set = sp.linsolve(constraints, remaining)
        except NonlinearError:
            system.evidence.record("solver", "Use nonlinsolve after linear classification failed.")
            system.evidence.completeness = "unknown"
            result_set = sp.nonlinsolve(constraints, remaining)
            if result_set == sp.S.EmptySet and not all(expression.is_rational_function(*remaining) for expression in constraints):
                # nonlinsolve can return EmptySet for satisfiable radical systems.
                return SolveResult(status="unresolved", message="Solver could not establish solutions for this nonpolynomial system.")
        if result_set == sp.S.EmptySet:
            if system.incomplete_parameters:
                return SolveResult(status="unresolved", message="Generic parameter case has no roots; zero-coefficient branches remain unresolved.")
            return SolveResult(status="inconsistent", completeness="complete", message="Constraints have no simultaneous solution.")
        if not isinstance(result_set, sp.FiniteSet) or result_set.has(sp.ConditionSet):
            return SolveResult(status="unresolved", solution_set=str(result_set), message="Solver could not determine a complete solution set.")
        rows = list(result_set)
    if any(len(row) != len(remaining) or any(not isinstance(value, sp.Expr) for value in row) for row in rows):
        return SolveResult(status="unresolved", solution_set=str(rows), message="Solver returned a non-explicit solution set.")
    reconstructed = [_reconstruct(symbols, remaining, definitions, row) for row in rows]
    return _rows(system, symbols, reconstructed, [])


def _rows(system: ConstraintSystem, symbols: list[sp.Symbol], rows, conditions: list[str]) -> SolveResult:
    with system.evidence.measure("verification_ms"):
        return _checked_rows(system, symbols, rows, conditions)


def _checked_rows(system: ConstraintSystem, symbols: list[sp.Symbol], rows, conditions: list[str]) -> SolveResult:
    solutions: list[Solution] = []
    free: set[str] = set()
    unresolved = system.incomplete_parameters
    expression_values: list[MathValue] = []
    for row in sorted(rows, key=str):
        if len(row) != len(symbols) or any(not isinstance(value, sp.Expr) for value in row):
            return SolveResult(status="unresolved", solution_set=str(rows), message="Solver returned a non-explicit solution set.")
        substitutions = dict(zip(symbols, row))
        branch_conditions = set(conditions)
        assumptions_valid, assumption_conditions = system.assumptions.check(substitutions)
        if not assumptions_valid:
            continue
        branch_conditions.update(assumption_conditions)
        conditions_valid, inherited_conditions = system.conditions.check(substitutions)
        if not conditions_valid:
            continue
        branch_conditions.update(inherited_conditions)
        if any(value.has(sp.zoo, sp.oo, -sp.oo, sp.nan) for value in row):
            continue
        if system.options.domain == "real":
            if any(value.is_real is False for value in row):
                continue
            branch_conditions.update(f"im({value}) = 0" for value in row if value.is_real is None)
        restrictions = [sp.simplify(value.subs(substitutions, simultaneous=True)) for value in system.denominators]
        if any(value.is_zero is True or value.has(sp.zoo, sp.oo, -sp.oo, sp.nan) for value in restrictions):
            continue
        for value in restrictions:
            if value.is_zero is None:
                branch_conditions.add(f"{value} != 0")
        for value in row:
            denominator = sp.denom(value)
            if not denominator.free_symbols or denominator.is_zero is False:
                continue
            branch_conditions.add(f"{denominator} != 0")
            if not any(sp.simplify(denominator - original) == 0 or sp.simplify(denominator + original) == 0 for original in restrictions):
                if not _zero_branch_excluded(denominator, system):
                    unresolved = True
        power_conditions = [sp.simplify(_power_condition(
            base.subs(substitutions, simultaneous=True), exponent.subs(substitutions, simultaneous=True),
        )) for base, exponent in system.power_domains]
        if any(condition is sp.S.false for condition in power_conditions):
            continue
        branch_conditions.update(_condition_text(condition) for condition in power_conditions if condition is not sp.S.true)
        residuals = [sp.simplify(value.subs(substitutions, simultaneous=True)) for value in system.constraints]
        if any(value.is_zero is False for value in residuals):
            continue
        if any(value.is_zero is None for value in residuals):
            unresolved = True
            branch_conditions.update(f"{value} = 0" for value in residuals if value.is_zero is None)
        values = {name: _value(substitutions.get(symbol, symbol), system.options.precision, system=system, symbol=symbol) for name, symbol in sorted(system.root.symbols.items())}
        expression_value = _value(system.expression.subs(substitutions, simultaneous=True), system.options.precision, system=system) if system.expression is not None else None
        if system.options.domain == "real" and expression_value is not None and system.expression.subs(substitutions, simultaneous=True).is_real is False:
            continue
        if system.options.domain == "real" and expression_value is not None and system.expression.subs(substitutions, simultaneous=True).is_real is None:
            branch_conditions.add(f"im({expression_value.exact}) = 0")
        verification = Verification(status="conditional" if branch_conditions else "exact", equations_checked=len(residuals),
                                    restrictions_checked=len(restrictions) + len(power_conditions) + system.assumptions.count,
                                    max_residual="0" if all(value.is_zero is True for value in residuals) else None)
        solution = Solution(values=values, value=expression_value, conditions=sorted(branch_conditions), verification=verification,
                            structured_conditions=source_conditions(system, substitutions))
        if solution not in solutions:
            solutions.append(solution)
        free.update(str(symbol) for value in row for symbol in value.free_symbols)
        if expression_value is not None:
            expression_values.append(expression_value)
    if not solutions:
        if system.incomplete_parameters or system.evidence.completeness == "unknown":
            return SolveResult(status="unresolved", message="Generic candidates failed verification; unresolved exceptional branches may still have solutions.")
        return SolveResult(status="inconsistent", message="No solutions satisfy the original equations and denominator restrictions.")
    system.evidence.record("verify", f"Checked {len(solutions)} candidate rows against {len(system.constraints)} original equations and domain restrictions.")
    status = "unresolved" if unresolved else "parametric" if free else "unique" if len(solutions) == 1 else "multiple"
    if not unresolved and system.evidence.completeness == "unknown":
        if status == "unique":
            status = "unresolved"  # One verified candidate does not establish uniqueness.
        system.evidence.diagnose("completeness_not_established", "Returned nonlinear candidates verify, but exhaustive coverage was not established.",
                                 "Retain these candidates and their conditions; verify remaining branches before treating them as all solutions.", sorted(free))
    common_conditions = set.intersection(*(set(solution.conditions) for solution in solutions))
    common_structured = [record for record in solutions[0].structured_conditions if all(record in row.structured_conditions for row in solutions[1:])]
    if unresolved:
        system.evidence.diagnose("unproved_branches", "Completeness or parameter-zero branches could not be established.",
                                 "Supply values for free parameters or split zero and nonzero parameter cases explicitly.", sorted(free))
    return SolveResult(status=status, solutions=solutions, free_parameters=sorted(free), conditions=sorted(common_conditions),
                       structured_conditions=common_structured,
                       completeness="unknown" if unresolved else system.evidence.completeness,
                       verification=Verification(status="conditional" if any(row.verification.status == "conditional" for row in solutions) else "exact",
                                                 equations_checked=len(system.constraints),
                                                 restrictions_checked=len(system.denominators) + len(system.power_domains) + system.assumptions.count, max_residual="0" if not unresolved else None),
                       value=expression_values[0] if len(expression_values) == 1 else None,
                       message={"unique": "One solution found.", "multiple": f"{len(solutions)} solutions found.",
                                "parametric": "Solutions depend on free parameters; retain the listed conditions.",
                                "unresolved": "Candidate solutions retain conditions; completeness or excluded parameter branches could not be established."}[status])


def solve_request(request: SolveRequest) -> SolveResult:
    """CPU-bound worker entry: validate syntax, solve, and cap serialized output."""
    started = perf_counter()
    evidence = EvidenceCollector(request.options.trace)
    system = None
    normalization = None
    try:
        if request.options.syntax == "latex":
            from src.capabilities.math.contract import NormalizationInfo
            from src.capabilities.math.utils.latex import normalize_latex
            original = request.options.expression
            sources = original if isinstance(original, list) else [original]
            converted = [normalize_latex(source) for source in sources]
            normalized = [entry[0] for entry in converted]
            normalization = NormalizationInfo(original=sources, normalized=normalized,
                                              notes=list(dict.fromkeys(note for _, notes in converted for note in notes)))
            request = request.model_copy(update={"equation": request.options.model_copy(update={
                "expression": normalized if isinstance(original, list) else normalized[0], "syntax": "math"})})
        with evidence.measure("parse_ms"):
            system = ConstraintSystem(request, evidence)
        if system.approximate_inputs and system.options.method == "certified":
            raise MathInputError("Approximate inputs cannot establish an exact original-problem certificate.")
        if system.options.method == "certified":
            from src.capabilities.math.utils.certification import solve_certified

            with evidence.measure("solve_ms"):
                result = solve_certified(system)
        elif system.options.method == "numeric":
            result = None
        else:
            with evidence.measure("solve_ms"):
                result = _solve(system)
                if system.options.split_cases and system.incomplete_parameters:
                    from src.capabilities.math.utils.cases import solve_cases

                    result = solve_cases(system, result, _solve)
        symbolic_verification_ms = evidence.timings["verification_ms"]
        evidence.timings["solve_ms"] = max(0.0, evidence.timings["solve_ms"] - symbolic_verification_ms)
        if system.options.method == "numeric" or (system.options.method == "auto" and result.status == "unresolved"):
            from src.capabilities.math.utils.numerical import solve_numerically

            with evidence.measure("numeric_ms"):
                result = solve_numerically(system, result)
            evidence.timings["numeric_ms"] = max(0.0, evidence.timings["numeric_ms"] - (evidence.timings["verification_ms"] - symbolic_verification_ms))
        if result.completeness == "unknown" and result.status in {"unique", "multiple", "parametric", "inconsistent"}:
            result.completeness = evidence.completeness
    except MathInputError as error:
        result = SolveResult(status=error.status, message=str(error))
    except (NotImplementedError, TypeError) as error:
        result = SolveResult(status="unresolved", message=f"Unsupported symbolic problem ({type(error).__name__}).")
    except (ValueError, SyntaxError, ZeroDivisionError):
        result = SolveResult(status="invalid", message="Expression is invalid or undefined.")
    except (RecursionError, MemoryError, OverflowError):
        result = SolveResult(status="limited", message="Calculation exceeded symbolic resource limits.")
    if result.status == "unresolved" and not evidence.diagnostics:
        evidence.diagnose("unsupported_symbolic", result.message,
                          "Try method auto or numeric with initial guesses or bounds; supply missing parameter values when needed.")
    elif result.status in {"invalid", "limited"}:
        evidence.diagnose("invalid_input" if result.status == "invalid" else "resource_limit", result.message,
                          "Check syntax, target names, and documented input limits; split large problems into smaller constraints.")
    result.engine = EngineInfo(version=sp.__version__)
    result.normalization = normalization
    result.assumptions = request.options.assumptions
    result.provenance = request.provenance
    if system is not None and system.approximate_inputs:
        result.provenance = {**result.provenance, "approximate_inputs": True}
        result.completeness = "partial" if result.status != "inconsistent" else "unknown"
        if result.status in {"unique", "multiple"}:
            result.status = "approximate"
        elif result.status == "inconsistent":
            result.status = "unresolved"
        for row in result.solutions:
            for value in [*row.values.values(), *([row.value] if row.value else [])]:
                value.approximate = value.approximate or value.exact
                value.exact = None
            row.verification.status = "numeric"
        if result.value:
            result.value.approximate = result.value.approximate or result.value.exact
            result.value.exact = None
        result.verification.status = "numeric" if result.solutions or result.value else "not_applicable"
        result.message += " Results depend on explicitly approximate inputs."
    if system is not None and system.units.active:
        result.unit_convention = "Symbolic variables, conditions, and certificate intervals use canonical SI magnitudes; numeric outputs use their indicated units."
        from src.capabilities.math.utils.units import canonical
        result.symbol_units = {name: canonical(system.units.dimensions[symbol]) for name, symbol in system.root.symbols.items()
                               if system.units.dimensions.get(symbol) is not None}
    result.trace = evidence.steps
    result.diagnostics = evidence.diagnostics
    result.timings = evidence.timings
    result.timings["worker_ms"] = (perf_counter() - started) * 1000
    if len(result.model_dump_json().encode("utf-8")) > MAX_OUTPUT_BYTES:
        return SolveResult(status="limited", message="Solution output exceeds 256 KiB.")
    return result
