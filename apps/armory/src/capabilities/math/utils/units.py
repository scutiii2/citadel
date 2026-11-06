"""Exact curated units and dimensional checks on unsimplified math expressions."""

from __future__ import annotations

import ast
from dataclasses import dataclass

import sympy as sp

from src.capabilities.math.utils.parser import MathInputError

ZERO = (sp.S.Zero,) * 7
BASE_NAMES = ("m", "kg", "s", "A", "K", "mol", "cd")


@dataclass(frozen=True)
class Unit:
    scale: sp.Expr
    dimensions: tuple
    label: str
    cost: int = 16

    def multiply(self, other, *, divide=False):
        sign = -1 if divide else 1
        cost = self.cost + other.cost
        dimensions = tuple(left + sign * right for left, right in zip(self.dimensions, other.dimensions))
        if cost > 1024 or any(abs(value) > 64 for value in dimensions):
            raise MathInputError("Cumulative unit scale or dimensional exponent exceeds limits.")
        return Unit(self.scale / other.scale if divide else self.scale * other.scale,
                    dimensions, "", cost)

    def power(self, exponent):
        dimensions = tuple(value * exponent for value in self.dimensions)
        cost = self.cost * abs(exponent)
        if cost > 1024 or any(abs(value) > 64 for value in dimensions):
            raise MathInputError("Cumulative unit scale or dimensional exponent exceeds limits.")
        return Unit(self.scale**exponent, dimensions, "", cost)


def _registry():
    registry = {"1": Unit(sp.S.One, ZERO, "1")}
    for index, name in enumerate(BASE_NAMES):
        dimensions = tuple(sp.S.One if axis == index else sp.S.Zero for axis in range(7))
        registry[name] = Unit(sp.S.One, dimensions, name)
    for name, base, scale in (
        ("km", "m", 1000), ("cm", "m", sp.Rational(1, 100)), ("mm", "m", sp.Rational(1, 1000)),
        ("um", "m", sp.Rational(1, 10**6)), ("ms", "s", sp.Rational(1, 1000)),
        ("us", "s", sp.Rational(1, 10**6)), ("min", "s", 60), ("h", "s", 3600),
        ("g", "kg", sp.Rational(1, 1000)), ("mg", "kg", sp.Rational(1, 10**6)),
    ):
        registry[name] = Unit(sp.Rational(scale), registry[base].dimensions, name)
    m, kg, second = registry["m"], registry["kg"], registry["s"]
    derived = {
        "N": kg.multiply(m).multiply(second.power(2), divide=True),
        "Hz": second.power(-1), "L": Unit(sp.Rational(1, 1000), m.power(3).dimensions, "L"),
        "rad": registry["1"], "deg": Unit(sp.pi / 180, ZERO, "deg"),
        "percent": Unit(sp.Rational(1, 100), ZERO, "percent"),
    }
    derived["Pa"] = derived["N"].multiply(m.power(2), divide=True)
    derived["J"] = derived["N"].multiply(m)
    derived["W"] = derived["J"].multiply(second, divide=True)
    registry.update({name: Unit(unit.scale, unit.dimensions, name) for name, unit in derived.items()})
    for name, base, factor in (("kPa", "Pa", 1000), ("MPa", "Pa", 10**6), ("kJ", "J", 1000), ("kW", "W", 1000),
                               ("mL", "L", sp.Rational(1, 1000)), ("bar", "Pa", 100000), ("atm", "Pa", 101325)):
        registry[name] = Unit(registry[base].scale * factor, registry[base].dimensions, name)
    return registry


REGISTRY = _registry()


def parse_unit(text: str) -> Unit:
    """No arbitrary symbols, calls, attributes, addition, or offset units."""
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as error:
        raise MathInputError("Invalid unit syntax.") from error
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise MathInputError("Unit expression exceeds 64 syntax nodes.")

    def visit(node):
        if isinstance(node, ast.Name) and node.id in REGISTRY:
            return REGISTRY[node.id]
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value == 1:
            return REGISTRY["1"]
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
            return visit(node.left).multiply(visit(node.right), divide=isinstance(node.op, ast.Div))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = node.right
            sign = 1
            if isinstance(exponent, ast.UnaryOp) and isinstance(exponent.op, (ast.UAdd, ast.USub)):
                sign = -1 if isinstance(exponent.op, ast.USub) else 1
                exponent = exponent.operand
            if isinstance(exponent, ast.Constant) and type(exponent.value) is int and abs(exponent.value) <= 12:
                return visit(node.left).power(sign * exponent.value)
        raise MathInputError("Unsupported unit; use curated units with *, /, and integer powers from -12 to 12.")

    result = visit(tree.body)
    return Unit(result.scale, result.dimensions, text)


def canonical(dimensions) -> str:
    parts = [name if exponent == 1 else f"{name}**({exponent})" for name, exponent in zip(BASE_NAMES, dimensions) if exponent != 0]
    return "*".join(parts) or "1"


class UnitSystem:
    def __init__(self, system) -> None:
        self.system = system
        self.active = bool(system.options.units or system.options.output_units or system.options.result_unit)
        self.inputs: dict = {}
        self.known: dict = {}
        self.dimensions: dict = {}
        self.expression_dimensions = ZERO
        self._dimension_equations = []
        self._unknowns = {}
        self.constant_magnitudes = {}

    def _declare(self, symbol, unit):
        previous = self.known.get(symbol)
        if previous is not None and previous != unit.dimensions:
            raise MathInputError(f"Conflicting dimensions declared for {symbol}.")
        self.known[symbol] = unit.dimensions

    def constant(self, symbol, explicit_unit, magnitude=None):
        declared = self.system.options.units.get(str(symbol))
        unit = parse_unit(explicit_unit or declared or "1")
        self.active |= bool(explicit_unit)
        self.inputs[symbol] = parse_unit(declared) if declared else unit
        self._declare(symbol, unit)
        if magnitude is not None:
            self.constant_magnitudes[symbol] = magnitude * unit.scale
        return unit.scale

    def input_scale(self, symbol):
        return self.inputs.get(symbol, REGISTRY["1"]).scale

    def _equal(self, left, right):
        self._dimension_equations.append(tuple(a - b for a, b in zip(left, right)))

    def _dim(self, expression):
        if expression.is_number and not expression.free_symbols:
            return ZERO
        if isinstance(expression, sp.Symbol):
            return self.known.get(expression, self._unknowns[expression]) if expression not in self.known else self.known[expression]
        if isinstance(expression, sp.Add):
            terms = [self._dim(value) for value in expression.args if value != sp.S.Zero]
            for term in terms[1:]:
                self._equal(terms[0], term)
            return terms[0] if terms else ZERO
        if isinstance(expression, sp.Mul):
            terms = [self._dim(value) for value in expression.args]
            return tuple(sum(term[axis] for term in terms) for axis in range(7))
        if isinstance(expression, sp.Pow):
            base, exponent = expression.args
            base_dim = self._dim(base)
            self._equal(self._dim(exponent), ZERO)
            exponent = sp.simplify(exponent.subs(self.constant_magnitudes, simultaneous=True))
            if exponent.is_Rational:
                return tuple(value * exponent for value in base_dim)
            self._equal(base_dim, ZERO)
            return ZERO
        if expression.func == sp.Abs:
            return self._dim(expression.args[0])
        if expression.is_Function:
            for argument in expression.args:
                self._equal(self._dim(argument), ZERO)
            return ZERO
        raise MathInputError("Unsupported expression in dimensional analysis.")

    def analyze(self):
        if not self.active:
            return
        for mapping in (self.system.options.units, self.system.options.output_units):
            missing = mapping.keys() - self.system.root.symbols.keys()
            if missing:
                raise MathInputError(f"Unit names absent from this system: {', '.join(sorted(missing))}.")
            for name, text in mapping.items():
                symbol = self.system.root.symbols[name]
                unit = parse_unit(text)
                self._declare(symbol, unit)
                if mapping is self.system.options.units:
                    self.inputs[symbol] = unit
        unknown_symbols = sorted(self.system.symbols - self.known.keys(), key=str)
        self._unknowns = {symbol: tuple(sp.Dummy(f"dimension_{index}_{axis}") for axis in range(7)) for index, symbol in enumerate(unknown_symbols)}
        for left, right in self.system.unit_equations:
            left_dim, right_dim = self._dim(left), self._dim(right)
            if left != sp.S.Zero and right != sp.S.Zero:
                self._equal(left_dim, right_dim)
        if self.system.expression is not None:
            self.expression_dimensions = self._dim(self.system.expression)
        substitutions = {}
        for axis in range(7):
            equations = [row[axis] for row in self._dimension_equations if row[axis] != 0]
            variables = [self._unknowns[symbol][axis] for symbol in unknown_symbols]
            if not variables:
                if equations:
                    raise MathInputError("Incompatible dimensions in equation or function arguments.")
                continue
            values = sp.linsolve(equations, variables) if equations else sp.FiniteSet(tuple(variables))
            if values == sp.S.EmptySet:
                raise MathInputError("Incompatible dimensions in equation or function arguments.")
            substitutions.update(zip(variables, next(iter(values))))
        self.dimensions = dict(self.known)
        for symbol, values in self._unknowns.items():
            values = tuple(sp.simplify(value.subs(substitutions, simultaneous=True)) for value in values)
            self.dimensions[symbol] = values if not any(value.free_symbols for value in values) else None
        expression_dims = tuple(sp.simplify(value.subs(substitutions, simultaneous=True)) for value in self.expression_dimensions)
        self.expression_dimensions = expression_dims if not any(value.free_symbols for value in expression_dims) else None
        if self.system.options.result_unit:
            requested = parse_unit(self.system.options.result_unit)
            if self.system.expression is None or self.expression_dimensions != requested.dimensions:
                raise MathInputError("Requested expression output unit has incompatible or unknown dimensions.")
        for symbol, spec in self.system.assumptions.specs.items():
            if spec.integer and (self.dimensions.get(symbol) != ZERO or self.input_scale(symbol) != 1):
                raise MathInputError("Integer assumptions with units require an unscaled dimensionless variable.")
        ambiguous = sorted(name for name, symbol in self.system.root.symbols.items() if self.dimensions.get(symbol) is None)
        if ambiguous:
            self.system.evidence.diagnose("ambiguous_units", "Physical dimensions are not uniquely determined for some variables.",
                                          "Declare their units explicitly before interpreting physical quantities.", ambiguous)
        self.system.evidence.record("units", "Checked unsimplified dimensions and converted numeric constants to canonical SI magnitudes.")

    def output(self, expression, symbol=None):
        if not self.active:
            return expression, None
        dimensions = self.dimensions.get(symbol) if symbol is not None else self.expression_dimensions
        if dimensions is None:
            return expression, None
        text = self.system.options.output_units.get(str(symbol)) if symbol is not None else self.system.options.result_unit
        desired = parse_unit(text) if text else self.inputs.get(symbol)
        if expression.is_number and desired is not None:
            return sp.simplify(expression / desired.scale), desired.label
        return expression, canonical(dimensions)
