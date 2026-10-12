"""How well an action suits the fight right now, from the effects it carries.

A heal at full HP, a cleanse with nothing to clean, a ward that is already up and a bleed the foe
already has are poor choices. This gives each such action a multiplier below 1 (or above 1 when it
is timely); the policy applies it after its normal two stages. Actions without effects are not listed.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from src.ascension.models import HARMFUL, Action, BattleSetup, BattleState, other

FOE_STATUS = {"bleed": "bleed", "slow": "slow", "weaken": "weaken", "exposed": "exposed"}
WASTED = 0.2  # an effect that does nothing at all
REPEATED = 0.5  # an effect the foe already carries


def action_fit(setup: BattleSetup, state: BattleState, side: str, legal: Sequence[Action]) -> Mapping[str, float]:
    me, foe = state.of(side), state.of(other(side))
    max_hp = setup.of(side).max_hp
    missing = 1 - me.hp / max_hp
    own = {s.id for s in me.statuses}
    theirs = {s.id for s in foe.statuses}
    fits: dict[str, float] = {}
    for action in legal:
        if action.kind != "ability":
            continue
        ability = next((a for a in setup.of(side).abilities if a.id == action.ability_id), None)
        if ability is None or not ability.effects:
            continue
        fit = 1.0
        for effect in ability.effects:
            if effect.kind in ("heal", "regen"):
                fit *= WASTED if missing < 0.05 else 1 + missing
            elif effect.kind == "cleanse":
                fit *= 2.0 if own & set(HARMFUL) else WASTED
            elif effect.kind == "ward":
                fit *= WASTED if "ward" in own else (1.5 if missing > 0.5 else 1.0)
            elif effect.kind in FOE_STATUS and FOE_STATUS[effect.kind] in theirs:
                fit *= REPEATED
        if fit != 1.0:
            fits[action.key] = fit
    return fits
