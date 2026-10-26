"""The admin's default decision strategy for the Triage Assistant (routes: server.py /agents/triage-strategy).

The value lives in the overlay file (core/tuning_overrides.py) and applies to every caller of the Laya service
that names no strategy of its own (llm/triage_flow.py). Names are checked against the service's own list."""

from __future__ import annotations

from typing import Any

from src.core import tuning_overrides
from src.llm import laya_model
from src.llm.laya_model import LayaServiceError


class StrategyError(Exception):
    """A change that cannot be made; `message` is safe to show and `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def describe(service: Any = None) -> dict[str, Any]:
    """`default` (None when unset) and the service's `strategies` (empty while the service cannot be reached)."""
    service = service or laya_model.agent()
    try:
        names = service.strategies()["strategies"]
    except LayaServiceError:
        names = []
    return {"default": tuning_overrides.triage_strategy(), "strategies": names}


def update(value: str | None, service: Any = None) -> dict[str, Any]:
    """Sets the default, or clears it with None, and returns `describe()`."""
    service = service or laya_model.agent()
    if value is not None:
        try:
            names = service.strategies()["strategies"]
        except LayaServiceError as error:
            raise StrategyError(f"The Laya service could not list its strategies: {error}", 502) from error
        if value not in names:
            raise StrategyError(f"unknown strategy {value!r}; choose one of: {', '.join(names)}", 400)
    tuning_overrides.set_triage_strategy(value)
    return describe(service)
