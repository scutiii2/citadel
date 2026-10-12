"""What an Ascended can read about the match, and the hidden mood it builds.

Both are derived from public battle state and its history, so nothing is saved and a
restarted battle decides identically. Pure: no database, clock or model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MoodConstants:
    """How fast the mood meters move. Set under `policy.mood` in the catalog."""

    rage_decay: float = 0.5  # share of rage kept each round
    rage_gain: float = 4.0  # rage per fraction of max HP lost in a round
    confidence_step: float = 0.2  # confidence change when the HP lead grows or shrinks
    nerves_follow: float = 0.5  # share of the gap to the target that nerves closes each round
    enemy_low: float = 0.3  # enemy HP fraction below which it counts as low
    streak_base: int = 2  # a hidden streak limit of streak_base to streak_base + streak_span - 1 rounds
    streak_span: int = 3


@dataclass(frozen=True)
class MatchState:
    own_hp: float = 1.0  # HP fractions
    enemy_hp: float = 1.0
    lead: float = 0.0  # own_hp - enemy_hp, from -1 to 1
    trend: float = 0.0  # change of lead over the last two rounds
    round: int = 1
    own_streak: int = 0  # how many rounds in a row it chose its last category
    own_last: str | None = None
    enemy_last: str | None = None
    hit_taken: float = 0.0  # own HP lost last round, as a fraction of max HP
    enemy_low: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class MoodMeters:
    rage: float = 0.0
    confidence: float = 0.5
    nerves: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in self.__dict__.items()}
