"""Bounded symbolic exchange without evaluating serialized Python strings."""

from __future__ import annotations

import re

import sympy as sp

from src.capabilities.math.contract import ExpressionNode, FUNCTIONS, PredicateNode, StructuredCondition
from src.capabilities.math.utils.parser import MathInputError

FUNCTION_MAP = {name: getattr(sp, name) for name in FUNCTIONS - {"abs"}}
FUNCTION_MAP.update(abs=sp.Abs, re=sp.re, im=sp.im)
RELATIONS = {"eq": sp.Eq, "ne": sp.Ne, "gt": sp.Gt, "ge": sp.Ge, "lt": sp.Lt, "le": sp.Le}


class Budget:
    def __init__(self):
        self.nodes = 0

    def check(self, depth):
        self.nodes += 1
        if depth > 16 or self.nodes > 256:
            raise MathInputError("Symbolic exchange exceeds depth 16 or 256 nodes.")


def encode_expression(value, *, _budget=None, _depth=0) -> ExpressionNode:
    budget = _budget or Budget()
    try:
        budget.check(_depth)
    except MathInputError:
        return ExpressionNode(kind="opaque", value=str(value)[:2048])
    if isinstance(value, sp.Symbol):
        return ExpressionNode(kind="symbol" if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", str(value)) else "opaque", value=str(value)[:2048])
    if value in (sp.I, sp.pi, sp.E, sp.oo, -sp.oo):
        return ExpressionNode(kind="constant", value=str(value))
    if isinstance(value, sp.Integer):
        return ExpressionNode(kind="integer" if len(str(value)) <= 400 else "opaque", value=str(value)[:2048])
    if isinstance(value, sp.Rational):
        return ExpressionNode(kind="rational" if len(str(value)) <= 400 else "opaque", value=str(value)[:2048])
    if isinstance(value, sp.Float):
        return ExpressionNode(kind="float", value=str(value))
    kind = "add" if isinstance(value, sp.Add) else "multiply" if isinstance(value, sp.Mul) else "power" if isinstance(value, sp.Pow) else None
    function_name = "abs" if value.func == sp.Abs else value.func.__name__
    if kind is None and function_name in FUNCTION_MAP:
        kind = "function"
    if kind is None or len(value.args) > 32:
        return ExpressionNode(kind="opaque", value=str(value)[:2048])
    return ExpressionNode(kind=kind, value=function_name if kind == "function" else None,
                          args=[encode_expression(arg, _budget=budget, _depth=_depth + 1) for arg in value.args])


def reusable_expression(node):
    return node.kind != "opaque" and all(reusable_expression(arg) for arg in node.args)


def decode_expression(node, resolve, *, _budget=None, _depth=0):
    budget = _budget or Budget()
    budget.check(_depth)
    value = node.value or ""
    if node.kind in {"integer", "rational", "float"}:
        if node.args or len(value) > 400 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:/\d+)?", value):
            raise MathInputError("Invalid numeric symbolic node.")
        if "e" in value.lower() and abs(int(re.split("[eE]", value)[1])) > 1000:
            raise MathInputError("Symbolic numeric exponent exceeds limits.")
        result = sp.Rational(value)
        if result.is_finite is not True:
            raise MathInputError("Non-finite symbolic numeric node.")
        return result
    if node.kind == "constant" and not node.args and value in {"I", "pi", "E", "oo", "-oo"}:
        return {"I": sp.I, "pi": sp.pi, "E": sp.E, "oo": sp.oo, "-oo": -sp.oo}[value]
    if node.kind == "symbol" and not node.args and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", value):
        return resolve(value)
    args = [decode_expression(arg, resolve, _budget=budget, _depth=_depth + 1) for arg in node.args]
    if node.kind == "add" and args:
        return sp.Add(*args, evaluate=False)
    if node.kind == "multiply" and args:
        return sp.Mul(*args, evaluate=False)
    if node.kind == "power" and len(args) == 2:
        if args[1].is_number and abs(args[1]) > 1000:
            raise MathInputError("Symbolic power exponent exceeds limits.")
        return sp.Pow(*args, evaluate=False)
    if node.kind == "function" and value in FUNCTION_MAP and len(args) == 1:
        return FUNCTION_MAP[value](*args, evaluate=False)
    raise MathInputError("Unsupported or opaque symbolic node; cannot reuse this condition.")


def _encode_predicate(value, budget, depth):
    budget.check(depth)
    if value is sp.S.true:
        return PredicateNode(operator="true")
    if value is sp.S.false:
        return PredicateNode(operator="false")
    if value.func in (sp.And, sp.Or, sp.Not):
        op = {sp.And: "and", sp.Or: "or", sp.Not: "not"}[value.func]
        if len(value.args) > 32:
            return PredicateNode(operator="opaque")
        return PredicateNode(operator=op, children=[_encode_predicate(arg, budget, depth + 1) for arg in value.args])
    for name, constructor in RELATIONS.items():
        if isinstance(value, constructor):
            return PredicateNode(operator=name, arguments=[encode_expression(arg, _budget=budget, _depth=depth + 1) for arg in value.args])
    if isinstance(value, sp.Contains) and value.args[1] in (sp.S.Integers, sp.S.Reals):
        return PredicateNode(operator="integer" if value.args[1] == sp.S.Integers else "real", arguments=[encode_expression(value.args[0], _budget=budget, _depth=depth + 1)])
    return PredicateNode(operator="opaque")


def encode_condition(value, source) -> StructuredCondition:
    try:
        node = _encode_predicate(value, Budget(), 0)
    except MathInputError:
        node = PredicateNode(operator="opaque")
    def reusable(predicate):
        return predicate.operator != "opaque" and all(reusable_expression(arg) for arg in predicate.arguments) and all(reusable(child) for child in predicate.children)
    return StructuredCondition(predicate=node, text=str(value)[:4096], source=source, reusable=reusable(node))


def decode_predicate(node, resolve, *, _budget=None, _depth=0):
    budget = _budget or Budget()
    budget.check(_depth)
    args = [decode_expression(arg, resolve, _budget=budget, _depth=_depth + 1) for arg in node.arguments]
    children = [decode_predicate(child, resolve, _budget=budget, _depth=_depth + 1) for child in node.children]
    if node.operator in RELATIONS and len(args) == 2 and not children:
        return RELATIONS[node.operator](*args, evaluate=False)
    if node.operator in {"integer", "real", "finite"} and len(args) == 1 and not children:
        if node.operator == "finite":
            return sp.Q.finite(args[0])
        return sp.Contains(args[0], sp.S.Integers if node.operator == "integer" else sp.S.Reals, evaluate=False)
    if not args:
        if node.operator in {"and", "or"} and children:
            return (sp.And if node.operator == "and" else sp.Or)(*children, evaluate=False)
        if node.operator == "not" and len(children) == 1:
            return sp.Not(children[0], evaluate=False)
        if not children and node.operator in {"true", "false"}:
            return sp.S.true if node.operator == "true" else sp.S.false
    raise MathInputError("Unsupported or malformed structured predicate.")


def source_conditions(system, substitutions, *, tolerance=None, constraints=None):
    """Keep root facts even when currently resolved; eliminate private helpers."""
    private = {symbol: value for symbol, value in substitutions.items() if symbol not in system.root.symbols.values()}
    records = list(system.preconditions)
    def add(value, source):
        if len(records) < 128:
            records.append(encode_condition(value.subs(private, simultaneous=True), source))
        elif len(records) == 128:
            records.append(StructuredCondition(predicate=PredicateNode(operator="opaque"), source="solver", reusable=False,
                                               text="Additional restrictions exceed exchange capacity; continuation is unsupported."))
    for value in system.denominators:
        add(sp.Ne(value, 0, evaluate=False), "domain")
    from src.capabilities.math.utils.solver import _power_condition

    for base, exponent in system.power_domains:
        add(_power_condition(base, exponent), "domain")
    for predicate in system.case_predicates:
        add(predicate, "case")
    if system.options.domain == "real":
        for symbol in system.root.symbols.values():
            add(sp.Contains(symbol, sp.S.Reals, evaluate=False), "domain")
    for symbol, spec in system.assumptions.specs.items():
        if spec.real or spec.positive or spec.nonnegative or spec.integer or spec.min is not None or spec.max is not None:
            add(sp.Contains(symbol, sp.S.Reals, evaluate=False), "assumption")
        if spec.integer:
            add(sp.Contains(symbol, sp.S.Integers, evaluate=False), "assumption")
        for active, condition in ((spec.positive, sp.Gt(symbol, 0, evaluate=False)), (spec.nonnegative, sp.Ge(symbol, 0, evaluate=False)),
                                  (spec.nonzero, sp.Ne(symbol, 0, evaluate=False))):
            if active:
                add(condition, "assumption")
        if spec.min is not None:
            add(sp.Ge(symbol, sp.Rational(str(spec.min)) * system.assumptions.scale(symbol), evaluate=False), "assumption")
        if spec.max is not None:
            add(sp.Le(symbol, sp.Rational(str(spec.max)) * system.assumptions.scale(symbol), evaluate=False), "assumption")
    for value in system.constraints if constraints is None else constraints:
        add(sp.Eq(value, 0, evaluate=False) if tolerance is None else sp.Le(sp.Abs(value, evaluate=False), tolerance, evaluate=False), "verification")
    return records


class ConditionEngine:
    def __init__(self, system, records):
        self.records = records
        def resolve(name):
            if name not in system.root.symbols:
                raise MathInputError(f"Inherited condition references unavailable variable {name}.")
            return system.root.symbols[name]
        self.predicates = [decode_predicate(record.predicate, resolve) for record in records]

    def check(self, substitutions):
        pending = []
        for predicate in self.predicates:
            try:
                value = sp.simplify(predicate.subs(substitutions, simultaneous=True))
            except (ValueError, TypeError, ZeroDivisionError):
                return False, []
            if value is sp.S.false or value.has(sp.nan, sp.zoo):
                return False, []
            if value is not sp.S.true:
                pending.append(str(value))
        return True, pending
