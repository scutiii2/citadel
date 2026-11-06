"""Prior result reuse keeps exact values, units, conditions, and approximation scope."""

from __future__ import annotations

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.continuation import build_continuation
from src.capabilities.math.utils.solver import solve_request


def previous(equation, data=None):
    return solve_request(SolveRequest(equation=equation, data=data or []))


def test_exact_fraction_result_can_feed_next_equation():
    old = previous("y=1/x", [{"type": "constant", "name": "x", "value": 2}])
    request = build_continuation("z=y+1", {"previous": old.model_dump()})
    result = solve_request(request)
    assert result.solutions[0].values["z"].exact == "3/2"


def test_reuse_preserves_assumed_positive_family_and_rejects_conflict():
    old = previous({"expression": "y=x", "assumptions": {"x": {"positive": True}}})
    request = build_continuation("z=y+1", {"previous": old.model_dump(), "bindings": [
        {"type": "constant", "name": "x", "value": -1},
    ]})
    assert solve_request(request).status == "inconsistent"


def test_numeric_result_requires_opt_in_and_never_becomes_exact():
    old = previous({"expression": "cos(x)=x", "method": "numeric", "numerical": {"initial_guesses": [{"x": 0.5}]}})
    from src.capabilities.math.utils.parser import MathInputError
    import pytest

    with pytest.raises(MathInputError):
        build_continuation("z=x+1", {"previous": old.model_dump()})
    result = solve_request(build_continuation("z=x+1", {"previous": old.model_dump(), "allow_approximate": True}))
    assert result.completeness == "partial"
    assert result.solutions[0].values["z"].exact is None
    assert result.provenance["approximate_inputs"] is True


def test_unitful_outputs_are_converted_back_before_reuse():
    old = previous({"expression": "v=d/t", "output_units": {"v": "km/h"}}, [
        {"type": "constant", "name": "d", "value": 100, "unit": "m"},
        {"type": "constant", "name": "t", "value": 5, "unit": "s"},
    ])
    result = solve_request(build_continuation("distance=v*duration", {"previous": old.model_dump(), "bindings": [
        {"type": "constant", "name": "duration", "value": 2, "unit": "s"},
    ]}))
    assert result.solutions[0].values["distance"].exact == "40"
    assert result.solutions[0].values["distance"].unit == "m"


def test_certified_exact_algebraic_root_is_reusable():
    old = previous({"expression": "x^2=2", "method": "certified", "domain": "real"})
    result = solve_request(build_continuation("z=x^2", {"previous": old.model_dump()}))
    assert result.solutions[0].values["z"].exact == "2"


def test_prior_verification_constraints_cannot_be_discarded_by_override():
    old = previous("y=x+1", [{"type": "constant", "name": "x", "value": 2}])
    result = solve_request(build_continuation("z=y", {"previous": old.model_dump(), "bindings": [
        {"type": "constant", "name": "y", "value": 999},
    ]}))
    assert result.status == "inconsistent"


def test_selected_root_cannot_be_overridden_with_another_valid_root():
    old = previous("x^2=1")
    selected = old.solutions[0].values["x"].exact
    other = 1 if selected == "-1" else -1
    result = solve_request(build_continuation("z=x", {"previous": old.model_dump(), "bindings": [
        {"type": "constant", "name": "x", "value": other},
    ]}))
    assert result.status == "inconsistent"


def test_real_family_cannot_be_reused_at_complex_parameter():
    old = previous({"expression": "y=x", "domain": "real"})
    result = solve_request(build_continuation("z=y", {"previous": old.model_dump(), "bindings": [
        {"type": "constant", "name": "x", "value": "I"},
    ]}))
    assert result.status == "inconsistent"


def test_approximate_symbolic_scalar_never_regains_exact_verification():
    old = previous("x+a", [{"type": "constant", "name": "a", "value": 0.1, "approximate": True}])
    result = solve_request(build_continuation("z=value", {"previous": old.model_dump(), "slot": "value", "allow_approximate": True,
        "bindings": [{"type": "constant", "name": "x", "value": 1}]}))
    assert result.status == "approximate" and result.completeness == "partial"
    assert result.verification.status == "numeric"
    assert result.solutions[0].values["z"].exact is None
