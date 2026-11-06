"""Build a bounded follow-up request while preserving selected-family facts."""

from __future__ import annotations

import json

import sympy as sp
from pydantic import ValidationError

from src.capabilities.math.contract import ContinuationInput, EquationSpec, MAX_BATCH_INPUT_BYTES, SolveRequest
from src.capabilities.math.utils.conditions import decode_expression, decode_predicate, encode_condition
from src.capabilities.math.utils.parser import MathInputError, MathParser


def build_continuation(equation, data) -> SolveRequest:
    try:
        size = len(json.dumps(data, default=lambda value: value.model_dump()).encode("utf-8"))
        if size > MAX_BATCH_INPUT_BYTES:
            raise MathInputError("Prior result exceeds 256 KiB; select a smaller result.")
        spec = ContinuationInput.model_validate(data)
        options = EquationSpec(expression=equation) if isinstance(equation, str) else EquationSpec.model_validate(equation)
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError) as error:
        raise MathInputError("Invalid bounded continuation input.") from error
    previous = spec.previous
    if spec.slot == "value":
        if previous.value is None:
            raise MathInputError("Previous result has no scalar value to reuse.")
        values = {spec.value_name: previous.value}
        conditions = previous.structured_conditions
        legacy_conditions = previous.conditions
    else:
        if spec.solution_index >= len(previous.solutions):
            raise MathInputError("Select an existing solution row; symbolic sets need an explicit point first.")
        selected = previous.solutions[spec.solution_index]
        values = selected.values
        conditions = selected.structured_conditions
        legacy_conditions = selected.conditions
    if legacy_conditions and not conditions:
        raise MathInputError("Legacy readable conditions have no structured equivalent; recompute the prior result.")
    if any(not condition.reusable for condition in conditions):
        raise MathInputError("Prior result contains opaque/private restrictions; cannot safely reuse this family.")
    conditions = list(conditions)
    symbols = {}
    def resolve(name):
        symbols.setdefault(name, sp.Symbol(name, complex=True))
        return symbols[name]
    bindings = {}
    approximate = False
    units = dict(options.units)
    for name, value in values.items():
        if value.exact is None:
            if not spec.allow_approximate or value.approximate is None:
                raise MathInputError("Approximate results need allow_approximate=true; they cannot become exact inputs.")
            expression = MathParser(resolve).parse(value.approximate)
            approximate = True
            is_approximate = True
        elif value.expression is not None:
            expression = decode_expression(value.expression, resolve)
            is_approximate = False
        else:
            expression = MathParser(resolve).parse(value.exact)
            is_approximate = False
        expression = sp.simplify(expression)
        from src.capabilities.math.utils.units import parse_unit
        scale = parse_unit(value.unit).scale if value.unit else sp.S.One
        selected_fact = encode_condition(sp.Eq(resolve(name), expression * scale, evaluate=False), "imported")
        if not selected_fact.reusable:
            raise MathInputError("Selected value exceeds safe symbolic exchange limits.")
        conditions.append(selected_fact)
        if expression.is_number:
            if expression.is_finite is not True:
                raise MathInputError("Cannot reuse a non-finite scalar.")
            bindings[name] = {"type": "constant", "name": name, "value": str(expression), "approximate": is_approximate,
                              **({"unit": value.unit} if value.unit else {})}
        elif isinstance(expression, sp.Symbol):
            bindings[name] = {"type": "variable", "name": name, "value": str(expression)}
            if value.unit:
                units.setdefault(name, value.unit)
        else:
            text = str(expression).replace("Abs(", "abs(")
            # Verify the output expression is in the ordinary restricted language.
            MathParser(resolve).parse(text)
            bindings[name] = {"type": "equation", "name": name, "value": {"equation": f"{name} = {text}", "data": []}}
            if value.unit:
                units.setdefault(name, value.unit)
        for symbol in expression.free_symbols:
            resolve(str(symbol))
    for condition in conditions:
        decode_predicate(condition.predicate, resolve)
    for name in symbols:
        bindings.setdefault(name, {"type": "variable", "name": name, "value": name})
        if name not in values and name in previous.symbol_units:
            units.setdefault(name, previous.symbol_units[name])
    for binding in spec.bindings:
        bindings[binding.name] = binding.model_dump()
    if approximate and options.method == "certified":
        raise MathInputError("Approximate prior inputs cannot obtain an exact original-problem certificate.")
    options = options.model_copy(update={"units": units})
    try:
        return SolveRequest(equation=options, data=list(bindings.values()), preconditions=conditions, provenance={
            "scope": "selected prior solution family", "solution_index": spec.solution_index,
            "prior_completeness": previous.completeness, "approximate_inputs": approximate,
        })
    except ValidationError as error:
        raise MathInputError("Selected result cannot fit the supported continuation input limits.") from error
