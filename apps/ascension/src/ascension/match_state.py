"""What an Ascended can read about the match, and the hidden mood it builds.
Bleed ticks count as damage, heals and regen as recovery.

Both are derived from public battle state and its history, so nothing is saved and a
restarted battle decides identically. Pure: no database, clock or model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.ascension.models import BattleSetup, BattleState, other


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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class MatchReader:
    """Reads one side's view of the match, and replays the history to get its mood meters."""

    def __init__(self, constants: MoodConstants) -> None:
        self._c = constants

    def read(self, setup: BattleSetup, state: BattleState, side: str) -> tuple[MatchState, MoodMeters]:
        foe = other(side)
        own, enemy = setup.of(side), setup.of(foe)
        c = self._c
        own_hp, enemy_hp = float(own.max_hp), float(enemy.max_hp)
        rage, confidence, nerves, hit = 0.0, 0.5, 0.0, 0.0
        leads = [0.0]
        for revealed in state.history:
            attacks = [e for e in revealed.events if e.get("type") == "attack"]
            bleeds = [e for e in revealed.events if e.get("type") == "tick" and e.get("kind") == "bleed"]
            heals = [e for e in revealed.events if e.get("type") == "heal" or (e.get("type") == "tick" and e.get("kind") == "regen")]
            taken = sum(e["damage"] for e in attacks if e["side"] == foe) + sum(e["amount"] for e in bleeds if e["side"] == side)
            dealt = sum(e["damage"] for e in attacks if e["side"] == side) + sum(e["amount"] for e in bleeds if e["side"] == foe)
            own_hp = min(float(own.max_hp), max(0.0, own_hp - taken + sum(e["amount"] for e in heals if e["side"] == side)))
            enemy_hp = min(float(enemy.max_hp), max(0.0, enemy_hp - dealt + sum(e["amount"] for e in heals if e["side"] == foe)))
            own_fraction, enemy_fraction = own_hp / own.max_hp, enemy_hp / enemy.max_hp
            lead = own_fraction - enemy_fraction
            hit = taken / own.max_hp
            rage = _clamp(rage * c.rage_decay + hit * c.rage_gain)
            if lead > leads[-1] + 1e-9:
                confidence = _clamp(confidence + c.confidence_step)
            elif lead < leads[-1] - 1e-9:
                confidence = _clamp(confidence - c.confidence_step)
            target = _clamp(max(0.0, -lead) + max(0.0, 0.5 - own_fraction))
            nerves = _clamp(nerves + c.nerves_follow * (target - nerves))
            leads.append(lead)
        own_now, enemy_now = state.of(side).hp / own.max_hp, state.of(foe).hp / enemy.max_hp
        mine = [r.actions[side][1] for r in state.history]
        theirs = [r.actions[foe][1] for r in state.history]
        streak = 0
        for category in reversed(mine):
            if category != mine[-1]:
                break
            streak += 1
        match = MatchState(
            own_hp=own_now, enemy_hp=enemy_now, lead=own_now - enemy_now,
            trend=leads[-1] - leads[max(0, len(leads) - 3)], round=state.round, own_streak=streak,
            own_last=mine[-1] if mine else None, enemy_last=theirs[-1] if theirs else None,
            hit_taken=hit, enemy_low=enemy_now < c.enemy_low,
        )
        return match, MoodMeters(rage, confidence, nerves)
