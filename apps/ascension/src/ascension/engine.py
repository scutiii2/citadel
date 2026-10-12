"""The battle rules. Pure: no database, HTTP, clock or model.

One round, in order: lock both actions, apply SUPPORT then DEFENSE, settle
CATCH-versus-FLEE, roll the action order once from the updated SPEED, resolve
ATTACK / CATCH / FLEE in that order, stop at the first terminal result, then
expire end-of-round effects.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from src.ascension.catalog import Catalog
from src.ascension.models import (
    HARMFUL,
    STAT_STATUS,
    Status,
    PLAYER,
    SIDES,
    WILD,
    AbilitySpec,
    Action,
    BattleSetup,
    BattleState,
    Buff,
    DefenseEffect,
    Fighter,
    Loadout,
    FighterState,
    RevealedRound,
    RoundOutcome,
    other,
)
from src.ascension.passives import Passive, PassiveFactory
from src.ascension.runtime import RandomSource, RecordingRandom

_EPS = 1e-9


class ActionError(ValueError):
    """The chosen action is not legal this round."""


class _Side:
    """Mutable working copy of one fighter while a round resolves."""

    def __init__(self, side: str, fighter: Fighter, fstate: FighterState, passive: Passive) -> None:
        self.side, self.fighter, self.passive = side, fighter, passive
        self.hp = fstate.hp
        self.buffs = list(fstate.buffs)
        self.defense = fstate.defense
        self.cooldowns = dict(fstate.cooldowns)
        self.statuses = list(fstate.statuses)

    def stat(self, name: str) -> int:
        value = getattr(self.fighter, name) + sum(b.amount for b in self.buffs if b.stat == name)
        value += sum(s.amount for s in self.statuses if STAT_STATUS.get(s.id) == name)
        return max(1, value)

    def status_amount(self, status_id: str) -> int:
        return sum(s.amount for s in self.statuses if s.id == status_id)

    def has_status(self, status_id: str) -> bool:
        return any(s.id == status_id for s in self.statuses)

    def marks(self) -> frozenset[str]:
        return frozenset(s.id[len("mark:"):] for s in self.statuses if s.id.startswith("mark:"))

    def set_status(self, status: Status) -> None:
        self.statuses = [s for s in self.statuses if s.id != status.id] + [status]

    def freeze(self) -> FighterState:
        return FighterState(self.hp, tuple(self.buffs), self.defense, tuple(sorted(self.cooldowns.items())), tuple(self.statuses))


class BattleEngine:
    def __init__(self, catalog: Catalog, passives: PassiveFactory | None = None) -> None:
        self._catalog = catalog
        self._passives = passives or PassiveFactory()

    # -- setup ---------------------------------------------------------------------

    def build_fighter(self, side: str, ascended_id: str, tier_id: str, level: int, loadout: Loadout | None = None) -> Fighter:
        kit = loadout or self._catalog.default_loadout(ascended_id)
        stat = lambda name: self._catalog.stat_value(ascended_id, level, tier_id, name)  # noqa: E731
        return Fighter(
            side=side, ascended_id=ascended_id, tier_id=tier_id, level=level,
            max_hp=stat("hp"), power=stat("power"), speed=stat("speed"),
            abilities=tuple(a for a in kit.abilities if a.unlock_level <= level), passive=kit.passive, extra_passives=kit.extra_passives,
        )

    def start_state(self, setup: BattleSetup) -> BattleState:
        def fresh(fighter: Fighter) -> FighterState:
            specs = (fighter.passive, *fighter.extra_passives)
            buffs = tuple(Buff(f"passive:{spec.kind}", stat, amount, None)
                          for spec in specs for stat, amount in self._passives.create(spec).start_buffs(fighter.power))
            return FighterState(hp=fighter.max_hp, buffs=buffs)

        return BattleState(round=1, player=fresh(setup.player), wild=fresh(setup.wild))

    def stat(self, fighter: Fighter, fstate: FighterState, name: str) -> int:
        """Current POWER or SPEED including temporary buffs and slow or weaken."""
        value = getattr(fighter, name) + sum(b.amount for b in fstate.buffs if b.stat == name)
        value += sum(s.amount for s in fstate.statuses if STAT_STATUS.get(s.id) == name)
        return max(1, value)

    # -- legal actions -------------------------------------------------------------

    def legal_actions(self, setup: BattleSetup, state: BattleState, side: str, *, can_collect: bool) -> list[Action]:
        """Every action `side` may choose this round. `can_collect` says whether
        the collecting side owns an EMBLEM; a wild Ascended may always CATCH (it
        only counters FLEE)."""
        fighter, fstate = setup.of(side), state.of(side)
        ready = dict(fstate.cooldowns)
        actions = [Action("attack", "ATTACK")]
        for ability in fighter.abilities:
            if state.round >= ready.get(ability.id, 0):
                actions.append(Action("ability", ability.category, ability.id, ability.percentage))
        actions.append(Action("flee", "FEAR"))
        if side == WILD or can_collect:
            actions.append(Action("catch", "INTERCEPT"))
        return actions

    def resolve_action(self, legal: list[Action], payload: dict[str, Any]) -> Action:
        """Match a client payload ({kind, ability_id?, emblem_tier?}) to a legal action."""
        kind, ability_id = payload.get("kind"), payload.get("ability_id")
        for action in legal:
            if action.kind == kind and action.ability_id == (ability_id if kind == "ability" else None):
                if kind != "catch":
                    return action
                tier = payload.get("emblem_tier")
                if not isinstance(tier, str):
                    raise ActionError("CATCH needs an emblem_tier")
                self._catalog.tier(tier)
                return replace(action, emblem_tier=tier)
        raise ActionError("that action is not available this round")

    # -- chances -------------------------------------------------------------------

    def capture_chance(self, emblem_tier: str, target: Fighter, target_state: FighterState) -> float:
        tier = self._catalog.tier(target.tier_id)
        resistance = (
            self._catalog.economy.base_capture_resistance * tier.capture_multiplier
            * (tier.hp_floor + (1 - tier.hp_floor) * target_state.hp / target.max_hp)
        )
        strength = self._catalog.tier(emblem_tier).emblem_strength
        return strength / (strength + resistance)

    # -- one round -----------------------------------------------------------------

    def resolve_round(
        self, setup: BattleSetup, state: BattleState, player_action: Action, wild_action: Action, rng: RandomSource
    ) -> RoundOutcome:
        rec = RecordingRandom(rng)
        sides = {s: _Side(s, setup.of(s), state.of(s), self._passives.create_all((setup.of(s).passive, *setup.of(s).extra_passives))) for s in SIDES}
        actions = {PLAYER: player_action, WILD: wild_action}
        events: list[dict[str, Any]] = []
        rnd = state.round

        for side, action in actions.items():  # cooldowns start when the action is revealed
            if action.kind == "ability":
                ability = self._ability(sides[side].fighter, action.ability_id)
                sides[side].cooldowns[ability.id] = rnd + sides[side].passive.cooldown(ability.cooldown) + 1
        for side in SIDES:  # SUPPORT first, so DEFENSE sees this round's POWER buffs
            if actions[side].category == "SUPPORT":
                spec = self._ability(sides[side].fighter, actions[side].ability_id)
                self._support(sides[side], spec, events)
                self._apply_effects(sides[side], sides[other(side)], spec, sides[side].fighter.power, events)  # unbuffed POWER
        for side in SIDES:
            if actions[side].category == "DEFENSE":
                spec = self._ability(sides[side].fighter, actions[side].ability_id)
                self._defense(sides[side], spec, events)
                self._apply_effects(sides[side], sides[other(side)], spec, sides[side].stat("power"), events)

        catchers: dict[str, int | None] = {}
        for side in SIDES:  # CATCH reduces FLEE whatever the action order; settled before any escape roll
            if actions[side].kind == "flee":
                foe = sides[other(side)]
                catchers[side] = foe.stat("power") if actions[other(side)].kind == "catch" else None
                if catchers[side] is not None:
                    events.append({"type": "catch_counters_flee", "side": other(side), "target": side})

        speed = {s: sides[s].stat("speed") for s in SIDES}
        chance_player_first = speed[PLAYER] / (speed[PLAYER] + speed[WILD])
        order = [PLAYER, WILD] if rec.next() < chance_player_first else [WILD, PLAYER]
        events.append({"type": "order", "first": order[0], "chance_player_first": round(chance_player_first, 4)})

        terminal: str | None = None
        emblem: str | None = None
        for side in order:
            if terminal:
                break
            action = actions[side]
            if action.category == "ATTACK":
                terminal = self._attack(sides, actions, side, events)
                if not terminal and action.kind == "ability":  # an ability's effects land after its hit
                    spec = self._ability(sides[side].fighter, action.ability_id)
                    self._apply_effects(sides[side], sides[other(side)], spec, sides[side].stat("power"), events)
            elif action.kind == "catch":
                terminal, spent = self._catch(setup, sides, actions, side, rec, events)
                emblem = spent or emblem
            elif action.kind == "flee":
                chance = self._flee(sides[side], catchers[side])  # uses HP as it is when the attempt resolves
                succeeded = rec.next() < chance
                events.append({"type": "flee", "side": side, "chance": round(chance, 4), "success": succeeded})
                if succeeded:
                    terminal = "escaped" if side == PLAYER else "wild_escaped"

        if not terminal:
            terminal = self._tick(sides, events)

        revealed = RevealedRound(rnd, {s: (actions[s].key, actions[s].category) for s in SIDES}, tuple(events))
        if not terminal:
            for side_obj in sides.values():
                self._expire(side_obj)
        new_state = BattleState(
            round=rnd if terminal else rnd + 1,
            player=sides[PLAYER].freeze(), wild=sides[WILD].freeze(), history=state.history + (revealed,),
        )
        return RoundOutcome(new_state, tuple(events), terminal, emblem, tuple(rec.draws))

    # -- parts of a round ----------------------------------------------------------

    @staticmethod
    def _ability(fighter: Fighter, ability_id: str | None) -> AbilitySpec:
        for ability in fighter.abilities:
            if ability.id == ability_id:
                return ability
        raise ActionError(f"unknown ability {ability_id!r}")

    @staticmethod
    def _support(me: _Side, ability: AbilitySpec, events: list) -> None:
        amount = math.floor(me.fighter.power * ability.percentage / 100 + _EPS)  # unbuffed POWER
        duration = ability.duration + me.passive.support_extra_rounds()
        me.buffs = [b for b in me.buffs if b.source != ability.id]  # reuse refreshes, never stacks
        me.buffs.append(Buff(ability.id, ability.stat, amount, duration))
        events.append({"type": "support", "side": me.side, "ability": ability.id, "stat": ability.stat, "amount": amount})

    @staticmethod
    def _defense(me: _Side, ability: AbilitySpec, events: list) -> None:
        rating = me.stat("power") * ability.percentage / 100 + me.passive.defense_rating_bonus(me.fighter.power)
        attacks, rounds = me.passive.defense_limits()
        if me.defense:
            rating = max(rating, me.defense.rating)  # overlapping defenses keep the strongest rating
        me.defense = DefenseEffect(rating, attacks, rounds)  # refresh resets the limits, nothing is banked
        events.append({"type": "defense", "side": me.side, "ability": ability.id, "rating": round(rating, 2)})

    @staticmethod
    def _ward(me: _Side, events: list) -> bool:
        """A ward turns a lethal hit into 1 HP, once. True when it saved the fighter."""
        if me.hp > 0 or not me.has_status("ward"):
            return False
        me.hp = 1
        me.statuses = [s for s in me.statuses if s.id != "ward"]
        events.append({"type": "ward_triggered", "side": me.side})
        return True

    @staticmethod
    def _give(caster: _Side, target: _Side, status: Status, events: list) -> None:
        target.set_status(status)
        events.append({"type": "status", "side": caster.side, "target": target.side, "status": status.id,
                       "amount": status.amount, "rounds": status.rounds_left})

    @staticmethod
    def _apply_effects(me: _Side, foe: _Side, spec: AbilitySpec, power: int, events: list) -> None:
        for effect in spec.effects:
            amount = math.floor(power * (effect.percentage or 0) / 100 + _EPS)
            rounds = effect.rounds or 0
            if effect.kind == "heal":
                bonus = me.passive.heal_multiplier(me.hp, me.fighter.max_hp)
                healed = min(math.floor(amount * bonus + _EPS), me.fighter.max_hp - me.hp)
                me.hp += healed
                events.append({"type": "heal", "side": me.side, "amount": healed})
            elif effect.kind == "regen":
                BattleEngine._give(me, me, Status("regen", max(1, amount), rounds), events)
            elif effect.kind == "bleed":
                BattleEngine._give(me, foe, Status("bleed", max(1, amount), rounds), events)
            elif effect.kind == "slow":
                cut = math.floor(foe.stat("speed") * (effect.percentage or 0) / 100 + _EPS)
                BattleEngine._give(me, foe, Status("slow", -max(1, cut), rounds), events)
            elif effect.kind == "weaken":
                cut = math.floor(foe.stat("power") * (effect.percentage or 0) / 100 + _EPS)
                BattleEngine._give(me, foe, Status("weaken", -max(1, cut), rounds), events)
            elif effect.kind == "exposed":
                BattleEngine._give(me, foe, Status("exposed", max(1, amount), rounds), events)
            elif effect.kind == "mark":
                target = me if effect.target == "self" else foe
                BattleEngine._give(me, target, Status(f"mark:{effect.name}", 0, rounds), events)
            elif effect.kind == "cleanse":
                removed = [s.id for s in me.statuses if s.id in HARMFUL]
                me.statuses = [s for s in me.statuses if s.id not in HARMFUL]
                events.append({"type": "cleanse", "side": me.side, "removed": removed})
            elif effect.kind == "ward":
                BattleEngine._give(me, me, Status("ward", 0, rounds), events)

    @staticmethod
    def _tick(sides: dict[str, _Side], events: list) -> str | None:
        """End of a surviving round: regen heals, bleed hurts (wild side first). A bleed can end the battle."""
        dead: list[str] = []
        for side in (WILD, PLAYER):
            me = sides[side]
            regen = me.status_amount("regen")
            if regen:
                bonus = me.passive.heal_multiplier(me.hp, me.fighter.max_hp)
                healed = min(math.floor(regen * bonus + _EPS), me.fighter.max_hp - me.hp)
                me.hp += healed
                events.append({"type": "tick", "side": side, "kind": "regen", "amount": healed, "hp": me.hp})
            bleed = me.status_amount("bleed")
            if bleed:
                me.hp = max(0, me.hp - bleed)
                if me.hp == 0:
                    BattleEngine._ward(me, events)
                events.append({"type": "tick", "side": side, "kind": "bleed", "amount": bleed, "hp": me.hp})
                if me.hp == 0:
                    dead.append(side)
        if WILD in dead:
            return "won"
        return "knocked_out" if PLAYER in dead else None

    @staticmethod
    def _flee(me: _Side, catcher_power: int | None) -> float:
        power = me.stat("power")
        chance = power / (100 + power) * me.hp / me.fighter.max_hp
        return chance * 100 / (100 + catcher_power) if catcher_power is not None else chance

    @staticmethod
    def _attack(sides: dict[str, _Side], actions: dict[str, Action], attacker: str, events: list) -> str | None:
        me, foe = sides[attacker], sides[other(attacker)]
        power = me.stat("power")
        raw = power * actions[attacker].percentage / 100 + me.passive.attack_bonus(
            power, me.hp, me.fighter.max_hp, actions[foe.side].category == "DEFENSE"
        ) + me.passive.marked_bonus(power, foe.marks())
        protected = bool(foe.defense and foe.defense.attacks_left > 0)
        if protected:
            rating = max(0.0, foe.defense.rating - foe.status_amount("exposed"))
            damage = math.floor(raw * 100 / (100 + rating) + _EPS)
            foe.defense = replace(foe.defense, attacks_left=foe.defense.attacks_left - 1)
        else:
            damage = math.floor(raw + _EPS)
        damage = max(1, damage)
        foe.hp = max(0, foe.hp - damage)
        if foe.hp == 0:
            BattleEngine._ward(foe, events)
        events.append({"type": "attack", "side": attacker, "damage": damage, "protected": protected, "target_hp": foe.hp})
        if foe.hp == 0:
            return "won" if foe.side == WILD else "knocked_out"
        return None

    def _catch(self, setup: BattleSetup, sides: dict[str, _Side], actions: dict[str, Action], catcher: str,
               rec: RecordingRandom, events: list) -> tuple[str | None, str | None]:
        foe = other(catcher)
        if actions[foe].kind == "flee":  # already counted against the escape; no collection, no EMBLEM
            return None, None
        if catcher == WILD:
            events.append({"type": "catch_ignored", "side": WILD})
            return None, None
        tier = actions[catcher].emblem_tier
        chance = self.capture_chance(tier, setup.of(foe), sides[foe].freeze())
        succeeded = rec.next() < chance
        events.append({"type": "capture_attempt", "side": catcher, "emblem": tier, "chance": round(chance, 4), "success": succeeded})
        return ("captured" if succeeded else None), tier

    @staticmethod
    def _expire(me: _Side) -> None:
        me.buffs = [replace(b, rounds_left=b.rounds_left - 1) if b.rounds_left is not None else b for b in me.buffs]
        me.buffs = [b for b in me.buffs if b.rounds_left is None or b.rounds_left > 0]
        if me.defense:
            left = replace(me.defense, rounds_left=me.defense.rounds_left - 1)
            me.defense = left if left.rounds_left > 0 and left.attacks_left > 0 else None
        me.statuses = [replace(s, rounds_left=s.rounds_left - 1) for s in me.statuses]
        me.statuses = [s for s in me.statuses if s.rounds_left > 0]
