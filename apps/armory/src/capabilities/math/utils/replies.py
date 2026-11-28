"""What the model is sent: short math results, with each full one kept here for a later continuation.

A model reads a tool result again on every later round, and most of a full result is evidence only
`tool_math_continue` needs. Both classes run on Armory's event loop and never block, so they take no lock.
"""

from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from src.capabilities.math.contract import (RESULT_ID_PREFIX, BatchResult, BatchRow, ContinuationInput,
                                            MathValue, ResultRef, SolveResult)

_VALUE = {"expression": True}
_SOLUTION = {"structured_conditions": True, "value": _VALUE, "values": {"__all__": _VALUE}}
# By position, not by name: a variable may be called `engine` or `expression`.
_LEFT_OUT = {
    "structured_conditions": True, "timings": True, "resources": True, "execution": True, "engine": True,
    "provenance": True, "value": _VALUE, "solutions": {"__all__": _SOLUTION},
    "cases": {"__all__": {"structured_conditions": True, "solutions": {"__all__": _SOLUTION}}},
    "matrix": {"__all__": {"__all__": _VALUE}},
}


class ResultStore:
    """Full results by random id, bound to one account and dropped by age, count per account and total size."""

    def __init__(self, *, ttl_seconds: float = 1800, per_owner: int = 128, max_bytes: int = 32 * 1024 * 1024,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._per_owner = per_owner
        self._max_bytes = max_bytes
        self._clock = clock
        self._entries: OrderedDict[str, tuple[str, float, str]] = OrderedDict()  # id: owner, expiry, JSON
        self._bytes = 0

    def put(self, owner: str, result: SolveResult) -> str:
        result_id = RESULT_ID_PREFIX + secrets.token_urlsafe(9)
        text = result.model_dump_json()
        self._entries[result_id] = (owner, self._clock() + self._ttl, text)
        self._bytes += len(text)
        self._evict(owner)
        return result_id

    def get(self, result_id: str, owner: str) -> SolveResult | None:
        """None for an unknown, expired or foreign id."""
        self._drop_expired()
        entry = self._entries.get(result_id)
        if entry is None or entry[0] != owner:
            return None
        return SolveResult.model_validate_json(entry[2])

    def _evict(self, owner: str) -> None:
        self._drop_expired()
        owned = [key for key, entry in self._entries.items() if entry[0] == owner]
        for key in owned[:max(0, len(owned) - self._per_owner)]:
            self._drop(key)
        while self._bytes > self._max_bytes and len(self._entries) > 1:
            self._drop(next(iter(self._entries)))

    def _drop_expired(self) -> None:
        now = self._clock()
        # One lifetime for all, so the oldest entry always expires first.
        while self._entries and next(iter(self._entries.values()))[1] <= now:
            self._drop(next(iter(self._entries)))

    def _drop(self, result_id: str) -> None:
        self._bytes -= len(self._entries.pop(result_id)[2])


class MathReplies:
    """Shorten results on the way out and give a continuation its full prior result back."""

    def __init__(self, store: ResultStore) -> None:
        self._store = store

    def reply(self, result: SolveResult | BatchResult, owner: str) -> dict[str, Any]:
        """The short form of `result`. Without an owner nothing can be kept, so the full result is returned."""
        if not owner:
            return result.model_dump(mode="json")
        if isinstance(result, SolveResult):
            return self._short(result, owner)
        data = _without_empty(result.model_dump(mode="json", exclude={"records"}, exclude_none=True))
        if result.records:
            data["records"] = [self._row(row, owner) for row in result.records]
        return data

    def _row(self, row: BatchRow, owner: str) -> dict[str, Any]:
        values = _clean_values(row.result)
        if values:
            return {
                "id": row.id,
                "values": {name: value.model_dump(mode="json", exclude=_VALUE, exclude_none=True)
                           for name, value in values.items()},
                "result_id": self._store.put(owner, row.result),
            }
        return {"index": row.index, "id": row.id, "result": self._short(row.result, owner)}

    def restore(self, data: ContinuationInput, owner: str) -> ContinuationInput | SolveResult:
        """`data` with a result_id replaced by the result it names, or the result that explains why it cannot."""
        if not isinstance(data.previous, ResultRef):
            return data
        full = self._store.get(data.previous.result_id, owner) if owner else None
        if full is None:
            return SolveResult(status="invalid", message=(
                "That result_id is not available: results are kept 30 minutes and lost when Armory restarts. "
                "Solve the original problem again."))
        return data.model_copy(update={"previous": full})

    def _short(self, result: SolveResult, owner: str) -> dict[str, Any]:
        data = _without_empty(result.model_dump(mode="json", exclude=_LEFT_OUT, exclude_none=True))
        if result.solutions or result.value is not None:
            data = {"result_id": self._store.put(owner, result), **data}
        return data


def _clean_values(result: SolveResult) -> dict[str, MathValue]:
    if (result.status != "unique" or result.completeness != "complete" or result.verification.status != "exact"
            or result.conditions or result.diagnostics or result.trace or result.cases or result.free_parameters
            or result.assumptions or result.certificate or (result.normalization and result.normalization.notes)
            or len(result.solutions) > 1):
        return {}
    if result.solutions:
        solution = result.solutions[0]
        if solution.conditions or solution.verification.status != "exact":
            return {}
        if solution.value is not None:
            return {"value": solution.value}
        return solution.values
    return {"value": result.value} if result.value is not None else {}


def _without_empty(data: dict[str, Any]) -> dict[str, Any]:
    """`data` without empty lists and objects, at any depth."""
    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cleaned for key, item in value.items() if (cleaned := clean(item)) not in ([], {})}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(data)


replies = MathReplies(ResultStore())
