"""Local variable assumptions, set domains, and candidate filtering."""

from __future__ import annotations

import sympy as sp

from src.capabilities.math.utils.parser import MathInputError


def symbol_properties(spec, *, real: bool = False) -> dict:
    properties = {"real": True} if real else {"complex": True}
    if spec is None:
        return properties
    for name in ("real", "positive", "nonnegative", "integer"):
        if getattr(spec, name):
            properties[name] = True
    if spec.min is not None or spec.max is not None:
        properties["real"] = True
    if spec.nonzero:
        properties["zero"] = False  # SymPy nonzero=True would incorrectly force realness.
    return properties


class AssumptionEngine:
    def __init__(self, system) -> None:
        self.system = system
        missing = set(system.options.assumptions) - system.root.symbols.keys()
        if missing:
            raise MathInputError(f"Assumption names are absent from this system: {', '.join(sorted(missing))}.")
        self.specs = {system.root.symbols[name]: spec for name, spec in system.options.assumptions.items()}

    def scale(self, symbol):
        units = getattr(self.system, "units", None)
        return units.input_scale(symbol) if units else sp.S.One

    @property
    def count(self) -> int:
        return sum(sum(bool(getattr(spec, name)) for name in ("real", "positive", "nonnegative", "nonzero", "integer"))
                   + int(spec.min is not None) + int(spec.max is not None) for spec in self.specs.values())

    def check(self, substitutions) -> tuple[bool, list[str]]:
        pending = []
        for symbol, spec in self.specs.items():
            value = substitutions.get(symbol, symbol)
            checks = []
            needs_real = spec.real or spec.positive or spec.nonnegative or spec.integer or spec.min is not None or spec.max is not None
            if needs_real:
                if value.is_real is False:
                    return False, []
                if value.is_real is None:
                    checks.append(sp.Eq(sp.im(value), 0))
            if spec.integer:
                if value.is_integer is False:
                    return False, []
                if value.is_integer is None:
                    checks.append(sp.Contains(value, sp.S.Integers))
            if spec.nonzero:
                checks.append(sp.Ne(value, 0))
            if spec.positive:
                checks.append(sp.Gt(value, 0))
            if spec.nonnegative:
                checks.append(sp.Ge(value, 0))
            if spec.min is not None:
                checks.append(sp.Ge(value, sp.Rational(str(spec.min)) * self.scale(symbol)))
            if spec.max is not None:
                checks.append(sp.Le(value, sp.Rational(str(spec.max)) * self.scale(symbol)))
            for condition in checks:
                condition = sp.simplify(condition)
                if condition is sp.S.false:
                    return False, []
                if condition is not sp.S.true:
                    pending.append(str(condition))
        return True, pending

    def domain_for(self, symbol, domain):
        spec = self.specs.get(symbol)
        if spec is None:
            return domain
        if spec.real or spec.positive or spec.nonnegative or spec.integer or spec.min is not None or spec.max is not None:
            domain = sp.Intersection(domain, sp.S.Reals)
        if spec.integer:
            domain = sp.Intersection(domain, sp.S.Integers)
        if spec.positive:
            domain = sp.Intersection(domain, sp.Interval.open(0, sp.oo))
        elif spec.nonnegative:
            domain = sp.Intersection(domain, sp.Interval(0, sp.oo))
        if spec.nonzero:
            domain = sp.Complement(domain, sp.FiniteSet(0))
        lower = sp.Rational(str(spec.min)) * self.scale(symbol) if spec.min is not None else -sp.oo
        upper = sp.Rational(str(spec.max)) * self.scale(symbol) if spec.max is not None else sp.oo
        if lower != -sp.oo or upper != sp.oo:
            domain = sp.Intersection(domain, sp.Interval(lower, upper))
        return domain
