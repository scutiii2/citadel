"""The action policy: how an Ascended picks its action when it plays on its own.

Pure and synchronous, in two stages. First a category (ATTACK, DEFENSE, SUPPORT,
FEAR, INTERCEPT) from the situation read, the round's personality weights and
the personality rules that fire for the current match; the number of actions in a
category does not change it. Then an action inside the chosen category from a
softmax over a small utility. The engine's seeded draw picks one action, so a
personality biases behaviour without making it predictable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.ascension.catalog import Catalog, PolicySpec
from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.models import CATEGORIES, Action, PersonalityInstance
from src.ascension.personality_rules import ActiveRule, holds

# What the Cunning personality answers with: DEFENSE after an ATTACK, ATTACK after SUPPORT or DEFENSE.
COUNTERS: dict[str, tuple[str, ...]] = {"ATTACK": ("DEFENSE",), "SUPPORT": ("ATTACK",), "DEFENSE": ("ATTACK",)}


@dataclass(frozen=True)
class Situation:
    """Each value is 0 to 1."""

    danger: float
    aggression: float  # how aggressively the enemy has acted
    advantage: float  # does this Ascended have the upper hand


@dataclass(frozen=True)
class PolicyContext:
    situation: Situation
    enemy_hp_fraction: float
    enemy_flee_share: float  # share of revealed rounds the enemy chose FLEE
    collector: bool  # True for the player's Ascended: CATCH can collect
    recent_keys: tuple[str, ...]  # this Ascended's own previous action keys, oldest first
    weights: Mapping[str, float]  # round personality weights per category
    match: MatchState | None = None  # None: no personality rule can fire
    meters: MoodMeters | None = None
    rules: tuple[ActiveRule, ...] = ()


@dataclass(frozen=True)
class PolicyDecision:
    action: Action
    probabilities: tuple[float, ...]  # same order as the actions passed in
    details: dict[str, Any] | None = None  # category probabilities and fired rules, for the private audit


@dataclass(frozen=True)
class Explanation:
    probabilities: list[float]
    categories: dict[str, float]  # stage 1, only categories that have a legal action
    fired: list[str]  # names of the rules that fired

    def audit(self) -> dict[str, Any]:
        return {"categories": {c: round(p, 4) for c, p in self.categories.items()}, "fired": list(self.fired)}


class Mood:
    """Which equipped personality leads this round, and the resulting weights and rules."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._off = catalog.policy.off_mood_factor

    @staticmethod
    def pick(count: int, u: float) -> int:
        """Uniform index of the leading instance for one draw u in [0, 1)."""
        return min(int(u * count), count - 1)

    def weights(self, instances: Sequence[PersonalityInstance], lead: int) -> dict[str, float]:
        """The lead instance counts fully, the others at the off-mood factor;
        weights add per category. A personality gives its tier as the weight for
        each of its categories."""
        totals = {category: 0.0 for category in CATEGORIES}
        for index, instance in enumerate(instances):
            factor = 1.0 if index == lead else self._off
            for category in self._catalog.personalities[instance.type_id].categories:
                totals[category] += instance.tier * factor
        return totals

    def active_rules(self, instances: Sequence[PersonalityInstance], lead: int | None) -> tuple[ActiveRule, ...]:
        """Every rule of every instance, with its strength: tier / 3, times the off-mood factor when not leading."""
        active = []
        for index, instance in enumerate(instances):
            factor = 1.0 if index == lead else self._off
            for number, rule in enumerate(self._catalog.personalities[instance.type_id].rules):
                active.append(ActiveRule(f"{instance.type_id}#{number}", rule, instance.tier / 3 * factor))
        return tuple(active)


class ActionPolicy:
    def __init__(self, spec: PolicySpec) -> None:
        self._spec = spec

    def situation_value(self, category: str, ctx: PolicyContext) -> float:
        s, c = ctx.situation, self._spec.coefficients[category]
        if category == "ATTACK":
            value = c["base"] + c["advantage"] * s.advantage + c["safety"] * (1 - s.danger)
        elif category == "DEFENSE":
            value = c["base"] + c["danger"] * s.danger + c["aggression"] * s.aggression
        elif category == "SUPPORT":
            value = c["base"] + c["safety"] * (1 - s.danger) + c["passivity"] * (1 - s.aggression)
        elif category == "FEAR":
            value = c["base"] + c["escape_pressure"] * s.danger * (1 - s.advantage)
        elif ctx.collector:
            value = c["collector_base"] + c["collector_weakness"] * (1 - ctx.enemy_hp_fraction) * (1 - s.danger)
        else:
            value = c["wild_base"] + c["wild_flee_share"] * ctx.enemy_flee_share
        return max(value, self._spec.floor)

    # -- stage 1: the category -----------------------------------------------------

    @staticmethod
    def _fired(ctx: PolicyContext) -> list[ActiveRule]:
        if ctx.match is None or ctx.meters is None:
            return []
        return [a for a in ctx.rules if holds(a.rule.when, ctx.match, ctx.meters)]

    def _category_probabilities(self, present: list[str], ctx: PolicyContext, fired: list[ActiveRule]) -> dict[str, float]:
        spec, match = self._spec, ctx.match
        base = {c: self.situation_value(c, ctx) * (1 + spec.gain * ctx.weights.get(c, 0.0)) for c in present}
        for active in fired:
            effects, k = active.rule.effects, active.strength
            for category, factor in effects.get("multiply", {}).items():
                if category in base:
                    base[category] *= 1 + (factor - 1) * k
            if "stay" in effects and match.own_last in base:
                base[match.own_last] *= 1 + (effects["stay"] - 1) * k
            boosted: tuple[str, ...] = ()
            if effects.get("counter") and match.enemy_last:
                boosted = COUNTERS.get(match.enemy_last, ())
            elif effects.get("copy_enemy") and match.enemy_last:
                boosted = (match.enemy_last,)
            for category in boosted:
                if category in base:
                    base[category] *= 1 + (spec.counter_boost - 1) * k
        total = sum(base.values())
        shares = {c: v / total for c, v in base.items()}
        return self._chaos(self._break_streak(shares, ctx, fired), fired)

    def _break_streak(self, shares: dict[str, float], ctx: PolicyContext, fired: list[ActiveRule]) -> dict[str, float]:
        """After a hidden streak limit the Ascended jumps to its least likely other category."""
        strength = max((a.strength for a in fired if a.rule.effects.get("break_streak")), default=0.0)
        match, mood = ctx.match, self._spec.mood
        if not strength or match.own_last not in shares or len(shares) < 2:
            return shares
        if match.own_streak < mood.streak_base + (match.round * 7) % mood.streak_span:
            return shares
        target = min((c for c in shares if c != match.own_last), key=lambda c: shares[c])
        blend = min(1.0, strength)
        return {c: (1 - blend) * v + (blend if c == target else 0.0) for c, v in shares.items()}

    @staticmethod
    def _chaos(shares: dict[str, float], fired: list[ActiveRule]) -> dict[str, float]:
        """Blend toward the inverse: the unlikely categories gain, the likely ones lose."""
        amount = min(1.0, sum(a.rule.effects.get("chaos", 0.0) * a.strength for a in fired))
        if amount <= 0 or len(shares) < 2:
            return shares
        spread = sum(1 - v for v in shares.values())
        return {c: (1 - amount) * v + amount * (1 - v) / spread for c, v in shares.items()}

    # -- stage 2: the action inside a category --------------------------------------

    def _within(self, members: list[Action], ctx: PolicyContext, fired: list[ActiveRule]) -> list[float]:
        if len(members) == 1:
            return [1.0]
        spec = self._spec
        mean = sum(a.percentage for a in members) / len(members)
        weight = spec.potency_weight
        for active in fired:
            pick = active.rule.effects.get("pick_by_percentage")
            if pick:
                weight = spec.pick_weight if pick == "high" else -spec.pick_weight
        overrides = [a.rule.effects["repeat"] for a in fired if "repeat" in a.rule.effects]
        repeat_factor = max(overrides) if overrides else spec.repeat_factor
        scores = []
        for action in members:
            repeats = 0
            for key in reversed(ctx.recent_keys):
                if key != action.key:
                    break
                repeats += 1
            potency = math.log(action.percentage / mean) if mean > 0 and action.percentage > 0 else 0.0
            scores.append(math.exp((weight * potency + repeats * math.log(repeat_factor)) / spec.temperature))
        total = sum(scores)
        return [s / total for s in scores]

    # -- public --------------------------------------------------------------------

    def explain(self, actions: Sequence[Action], ctx: PolicyContext) -> Explanation:
        if not actions:
            raise ValueError("no legal actions to choose from")
        members: dict[str, list[int]] = {}
        for index, action in enumerate(actions):
            members.setdefault(action.category, []).append(index)
        present = [c for c in CATEGORIES if c in members]
        fired = self._fired(ctx)
        categories = self._category_probabilities(present, ctx, fired)
        probabilities = [0.0] * len(actions)
        for category, indexes in members.items():
            shares = self._within([actions[i] for i in indexes], ctx, fired)
            for index, share in zip(indexes, shares):
                probabilities[index] = categories[category] * share
        return Explanation(probabilities, categories, [a.name for a in fired])

    def probabilities(self, actions: Sequence[Action], ctx: PolicyContext) -> list[float]:
        return self.explain(actions, ctx).probabilities

    def choose(self, actions: Sequence[Action], ctx: PolicyContext, u: float) -> PolicyDecision:
        explanation = self.explain(actions, ctx)
        cumulative = 0.0
        for action, probability in zip(actions, explanation.probabilities):
            cumulative += probability
            if u < cumulative:
                return PolicyDecision(action, tuple(explanation.probabilities), explanation.audit())
        return PolicyDecision(actions[-1], tuple(explanation.probabilities), explanation.audit())  # u rounding past the last bucket
