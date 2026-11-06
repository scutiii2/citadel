"""Explicit partitions cover coefficient-zero branches without generic division."""

from __future__ import annotations

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request


def cases(expression, **options):
    return solve_request(SolveRequest(equation={"expression": expression, "solve_for": ["x"], "split_cases": True, **options}, data=[]))


def test_zero_coefficient_yields_free_target_and_nonzero_branch():
    result = cases("m*x=0")
    assert result.status == "parametric"
    assert result.completeness == "complete"
    assert len(result.cases) == 2
    assert any("m = 0" in branch.conditions and branch.solutions[0].values["x"].exact == "x" for branch in result.cases)
    assert any("m != 0" in branch.conditions and branch.solutions[0].values["x"].exact == "0" for branch in result.cases)


def test_second_parameter_condition_is_split_when_needed():
    result = cases("m*x=y")
    assert result.completeness == "complete"
    assert len(result.cases) == 2
    assert any("m = 0" in branch.conditions and branch.solutions[0].values["y"].exact == "0"
               and branch.free_parameters == ["x"] for branch in result.cases)


def test_complex_quadratic_parameter_zeros_are_partitioned():
    result = cases("(m^2+1)*x=0")
    assert result.completeness == "complete"
    assert len(result.cases) == 3
    assert any("m = I" in branch.conditions for branch in result.cases)
    assert any("m = -I" in branch.conditions for branch in result.cases)


def test_case_budget_never_claims_exhaustiveness_after_cutoff():
    result = cases("m*n*x=0", case_limit=2)
    assert result.completeness == "unknown"
    assert result.status == "unresolved"
    assert len(result.cases) <= 2
    assert any(item.code == "case_limit" for item in result.diagnostics)


def test_positive_parameter_needs_no_zero_case():
    result = cases("m*x=0", assumptions={"m": {"positive": True}})
    assert result.completeness == "complete"
    assert result.solutions[0].values["x"].exact == "0"


def test_transcendental_parameter_zeros_stay_explicitly_unresolved():
    result = cases("sin(m)*x=0")
    assert result.status == "unresolved"
    assert result.completeness == "unknown"


def test_case_solving_preserves_original_denominator_exclusions():
    result = cases("m*x=0/(m+1)")
    assert result.completeness == "complete"
    assert all(any("m + 1" in condition for condition in row.conditions) or row.values["m"].exact == "0" for row in result.solutions)


def test_matrix_rank_change_at_nonzero_parameter_is_not_lost():
    request = SolveRequest(equation={"expression": ["a*x+a*y=0", "a*x+a*a*y=0"],
                                    "solve_for": ["x", "y"], "split_cases": True}, data=[])
    result = solve_request(request)
    assert result.completeness == "complete"
    assert any("a = 1" in branch.conditions and branch.solutions[0].values["x"].exact == "-y" for branch in result.cases)


def test_rejected_generic_candidates_do_not_prove_exceptional_cases_impossible():
    request = SolveRequest(equation={"expression": ["a*x=a", "y=x"], "solve_for": ["x", "y"],
                                    "assumptions": {"x": {"min": 2}}}, data=[])
    result = solve_request(request)
    assert result.status == "unresolved"
    assert result.completeness == "unknown"
