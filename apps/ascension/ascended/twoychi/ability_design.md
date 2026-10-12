# Twoychi: ability design

The tree has four active slots and two passive slots. Each node has one home branch, including cross-tree nodes.
Troy's forms are loadout slots with no form bonus. Water is Aya's identity and animation only; Water has no mechanic.
All numbers, including Waterbound and the new Aya passives, are placeholders (?).

| Slot | Takes |
|---|---|
| A1 | Wolf abilities |
| A2 | Bear abilities |
| A3 | Dog abilities (Comforting Presence root) |
| A4 | Aya abilities |
| P1 | Wolf, Bear and Dog passives (Troy) |
| P2 | Aya passives (Waterbound root) |

The catalog roots unlock at levels 1, 10, 20 and 30. The tree uses the engine's healing, regeneration, bleed,
slow, exposed, marks, cleanse and ward effects. The status tables below retain their original draft notes;
`tree.json` is the current implementation. Later possibilities include taunt, roots, revive, positions and several targets.

## Identity of each tree

| Tree | Identity | Grows from |
|---|---|---|
| Troy Wolf | Hunt, damage, speed, execution | Troy's Hunt (ATTACK) |
| Troy Bear | Tank, protection, bruiser | Mournful Veil (DEFENSE) |
| Troy Dog | Utility, recovery, companionship (not a weaker wolf) | Comforting Presence (SUPPORT) |
| Aya | Healing, water, cleansing, mercy | Tidecall (SUPPORT) |

## Status of every ability

"In tree" gives the node it became and what is approximated. "Later" gives what the engine would need.

### Troy Wolf

| Ability | Status |
|---|---|
| Predator's Instinct (passive) | In tree: `attack_bonus_vs_defense` 0.2. Isolated or low-health bonus: later (needs marks and several enemies). |
| Wolf Hunt | The root Troy's Hunt (ATTACK 160). The Prey mark: later. |
| Relentless Pursuit (passive) | In tree: `battle_start_speed` 0.4. Movement and crowd-control resistance: later. |
| Rending Bite | In tree: ATTACK 180. Bleeding and the Prey bonus: later. |
| Hamstring | In tree: ATTACK 95, cooldown 1. The heavy slow: later. |
| Circle the Prey | In tree: SUPPORT speed 80 for 2 rounds. The enemy defense drop: later. |
| Blood Trail (passive) | Later: needs Bleeding and a trail mark. |
| Pack Echoes | In tree: ATTACK 150. Spectral copies: flavour only. |
| Sixfold Hunt | In tree: ATTACK 280. Six wolves on several enemies: later (needs several targets). |
| Alpha Strike | In tree: ATTACK 230. The health-threshold bonus and knockdown: later. |
| No Escape (passive) | Later: needs the Prey mark and distance. |
| Apex Hunt (ultimate) | In tree: ATTACK 340, cooldown 4. Chaining to the next enemy: later. |

### Troy Bear

| Ability | Status |
|---|---|
| Guardian's Instinct (passive) | Later: needs Aya's HP as a separate pool. |
| Bear Form | In tree: SUPPORT power 70 for 3 rounds. Real stance (health, defense, size): later. |
| Maul | In tree: ATTACK 170. The stagger: later. |
| Crushing Paw | In tree: ATTACK 160. Area knockdown: later. |
| Guardian Leap | Later: needs positions. |
| Stand Behind Me | In tree: DEFENSE 250. Intercepting for Aya: flavour in a 1v1. |
| Unmovable (passive) | In tree: `defense_extension` (2 attacks, 1 round). Displacement resistance: later. |
| Territorial Roar | Later: needs taunt and an enemy damage debuff. |
| Earthbreaker | In tree: ATTACK 240. The slow: later. |
| Protective Rage (passive) | In tree: `low_hp_attack_bonus` 0.3 on its own HP. Aya's HP as the trigger: later. |
| Living Rampart | In tree: DEFENSE 320. Ranged protection for allies: later. |
| Bear Hug | Later: needs immobilize and throws. |
| Landslide (ultimate) | In tree: ATTACK 360, cooldown 4. Carrying enemies: later. |

### Troy Dog

| Ability | Status |
|---|---|
| Faithful Companion (passive) | In tree: `defense_rating_bonus` 0.3. Regeneration near Aya: later (needs healing). |
| Stay Close (passive) | In tree: `battle_start_speed` 0.25. Distance to Aya: later. |
| Comforting Presence (passive in the list) | In tree as SUPPORT power 50 for 4 rounds. Ally regeneration and fear cleanse: later. |
| Guard | In tree: DEFENSE 200. Counter-attack on the first attacker: later. |
| Fetch | Later: needs pickups. |
| Warning Bark | Later: needs hidden enemies. |
| Protective Bark | In tree: DEFENSE 140. Interrupting enemies: later. |
| Good Boy (passive in the list) | In tree as SUPPORT speed 70 for 3 rounds. Triggering on Aya's heal: later. |
| Shake It Off | Later: needs cleanse. |
| Watchful Rest | In tree: DEFENSE 280. Area healing and revealing: later. |
| Find Them | Later: needs tracking and marks. |
| Never Leave Her (passive) | In tree: `defense_extension` (1 attack, 2 rounds). Running to Aya: later. |
| Soulkeeper (passive) | Later: needs revive. The lore basis: when Aya dies Troy's soul stays where she fell. |
| Home Is Wherever You Are (ultimate) | In tree: SUPPORT power 120 for 4 rounds. The healing aura: later. No giant explosion, by design. |

### Aya

| Ability | Status |
|---|---|
| Waterbound (passive) | Later: needs the Water resource. |
| Mending Current | In tree: SUPPORT power 70 for 3 rounds. The heal over time: later (needs healing). |
| Tidal Mend | In tree: DEFENSE 180 (stands in for the water shield from excess healing). The heal: later. |
| Purifying Water | Later: needs cleanse. |
| Flowing Veil | In tree: DEFENSE 220. |
| Undertow | Later: needs displacement. |
| Rising Tide | Later: needs launch and several targets. |
| River's Grasp | Later: needs root. |
| Healing Rain | In tree: SUPPORT power 90 for 4 rounds. Regeneration and the Soaked mark: later. |
| Soaked (mechanic) | Later: the mark that links Troy's bonuses (wolf: damage, bear: stagger, dog: detection). |
| Life Current | Later: needs several allies. |
| Borrowed Breath | In tree: DEFENSE 300 (stands in for preventing death). The real rule: later (needs revive or survive-at-1). |
| Still Water | Later: needs an enemy slow. |
| Waterwalk (passive) | Later: needs terrain. |
| River Step | Later: needs positions. |
| Give Until Empty (passive) | In tree: `low_hp_attack_bonus` 0.25. Healing scaling with low Water: later. |
| Mercy's Current (ultimate) | In tree: DEFENSE 400, cooldown 4. The wave, stabilise and push back: later. |

### Cross-tree nodes (need two branches)

| Ability | Needs | Status |
|---|---|---|
| Blood in the Water | Wolf (Rending Bite) + Aya (Tidal Mend) | In tree: ATTACK 200. Soaked plus Bleeding becomes Prey: later. |
| Breakwater | Bear (Maul) + Aya (Flowing Veil) | In tree: `defense_rating_bonus` 0.4. Water gain on block: later. |
| Quiet River | Dog (Faithful Companion) + Aya (Mending Current) | In tree: `cooldown_reduction` 1. Healing recharge while resting: later. |
| Scent of Danger | Wolf (Hamstring) + Dog (Stay Close) | In tree: ATTACK 170. Mark then hunt: later. |
| Loyal Guardian | Bear (Crushing Paw) + Dog (Guard) | In tree: DEFENSE 300. Auto-transform and intercept: later. |
| Two Hearts, One Soul | the four ultimates | In tree: `defense_extension` (3 attacks, 3 rounds) at level 30. Cannot die while the other lives: later. |

## The original draft

The list below is kept as the source. It is the design intent; where it disagrees with the tree, the tree is what the game
does today.

**Troy Wolf** (hunt, pursuit, execution): Predator's Instinct, Wolf Hunt, Relentless Pursuit, Rending Bite, Hamstring, Circle
the Prey, Blood Trail, Pack Echoes, Sixfold Hunt (six wolves, from Unchosen), Alpha Strike, No Escape, Apex Hunt (ultimate).

**Troy Bear** (tank, protection, crowd control): Guardian's Instinct, Bear Form, Maul, Crushing Paw, Guardian Leap, Stand Behind
Me, Unmovable, Territorial Roar, Earthbreaker, Protective Rage, Living Rampart, Bear Hug, Landslide (ultimate, the enormous bear
from Unchosen).

**Troy Dog** (utility, detection, recovery, companionship; not a weaker wolf): Faithful Companion, Stay Close, Comforting Presence,
Guard, Fetch, Warning Bark, Protective Bark, Good Boy, Shake It Off, Watchful Rest, Find Them, Never Leave Her, Soulkeeper (when
Aya dies Troy stays beside her spirit and she can return at his place), Home Is Wherever You Are (ultimate: back to Dog Form with a
peaceful aura around Aya; no explosion, no transformation).

**Aya** (healing, water, cleansing, resurrection): Waterbound, Mending Current, Tidal Mend, Purifying Water, Flowing Veil,
Undertow, Rising Tide, River's Grasp, Healing Rain, Soaked (marks enemies; Troy gains form-dependent bonuses: wolf tracking and
damage, bear knockback, dog detection), Life Current, Borrowed Breath, Still Water, Waterwalk, River Step, Give Until Empty (healing
grows as her Water falls), Mercy's Current (ultimate: heal allies, stabilise the downed, push enemies back, put out fires).

**Cross-tree:** Blood in the Water (Wolf + Aya), Breakwater (Bear + Aya), Quiet River (Dog + Aya), Scent of Danger (Wolf + Dog),
Loyal Guardian (Bear + Dog), Two Hearts One Soul (all four trees: neither half can die for good while the other lives).
