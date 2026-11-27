"""The sum of one table page's row values, added exactly by the math engine so no second tool call is needed."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection

from src.capabilities.math.contract import BatchResult, MathValue, SolveRequest, SolveResult, TableTotal


class PageTotal:
    """Pick the one value of each row and add them. `solve` is the desk's isolated, non-blocking solver."""

    def __init__(self, solve: Callable[..., Awaitable[SolveResult]]) -> None:
        self._solve = solve

    async def add(self, equation, page: BatchResult, bound: Collection[str]) -> TableTotal:
        """The sum of `page`, or why there is none. `bound` names the variables the page itself supplied."""
        values = [self._row_value(row.result, bound) for row in page.records]
        count = len(values)
        unusable = sum(value is None for value in values)
        if unusable:
            return self._refused(count, f"{unusable} of {count} rows have no single exact value.")
        if len({value.unit for value in values}) > 1:
            return self._refused(count, "the rows have different units.")
        spec = SolveRequest(equation=equation, data=[]).equation  # already accepted by the batch
        added = await self._solve({
            "expression": " + ".join(f"({value.exact})" for value in values),
            "precision": getattr(spec, "precision", 15),
        }, [])
        if added.status != "unique" or added.value is None:
            return self._refused(count, f"the row values could not be added. {added.message[:256]}")
        total_rows = page.source.total_rows
        message = f"Exact sum of {count} of {total_rows} rows."
        if count < total_rows:
            message += " It covers this page only; add every page's total for the whole table."
        value = MathValue(exact=added.value.exact, approximate=added.value.approximate, unit=values[0].unit)
        return TableTotal(rows=count, value=value, message=message)

    @staticmethod
    def _refused(count: int, reason: str) -> TableTotal:
        return TableTotal(rows=count, message=f"No total: {reason}")

    @staticmethod
    def _row_value(result: SolveResult, bound: Collection[str]) -> MathValue | None:
        """A row's value only when it is complete, exact, unconditional and the only one."""
        if result.status != "unique" or result.completeness != "complete" or len(result.solutions) != 1:
            return None
        solution = result.solutions[0]
        if result.conditions or solution.conditions or result.free_parameters:
            return None
        value = solution.value  # a bare expression
        if value is None:  # an equality: the one variable the page did not supply
            targets = [name for name in solution.values if name not in bound]
            value = solution.values[targets[0]] if len(targets) == 1 else None
        return value if value is not None and value.exact is not None else None
