"""Dimensional analysis and exact conversions precede mathematical cancellation."""

from __future__ import annotations

import pytest

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request


def constant(name, value, unit=None):
    return {"type": "constant", "name": name, "value": value, **({"unit": unit} if unit else {})}


def solve(expression, data=None, **options):
    return solve_request(SolveRequest(equation={"expression": expression, **options}, data=data or []))


def test_compatible_lengths_convert_before_addition():
    result = solve("y=a+b", [constant("a", 1, "m"), constant("b", 50, "cm")], output_units={"y": "cm"})
    assert result.status == "unique"
    assert result.solutions[0].values["y"].exact == "150"
    assert result.solutions[0].values["y"].unit == "cm"


def test_velocity_dimensions_are_inferred_from_distance_and_time():
    result = solve("v=d/t", [constant("d", 100, "m"), constant("t", 5, "s")], output_units={"v": "km/h"})
    assert result.solutions[0].values["v"].exact == "72"
    assert result.solutions[0].values["v"].unit == "km/h"


def test_dimensionally_invalid_addition_is_rejected():
    result = solve("y=a+b", [constant("a", 1, "m"), constant("b", 2, "s")])
    assert result.status == "invalid"
    assert "dimension" in result.message.lower()


def test_zero_factor_does_not_hide_dimensionally_invalid_addition():
    result = solve("y=a+0*b", [constant("a", 1, "m"), constant("b", 2, "s")])
    assert result.status == "invalid"


def test_transcendental_functions_require_dimensionless_arguments():
    assert solve("y=sin(d)", [constant("d", 1, "m")]).status == "invalid"
    result = solve("y=sin(theta)", [constant("theta", 90, "deg")])
    assert result.solutions[0].values["y"].exact == "1"


def test_declared_unknown_unit_and_force_relation_are_checked():
    result = solve("F=m*a", [constant("m", 2, "kg"), constant("a", 3, "m/s^2")], output_units={"F": "N"})
    assert result.solutions[0].values["F"].exact == "6"
    assert result.solutions[0].values["F"].unit == "N"
    assert solve("F=m*a", [constant("m", 2, "kg"), constant("a", 3, "m/s^2")], units={"F": "s"}).status == "invalid"


def test_units_can_supply_default_unit_for_numeric_bindings():
    result = solve("y=x", [constant("x", 50)], units={"x": "cm"}, output_units={"y": "m"})
    assert result.solutions[0].values["y"].exact == "1/2"


def test_numerical_bounds_and_guesses_use_declared_input_units():
    result = solve("x=a", [constant("a", 1, "m")], units={"x": "cm"}, method="numeric", domain="real",
                   numerical={"bounds": {"x": [90, 110]}})
    assert result.status == "approximate"
    assert float(result.solutions[0].values["x"].approximate) == pytest.approx(100)
    assert result.solutions[0].values["x"].unit == "cm"


def test_certificates_state_canonical_units_and_filter_helper_realness():
    result = solve("x^2=a", [constant("a", 2, "m^2")], units={"x": "m"}, method="certified", domain="real")
    assert result.certificate.status == "certified"
    assert result.certificate.unit == "m"
    invalid = solve(["x^2=2", "b=I"], method="certified", domain="real", solve_for=["x"])
    assert invalid.status == "inconsistent"
    assert invalid.certificate.distinct_roots == 0


def test_bad_output_dimension_is_rejected():
    assert solve("y=x", [constant("x", 1, "m")], output_units={"y": "s"}).status == "invalid"


@pytest.mark.parametrize("unit", ["__import__('os')", "m.__class__", "m[0]", "degC", "m^1000", "m+s"])
def test_unknown_or_unsafe_unit_syntax_is_rejected(unit):
    assert solve("y=x", [constant("x", 1, unit)]).status == "invalid"


def test_ambiguous_unknown_dimensions_are_reported():
    result = solve("y=m*x", [constant("m", 2, "kg")])
    assert any(item.code == "ambiguous_units" for item in result.diagnostics)
    assert result.solutions[0].values["y"].unit is None


def test_constant_exponent_arithmetic_preserves_dimensions():
    result = solve("x^(1/2)", [constant("x", 4, "m^2")])
    assert result.status == "unique"
    assert result.value.exact == "2"
    assert result.value.unit == "m"
    squared = solve("x^(1+1)", [constant("x", 4, "m")])
    assert squared.status == "unique"
    assert squared.value.unit == "m**(2)"


def test_nested_unit_powers_are_bounded_before_computing_scales():
    # Dimensionless scales also need a cumulative limit, not just exponent checks.
    for name in ("m", "percent"):
        unit = name
        for _ in range(10):
            unit = f"({unit}**12)"
        result = solve("y=x", [constant("x", 1, unit)])
        assert result.status == "invalid"
