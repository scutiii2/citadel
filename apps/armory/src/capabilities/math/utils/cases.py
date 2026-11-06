"""Bounded exhaustive partitions for supported parameter coefficient zeros."""

from __future__ import annotations

from copy import copy

import sympy as sp

from src.capabilities.math.contract import ParameterCase, SolveResult, Verification
from src.capabilities.math.utils.evidence import EvidenceCollector


def polynomial_zeros(expression, symbol):
    """Only finite numeric roots of degree <=4 produce an exact partition."""
    try:
        polynomial = sp.Poly(expression, symbol)
    except sp.PolynomialError:
        return None
    if not 1 <= polynomial.degree() <= 4 or any(value.is_number is not True for value in polynomial.all_coeffs()):
        return None
    roots = sp.solveset(polynomial.as_expr(), symbol, domain=sp.S.Complexes)
    if not isinstance(roots, sp.FiniteSet) or len(roots) > 4 or any(root.is_finite is not True or root.free_symbols for root in roots):
        return None
    return sorted(roots, key=str)


def _split_choice(system):
    from src.capabilities.math.utils.solver import _zero_branch_excluded

    for coefficient in system.case_coefficients:
        if len(coefficient.free_symbols) == 1:
            symbol = next(iter(coefficient.free_symbols))
            if symbol in system.parameters:
                roots = polynomial_zeros(coefficient, symbol)
                if roots:
                    roots = [root for root in roots if not any(sp.simplify(value.subs(symbol, root)).is_zero is True for value in system.denominators)]
                    if roots:
                        return symbol, coefficient, roots
        for factor in sp.Mul.make_args(sp.factor(coefficient)):
            base = factor.base if isinstance(factor, sp.Pow) and factor.exp.is_Integer and factor.exp > 0 else factor
            if isinstance(base, sp.Symbol) and base in system.parameters and not _zero_branch_excluded(base, system):
                return base, base, [sp.S.Zero]
    return None


def _child(system):
    child = copy(system)
    child.constraints = list(system.constraints)
    child.denominators = list(system.denominators)
    child.bound_symbols = set(system.bound_symbols)
    child.parameters = set(system.parameters)
    child.case_coefficients = []
    child.case_predicates = list(system.case_predicates)
    child.incomplete_parameters = False
    child.evidence = EvidenceCollector(system.options.trace)
    return child


def solve_cases(system, initial: SolveResult, solve_core) -> SolveResult:
    pending = [(system, [], initial)]
    leaves = []
    limited = False
    while pending:
        current, conditions, result = pending.pop(0)
        if result is None:
            result = solve_core(current)
        if result.completeness == "unknown" and result.status in {"unique", "multiple", "parametric", "inconsistent"}:
            result.completeness = current.evidence.completeness
        choice = _split_choice(current) if current.incomplete_parameters else None
        if choice:
            symbol, coefficient, roots = choice
            if len(leaves) + len(pending) + len(roots) + 1 <= system.options.case_limit:
                system.evidence.record("case", f"Partition {coefficient} = 0 and {coefficient} != 0.")
                for root in roots:
                    child = _child(current)
                    child.constraints.append(symbol - root)
                    child.case_predicates.append(sp.Eq(symbol, root, evaluate=False))
                    child.parameters.remove(symbol)
                    child.bound_symbols.add(symbol)
                    pending.append((child, conditions + [f"{symbol} = {root}"], None))
                child = _child(current)
                child.denominators.append(coefficient)
                child.case_predicates.append(sp.Ne(coefficient, 0, evaluate=False))
                pending.append((child, conditions + [f"{coefficient} != 0"], None))
                continue
            limited = True
        leaves.append((conditions, result))
        if current is not system:
            for step in current.evidence.steps:
                system.evidence.record(step.action, f"Case {', '.join(conditions)}: {step.detail}")
            system.evidence.timings["verification_ms"] += current.evidence.timings["verification_ms"]

    if len(leaves) == 1 and not leaves[0][0]:
        return initial
    cases = []
    solutions = []
    for conditions, result in leaves:
        rows = []
        for row in result.solutions:
            row = row.model_copy(deep=True)
            row.conditions = sorted(set(conditions + row.conditions))
            row.verification.status = "conditional"
            rows.append(row)
            solutions.append(row)
        cases.append(ParameterCase(conditions=conditions, status=result.status, completeness=result.completeness,
                                   solutions=rows, free_parameters=result.free_parameters, solution_set=result.solution_set,
                                   verification=result.verification,
                                   structured_conditions=rows[0].structured_conditions if rows else result.structured_conditions))
    complete = all(result.completeness == "complete" for _, result in leaves)
    if complete:
        system.evidence.diagnostics = [item for item in system.evidence.diagnostics if item.code != "unproved_branches"]
        system.evidence.completeness = "complete"
    if limited:
        system.evidence.diagnose("case_limit", "Some parameter branches reached the bounded case budget.",
                                 "Supply parameter values or request separate case subproblems.")
    valid = [result for _, result in leaves if result.status != "inconsistent"]
    status = "unresolved" if not complete else "inconsistent" if not valid else "parametric" if any(
        result.free_parameters or result.solution_set for result in valid
    ) else "unique" if len(solutions) == 1 else "multiple"
    return SolveResult(status=status, solutions=solutions, cases=cases, completeness="complete" if complete else "unknown",
                       free_parameters=sorted({name for result in valid for name in result.free_parameters}),
                       verification=Verification(status="conditional" if valid else "not_applicable", equations_checked=len(system.constraints),
                                                 restrictions_checked=len(system.denominators) + len(system.power_domains) + system.assumptions.count),
                       message="Explicit parameter cases cover all supported branches." if complete else "Explicit parameter cases retain unresolved branches.")
