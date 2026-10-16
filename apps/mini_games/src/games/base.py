"""The Game protocol every plugin implements, and the types it exchanges.

Moves are plain JSON objects (dict) so the API, the sessions and the Laya
picker never need to know a game's move type. States are immutable values
owned by the plugin; callers pass them back unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

Move = dict[str, Any]


class GameError(Exception):
    """Base for errors a caller can fix (bad move, bad option)."""


class IllegalMove(GameError):
    """The move is not legal in this position."""


class InvalidOptions(GameError):
    """Unknown or out-of-range game option, or unknown game id."""


@dataclass(frozen=True)
class Status:
    finished: bool
    winner: str | None = None  # a side name; None with finished=True is a draw
    reason: str = ""


@dataclass(frozen=True)
class Candidate:
    move: Move
    score: float  # higher is better for the side to move
    features: dict[str, Any] = field(default_factory=dict)


class Game(Protocol):
    id: str

    def option_schema(self) -> dict[str, Any]:
        """JSON-friendly description of the options new_state accepts."""

    def assign_sides(self, options: dict[str, Any]) -> tuple[str, str]:
        """(player side, bot side) for these options."""

    def new_state(self, options: dict[str, Any]) -> Any:
        """Start a game; raises InvalidOptions."""

    def side_to_move(self, state: Any) -> str | None:
        """The side that must move next; None when the game is over."""

    def legal_moves(self, state: Any) -> list[Move]: ...

    def apply(self, state: Any, move: Move) -> Any:
        """The state after the move; raises IllegalMove."""

    def status(self, state: Any) -> Status: ...

    def evaluate(self, state: Any, side: str) -> float:
        """Engine score of the position from `side`'s view; higher is better."""

    def candidates(self, state: Any, k: int, depth: int, time_limit: float) -> list[Candidate]:
        """Up to k best moves for the side to move, best first. Blocking CPU
        work: callers run it in a worker thread."""

    def summarize(self, state: Any, candidate: Candidate) -> str:
        """One short feature line for a candidate, for the Laya question."""

    def describe_position(self, state: Any) -> str:
        """A compact text summary of the position, for the Laya question."""

    def to_dict(self, state: Any) -> dict[str, Any]:
        """The JSON shape the API sends for this state."""
