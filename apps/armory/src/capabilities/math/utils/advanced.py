"""Bounded exact matrix and calculus operations executed only in workers."""

from __future__ import annotations

from time import perf_counter

import sympy as sp
from sympy.calculus.util import continuous_domain

from src.capabilities.math.contract import (
    MAX_OUTPUT_BYTES, CalculusRequest, EngineInfo, MathValue, MatrixRequest,
    NormalizationInfo, SolveResult, Verification,
)
from src.capabilities.math.utils.conditions import encode_condition, encode_expression
from src.capabilities.math.utils.parser import MathInputError, MathParser


class AdvancedCalculator:
    """Share safe parsing, output conversion, and domain evidence across operations."""

    def __init__(self, request):
        self.request = request
        self.options = request.data
        self.original = []
        self.normalized = []
        self.notes = []

    def parse(self, source, resolve):
        text = str(source)
        if self.options.syntax == "latex":
            from src.capabilities.math.utils.latex import normalize_latex
            converted, notes = normalize_latex(text)
            self.original.append(text)
            self.normalized.append(converted)
            self.notes.extend(notes)
            text = converted
        parser = MathParser(resolve)
        return parser.parse(text), parser

    def constant(self, source):
        def reject(name):
            raise MathInputError(f"Constant entry contains variable {name}.")
        value, _ = self.parse(source, reject)
        value = sp.simplify(value)
        if value.is_number is not True or value.is_finite is not True:
            raise MathInputError("Entries must be finite numeric constant expressions.")
        return value

    def value(self, expression):
        value = sp.simplify(expression)
        return MathValue(exact=str(value), approximate=str(sp.N(value, self.options.precision)) if not value.free_symbols else None,
                         expression=encode_expression(value))

    def matrix(self):
        operation = self.request.operation
        matrices = []
        for rows in self.options.matrices:
            if len({len(row) for row in rows}) != 1:
                raise MathInputError("Matrix rows must have equal lengths.")
            matrices.append(sp.Matrix([[self.constant(cell) for cell in row] for row in rows]))
        required = 2 if operation in {"add", "subtract", "multiply", "solve"} else 1
        if len(matrices) != required:
            raise MathInputError(f"Operation {operation} requires {required} matrices.")
        left = matrices[0]
        right = matrices[1] if required == 2 else None
        if operation in {"determinant", "inverse"} and left.rows != left.cols:
            raise MathInputError("This operation requires a square matrix.")
        if operation in {"add", "subtract"} and left.shape != right.shape:
            raise MathInputError("Addition/subtraction requires matching matrix shapes.")
        if operation in {"multiply", "solve"} and (left.cols != right.rows if operation == "multiply" else left.rows != right.rows):
            raise MathInputError("Matrix shapes do not match this operation.")
        if operation in {"inverse", "rank", "rref", "solve"} and any(cell.is_algebraic is not True for matrix in matrices for cell in matrix):
            return SolveResult(status="unresolved", message="Structural matrix operations require exact algebraic entries with decidable zero tests.")
        result = SolveResult(status="unique", completeness="complete", verification=Verification(status="exact"), message=f"Exact matrix {operation} computed.")
        if operation == "determinant":
            result.value = self.value(left.det())
            return result
        if operation in {"rank", "rref"}:
            reduced, pivots = left.rref()
            result.rank = len(pivots)
            result.pivots = list(pivots)
            if operation == "rank":
                result.value = self.value(sp.Integer(len(pivots)))
                return result
            output = reduced
        elif operation == "inverse":
            if left.det().is_zero is True:
                raise MathInputError("Singular matrix has no inverse.")
            output = left.inv()
            if any(sp.simplify(cell) != 0 for cell in left * output - sp.eye(left.rows)):
                return SolveResult(status="unresolved", message="Inverse identity could not be verified.")
        elif operation == "solve":
            try:
                output, parameters = left.gauss_jordan_solve(right)
            except ValueError:
                return SolveResult(status="inconsistent", completeness="complete", verification=Verification(status="exact"), message="Matrix system has no solution.")
            if any(sp.simplify(cell) != 0 for cell in left * output - right):
                return SolveResult(status="unresolved", message="Matrix solution residual could not be verified.")
            result.free_parameters = sorted({str(value) for value in parameters})
            if result.free_parameters:
                result.status = "parametric"
                result.message = "Matrix solution depends on listed free parameters."
        elif operation == "add":
            output = left + right
        elif operation == "subtract":
            output = left - right
        elif operation == "multiply":
            output = left * right
        else:
            output = left.T
        if output.rows > 8 or output.cols > 8:
            raise MathInputError("Matrix output exceeds 8 by 8.", "limited")
        result.matrix = [[self.value(output[i, j]) for j in range(output.cols)] for i in range(output.rows)]
        return result

    def calculus(self):
        symbols = {}
        def resolve(name):
            if name not in symbols:
                symbols[name] = sp.Symbol(name, real=True) if self.options.domain == "real" else sp.Symbol(name)
            return symbols[name]
        variable = resolve(self.options.variable)
        original, parser = self.parse(self.request.expression, resolve)
        expression = sp.simplify(original)
        domain_known = True
        conditions = [encode_condition(sp.Ne(value, 0, evaluate=False), "domain") for value in parser.denominators]
        if self.options.domain == "real":
            conditions.extend(encode_condition(sp.Contains(symbol, sp.S.Reals, evaluate=False), "domain") for symbol in symbols.values())
        domain = None
        try:
            domain = continuous_domain(original, variable, sp.S.Reals) if self.options.domain == "real" else None
            if domain is not None and domain != sp.S.Reals:
                conditions.append(encode_condition(domain.as_relational(variable), "domain"))
        except (NotImplementedError, ValueError, TypeError):
            domain_known = False
            conditions.append(encode_condition(sp.Contains(original, sp.S.Reals, evaluate=False), "domain"))
        if domain is sp.S.EmptySet or (self.options.domain == "real" and expression.is_real is False):
            raise MathInputError("Expression has no real domain under the supplied assumptions.")
        if self.options.domain == "complex":
            if original.has(sp.Abs, sp.asin, sp.acos, sp.atan):
                return SolveResult(status="unresolved", message="Complex calculus for absolute values and inverse trigonometric branches is unsupported.")
            self._complex_branches(original, variable, conditions)
        bounds = self.options.bounds
        if bounds is not None:
            lower, upper = (self.constant(bound) for bound in bounds)
            if lower.is_real is not True or upper.is_real is not True:
                raise MathInputError("Integration bounds must be finite real constants.")
            if expression.free_symbols - {variable}:
                return SolveResult(status="unresolved", structured_conditions=conditions, message="Definite integration needs all other parameters resolved.")
            interval = sp.Interval(sp.Min(lower, upper), sp.Max(lower, upper))
            safe = domain is not None and interval.is_subset(domain) is True
            for denominator in parser.denominators:
                zeros = sp.solveset(denominator, variable, domain=interval)
                safe = safe and zeros is sp.S.EmptySet
            if not safe:
                return SolveResult(status="unresolved", structured_conditions=conditions,
                                   conditions=[record.text for record in conditions],
                                   message="Continuity on the closed interval was not established; improper integrals and principal values are unsupported.")
            output = sp.integrate(expression, (variable, lower, upper))
        elif self.options.operation == "differentiate":
            output = sp.diff(expression, variable, self.options.order)
        else:
            output = sp.integrate(expression, variable)
        if output.has(sp.Integral, sp.Derivative, sp.nan, sp.zoo, sp.oo, -sp.oo):
            return SolveResult(status="unresolved", structured_conditions=conditions, message="Operation did not produce a finite evaluated expression.")
        conditional = not domain_known
        if bounds is None:
            if self.options.operation == "integrate" and sp.simplify(sp.diff(output, variable) - expression) != 0:
                return SolveResult(status="unresolved", value=self.value(output), structured_conditions=conditions,
                                   message="Candidate antiderivative could not be verified by differentiation.")
            if self.options.domain == "real":
                try:
                    output_domain = continuous_domain(output, variable, sp.S.Reals)
                    if output_domain != sp.S.Reals:
                        conditions.append(encode_condition(output_domain.as_relational(variable), "domain"))
                        conditional = True
                except (NotImplementedError, TypeError, ValueError):
                    conditional = True
                    conditions.append(encode_condition(sp.Contains(output, sp.S.Reals, evaluate=False), "domain"))
            else:
                conditional = True
                if output.has(sp.Abs, sp.asin, sp.acos, sp.atan):
                    return SolveResult(status="unresolved", message="Antiderivative introduces unsupported complex branches.")
                self._complex_branches(output, variable, conditions)
            # Abs has corners; excluded zeros are conservative sufficient conditions.
            for absolute in expression.atoms(sp.Abs):
                conditions.append(encode_condition(sp.Ne(absolute.args[0], 0, evaluate=False), "domain"))
                conditional = True
        result = SolveResult(status="unique", completeness="partial" if conditional else "complete", value=self.value(output),
                             structured_conditions=conditions, conditions=[record.text for record in conditions],
                             verification=Verification(status="conditional" if conditional else "exact", equations_checked=1),
                             message="Calculated on the listed domain; retain all domain and branch conditions.")
        if bounds is None and self.options.operation == "integrate":
            suffix = 0
            while (name := "C" if suffix == 0 else f"C{suffix}") in symbols:
                suffix += 1
            result.integration_constant = name
            result.message += f" Add arbitrary constant {name} on each connected domain component."
        return result

    @staticmethod
    def _complex_branches(expression, variable, conditions):
        """Sufficient open domains for principal logarithms and powers."""
        arguments = [log.args[0] for log in expression.atoms(sp.log)]
        arguments.extend(power.base for power in expression.atoms(sp.Pow) if power.exp.is_integer is not True)
        for argument in arguments:
            if not argument.has(variable):
                continue  # Fixed coefficients need finite values, not analyticity in their parameters.
            cut = sp.Or(sp.Ne(sp.im(argument), 0, evaluate=False), sp.Gt(sp.re(argument), 0, evaluate=False), evaluate=False)
            conditions.append(encode_condition(cut, "domain"))

    def run(self):
        result = self.matrix() if isinstance(self.request, MatrixRequest) else self.calculus()
        if self.original:
            result.normalization = NormalizationInfo(original=self.original, normalized=self.normalized, notes=list(dict.fromkeys(self.notes)))
        return result


def calculate(request: MatrixRequest | CalculusRequest) -> SolveResult:
    """Worker-only entry; shared process pool supplies wall time and OS budgets."""
    started = perf_counter()
    try:
        result = AdvancedCalculator(request).run()
    except MathInputError as error:
        result = SolveResult(status=error.status, message=str(error))
    except (NotImplementedError, TypeError):
        result = SolveResult(status="unresolved", message="Operation is unsupported for these expressions.")
    except (ValueError, ZeroDivisionError, sp.matrices.exceptions.MatrixError):
        result = SolveResult(status="invalid", message="Invalid or undefined matrix/calculus input.")
    except (RecursionError, MemoryError, OverflowError):
        result = SolveResult(status="limited", message="Operation exceeded symbolic resource limits.")
    result.engine = EngineInfo(version=sp.__version__)
    result.timings["worker_ms"] = (perf_counter() - started) * 1000
    if len(result.model_dump_json().encode("utf-8")) > MAX_OUTPUT_BYTES:
        return SolveResult(status="limited", message="Operation output exceeds 256 KiB.")
    return result
