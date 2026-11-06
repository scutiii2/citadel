"""Direct systems and declared assumptions constrain every returned candidate."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request


def solve(expression, data=None, **options):
    return solve_request(SolveRequest(equation={"expression": expression, **options}, data=data or []))


def test_direct_system_solves_both_variables():
    result = solve(["x+y=5", "x-y=1"])
    assert result.status == "unique"
    assert result.solutions[0].values["x"].exact == "3"
    assert result.solutions[0].values["y"].exact == "2"
    assert result.verification.equations_checked == 2


def test_direct_system_and_recursive_data_share_constraints():
    result = solve(["x+y=b", "x-y=1"], data=[
        {"type": "equation", "name": "b", "value": {"equation": "b=2*m+1", "data": [
            {"type": "constant", "name": "m", "value": 2},
        ]}},
    ])
    assert result.solutions[0].values["x"].exact == "3"
    assert "m" not in result.solutions[0].values


def test_system_with_conflicting_equations_is_inconsistent():
    assert solve(["x=1", "x=2"]).status == "inconsistent"


def test_positive_assumption_removes_negative_root_and_is_reported():
    result = solve("x^2=4", assumptions={"x": {"positive": True}})
    assert result.status == "unique"
    assert result.solutions[0].values["x"].exact == "2"
    assert result.assumptions["x"].positive is True


def test_integer_assumption_excludes_irrational_roots():
    result = solve("x^2=2", assumptions={"x": {"integer": True}})
    assert result.status == "inconsistent"


def test_assumption_limits_filter_roots_inclusively():
    result = solve("x^2=4", assumptions={"x": {"min": -2, "max": 0}})
    assert result.solutions[0].values["x"].exact == "-2"


def test_nonzero_does_not_imply_real_for_complex_variables():
    result = solve("x^2=-1", assumptions={"x": {"nonzero": True}})
    assert result.status == "multiple"
    assert {row.values["x"].exact for row in result.solutions} == {"I", "-I"}


def test_assumptions_check_data_constants_too():
    result = solve("y=x", assumptions={"x": {"positive": True}}, data=[
        {"type": "constant", "name": "x", "value": -1},
    ])
    assert result.status == "inconsistent"


def test_assumption_range_is_retained_for_free_variable():
    result = solve("y=x", assumptions={"x": {"min": 1, "max": 3}})
    assert result.status == "parametric"
    assert any("1" in value and "x" in value for value in result.solutions[0].conditions)


def test_assumption_applies_before_infinite_set_return():
    result = solve("sin(x)=0", assumptions={"x": {"positive": True}})
    assert result.status == "parametric"
    assert result.solution_set
    assert "0" in str(result.assumptions["x"].positive) or result.assumptions["x"].positive


def test_numerical_candidates_obey_integer_assumptions():
    result = solve("x^2=2", assumptions={"x": {"integer": True}}, method="numeric",
                   numerical={"initial_guesses": [{"x": 1}]})
    assert result.status == "unresolved"
    assert not result.solutions


@pytest.mark.parametrize("options", [
    {"assumptions": {"x": {"min": 3, "max": 2}}},
    {"assumptions": {"x": {"positive": True, "max": 0}}},
    {"assumptions": {"x": {"nonzero": True, "min": 0, "max": 0}}},
    {"expression": []}, {"expression": ["x=1"] * 17},
])
def test_invalid_system_or_assumption_controls_are_rejected(options):
    with pytest.raises(ValidationError):
        SolveRequest(equation={"expression": "x=1", **options}, data=[])


def test_absent_assumption_name_is_rejected():
    assert solve("x=1", assumptions={"typo": {"positive": True}}).status == "invalid"


def test_bare_expressions_are_not_accepted_inside_equation_system():
    assert solve(["x=1", "x+1"]).status == "invalid"
