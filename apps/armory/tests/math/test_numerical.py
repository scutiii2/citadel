"""Numerical searches return checked approximations, never complete root claims."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request


def numeric(expression, *, guesses=None, bounds=None, data=None, **options):
    hints = {}
    if guesses is not None:
        hints["initial_guesses"] = guesses
    if bounds is not None:
        hints["bounds"] = bounds
    equation = {"expression": expression, "method": "numeric", "precision": 40, "numerical": hints, **options}
    return solve_request(SolveRequest(equation=equation, data=data or []))


def test_transcendental_root_has_numeric_verification_and_no_exact_claim():
    result = numeric("cos(x) = x", guesses=[{"x": 0.5}], domain="real", trace=True)
    assert result.status == "approximate"
    assert result.completeness == "partial"
    value = result.solutions[0].values["x"]
    assert value.exact is None
    assert value.approximate.startswith("0.739085133215160641655312087673")
    assert result.verification.status == "numeric"
    assert Decimal(result.verification.max_residual) <= Decimal(result.verification.tolerance)
    assert result.solutions[0].verification.equations_checked == 1
    assert any(step.action == "numeric" for step in result.trace)


def test_auto_falls_back_only_after_symbolic_solver_is_unresolved():
    result = numeric("cos(x) = x", guesses=[{"x": 0.5}], method="auto")
    assert result.status == "approximate"
    exact = numeric("x^2 = 4", guesses=[{"x": 1}], method="auto", trace=True)
    assert exact.status == "multiple"
    assert exact.completeness == "complete"
    assert {row.values["x"].exact for row in exact.solutions} == {"-2", "2"}
    assert not any(step.action == "numeric" for step in exact.trace)


def test_bounded_search_keeps_root_inside_supplied_interval():
    result = numeric("sin(x) = 0", bounds={"x": [3, 4]}, domain="real")
    assert result.status == "approximate"
    value = Decimal(result.solutions[0].values["x"].approximate)
    assert Decimal(3) <= value <= Decimal(4)
    assert str(value).startswith("3.141592653589793238462643383279")
    assert result.completeness == "partial"


def test_roots_outside_bounds_are_not_returned():
    result = numeric("x^2 = 4", guesses=[{"x": 0.5}], bounds={"x": [0, 1]}, domain="real")
    assert result.status == "unresolved"
    assert not result.solutions
    assert any(item.code in {"outside_bounds", "no_convergence"} for item in result.diagnostics)


def test_bounded_linear_candidate_survives_safe_elimination():
    result = numeric("x=1", bounds={"x": [0, 2]}, domain="real")
    assert result.status == "approximate"
    assert Decimal(result.solutions[0].values["x"].approximate) == 1
    excluded = numeric("x=3", bounds={"x": [0, 2]}, domain="real")
    assert excluded.status == "unresolved"
    assert not excluded.solutions


def test_small_constant_scaling_cannot_turn_nonroot_into_verified_root():
    result = numeric("(x^2+1)/10^30=0", guesses=[{"x": 1}], precision=15, domain="real")
    assert result.status == "unresolved"
    assert not result.solutions


def test_valid_scaled_equation_uses_normalized_original_residual():
    result = numeric("(cos(x)-x)/10^30=0", guesses=[{"x": 0.5}], domain="real")
    assert result.status == "approximate"
    assert result.verification.residual_kind == "normalized_absolute"
    assert Decimal(result.verification.max_residual) <= Decimal(result.verification.tolerance)


def test_complex_seeds_return_independent_partial_roots():
    result = numeric("x^2 = -1", guesses=[{"x": "I"}, {"x": "-I"}])
    assert result.status == "approximate"
    assert len(result.solutions) == 2
    assert all(row.values["x"].exact is None for row in result.solutions)
    assert result.completeness == "partial"


def test_repeated_seeds_do_not_duplicate_same_root():
    result = numeric("cos(x) = x", guesses=[{"x": 0.5}, {"x": 0.6}], domain="real")
    assert result.status == "approximate"
    assert len(result.solutions) == 1


def test_missing_parameter_diagnostic_names_binding_to_supply():
    result = numeric("a*x = 1", guesses=[{"x": 1}], solve_for=["x"])
    assert result.status == "unresolved"
    assert not result.solutions
    diagnostic = next(item for item in result.diagnostics if item.code == "missing_parameters")
    assert diagnostic.variables == ["a"]
    assert "data" in diagnostic.suggestion


def test_failed_search_does_not_claim_inconsistency():
    result = numeric("exp(x) = -1", bounds={"x": [-1, 1]}, domain="real")
    assert result.status == "unresolved"
    assert result.completeness == "unknown"
    assert not result.solutions
    assert result.diagnostics


def test_numerical_verification_rejects_root_at_original_function_pole():
    result = numeric("x = pi/2 + 0*tan(x)", guesses=[{"x": 1.5}], domain="real")
    assert result.status == "unresolved"
    assert not result.solutions
    assert any(item.code == "near_singularity" for item in result.diagnostics)


def test_joint_system_is_verified_against_original_equations_after_reduction():
    result = numeric("y = cos(x)", guesses=[{"x": 0.5, "y": 0.5}], domain="real", data=[
        {"type": "equation", "name": "x", "value": {"equation": "x = y", "data": []}},
    ])
    assert result.status == "approximate"
    row = result.solutions[0]
    assert row.values["x"].approximate.startswith("0.73908513321516064165")
    assert row.values["y"].approximate.startswith("0.73908513321516064165")
    assert row.verification.equations_checked == 2


@pytest.mark.parametrize("seed", ["__import__('os')", "unknown", "1/0", "10^1001"])
def test_seed_expressions_use_same_restricted_parser(seed):
    result = numeric("cos(x) = x", guesses=[{"x": seed}])
    assert result.status in {"invalid", "limited"}
    assert not result.solutions


def test_bad_hint_names_are_rejected():
    result = numeric("cos(x) = x", guesses=[{"misspelled": 0.5}])
    assert result.status == "invalid"
    assert any(item.code == "invalid_numerical_hints" for item in result.diagnostics)
