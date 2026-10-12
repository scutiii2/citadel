"""Turns a battle's public state into one Ascended's action: situation read,
mood draw, match and mood, rules, probabilities, seeded draw."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from src.ascension.catalog import Catalog
from src.ascension.engine import BattleEngine
from src.ascension.match_state import MatchReader
from src.ascension.models import PLAYER, Action, BattleSetup, BattleState, PersonalityInstance
from src.ascension.policy import ActionPolicy, Mood, PolicyContext
from src.ascension.runtime import RandomSource
from src.ascension.status_fit import action_fit
from src.ascension.situation import SituationReader, SituationViewBuilder


@dataclass(frozen=True)
class Decision:
    action: Action
    audit: dict[str, Any]  # kept privately with the round; never in a public view


class ActionDecider:
    def __init__(self, catalog: Catalog, engine: BattleEngine, policy: ActionPolicy, mood: Mood,
                 reader: SituationReader, views: SituationViewBuilder) -> None:
        self._catalog, self._engine, self._policy, self._mood = catalog, engine, policy, mood
        self._reader, self._views = reader, views
        self._matches = MatchReader(catalog.policy.mood)

    async def decide(
        self, setup: BattleSetup, state: BattleState, side: str, instances: Sequence[PersonalityInstance],
        rng: RandomSource, *, can_collect: bool,
    ) -> Decision:
        """Pick `side`'s action from public state, its own personalities and its own history.
        Nothing about the opponent's pending choice is available here."""
        view = self._views.build(setup, state, side)
        situation = await self._reader.read(view)
        legal = self._engine.legal_actions(setup, state, side, can_collect=can_collect)
        lead = Mood.pick(len(instances), rng.next()) if instances else None
        weights = self._mood.weights(instances, lead) if instances else {}
        history = view.enemy_history
        flee_share = history.count("FEAR") / len(history) if history else self._catalog.policy.default_flee_share
        match, meters = self._matches.read(setup, state, side)
        rules = self._mood.active_rules(instances, lead) if instances else ()
        context = PolicyContext(
            situation=situation, enemy_hp_fraction=view.enemy_hp_fraction, enemy_flee_share=flee_share,
            collector=side == PLAYER, recent_keys=tuple(r.actions[side][0] for r in state.history), weights=weights,
            match=match, meters=meters, rules=rules, fit=action_fit(setup, state, side, legal),
        )
        decision = self._policy.choose(legal, context, rng.next())
        details = decision.details or {}
        audit = {
            "side": side, "mood": instances[lead].id if instances else None,
            "situation": {"danger": situation.danger, "aggression": situation.aggression, "advantage": situation.advantage},
            "match": match.to_dict(), "mood_meters": meters.to_dict(),
            "categories": details.get("categories", {}), "fired": details.get("fired", []),
            "probabilities": {a.key: round(p, 4) for a, p in zip(legal, decision.probabilities)},
            "chosen": decision.action.key,
        }
        return Decision(decision.action, audit)
