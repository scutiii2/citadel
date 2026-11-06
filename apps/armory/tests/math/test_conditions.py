"""Structured restrictions preserve executable meaning without string evaluation."""

from __future__ import annotations

import pytest
import sympy as sp

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.conditions import decode_predicate, encode_condition
from src.capabilities.math.utils.parser import MathInputError
from src.capabilities.math.utils.solver import solve_request


def test_predicate_round_trip_retains_complex_nonzero_and_boolean_logic():
    x = sp.Symbol("x", complex=True)
    predicate = sp.Or(sp.Ne(x, 0), sp.And(sp.Eq(sp.im(x), 0), sp.Ge(sp.re(x), 0)))
    record = encode_condition(predicate, "domain")
    rebuilt = decode_predicate(record.predicate, lambda name: x)
    assert rebuilt.subs(x, sp.I) is sp.S.true
    assert rebuilt.subs(x, -1) is sp.S.true
    assert record.reusable is True
    assert record.source == "domain"


def test_assumed_facts_are_explicit_even_when_symbol_properties_simplify_them():
    result = solve_request(SolveRequest(equation={"expression": "y=x", "assumptions": {"x": {"positive": True}}}, data=[]))
    facts = result.solutions[0].structured_conditions
    positive = [fact for fact in facts if fact.source == "assumption" and fact.predicate.operator == "gt"]
    assert positive
    x = sp.Symbol("x", complex=True)
    assert decode_predicate(positive[0].predicate, lambda name: x).subs(x, -1) is sp.S.false


def test_resolved_domain_restrictions_remain_available_for_continuation():
    result = solve_request(SolveRequest(equation="y=1/x", data=[{"type": "constant", "name": "x", "value": 2}]))
    facts = result.solutions[0].structured_conditions
    assert any(fact.source == "domain" and fact.predicate.operator == "ne" for fact in facts)
    assert result.solutions[0].values["y"].expression.kind == "rational"


def test_inherited_condition_rejects_a_conflicting_binding():
    x = sp.Symbol("x")
    condition = encode_condition(sp.Ne(x, 0, evaluate=False), "imported")
    result = solve_request(SolveRequest(equation="y=x", data=[{"type": "constant", "name": "x", "value": 0}], preconditions=[condition]))
    assert result.status == "inconsistent"


def test_unknown_or_opaque_predicates_fail_explicitly():
    record = encode_condition(sp.Contains(sp.Symbol("x"), sp.FiniteSet(1, 2)), "solver")
    if not record.reusable:
        with pytest.raises(MathInputError):
            decode_predicate(record.predicate, lambda name: sp.Symbol(name))


def test_deep_predicate_trees_are_bounded():
    from src.capabilities.math.contract import PredicateNode

    node = PredicateNode(operator="true")
    for _ in range(20):
        node = PredicateNode(operator="not", children=[node])
    with pytest.raises(MathInputError):
        decode_predicate(node, lambda name: sp.Symbol(name))
