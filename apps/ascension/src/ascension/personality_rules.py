"""Personality rules: a condition on the match, and an effect on the choice.

A rule is data from the catalog. `holds` decides whether its condition is met;
the policy applies the effects of every rule that holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.models import CATEGORIES

NUMBER_CONDITIONS = (
    "lead_over", "lead_under", "own_hp_under", "rage_over", "confidence_over", "nerves_over",
    "hit_taken_over", "streak_over", "round_under", "round_over",
)
EFFECTS = ("multiply", "chaos", "counter", "copy_enemy", "break_streak", "stay", "repeat", "pick_by_percentage")


@dataclass(frozen=True)
class Rule:
    when: Mapping[str, Any]
    effects: Mapping[str, Any]


@dataclass(frozen=True)
class ActiveRule:
    """A rule of one personality instance this round, with its strength (tier / 3, less if it is not leading)."""

    name: str
    rule: Rule
    strength: float


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_effects(effects: Mapping[str, Any], at: str) -> None:
    for key, value in effects.items():
        if key == "multiply":
            ok = isinstance(value, Mapping) and value and all(c in CATEGORIES and _number(f) and f > 0 for c, f in value.items())
        elif key == "chaos":
            ok = _number(value) and 0 < value <= 1
        elif key in ("counter", "copy_enemy", "break_streak"):
            ok = value is True
        elif key == "stay":
            ok = _number(value) and value > 0
        elif key == "repeat":
            ok = _number(value) and 0 < value <= 1
        else:  # pick_by_percentage
            ok = value in ("high", "low")
        if not ok:
            raise ValueError(f"{at}: bad value for {key}")


def parse_rules(raw: Any, where: str) -> tuple[Rule, ...]:
    """Validate a personality's rules. Raises ValueError with the place and the problem."""
    if not isinstance(raw, list):
        raise ValueError(f"{where}: rules must be a list")
    rules = []
    for index, item in enumerate(raw):
        at = f"{where} rule {index}"
        if not isinstance(item, Mapping):
            raise ValueError(f"{at}: must be an object")
        unknown = set(item) - {"when"} - set(EFFECTS)
        if unknown:
            raise ValueError(f"{at}: unknown key {sorted(unknown)[0]!r}")
        when = item.get("when", {})
        if not isinstance(when, Mapping):
            raise ValueError(f"{at}: when must be an object")
        for key, value in when.items():
            if key in NUMBER_CONDITIONS:
                if not _number(value):
                    raise ValueError(f"{at}: {key} needs a number")
            elif key == "enemy_low":
                if not isinstance(value, bool):
                    raise ValueError(f"{at}: enemy_low needs true or false")
            elif key == "enemy_last_is":
                if value not in CATEGORIES:
                    raise ValueError(f"{at}: enemy_last_is needs a category")
            else:
                raise ValueError(f"{at}: unknown condition {key!r}")
        effects = {k: v for k, v in item.items() if k != "when"}
        if not effects:
            raise ValueError(f"{at}: needs at least one effect")
        _check_effects(effects, at)
        rules.append(Rule(dict(when), effects))
    return tuple(rules)


def holds(when: Mapping[str, Any], match: MatchState, meters: MoodMeters) -> bool:
    """True when every condition is met. An empty condition always holds."""
    checks = {
        "lead_over": lambda v: match.lead > v, "lead_under": lambda v: match.lead < v,
        "own_hp_under": lambda v: match.own_hp < v, "enemy_low": lambda v: match.enemy_low is v,
        "rage_over": lambda v: meters.rage > v, "confidence_over": lambda v: meters.confidence > v,
        "nerves_over": lambda v: meters.nerves > v, "hit_taken_over": lambda v: match.hit_taken > v,
        "streak_over": lambda v: match.own_streak > v, "round_under": lambda v: match.round < v,
        "round_over": lambda v: match.round > v, "enemy_last_is": lambda v: match.enemy_last == v,
    }
    return all(checks[key](value) for key, value in when.items())
