"""Exact certificates cover admissible rational-polynomial roots, not searches."""

from __future__ import annotations

from fractions import Fraction

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request


def certified(expression, data=None, **options):
    return solve_request(SolveRequest(equation={"expression": expression, "method": "certified", "domain": "real", "precision": 20, **options}, data=data or []))


def test_irrational_roots_have_rational_isolating_intervals_and_exact_count():
    result = certified("x^2=2")
    assert result.status == "certified"
    assert result.completeness == "complete"
    assert result.certificate.status == "certified"
    assert result.certificate.distinct_roots == 2
    for interval in result.certificate.intervals:
        assert Fraction(interval.upper) - Fraction(interval.lower) <= Fraction(1, 10**20)
        assert interval.multiplicity == 1
    assert result.verification.status == "certified"


def test_repeated_roots_report_distinct_count_and_multiplicity():
    result = certified("(x-1)^2*(x+2)=0")
    assert result.certificate.distinct_roots == 2
    assert sorted(interval.multiplicity for interval in result.certificate.intervals) == [1, 2]


def test_direct_polynomial_system_uses_common_roots():
    result = certified(["x^2=4", "x=2"])
    assert result.certificate.distinct_roots == 1
    assert result.certificate.intervals[0].lower == "2"
    assert result.certificate.intervals[0].upper == "2"


def test_certificate_excludes_original_denominator_zeros():
    result = certified("(x^2-1)/(x-1)=0")
    assert result.certificate.distinct_roots == 1
    assert result.certificate.intervals[0].lower == "-1"


def test_certification_obeys_bounds_and_positive_assumptions():
    result = certified("x^2=2", numerical={"bounds": {"x": [0, 2]}}, assumptions={"x": {"positive": True}})
    assert result.certificate.distinct_roots == 1
    assert Fraction(result.certificate.intervals[0].lower) > 0


def test_integer_assumptions_restrict_certified_root_count():
    result = certified("x^2=2", assumptions={"x": {"integer": True}})
    assert result.status == "inconsistent"
    assert result.certificate.status == "certified"
    assert result.certificate.distinct_roots == 0


def test_known_binding_is_reduced_before_certifying():
    result = certified("a*x^2=2", data=[{"type": "constant", "name": "a", "value": 1}])
    assert result.certificate.distinct_roots == 2


def test_no_real_roots_is_certified_no_solution():
    result = certified("x^2=-1")
    assert result.status == "inconsistent"
    assert result.completeness == "complete"
    assert result.certificate.distinct_roots == 0


def test_unsupported_functions_do_not_receive_fake_certificates():
    for expression in ("cos(x)=x", "x^33=2", "x^2=y", "x^2-1+0/log(x)=0"):
        result = certified(expression, solve_for=["x"])
        assert result.status == "unresolved"
        assert result.certificate.status == "unsupported"
        assert result.completeness == "unknown"
        assert any(item.code == "certification_unsupported" for item in result.diagnostics)


def test_complex_domain_is_explicitly_outside_real_certificate_scope():
    result = certified("x^2=-1", domain="complex")
    assert result.certificate.status == "unsupported"
    assert result.status == "unresolved"


def test_printed_approximations_are_inside_certified_intervals():
    result = certified("x^2=2", precision=15)
    for row, interval in zip(result.solutions, result.certificate.intervals):
        approximation = Fraction(row.values["x"].approximate)
        assert Fraction(interval.lower) <= approximation <= Fraction(interval.upper)


def test_expression_evaluation_is_not_mistaken_for_root_certification():
    result = certified("sqrt(x)", solve_for=["x"], data=[{"type": "constant", "name": "x", "value": -1}])
    assert result.status == "unresolved"
    assert result.certificate.status == "unsupported"
