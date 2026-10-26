"""Shared types of the decision provider: one request shape, one answer shape, any gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DecisionError(Exception):
    """A gateway could not answer: not configured, unreachable, refused, or an unusable reply."""


@dataclass(frozen=True)
class DecisionRequest:
    text: str
    questions: dict[str, dict[str, Any]]
    min_confidence: float = 0.9
    # Only gateways that keep the text on this machine may answer.
    local_only: bool = False


@dataclass(frozen=True)
class GatewayResult:
    answers: dict[str, dict[str, Any]]
    tokens: int = 0
    model: str = ""


class DecisionGateway(Protocol):
    id: str
    local: bool

    def available(self) -> bool: ...

    def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult: ...
