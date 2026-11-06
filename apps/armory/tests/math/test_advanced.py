"""Exact bounded matrix operations and calculus retain honest domain evidence."""

import pytest

from src.capabilities.math.contract import CalculusRequest, MatrixRequest
from src.capabilities.math.utils.advanced import calculate


def matrix(operation, *matrices):
    return calculate(MatrixRequest(operation=operation, data={"matrices": list(matrices)}))


def calculus(expression, **options):
    return calculate(CalculusRequest(expression=expression, data={"variable": "x", **options}))


def test_matrix_exact_inverse_product_and_pivots():
    inverse = matrix("inverse", [[1, 2], [3, 4]])
    assert [[v.exact for v in row] for row in inverse.matrix] == [["-2", "1"], ["3/2", "-1/2"]]
    product = matrix("multiply", [[1, 2], [3, 4]], [[-2, 1], ["3/2", "-1/2"]])
    assert [[v.exact for v in row] for row in product.matrix] == [["1", "0"], ["0", "1"]]
    reduced = matrix("rref", [[1, 2], [2, 4]])
    assert reduced.rank == 1 and reduced.pivots == [0]
    assert matrix("determinant", [[1, 2], [3, 4]]).value.exact == "-2"


def test_matrix_shape_singularity_and_underdetermined_system():
    assert matrix("inverse", [[1, 2], [2, 4]]).status == "invalid"
    assert matrix("multiply", [[1, 2]], [[1, 2]]).status == "invalid"
    assert matrix("rank", [[1], [1, 2]]).status == "invalid"
    assert matrix("solve", [[1, 1], [2, 2]], [[1], [3]]).status == "inconsistent"
    family = matrix("solve", [[1, 1], [2, 2]], [[1], [2]])
    assert family.status == "parametric" and family.free_parameters
    assert matrix("solve", [[2, 0], [0, 4]], [[1], [1]]).matrix[1][0].exact == "1/4"


def test_derivative_exact_and_original_hole_retained():
    result = calculus("(x^2-1)/(x-1)", operation="differentiate")
    assert result.value.exact == "1"
    assert any("x - 1" in c.text and c.source == "domain" for c in result.structured_conditions)
    second = calculus("sin(x)", operation="differentiate", order=2)
    assert second.value.exact == "-sin(x)"


def test_integrals_verified_and_singular_definite_integrals_refused():
    result = calculus("x^2", operation="integrate")
    assert result.value.exact == "x**3/3" and result.integration_constant
    assert result.verification.status == "exact"
    assert calculus("x^2", operation="integrate", bounds=[0, 3]).value.exact == "9"
    assert calculus("x^2", operation="integrate", bounds=[3, 0]).value.exact == "-9"
    assert calculus("1/x", operation="integrate", bounds=[-1, 1]).status == "unresolved"
    assert calculus("(x^2-1)/(x-1)", operation="integrate", bounds=[0, 2]).status == "unresolved"


@pytest.mark.parametrize("entry", ["x", "__import__('os')", "1/0"])
def test_matrix_entries_cannot_execute_code_or_reference_symbols(entry):
    assert matrix("rank", [[entry]]).status == "invalid"


def test_real_log_integral_does_not_claim_global_real_primitive():
    result = calculus("1/x", operation="integrate")
    assert result.verification.status in {"conditional", "exact"}
    assert result.conditions  # Domain/branch restrictions must accompany primitive.


@pytest.mark.parametrize("expression", ["sqrt(-1)", "log(-1)"])
def test_empty_real_domain_cannot_produce_exact_derivative(expression):
    assert calculus(expression, operation="differentiate").status == "invalid"


def test_parameter_domains_are_real_predicates_and_unproven_scope_is_conditional():
    import sympy as sp
    from src.capabilities.math.utils.conditions import decode_predicate
    result = calculus("sqrt(y)", operation="differentiate")
    assert result.verification.status == "conditional" and result.completeness == "partial"
    resolve = lambda name: sp.Symbol(name, real=True)
    assert any(sp.simplify(decode_predicate(record.predicate, resolve).subs(resolve("y"), -1)) is sp.S.false
               for record in result.structured_conditions)


@pytest.mark.parametrize("expression", ["log(x)", "sqrt(x)"])
def test_complex_derivatives_exclude_principal_branch_cut(expression):
    import sympy as sp
    from src.capabilities.math.utils.conditions import decode_predicate
    result = calculus(expression, operation="differentiate", domain="complex")
    resolve = lambda name: sp.Symbol(name)
    assert any(sp.simplify(decode_predicate(record.predicate, resolve).subs(resolve("x"), -1)) is sp.S.false
               for record in result.structured_conditions if record.reusable)


@pytest.mark.parametrize("expression,expected", [("sqrt(-1)*x", "I"), ("log(-1)*x", "I*pi")])
def test_complex_branch_constants_are_valid_coefficients(expression, expected):
    import sympy as sp
    from src.capabilities.math.utils.conditions import decode_predicate
    result = calculus(expression, operation="differentiate", domain="complex")
    assert result.value.exact == expected
    assert all(sp.simplify(decode_predicate(record.predicate, sp.Symbol)) is not sp.S.false for record in result.structured_conditions)
