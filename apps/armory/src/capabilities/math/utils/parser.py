"""Construct symbolic objects from an allowlisted AST, never Python evaluation."""

from __future__ import annotations

import ast
import math
import re
from collections.abc import Callable

import sympy as sp

from src.capabilities.math.contract import FUNCTIONS


class MathInputError(ValueError):
    def __init__(self, message: str, status: str = "invalid") -> None:
        super().__init__(message)
        self.status = status


class MathParser:
    """Keep original denominator constraints alongside each parsed expression."""

    def __init__(self, resolve: Callable[[str], sp.Symbol]) -> None:
        self.resolve = resolve
        self.denominators: list[sp.Expr] = []
        self.power_domains: list[tuple[sp.Expr, sp.Expr]] = []
        self.symbols: set[sp.Symbol] = set()
        self._source = ""

    def parse(self, source: str) -> sp.Expr:
        self._source = source.strip().replace("^", "**")
        try:
            tree = ast.parse(self._source, mode="eval")
        except (SyntaxError, ValueError, RecursionError) as error:
            raise MathInputError("Invalid math syntax; use explicit multiplication such as m * b.") from error
        if sum(1 for _ in ast.walk(tree)) > 512:
            raise MathInputError("Expression exceeds 512 syntax nodes.", "limited")
        return self._visit(tree.body)

    def _visit(self, node: ast.AST) -> sp.Expr:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            text = ast.get_source_segment(self._source, node) or ""
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise MathInputError("Numeric literals must be finite.")
            if not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
                raise MathInputError("Use decimal numeric literals.")
            if sum(character.isdigit() for character in text) > 100:
                raise MathInputError("Numeric literals exceed 100 digits.", "limited")
            exponent = re.search(r"[eE]([+-]?\d+)$", text)
            if exponent and abs(int(exponent[1])) > 1000:
                raise MathInputError("Decimal exponent exceeds 1000.", "limited")
            return sp.Rational(text)
        if isinstance(node, ast.Name):
            constants = {"i": sp.I, "I": sp.I, "pi": sp.pi, "E": sp.E}
            if node.id in constants:
                return constants[node.id]
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", node.id) or node.id in FUNCTIONS:
                raise MathInputError("Invalid or reserved variable name.")
            symbol = self.resolve(node.id)
            self.symbols.add(symbol)
            return symbol
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = self._visit(node.operand)
            return operand if isinstance(node.op, ast.UAdd) else sp.Mul(-1, operand, evaluate=False)
        if isinstance(node, ast.BinOp):
            left, right = self._visit(node.left), self._visit(node.right)
            if isinstance(node.op, ast.Add):
                return sp.Add(left, right, evaluate=False)
            if isinstance(node.op, ast.Sub):
                return sp.Add(left, sp.Mul(-1, right, evaluate=False), evaluate=False)
            if isinstance(node.op, ast.Mult):
                return sp.Mul(left, right, evaluate=False)
            if isinstance(node.op, ast.Div):
                self._denominator(right)
                return sp.Mul(left, sp.Pow(right, -1, evaluate=False), evaluate=False)
            if isinstance(node.op, ast.Pow):
                if right.is_number and abs(right) > 1000:
                    raise MathInputError("Numeric exponent magnitude exceeds 1000.", "limited")
                if right.is_negative:
                    self._denominator(left)
                elif right.is_nonnegative is not True:
                    # Its sign/domain can change after recursive bindings resolve.
                    self.power_domains.append((left, right))
                return sp.Pow(left, right, evaluate=False)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name in FUNCTIONS and len(node.args) == 1 and not node.keywords:
                argument = self._visit(node.args[0])
                if name == "sqrt":
                    return sp.Pow(argument, sp.Rational(1, 2), evaluate=False)
                if name == "log":
                    self._denominator(argument)
                elif name == "tan":
                    self._denominator(sp.cos(argument, evaluate=False))
                elif name == "tanh":
                    self._denominator(sp.cosh(argument, evaluate=False))
                elif name == "atan":
                    self._denominator(1 + argument**2)
                function = sp.Abs if name == "abs" else getattr(sp, name)
                return function(argument, evaluate=False)
        raise MathInputError("Only numbers, variables, arithmetic, and approved single-argument math functions are accepted.")

    def _denominator(self, value: sp.Expr) -> None:
        if value.is_zero is True:
            raise MathInputError("Division by zero is undefined.")
        self.denominators.append(value)
