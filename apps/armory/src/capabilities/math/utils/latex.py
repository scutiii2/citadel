"""A bounded, explicit LaTeX subset translated to restricted math syntax.

This module performs no symbolic computation. Its output is input for MathParser
inside the existing isolated math worker, never for Python evaluation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.capabilities.math.contract import FUNCTIONS
from src.capabilities.math.utils.parser import MathInputError

_MAX_LENGTH = 4096
_MAX_TOKENS = 1024
_MAX_DEPTH = 32
_FUNCTIONS = {name: name for name in FUNCTIONS if name != "sqrt"}
_FUNCTIONS.update({"ln": "log", "arcsin": "asin", "arccos": "acos", "arctan": "atan"})
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z")


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str


def _tokenize(source: str) -> tuple[list[_Token], bool]:
    tokens: list[_Token] = []
    adjacent_letters = False
    index = 0
    previous_letter = False
    while index < len(source):
        character = source[index]
        if character.isspace():
            index += 1
            continue
        if character == "\\":
            match = re.match(r"\\([A-Za-z]+)", source[index:])
            if not match:
                raise MathInputError("Unsupported LaTeX escape.")
            command = match[1]
            index += len(match[0])
            if command in {"left", "right"}:
                while index < len(source) and source[index].isspace():
                    index += 1
                delimiters = "(|" if command == "left" else ")|"
                if index >= len(source) or source[index] not in delimiters:
                    raise MathInputError("LaTeX left/right must precede a supported delimiter.")
                continue
            if command in {"mathrm", "operatorname"}:
                match = re.match(r"\s*\{([^{}]*)\}", source[index:])
                if not match:
                    raise MathInputError(f"LaTeX {command} requires one braced name.")
                name = match[1]
                index += len(match[0])
                if command == "mathrm":
                    if not _NAME.fullmatch(name) or name in FUNCTIONS:
                        raise MathInputError("LaTeX mathrm requires one safe, non-function variable name.")
                    token = _Token("name", name)
                else:
                    if name not in FUNCTIONS:
                        raise MathInputError("LaTeX operatorname requires an approved math function.")
                    token = _Token("function", name)
            elif command == "frac":
                token = _Token("frac", command)
            elif command == "sqrt":
                token = _Token("sqrt", command)
            elif command in _FUNCTIONS:
                token = _Token("function", _FUNCTIONS[command])
            elif command == "pi":
                token = _Token("name", "pi")
            elif command in {"cdot", "times", "div"}:
                token = _Token("*" if command != "div" else "/", command)
            else:
                raise MathInputError(f"Unsupported LaTeX command: {command}.")
            previous_letter = False
        elif character in "+-*/^=(){}|_":
            token = _Token(character, character)
            index += 1
            previous_letter = False
        elif character.isascii() and character.isalpha():
            adjacent_letters |= previous_letter
            token = _Token("name", character)
            previous_letter = True
            index += 1
        elif character.isascii() and (character.isdigit() or character == "."):
            match = re.match(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", source[index:])
            if not match:
                raise MathInputError("Invalid LaTeX decimal number.")
            token = _Token("number", match[0])
            index += len(match[0])
            previous_letter = False
        else:
            raise MathInputError(f"Unsupported character in LaTeX: {character!r}.")
        tokens.append(token)
        if len(tokens) > _MAX_TOKENS:
            raise MathInputError("LaTeX exceeds 1024 tokens.", "limited")
    tokens.append(_Token("end", ""))
    return tokens, adjacent_letters


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.depth = 0

    @property
    def kind(self) -> str:
        return self.tokens[self.index].kind

    def take(self, kind: str) -> _Token:
        if self.kind != kind:
            raise MathInputError(f"Expected {kind!r} in LaTeX expression.")
        token = self.tokens[self.index]
        self.index += 1
        return token

    def checked(self, value: str) -> str:
        if len(value) > _MAX_LENGTH:
            raise MathInputError("Normalized LaTeX exceeds 4096 characters.", "limited")
        return value

    def nested(self, operation) -> str:
        self.depth += 1
        try:
            if self.depth > _MAX_DEPTH:
                raise MathInputError("LaTeX nesting exceeds 32 levels.", "limited")
            return operation()
        finally:
            self.depth -= 1

    def expression(self, stop: str = "end") -> str:
        value = self.product(stop)
        while self.kind in {"+", "-"}:
            operator = self.kind
            self.take(operator)
            value = self.checked(f"({value}{operator}{self.product(stop)})")
        return value

    def product(self, stop: str) -> str:
        value = self.unary(stop)
        starts = {"number", "name", "(", "{", "|", "frac", "sqrt", "function"}
        while self.kind != stop:
            if self.kind in {"*", "/"}:
                operator = self.kind
                self.take(operator)
            elif self.kind in starts:
                operator = "*"
            else:
                break
            value = self.checked(f"({value}{operator}{self.unary(stop)})")
        return value

    def unary(self, stop: str) -> str:
        if self.kind in {"+", "-"}:
            operator = self.kind
            self.take(operator)
            return self.checked(f"({operator}{self.nested(lambda: self.unary(stop))})")
        return self.power(stop)

    def power(self, stop: str) -> str:
        value = self.atom(stop)
        if self.kind == "^":
            self.take("^")
            exponent = self.nested(lambda: self.unary(stop))
            value = self.checked(f"({value}**{exponent})")
        return value

    def group(self, opening: str, closing: str) -> str:
        self.take(opening)
        value = self.nested(lambda: self.expression(closing))
        self.take(closing)
        return value

    def atom(self, stop: str) -> str:
        kind = self.kind
        if kind == "number":
            return self.take(kind).value
        if kind == "name":
            value = self.take(kind).value
            if self.kind == "_":
                self.take("_")
                braced = self.kind == "{"
                if braced:
                    self.take("{")
                if self.kind not in {"number", "name"}:
                    raise MathInputError("LaTeX subscripts require one letter or integer.")
                subscript = self.take(self.kind).value
                if not re.fullmatch(r"[A-Za-z]|[0-9]+", subscript):
                    raise MathInputError("LaTeX subscripts require one letter or integer.")
                if braced:
                    self.take("}")
                value += "_" + subscript
                if not _NAME.fullmatch(value):
                    raise MathInputError("LaTeX variable name exceeds 32 characters.")
            return value
        if kind in {"(", "{"}:
            return self.group(kind, ")" if kind == "(" else "}")
        if kind == "|" and stop != "|":
            return self.checked(f"abs({self.group('|', '|')})")
        if kind == "frac":
            self.take(kind)
            numerator = self.group("{", "}")
            denominator = self.group("{", "}")
            return self.checked(f"({numerator}/{denominator})")
        if kind == "sqrt":
            self.take(kind)
            return self.checked(f"sqrt({self.group('{', '}')})")
        if kind == "function":
            name = self.take(kind).value
            exponent = None
            if self.kind == "^":
                self.take("^")
                exponent = self.nested(lambda: self.unary(stop))
            if self.kind in {"(", "{"}:
                argument = self.atom(stop)
            else:
                argument = self.nested(lambda: self.unary(stop))
            value = self.checked(f"{name}({argument})")
            return self.checked(f"({value}**{exponent})") if exponent is not None else value
        raise MathInputError("Expected a number, variable, group, or approved LaTeX function.")


def normalize_latex(source: str) -> tuple[str, list[str]]:
    """Normalize one expression or equality without evaluating any math."""
    if not isinstance(source, str) or not source.strip():
        raise MathInputError("LaTeX expression must be a nonempty string.")
    if len(source) > _MAX_LENGTH:
        raise MathInputError("LaTeX source exceeds 4096 characters.", "limited")
    tokens, adjacent = _tokenize(source)
    parser = _Parser(tokens)
    result = parser.expression()
    if parser.kind == "=":
        parser.take("=")
        result = parser.checked(f"{result}={parser.expression()}")
    parser.take("end")
    notes = ["Bare adjacent letters are interpreted as multiplication; use \\mathrm{name} for a single variable."] if adjacent else []
    return result, notes
