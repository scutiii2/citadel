"""Ascended passives as small polymorphic objects.

Each passive overrides only the hooks it changes; the base class holds the
neutral defaults, so the engine asks every passive the same questions.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from src.ascension.models import PassiveSpec


class Passive:
    """Neutral behavior: an Ascended without a passive effect."""

    def start_buffs(self, power: int) -> list[tuple[str, int]]:
        """(stat, amount) bonuses applied once when the battle starts."""
        return []

    def defense_limits(self) -> tuple[int, int]:
        """(protected attacks, rounds) of a fresh DEFENSE effect."""
        return 1, 1

    def defense_rating_bonus(self, power: int) -> float:
        return 0.0

    def support_extra_rounds(self) -> int:
        return 0

    def attack_bonus(self, power: int, hp: int, max_hp: int, target_chose_defense: bool) -> float:
        """Raw damage added to an attack, before mitigation."""
        return 0.0

    def marked_bonus(self, power: int, marks: frozenset[str]) -> float:
        """Raw damage added to an attack against a target carrying one of these marks."""
        return 0.0

    def heal_multiplier(self, hp: int, max_hp: int) -> float:
        return 1.0

    def cooldown(self, base: int) -> int:
        return base


class DefenseExtension(Passive):
    def __init__(self, protected_attacks: int, rounds: int) -> None:
        self._attacks, self._rounds = protected_attacks, rounds

    def defense_limits(self) -> tuple[int, int]:
        return self._attacks, self._rounds


class LowHpAttackBonus(Passive):
    def __init__(self, hp_below: float, power_fraction: float) -> None:
        self._below, self._fraction = hp_below, power_fraction

    def attack_bonus(self, power: int, hp: int, max_hp: int, target_chose_defense: bool) -> float:
        return power * self._fraction if hp < max_hp * self._below else 0.0


class BattleStartSpeed(Passive):
    def __init__(self, power_fraction: float) -> None:
        self._fraction = power_fraction

    def start_buffs(self, power: int) -> list[tuple[str, int]]:
        return [("speed", math.floor(power * self._fraction))]


class DefenseRatingBonus(Passive):
    def __init__(self, power_fraction: float) -> None:
        self._fraction = power_fraction

    def defense_rating_bonus(self, power: int) -> float:
        return power * self._fraction


class AttackBonusVersusDefense(Passive):
    def __init__(self, power_fraction: float) -> None:
        self._fraction = power_fraction

    def attack_bonus(self, power: int, hp: int, max_hp: int, target_chose_defense: bool) -> float:
        return power * self._fraction if target_chose_defense else 0.0


class SupportDurationBonus(Passive):
    def __init__(self, rounds: int) -> None:
        self._rounds = rounds

    def support_extra_rounds(self) -> int:
        return self._rounds


class CooldownReduction(Passive):
    def __init__(self, rounds: int, minimum: int) -> None:
        self._rounds, self._minimum = rounds, minimum

    def cooldown(self, base: int) -> int:
        return max(base - self._rounds, self._minimum)


class AttackBonusVersusMarked(Passive):
    def __init__(self, mark: str, power_fraction: float) -> None:
        self._mark, self._fraction = mark, power_fraction

    def marked_bonus(self, power: int, marks: frozenset[str]) -> float:
        return power * self._fraction if self._mark in marks else 0.0


class HealBonus(Passive):
    """Heals and regeneration grow by `fraction`; with `hp_below` only while own HP is below that share of max HP."""

    def __init__(self, fraction: float, hp_below: float | None = None) -> None:
        self._fraction, self._below = fraction, hp_below

    def heal_multiplier(self, hp: int, max_hp: int) -> float:
        return 1 + self._fraction if self._below is None or hp < max_hp * self._below else 1.0


class CombinedPassive(Passive):
    """Several equipped passives acting as one: bonuses add, multipliers multiply, limits take the best."""

    def __init__(self, passives: Sequence[Passive]) -> None:
        self._passives = tuple(passives)

    def start_buffs(self, power: int) -> list[tuple[str, int]]:
        return [buff for p in self._passives for buff in p.start_buffs(power)]

    def defense_limits(self) -> tuple[int, int]:
        limits = [p.defense_limits() for p in self._passives]
        return max(a for a, _ in limits), max(r for _, r in limits)

    def defense_rating_bonus(self, power: int) -> float:
        return sum(p.defense_rating_bonus(power) for p in self._passives)

    def support_extra_rounds(self) -> int:
        return sum(p.support_extra_rounds() for p in self._passives)

    def attack_bonus(self, power: int, hp: int, max_hp: int, target_chose_defense: bool) -> float:
        return sum(p.attack_bonus(power, hp, max_hp, target_chose_defense) for p in self._passives)

    def marked_bonus(self, power: int, marks: frozenset[str]) -> float:
        return sum(p.marked_bonus(power, marks) for p in self._passives)

    def heal_multiplier(self, hp: int, max_hp: int) -> float:
        result = 1.0
        for p in self._passives:
            result *= p.heal_multiplier(hp, max_hp)
        return result

    def cooldown(self, base: int) -> int:
        for p in self._passives:
            base = p.cooldown(base)
        return base


class PassiveFactory:
    """Builds a Passive from the saved spec. Register new kinds with `register`."""

    def __init__(self) -> None:
        self._kinds: dict[str, Callable[..., Passive]] = {
            "none": Passive,
            "attack_bonus_vs_marked": AttackBonusVersusMarked,
            "heal_bonus": HealBonus,
            "defense_extension": DefenseExtension,
            "low_hp_attack_bonus": LowHpAttackBonus,
            "battle_start_speed": BattleStartSpeed,
            "defense_rating_bonus": DefenseRatingBonus,
            "attack_bonus_vs_defense": AttackBonusVersusDefense,
            "support_duration_bonus": SupportDurationBonus,
            "cooldown_reduction": CooldownReduction,
        }

    def register(self, kind: str, builder: Callable[..., Passive]) -> None:
        self._kinds[kind] = builder

    def create(self, spec: PassiveSpec) -> Passive:
        try:
            return self._kinds[spec.kind](**spec.params)
        except KeyError:
            raise ValueError(f"unknown passive kind {spec.kind!r}") from None

    def create_all(self, specs: Sequence[PassiveSpec]) -> Passive:
        """One passive for a whole equipped set: neutral for none, that passive for one, a combination for several."""
        built = [self.create(s) for s in specs]
        if not built:
            return Passive()
        return built[0] if len(built) == 1 else CombinedPassive(built)
