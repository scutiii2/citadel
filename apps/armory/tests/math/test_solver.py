"""Behavioral coverage for scoped equation solving and untrusted expressions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request


def constant(name, value):
    return {"type": "constant", "name": name, "value": value}


def nested(name, equation, data):
    return {"type": "equation", "name": name, "value": {"equation": equation, "data": data}}


def calculate(equation, data=None):
    return solve_request(SolveRequest(equation=equation, data=data or []))


def exact(result, variable):
    return {solution.values[variable].exact for solution in result.solutions}


def test_recursive_bindings_evaluate_to_twenty():
    result = calculate("y = (m * b / 2) + x", [
        constant("m", 5), {"type": "variable", "name": "x", "value": "m"},
        nested("b", "b = (p + 4) / q", [constant("p", 8), constant("q", 2)]),
    ])
    assert result.status == "unique"
    assert exact(result, "y") == {"20"}
    assert exact(result, "b") == {"6"}
    assert "p" not in result.solutions[0].values


def test_circular_equations_are_solved_together():
    result = calculate("y = m * b / 2 + x", [
        constant("m", 5), {"type": "variable", "name": "x", "value": "m"},
        nested("b", "b = (y + 4) / x", []),
    ])
    assert result.status == "unique"
    assert exact(result, "y") == {"14"}
    assert exact(result, "b") == {"18/5"}


def test_nested_helpers_shadow_parent_without_leaking():
    result = calculate("y = b + p", [constant("p", 100), nested(
        "b", "b = p + c", [constant("p", 2), nested("c", "c = p * 3", [])],
    )])
    assert exact(result, "y") == {"108"}
    assert exact(result, "p") == {"100"}
    assert "c" not in result.solutions[0].values


def test_sibling_helper_names_are_independent():
    result = calculate("y = a + b", [
        nested("a", "a = t", [constant("t", 2)]),
        nested("b", "b = t", [constant("t", 5)]),
    ])
    assert exact(result, "y") == {"7"}


def test_complex_roots_return_both_values_and_approximations():
    result = calculate("x^2 = -1")
    assert result.status == "multiple"
    assert exact(result, "x") == {"-I", "I"}
    assert all(row.values["x"].approximate for row in result.solutions)


def test_nonlinear_system_keeps_correlated_solution_branches():
    result = calculate("x^2 = y", [nested("y", "y = 4", [])])
    assert result.status == "multiple"
    assert exact(result, "x") == {"-2", "2"}
    assert exact(result, "y") == {"4"}


def test_free_variables_are_reported_as_parametric():
    result = calculate("y = m * x")
    assert result.status == "parametric"
    assert result.free_parameters
    assert result.solutions
    assert exact(result, "y") == {"m*x"}
    assert result.solutions[0].conditions == []


def test_identity_retains_unknown_and_infinite_domain():
    result = calculate("x = x")
    assert result.status == "parametric"
    assert result.free_parameters == ["x"]


def test_trigonometric_infinite_set_is_not_finite_solutions():
    result = calculate("sin(x) = 0")
    assert result.status == "parametric"
    assert result.solution_set
    assert not result.solutions


@pytest.mark.parametrize("equation,data", [
    ("x = 2", [constant("x", 1)]),
    ("1 = 2", []),
    ("x / x = 0", []),
    ("(x^2 - 1) / (x - 1) = 2", []),
])
def test_inconsistent_constraints_and_excluded_roots(equation, data):
    assert calculate(equation, data).status == "inconsistent"


def test_identity_retains_denominator_restriction():
    result = calculate("x / x = 1")
    assert result.status == "parametric"
    assert result.conditions
    assert "0" in " ".join(result.conditions)


def test_decimal_inputs_preserve_exact_arithmetic():
    result = calculate("y = x + 0.2", [constant("x", 0.1)])
    assert exact(result, "y") == {"3/10"}


def test_plain_expression_returns_value():
    result = calculate("sqrt(2)^2 + 3")
    assert result.status == "unique"
    assert result.value.exact == "5"


def test_unsupported_equation_is_unresolved_not_no_solution():
    result = calculate("cos(x) = x")
    assert result.status == "unresolved"
    assert not result.solutions


def test_nonpolynomial_system_solver_empty_set_is_not_proof_of_inconsistency():
    # SymPy nonlinsolve can return EmptySet for this satisfiable radical relation.
    result = calculate("y = sqrt(x)")
    assert result.status in {"parametric", "unresolved"}


def test_denominator_conditions_belong_to_individual_solution_branches():
    result = calculate("x * y + 0 / (x + y) = 0")
    assert result.status == "parametric"
    assert result.conditions == []
    assert len(result.solutions) == 2
    for row in result.solutions:
        if row.values["x"].exact == "0":
            assert row.conditions == ["y != 0"]
        else:
            assert row.conditions == ["x != 0"]


def test_complex_exponents_are_supported():
    result = calculate("I^I")
    assert result.status == "unique"
    assert result.value.exact in {"I**I", "exp(-pi/2)"}
    assert float(result.value.approximate) == pytest.approx(0.207879576350762)


def test_expression_value_is_returned_for_each_solution_branch():
    result = calculate("x + 1", [nested("x", "x = 4 / x", [])])
    assert result.status == "multiple"
    assert {row.value.exact for row in result.solutions} == {"-1", "3"}


def test_symbolic_negative_exponent_retains_domain_after_binding():
    result = calculate("0 * x^(-n) = 0", [constant("n", 1)])
    assert result.status == "parametric"
    assert result.solutions[0].conditions == ["x != 0"]


def test_symbolic_power_domain_is_conditional_until_exponent_is_known():
    result = calculate("0 * x^(-n) = 0")
    assert result.status == "parametric"
    assert result.solutions[0].conditions


def test_zero_factor_cannot_hide_logarithm_singularity():
    assert calculate("x = 0 * log(x)").status == "inconsistent"
    result = calculate("0 * log(x) = 0")
    assert result.status == "parametric"
    assert result.solutions[0].conditions == ["x != 0"]


@pytest.mark.parametrize("equation", ["x = pi/2 + 0*tan(x)", "x = I + 0*atan(x)"])
def test_zero_factor_cannot_hide_function_poles(equation):
    assert calculate(equation).status == "inconsistent"


@pytest.mark.parametrize("expression", [
    "__import__('os').getcwd()", "x.__class__", "x[0]", "[x for x in y]",
    "open(1)", "lambda: 1", "2m", "x < 2", "sin(x, y)", "True", "x = y = 2",
    "1 / 0", "10^1001", "1e9999", "9" * 101,
])
def test_invalid_or_expensive_syntax_is_rejected(expression):
    assert calculate(expression).status in {"invalid", "limited"}


@pytest.mark.parametrize("data", [
    [constant("x", 1), constant("x", 2)],
    [constant("pi", 3)],
    [constant("__x", 1)],
    [nested("b", "c = 2", [])],
    [nested("b", "b = 2", [constant("b", 3)])],
])
def test_invalid_binding_definitions_are_rejected(data):
    try:
        result = calculate("y = 1", data)
    except ValidationError:
        return
    assert result.status == "invalid"


def test_nonfinite_and_boolean_constants_are_rejected():
    for value in (True, float("inf"), float("nan")):
        with pytest.raises(ValidationError):
            SolveRequest(equation="x", data=[constant("x", value)])


def test_recursion_depth_is_bounded():
    data = []
    for index in range(10):
        data = [nested(f"v{index}", f"v{index} = 1", data)]
    with pytest.raises(ValidationError):
        SolveRequest(equation="y = 1", data=data)


def test_total_bindings_are_bounded_across_scopes():
    data = [nested("b", "b = 1", [constant(f"v{i}", i) for i in range(64)])]
    with pytest.raises(ValidationError):
        SolveRequest(equation="y = b", data=data)


def test_numeric_constant_digit_limit_matches_expression_literals():
    with pytest.raises(ValidationError):
        SolveRequest(equation="y = m", data=[constant("m", 10**100)])


def test_symbol_count_limit_is_enforced():
    result = calculate(" + ".join(f"v{i}" for i in range(33)))
    assert result.status == "limited"


def test_safe_elimination_keeps_zero_coefficient_degenerate_branch():
    result = calculate("m * y = x")
    assert result.status == "parametric"
    assert exact(result, "x") == {"m*y"}
    assert result.solutions[0].conditions == []


def test_general_parametrization_with_unproved_missing_branches_is_unresolved():
    result = calculate("x * y = z * w")
    assert result.status == "unresolved"
    assert result.solutions[0].conditions


def test_syntax_node_limit_is_enforced():
    result = calculate(" + ".join("x" for _ in range(150)))
    assert result.status == "limited"
