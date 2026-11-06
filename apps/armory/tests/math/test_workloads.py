"""Versioned representative corpus and independently checked equivalences."""

import json
from fractions import Fraction
from pathlib import Path

import pytest

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.solver import solve_request

CORPUS = json.loads((Path(__file__).parent / "fixtures" / "workloads.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["id"])
def test_representative_workload(case):
    assert CORPUS["version"] == 1
    result = solve_request(SolveRequest(equation=case["equation"], data=case["data"]))
    assert result.status == case.get("status", "unique")
    for variable, expected in case.get("expected", {}).items():
        assert result.solutions[0].values[variable].exact == expected
        if variable in case.get("unit", {}):
            assert result.solutions[0].values[variable].unit == case["unit"][variable]
    if "roots" in case:
        assert sorted(row.values["x"].exact for row in result.solutions) == sorted(case["roots"])


@pytest.mark.parametrize("a", range(1, 5))
@pytest.mark.parametrize("b", range(-2, 3))
def test_scaled_linear_equations_match_independent_fraction_oracle(a, b):
    expected = str(Fraction(b, a))
    for multiplier in (1, 3, -2):
        result = solve_request(SolveRequest(equation=f"{multiplier*a}*x={multiplier*b}", data=[]))
        assert result.status == "unique"
        assert result.solutions[0].values["x"].exact == expected


def test_equation_order_and_equivalent_units_preserve_values():
    for equations in (["x+y=7", "2*x-y=2"], ["2*x-y=2", "x+y=7"]):
        result = solve_request(SolveRequest(equation={"expression": equations}, data=[]))
        assert {name: value.exact for name, value in result.solutions[0].values.items()} == {"x": "3", "y": "4"}
    for magnitude, unit in ((1000, "m"), (1, "km")):
        result = solve_request(SolveRequest(equation="v=d/t", data=[
            {"type": "constant", "name": "d", "value": magnitude, "unit": unit},
            {"type": "constant", "name": "t", "value": 20, "unit": "s"},
        ]))
        assert result.solutions[0].values["v"].exact == "50"
