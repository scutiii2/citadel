"""Strict LaTeX subset normalizes visibly before restricted math parsing."""

from __future__ import annotations

import pytest

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.latex import normalize_latex
from src.capabilities.math.utils.parser import MathInputError
from src.capabilities.math.utils.solver import solve_request


def test_fraction_and_implicit_products_match_equivalent_math():
    result = solve_request(SolveRequest(equation={"expression": r"y=\frac{m b}{2}+x", "syntax": "latex"}, data=[
        {"type": "constant", "name": "m", "value": 5}, {"type": "constant", "name": "b", "value": 6},
        {"type": "constant", "name": "x", "value": 5},
    ]))
    assert result.solutions[0].values["y"].exact == "20"
    assert result.normalization.syntax == "latex"
    assert "*" in result.normalization.normalized[0]


@pytest.mark.parametrize("source, expected", [
    (r"\sqrt{4}", "2"), (r"\sin^{2}(\pi/2)", "1"),
    (r"\left| -3 \right|", "3"), (r"2(3+4)", "14"),
    (r"-2^2", "-4"), (r"2^{-2}", "1/4"),
    (r"\frac{1}{\frac{2}{3}}", "3/2"),
])
def test_supported_notation_preserves_mathematical_precedence(source, expected):
    result = solve_request(SolveRequest(equation={"expression": source, "syntax": "latex"}, data=[]))
    assert result.status == "unique"
    assert result.value.exact == expected


def test_roman_variable_names_and_subscripts_remain_single_symbols():
    result = solve_request(SolveRequest(equation={"expression": r"y=\mathrm{mass}+x_{1}", "syntax": "latex"}, data=[
        {"type": "constant", "name": "mass", "value": 3}, {"type": "constant", "name": "x_1", "value": 2},
    ]))
    assert result.solutions[0].values["y"].exact == "5"


def test_bare_adjacent_letters_expose_product_interpretation():
    normalized, notes = normalize_latex("mb")
    assert "*" in normalized
    assert notes


@pytest.mark.parametrize("source", [r"\input{secret}", r"\newcommand{\x}{1}", r"\begin{matrix}1\end{matrix}",
                                         r"\frac{1}", r"\sqrt[3]{8}", r"\unknown{x}", "x.__class__", r"\mathrm{bad name}"])
def test_unsupported_or_unsafe_tex_fails_explicitly(source):
    with pytest.raises(MathInputError):
        normalize_latex(source)
