"""Controls and evidence must preserve the original two-parameter contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request


def solve(expression, **options):
    return solve_request(SolveRequest(equation={"expression": expression, **options}, data=[]))


def test_old_strings_keep_exact_solutions_and_add_verification():
    result = solve_request(SolveRequest(equation="x^2 = 4", data=[]))
    assert result.status == "multiple"
    assert result.completeness == "complete"
    assert result.verification.status == "exact"
    assert all(row.verification.equations_checked == 1 for row in result.solutions)


def test_explicit_target_preserves_other_variables_as_parameters():
    result = solve("x^2 = y", solve_for=["x"])
    assert result.status == "parametric"
    assert {row.values["x"].exact for row in result.solutions} == {"-sqrt(y)", "sqrt(y)"}
    assert result.free_parameters == ["y"]
    assert result.completeness == "complete"


def test_target_coefficient_degeneracy_stays_unresolved():
    result = solve("m*x = y", solve_for=["x"])
    assert result.status == "unresolved"
    assert result.completeness == "unknown"
    assert any(item.code == "unproved_branches" for item in result.diagnostics)
    assert result.solutions[0].conditions == ["m != 0"]


@pytest.mark.parametrize("expression", ["m*x=0", "m*x=m", "a*x^2=0", "m*exp(x)=0"])
def test_canceled_parameter_coefficients_do_not_claim_complete_answers(expression):
    result = solve(expression, solve_for=["x"])
    assert result.status == "unresolved"
    assert result.completeness == "unknown"
    assert any(item.code == "unproved_branches" for item in result.diagnostics)


def test_target_without_a_numeric_result_is_not_missing_data_error():
    result = solve("y = m*x", solve_for=["y"])
    assert result.solutions[0].values["y"].exact == "m*x"
    assert result.verification.status == "exact"
    assert result.completeness == "complete"


def test_real_domain_excludes_complex_roots():
    result = solve("x^2 = -1", domain="real")
    assert result.status == "inconsistent"
    assert result.completeness == "complete"
    assert not result.solutions


def test_real_domain_applies_to_bindings_and_expression_values():
    request = SolveRequest(equation={"expression": "y = b", "domain": "real"}, data=[
        {"type": "equation", "name": "b", "value": {"equation": "b = sqrt(-1)", "data": []}},
    ])
    assert solve_request(request).status == "inconsistent"
    assert solve("sqrt(-1)", domain="real").status == "inconsistent"


def test_real_expression_preserves_conditional_realness():
    result = solve("sqrt(x)", domain="real")
    assert result.status == "parametric"
    assert result.solutions[0].conditions
    assert result.verification.status == "conditional"


def test_infinite_root_set_still_checks_realness_of_reconstructed_helpers():
    data = [{"type": "equation", "name": "b", "value": {"equation": "b=i", "data": []}}]
    real = solve_request(SolveRequest(equation={"expression": "sin(x)=0", "domain": "real"}, data=data))
    assert real.status == "inconsistent"
    assert real.completeness == "complete"
    complex_result = solve_request(SolveRequest(equation="sin(x)=0", data=data))
    assert complex_result.status == "parametric"


def test_requested_precision_controls_numeric_approximations():
    result = solve("sqrt(2)", precision=50)
    assert result.value.exact == "sqrt(2)"
    assert result.value.approximate.startswith("1.4142135623730950488016887242096980785696718753769")


def test_conditional_verification_retains_original_domain_check_count():
    result = solve("x/x = 1")
    assert result.verification.status == "conditional"
    assert result.solutions[0].verification.restrictions_checked >= 1
    assert result.solutions[0].conditions == ["x != 0"]


def test_unresolved_problem_explains_next_action():
    result = solve("cos(x) = x")
    assert result.status == "unresolved"
    assert result.completeness == "unknown"
    assert result.diagnostics
    assert result.diagnostics[0].suggestion
    assert result.verification.status == "not_applicable"


def test_verified_general_nonlinear_rows_do_not_imply_exhaustive_coverage():
    request = SolveRequest(equation="x*y=0", data=[
        {"type": "equation", "name": "y", "value": {"equation": "y=y^2", "data": []}},
    ])
    result = solve_request(request)
    assert result.solutions
    assert result.status == "parametric"
    assert result.completeness == "unknown"
    assert any(item.code == "completeness_not_established" for item in result.diagnostics)


def test_trace_contains_performed_substitution_and_verification():
    request = SolveRequest(equation={"expression": "y = m / 2", "trace": True}, data=[
        {"type": "constant", "name": "m", "value": 5},
    ])
    result = solve_request(request)
    assert result.solutions[0].values["y"].exact == "5/2"
    assert any(step.action == "binding" and "m" in step.detail for step in result.trace)
    assert any(step.action == "eliminate" and "y" in step.detail for step in result.trace)
    assert any(step.action == "verify" for step in result.trace)
    assert result.engine.name == "sympy"
    assert result.engine.version


def test_trace_is_opt_in_and_timings_are_nonnegative():
    result = solve("x = 3")
    assert result.trace == []
    assert result.timings["parse_ms"] >= 0
    assert result.timings["solve_ms"] >= 0
    assert result.timings["verification_ms"] >= 0


@pytest.mark.parametrize("options", [
    {"precision": 14}, {"precision": 101}, {"solve_for": ["x", "x"]},
    {"solve_for": ["pi"]}, {"domain": "integer"}, {"method": "numeric"},
])
def test_invalid_controls_fail_validation(options):
    with pytest.raises(ValidationError):
        SolveRequest(equation={"expression": "x = 1", **options}, data=[])


def test_target_typo_is_rejected_without_creating_an_extra_unknown():
    result = solve("x^2 = 4", solve_for=["missing"])
    assert result.status == "invalid"
    assert "missing" in result.message


def test_trace_and_results_stay_bounded():
    result = solve(" + ".join(f"v{i}" for i in range(30)), trace=True)
    assert len(result.trace) <= 128
