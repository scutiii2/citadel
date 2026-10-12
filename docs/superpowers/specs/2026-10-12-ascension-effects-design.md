# Ascension: healing, statuses and safety effects

Date: 2026-10-12. Status: built.
Builds on the ability trees (`2026-10-12-ascension-ability-trees-design.md`). It gives the battle the mechanics that
Twoychi's design list needs and the engine lacks (`ascended/twoychi/ability_design.md`, every item marked "later" that
this spec covers).

## Goal

Abilities can do more than damage, shield or buff your own stat: heal, regenerate, put a lasting status on the enemy
(bleed, slow, weaken, exposed, named marks), cleanse, and ward off one lethal hit. A plain ability with no effects behaves
exactly as today.

Out of scope: the Water resource, Troy as a form stance, several targets, positions, pickups, hidden enemies, and any
change to the autonomous policy or the Laya situation text for statuses (the policy does not yet know that healing at
full HP is pointless; a later change can add a "fit" term). Converting Twoychi's tree to real effects is a follow-up plan.

## Decisions

| Question | Decision |
|---|---|
| Where effects live | An ability gets an optional `effects` list. Categories stay ATTACK, DEFENSE, SUPPORT. |
| When they apply | SUPPORT and DEFENSE abilities apply them in their own phase, after their buff or shield. ATTACK abilities apply them on hit, after the damage, if the target is alive. |
| Stacking | One status per id per fighter. Applying it again refreshes the rounds and the amount. Nothing stacks. |
| Cleanse | Removes bleed, slow, weaken and exposed from yourself. Marks, regen and ward stay. |
| Ward | The next lethal hit (an attack or a bleed tick) leaves 1 HP instead and removes the ward. It expires after its rounds. |
| Both die in one tick | The wild side's HP is checked first, so the player's Ascended wins the tie. Very rare. |
| Stat floors | Slow and weaken cannot take speed or power below 1. |

## Effects

Each effect is an object in the ability's `effects` list (at most 3 per ability). `percentage` is of the user's power
at the moment of use (the unbuffed power for SUPPORT, as the existing buff does; the current power otherwise).

| `kind` | Target | Fields | Meaning |
|---|---|---|---|
| `heal` | self | `percentage` | Restore `floor(power * pct / 100)` HP now, up to max HP. |
| `regen` | self | `percentage`, `rounds` | Restore that amount (at least 1) at the end of each of `rounds` rounds. |
| `bleed` | foe | `percentage`, `rounds` | Deal that amount (at least 1) at the end of each of `rounds` rounds. Ignores defense. |
| `slow` | foe | `percentage`, `rounds` | Lower the target's speed by `pct` percent of its current speed (at least 1). |
| `weaken` | foe | `percentage`, `rounds` | Lower the target's power by `pct` percent of its current power (at least 1). |
| `exposed` | foe | `percentage`, `rounds` | Lower the defense rating of the target's shield by `floor(power * pct / 100)` (at least 1). |
| `mark` | `foe` or `self` (default `foe`) | `name`, `rounds` | A named mark with no effect itself, for passives to read (`prey`, `soaked`). |
| `cleanse` | self | none | Remove bleed, slow, weaken and exposed. |
| `ward` | self | `rounds` | Survive one lethal hit at 1 HP. |

Example, in an ability node or `catalog.json` ability:

```json
{"id": "twoychi_rending_bite", "name": "Rending Bite", "unlock_level": 10, "category": "ATTACK", "percentage": 180, "cooldown": 2,
 "effects": [{"kind": "bleed", "percentage": 20, "rounds": 3}, {"kind": "mark", "name": "prey", "rounds": 3}]}
```

## State and resolution

- `FighterState` gains `statuses: tuple[Status, ...]`, where `Status(id, amount, rounds_left)`. The ids are `bleed`, `slow`,
  `weaken`, `exposed`, `regen`, `ward` and `mark:<name>`. Old saved battles load with no statuses.
- `_Side.stat` and `BattleEngine.stat` add the (negative) amount of `slow` to speed and of `weaken` to power, with a floor
  of 1, so speed order, damage, flee chance and the public numbers already follow.
- `_attack` subtracts the attacker's `exposed` amount from the defender's shield rating (never below 0).
- Round order: cooldowns, SUPPORT (buff, then its effects), DEFENSE (shield, then its effects), catch counters, action
  order, then the actions. After an ATTACK that does not end the battle, the attacking ability's effects apply to the
  target. At the end of a surviving round: `regen` and `bleed` tick (wild side first), a ward rescues a bleed that would
  kill, then rounds count down and statuses at zero expire. A bleed that kills ends the battle (`won` or `knocked_out`)
  and the round does not advance.
- New events in the revealed round: `heal`, `status` (id, target, amount, rounds), `cleanse`, `tick` (bleed or regen,
  amount, hp), `ward_triggered`. They are public like the existing ones, and `MatchReader` still reads only `attack`
  events (the mood replay counts bleed ticks as damage and heals and regen as recovery).

## Passives

Two new kinds in `passives.py`, no change to the existing ones:
- `attack_bonus_vs_marked` `{mark, power_fraction}`: attacks add `power * fraction` raw damage against a target that has
  `mark:<mark>`. Used for Predator's Instinct and No Escape.
- `heal_bonus` `{fraction, hp_below}`: heals and regen are multiplied by `1 + fraction`; if `hp_below` is given (0 to 1) the
  bonus applies only while own HP is below that fraction (Give Until Empty). Without `hp_below` it always applies (Good Boy).

## Catalog

`AbilitySpec` gains `effects: tuple[EffectSpec, ...] = ()` and keeps `to_dict`/`from_dict` compatible with saved
fighters (a missing `effects` is empty). `_ability` validates: a known `kind`; `percentage` above 0 for `heal`, `regen`,
`bleed`, `slow`, `weaken`, `exposed`; `rounds` of at least 1 for every kind that takes it; `mark` has a lowercase
`name` of letters and underscores and a `target` of `foe` or `self`; no unknown fields; at most 3 effects. The same rules
apply to ability nodes in `tree.json`.

## API and UI

- The public battle view adds `statuses` to each fighter, and each ability in the view and in the catalog and tree
  summaries carries its `effects`.
- `BattleArena` shows statuses beside buffs (`bleed 5 for 2 rounds`, `slow`, `marked prey`). The ability lists on the
  collection card, the tree node detail and the battle action bar describe an ability's effects in one short line
  (for example "Heals 70% of power. Bleeds 20% for 3 rounds.") from one shared helper, `effectText`.

## Tests

- engine: each effect (heal capped at max HP, regen over rounds, bleed tick and kill, slow and weaken change speed and
  power with the floor, exposed lowers the shield, cleanse removes only the harmful four, ward saves from an attack and
  from a bleed once, marks appear and expire); refresh instead of stack; an ATTACK ability applies its effects only on hit
  and only if the target lives; effects of an ability that was never used do nothing; old saved states and fighters load;
  both-die tie rule; the same seed replays the same battle.
- passives: both new kinds, and a mark of another name does nothing.
- catalog: every validation rule above, in a catalog ability and in a tree node.
- view and web: statuses in the public view, `effectText`, the arena and tree-node text.
- a battle with no effects anywhere replays exactly as before (existing tests stay green).

## Open questions

- The numbers are placeholders (?). Bleed ignoring defense and slow as a percentage of speed are first guesses.
- Done: the autonomous policy applies a fit multiplier (`status_fit.py`) after its two stages: heals at full HP, cleanses with
  nothing to clean, a ward already up and a status the foe already has are weighted down; a cleanse with a harmful status
  on you and a heal when wounded are weighted up.
- Marks are only readable by the two new passives for now; abilities that react to a mark are a later addition.
- Twoychi's conversion (which "later" abilities become real effects) is its own plan after this lands.
