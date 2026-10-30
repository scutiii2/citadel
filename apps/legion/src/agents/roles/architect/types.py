"""Plans carry data; the executor owns scheduling and the runner owns work."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Status = Literal["done", "failed", "skipped", "cancelled"]


@dataclass(frozen=True)
class Unit:
    id: str
    spec: str
    depends_on: tuple[str, ...] = ()
    name: str = ""
    signature: str = ""
    effect: Literal["read", "write"] = "read"
    needs_body_of: tuple[str, ...] = ()
    tier_hint: str = "standard"
    agent_id: str = ""
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class Step:
    id: str
    architect: str
    brief: str
    depends_on: tuple[str, ...] = ()
    # An architect brief may include writes; only its later pipeline can classify units.
    effect: Literal["read", "write"] = "write"
    tier_hint: str = "standard"
    reasoning_effort: str | None = None

    @property
    def agent_id(self) -> str:
        return self.architect


@dataclass(frozen=True)
class Plan:
    steps: tuple[Step, ...]


@dataclass
class NodeResult:
    status: Status
    output: Any = None
    error: str | None = None
    agent_usage: list[dict[str, Any]] = field(default_factory=list)


Node = Unit | Step
