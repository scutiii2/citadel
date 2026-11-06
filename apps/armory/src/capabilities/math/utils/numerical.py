"""Bounded local root searches with original-equation and domain verification."""

from __future__ import annotations

import sympy as sp

from src.capabilities.math.contract import MathValue, Solution, SolveResult, Verification
from src.capabilities.math.utils.parser import MathInputError, MathParser
from src.capabilities.math.utils.solver import _eliminate, _power_condition, _reconstruct
from src.capabilities.math.utils.conditions import encode_expression, source_conditions


class NumericalSolver:
    """Never infer completeness or inconsistency from a local numerical search."""

    def __init__(self, system) -> None:
        self.system = system
        self.options = system.options
        self.evidence = system.evidence
        self.precision = self.options.precision
        self.guard_precision = self.precision + 10
        self.tolerance = sp.Rational(1, 10 ** (self.precision - 5))
        self.symbols = system.targets + sorted(system.symbols - set(system.targets), key=str)
        self.normalized_constraints = [self._normalize(value) for value in system.constraints]

    @staticmethod
    def _normalize(expression):
        """Remove known nonzero numeric scaling without canceling variable factors."""
        expression = sp.factor_terms(sp.simplify(expression), clear=True)
        scale, primitive = expression.as_independent(*expression.free_symbols, as_Add=False)
        return primitive if scale.is_number and scale.is_finite is True and scale.is_zero is False else expression

    def _failure(self, base, code, detail, suggestion, variables=None, *, invalid=False):
        self.evidence.diagnose(code, detail, suggestion, variables)
        result = base.model_copy(deep=True) if base is not None else SolveResult(status="unresolved", message=detail)
        result.status = "invalid" if invalid else "unresolved"
        result.completeness = "unknown"
        result.message = detail + (" Partial symbolic relationships are retained." if result.solutions else "")
        return result

    @staticmethod
    def _seed(value):
        def reject_symbol(name):
            raise MathInputError(f"Numerical seeds must be constant expressions; found {name}.")

        parser = MathParser(reject_symbol)
        result = sp.simplify(parser.parse(str(value)))
        if result.free_symbols or result.is_number is not True or result.is_finite is not True:
            raise MathInputError("Numerical seeds must be finite constant expressions.")
        return result

    def _input_seed(self, name, value):
        return self._seed(value) * self.system.units.input_scale(self.system.root.symbols[name])

    def solve(self, base: SolveResult | None = None) -> SolveResult:
        hints = self.options.numerical
        if hints is None:
            return self._failure(base, "numerical_hints_required", "No controlled numerical search was attempted.",
                                 "Supply numerical.initial_guesses or numerical.bounds.")
        constraints = list(self.normalized_constraints)
        eligible = [symbol for symbol in self.symbols if symbol not in self.system.parameters]
        constraints, remaining, definitions = _eliminate(constraints, self.symbols, self.evidence,
                                                          parameters=self.system.parameters, protected=set(self.system.targets or eligible))
        remaining = [symbol for symbol in remaining if symbol not in self.system.parameters]
        constraints = [self._normalize(value) for value in constraints]
        resolved = dict(zip(self.symbols, _reconstruct(self.symbols, remaining, definitions, tuple(remaining))))
        parameter_symbols = set().union(*(value.free_symbols for value in constraints + list(resolved.values()))) - set(remaining)
        if parameter_symbols:
            names = sorted(map(str, parameter_symbols))
            return self._failure(base, "missing_parameters", "Numerical solving needs values for independent parameters.",
                                 "Supply constants for these parameters in data, including nested data for private helpers.", names)
        known = set(self.system.root.symbols)
        hint_names = set(hints.bounds).union(*(set(guess) for guess in hints.initial_guesses))
        if hint_names - known:
            return self._failure(base, "invalid_numerical_hints", "Numerical hints contain unknown variable names.",
                                 "Use root variable names from the equation and data.", sorted(hint_names - known), invalid=True)
        names = [str(symbol) for symbol in remaining]
        if hints.bounds and remaining and (len(remaining) != 1 or set(hints.bounds) != set(names)):
            return self._failure(base, "invalid_numerical_hints", "Bounds require exactly one remaining numerical unknown.",
                                 "Bound that variable or supply initial_guesses for a joint system.", names, invalid=True)
        for guess in hints.initial_guesses:
            missing = set(names) - guess.keys()
            if missing:
                return self._failure(base, "missing_initial_guesses", "Initial guess is missing numerical unknowns.",
                                     "Supply a guess for each listed unknown, or bind it to a constant in data.", sorted(missing))

        attempts: list[tuple[str, list[sp.Expr]]] = []
        if hints.bounds:
            low, high = next(iter(hints.bounds.values()))
            name = next(iter(hints.bounds))
            attempts.append(("bisect", [self._input_seed(name, low), self._input_seed(name, high)]))
        for guess in hints.initial_guesses:
            seeds = [self._input_seed(name, guess[name]) for name in names]
            if self.options.domain == "real" and any(value.is_real is not True for value in seeds):
                raise MathInputError("Real-domain numerical guesses must be real numbers.")
            attempts.append(("seed", seeds))
        if not remaining:
            attempts = [("constant", [])]
        elif not constraints:
            return self._failure(base, "underdetermined", "No equations determine the remaining numerical unknowns.",
                                 "Add independent equation or constant bindings in data.", names)

        solutions: list[Solution] = []
        accepted_rows: list[tuple] = []
        for method, seeds in attempts:
            self.evidence.record("numeric", f"Run {method} search for {', '.join(names) or 'fully constrained values'} at {self.precision} digits.")
            try:
                if method == "constant":
                    candidate = ()
                elif method == "bisect":
                    root = sp.nsolve(constraints[0], remaining[0], tuple(seeds), solver="bisect",
                                     prec=self.guard_precision, tol=self.tolerance**2, maxsteps=512, verify=True)
                    candidate = (root,)
                else:
                    root = sp.nsolve(constraints, remaining, seeds, prec=self.guard_precision,
                                     tol=self.tolerance**2, maxsteps=100, verify=True)
                    candidate = tuple(root)
            except (ValueError, ZeroDivisionError, OverflowError, TypeError, NotImplementedError):
                self.evidence.diagnose("no_convergence", "A numerical search did not converge to a usable candidate.",
                                       "Try different starting guesses or a bracket around a continuous real root.")
                continue
            row = _reconstruct(self.symbols, remaining, definitions, candidate)
            with self.evidence.measure("verification_ms"):
                solution = self._verify(row, hints.bounds)
            if solution is None:
                continue
            if any(all(sp.Abs(left - right).evalf(self.guard_precision) <= self.tolerance for left, right in zip(row, previous)) for previous in accepted_rows):
                continue
            accepted_rows.append(row)
            solutions.append(solution)
        if not solutions:
            return self._failure(base, "no_verified_roots", "No numerical candidates passed original-equation and domain checks.",
                                 "Try other guesses, different bounds, more precision, or supply additional constraints; this is not proof of no solution.")
        self.evidence.record("verify", f"Verified {len(solutions)} numerical candidates against original equations; local searches do not establish completeness.")
        maximum = max(sp.Rational(row.verification.max_residual) for row in solutions)
        raw_maximum = max(sp.Rational(row.verification.max_raw_residual) for row in solutions)
        return SolveResult(status="approximate", solutions=solutions,
                           value=solutions[0].value if len(solutions) == 1 else None, completeness="partial",
                           verification=Verification(status="numeric", equations_checked=len(self.system.constraints),
                                                     restrictions_checked=len(self.system.denominators) + len(self.system.power_domains),
                                                     max_residual=str(maximum.evalf(self.precision)), max_raw_residual=str(raw_maximum.evalf(self.precision)),
                                                     residual_kind="normalized_absolute", tolerance=str(self.tolerance.evalf(self.precision))),
                           message=f"{len(solutions)} numerically verified candidate(s) found; additional roots may exist.")

    def _verify(self, row, bounds) -> Solution | None:
        if any(value.is_number is not True or value.is_finite is not True for value in row):
            return None
        if self.options.domain == "real":
            if any(sp.Abs(sp.im(value)).evalf(self.guard_precision) > self.tolerance for value in row):
                self.evidence.diagnose("outside_domain", "Candidate is outside the requested real domain.", "Use complex domain or a real starting bracket.")
                return None
            row = tuple(sp.re(value) for value in row)
        substitutions = dict(zip(self.symbols, row))
        valid_assumptions, pending_assumptions = self.system.assumptions.check(substitutions)
        if not valid_assumptions or pending_assumptions:
            self.evidence.diagnose("outside_assumptions", "Candidate does not satisfy declared variable assumptions.",
                                   "Choose compatible guesses, bounds, or a symbolic/certified method for integer constraints.")
            return None
        valid_conditions, pending_conditions = self.system.conditions.check(substitutions)
        if not valid_conditions or pending_conditions:
            self.evidence.diagnose("outside_inherited_conditions", "Candidate violates or cannot verify inherited conditions.", "Choose compatible inputs or a different prior solution family.")
            return None
        for name, (low, high) in bounds.items():
            value = substitutions[self.system.root.symbols[name]]
            if value.is_real is not True or value < self._input_seed(name, low) or value > self._input_seed(name, high):
                self.evidence.diagnose("outside_bounds", "Candidate lies outside the supplied bounds.", "Use a bracket containing the desired root.")
                return None
        restrictions = [self._normalize(value).subs(substitutions, simultaneous=True).evalf(self.guard_precision) for value in self.system.denominators]
        if any(value.is_finite is not True or sp.Abs(value) <= sp.sqrt(self.tolerance) for value in restrictions):
            self.evidence.diagnose("near_singularity", "Candidate is at or too close to an original domain singularity.",
                                   "Increase precision or choose bounds away from denominator zeros and function poles.")
            return None
        if any(sp.simplify(_power_condition(base.subs(substitutions, simultaneous=True), exponent.subs(substitutions, simultaneous=True))) is not sp.S.true
               for base, exponent in self.system.power_domains):
            self.evidence.diagnose("outside_domain", "A power-domain restriction could not be verified.", "Choose a candidate in the power's defined domain.")
            return None
        residuals = [sp.Abs(value.subs(substitutions, simultaneous=True).evalf(self.guard_precision)) for value in self.normalized_constraints]
        raw_residuals = [sp.Abs(value.subs(substitutions, simultaneous=True).evalf(self.guard_precision)) for value in self.system.constraints]
        if any(value.is_finite is not True or value > self.tolerance for value in residuals):
            self.evidence.diagnose("residual_too_large", "Candidate does not satisfy all original equations within tolerance.",
                                   "Increase precision, adjust starting guesses, or check for conflicting equations.")
            return None
        def numeric_value(value, symbol=None):
            value, unit = self.system.units.output(value, symbol)
            return MathValue(approximate=str(value.evalf(self.precision)), unit=unit, expression=encode_expression(value))

        value = self.system.expression.subs(substitutions, simultaneous=True) if self.system.expression is not None else None
        if value is not None and (value.is_finite is not True or (self.options.domain == "real" and value.is_real is not True)):
            return None
        return Solution(values={name: numeric_value(substitutions[symbol], symbol) for name, symbol in sorted(self.system.root.symbols.items())},
                        value=numeric_value(value) if value is not None else None,
                        structured_conditions=source_conditions(self.system, substitutions, tolerance=self.tolerance, constraints=self.normalized_constraints),
                        verification=Verification(status="numeric", equations_checked=len(residuals), restrictions_checked=len(restrictions) + len(self.system.power_domains),
                                                  max_residual=str(max(residuals, default=sp.S.Zero).evalf(self.precision)),
                                                  max_raw_residual=str(max(raw_residuals, default=sp.S.Zero).evalf(self.precision)), residual_kind="normalized_absolute",
                                                  tolerance=str(self.tolerance.evalf(self.precision))))


def solve_numerically(system, symbolic_result: SolveResult | None = None) -> SolveResult:
    return NumericalSolver(system).solve(symbolic_result)
