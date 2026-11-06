"""Exact real-root isolation with explicit bounded certification scope."""

from __future__ import annotations

import sympy as sp

from src.capabilities.math.contract import ConstantBinding, MathValue, RootCertificate, RootInterval, Solution, SolveResult, Verification
from src.capabilities.math.utils.solver import _eliminate, _power_condition, _reconstruct
from src.capabilities.math.utils.units import canonical, parse_unit
from src.capabilities.math.utils.conditions import encode_expression, source_conditions


class CertificationUnsupported(ValueError):
    pass


def _polynomial(expression, symbol):
    try:
        polynomial = sp.Poly(expression, symbol, domain=sp.QQ)
    except (sp.PolynomialError, sp.CoercionFailed) as error:
        raise CertificationUnsupported("Certification requires rational-coefficient polynomials with no remaining parameters.") from error
    if polynomial.degree() > 32:
        raise CertificationUnsupported("Certified polynomial degree exceeds 32.")
    return polynomial


def _certify(system):
    if system.expression is not None:
        raise CertificationUnsupported("Certified mode requires equality constraints; use symbolic mode to evaluate a plain expression.")
    if system.options.domain != "real":
        raise CertificationUnsupported("This certificate supports real roots; request domain real.")
    targets = system.targets or sorted(system.symbols - system.bound_symbols, key=str)
    if not system.options.solve_for:
        constants = {system.root.resolve(binding.name) for binding in system.root.bindings if isinstance(binding, ConstantBinding)}
        targets = [target for target in targets if target not in constants] or targets
    if len(targets) != 1:
        raise CertificationUnsupported("Certification requires one selected target variable.")
    symbol = targets[0]
    symbols = sorted(system.symbols, key=str)
    eligible = [value for value in symbols if value != symbol]
    constraints, remaining, definitions = _eliminate(list(system.constraints), eligible, system.evidence,
                                                      parameters=system.parameters, protected={symbol})
    if remaining:
        raise CertificationUnsupported("Bind all independent parameters before requesting certification.")
    resolved = dict(zip(symbols, _reconstruct(symbols, [], definitions, ())))
    polynomial = None
    for expression in constraints:
        numerator, _ = sp.together(expression).as_numer_denom()
        current = _polynomial(numerator, symbol)
        if current.is_zero:
            continue
        polynomial = current if polynomial is None else sp.gcd(polynomial, current)
    if polynomial is None:
        raise CertificationUnsupported("An identity has infinitely many roots rather than finite isolating intervals.")
    for original in system.denominators:
        denominator = sp.simplify(original.subs(resolved, simultaneous=True))
        numerator, _ = sp.together(denominator).as_numer_denom()
        excluded = _polynomial(numerator, symbol)
        if excluded.is_zero:
            polynomial = sp.Poly(1, symbol)
            break
        while polynomial.degree() > 0:
            common = sp.gcd(polynomial, excluded)
            if common.degree() <= 0:
                break
            polynomial = polynomial.exquo(common)
    spec = system.assumptions.specs.get(symbol)
    if spec is not None and spec.integer and polynomial.degree() > 0:
        integer_roots = {root: multiplicity for root, multiplicity in polynomial.ground_roots().items() if root.is_Integer}
        expression = sp.prod((symbol - root)**multiplicity for root, multiplicity in integer_roots.items())
        polynomial = sp.Poly(expression, symbol, domain=sp.QQ)
    lower, upper = -sp.oo, sp.oo
    scale = system.assumptions.scale(symbol)
    if spec is not None:
        if spec.min is not None:
            lower = sp.Rational(str(spec.min)) * scale
        if spec.max is not None:
            upper = sp.Rational(str(spec.max)) * scale
    hints = system.options.numerical
    if hints and hints.bounds:
        if set(hints.bounds) != {str(symbol)}:
            raise CertificationUnsupported("Certificate bounds must name the selected target.")
        lo, hi = hints.bounds[str(symbol)]
        lower = max(lower, sp.Rational(str(lo)) * scale)
        upper = min(upper, sp.Rational(str(hi)) * scale)
    if any(value not in (-sp.oo, sp.oo) and value.is_Rational is not True for value in (lower, upper)):
        raise CertificationUnsupported("Certified interval bounds must convert to rational canonical magnitudes.")
    intervals = []
    solutions = []
    if polynomial.degree() > 0 and lower <= upper:
        isolated = polynomial.intervals(eps=sp.Rational(1, 10**system.options.precision))
        roots = polynomial.real_roots(multiple=False)
        for (root, multiplicity), ((left, right), isolated_multiplicity) in zip(roots, isolated):
            if multiplicity != isolated_multiplicity:
                raise CertificationUnsupported("Root multiplicity evidence did not align with isolation intervals.")
            if root < lower or root > upper:
                continue
            substitutions = {name: value.subs(symbol, root) for name, value in resolved.items()}
            if any(value.has(sp.zoo, sp.oo, -sp.oo, sp.nan) or value.is_real is False for value in substitutions.values()):
                continue
            if any(value.is_real is None for value in substitutions.values()):
                raise CertificationUnsupported("Reconstructed helper realness could not be decided exactly.")
            valid, pending = system.assumptions.check(substitutions)
            if not valid:
                continue
            if pending:
                raise CertificationUnsupported("A candidate's declared assumptions could not be decided exactly.")
            valid, pending = system.conditions.check(substitutions)
            if not valid:
                continue
            if pending:
                raise CertificationUnsupported("Inherited conditions could not be decided exactly.")
            power_conditions = [sp.simplify(_power_condition(base.subs(substitutions, simultaneous=True), exponent.subs(substitutions, simultaneous=True)))
                                for base, exponent in system.power_domains]
            if any(value is sp.S.false for value in power_conditions):
                continue
            if any(value is not sp.S.true for value in power_conditions):
                raise CertificationUnsupported("Original power-domain restrictions could not be decided exactly.")
            left, right = max(left, lower), min(right, upper)
            intervals.append(RootInterval(lower=str(left), upper=str(right), multiplicity=multiplicity))
            midpoint = (left + right) / 2
            magnitude, unit = system.units.output(midpoint, symbol)
            approximation = str(magnitude.evalf(system.options.precision))
            if left != right:
                text = system.options.output_units.get(str(symbol))
                scale = parse_unit(text).scale if text else system.units.input_scale(symbol) if system.units.active else sp.S.One
                digits = system.options.precision + 10
                while digits <= 4096:
                    approximation = str(magnitude.evalf(digits))
                    printed = sp.Rational(approximation) * scale
                    if left <= printed <= right:
                        break
                    digits *= 2
                else:
                    raise CertificationUnsupported("Could not print a bounded approximation inside its certified interval.")
            exact_root, _ = system.units.output(root, symbol)
            solutions.append(Solution(values={str(symbol): MathValue(exact=str(exact_root), expression=encode_expression(exact_root),
                                                                     approximate=approximation, unit=unit)},
                                      structured_conditions=source_conditions(system, substitutions),
                                      verification=Verification(status="certified", equations_checked=len(system.constraints),
                                                                restrictions_checked=len(system.denominators) + len(system.power_domains) + system.assumptions.count)))
    certificate = RootCertificate(status="certified", variable=str(symbol), polynomial=str(polynomial.as_expr()), distinct_roots=len(intervals),
                                  intervals=intervals, lower_bound=str(lower) if lower != -sp.oo else None,
                                  upper_bound=str(upper) if upper != sp.oo else None)
    if system.units.active and system.units.dimensions.get(symbol) is not None:
        certificate.unit = canonical(system.units.dimensions[symbol])
    system.evidence.record("certify", f"Isolated {len(intervals)} admissible distinct real roots with exact rational endpoints.")
    return SolveResult(status="certified" if intervals else "inconsistent", solutions=solutions, certificate=certificate, completeness="complete",
                       verification=Verification(status="certified", equations_checked=len(system.constraints),
                                                 restrictions_checked=len(system.denominators) + len(system.power_domains) + system.assumptions.count),
                       message=f"Certified {len(intervals)} admissible distinct real roots; intervals include multiplicities.")


def solve_certified(system) -> SolveResult:
    try:
        return _certify(system)
    except CertificationUnsupported as error:
        system.evidence.diagnose("certification_unsupported", str(error),
                                 "Use one real rational-polynomial target of degree at most 32, or choose symbolic/numeric solving without certification.")
        return SolveResult(status="unresolved", certificate=RootCertificate(status="unsupported"), message=str(error))
