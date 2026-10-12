# Ascension: ability trees and loadouts

Date: 2026-10-12. Status: proposed, waiting for review.
Follows the Unity project (`Game Developing/Unity 6/Ascension`, `Assets/Guides/AbilityTrees.md`): a tree is the set of
abilities an Ascended can learn, a book holds what it learned, and a loadout holds what it has equipped.

## Goal

Each Ascended gets its own ability tree, drawn as a different node graph. The player learns nodes with level,
prerequisites and essence, then equips learned nodes into slots. The equipped loadout decides which abilities and which
passive the Ascended fights with.

Out of scope: new engine mechanics, new ability categories, the autonomous policy redesign (see
`2026-10-12-ascension-autonomous-policy-design.md`, built after this).

## Decisions

| Question | Decision |
|---|---|
| Slots | 3 ability slots and 1 passive slot. Any learned node of the right kind, no duplicates in a slot set. |
| Learning | Needs level >= `unlock_level`, all prerequisites learned, and the essence cost. Permanent, per account. |
| Roots | The current 3 abilities and the current passive stay in `catalog.json` as the default loadout. They are free, pre-learned root nodes. |
| Tree look | Hand-placed `x`/`y` per node and drawn prerequisite lines. Every Ascended has its own shape. |
| Swapping | Allowed any time outside an active battle. A battle freezes its loadout when it starts (the fighter is already frozen). |
| Mixed loadouts | Any combination is legal, including 3 ATTACK abilities and no DEFENSE. The basic attack, FLEE and CATCH always stay legal. |

## Data

`ascended/<id>/tree.json`, beside `catalog.json`. The catalog loader reads it with the Ascended.

```json
{
  "nodes": [
    {"id": "guardian_bulwark", "root": true, "x": 40, "y": 120, "requires": []},
    {"id": "guardian_ironwall", "kind": "ability", "name": "Iron Wall", "category": "DEFENSE",
     "percentage": 260, "cooldown": 3, "unlock_level": 12, "requires": ["guardian_bulwark"],
     "cost": {"tier": "rare", "amount": 3}, "x": 200, "y": 60},
    {"id": "guardian_stoneskin", "kind": "passive", "name": "Stoneskin",
     "passive": {"kind": "defense_rating_bonus", "params": {"power_fraction": 0.4}},
     "unlock_level": 15, "requires": ["guardian_ironwall"], "cost": {"tier": "rare", "amount": 4}, "x": 360, "y": 60}
  ]
}
```

- A root node has `root: true` and only an `id` that matches an ability or the passive in `catalog.json`; its text and
  numbers are not repeated. Roots have no cost and are always learned.
- An ability node carries the same fields as an ability in `catalog.json` (`category`, `percentage`, `cooldown`,
  optional `stat` and `duration` for SUPPORT) plus `unlock_level`, `requires`, `cost`, `x`, `y`.
- A passive node carries a `passive` with a kind that `passives.py` already knows. No new passive kinds in this spec.
- Ids are unique across all Ascended, like ability ids today.

Catalog validation (clear `CatalogError` messages):
- the tree has no cycles, every `requires` id exists in the same tree, and every node is reachable from a root;
- every root id exists in `catalog.json` as one ability or the passive;
- categories, `stat` and passive kinds are valid; `cost.tier` is a regular tier; `amount` is a whole number of at least 1;
- `x` and `y` are numbers; two nodes may not sit on the same point;
- `ABILITY_UNLOCK_LEVELS` (1, 10, 20) stays the rule only for the three catalog abilities. Tree nodes set their own level.

## Storage

Database version 5 (migration from 4 adds the tables, no data change):

```sql
CREATE TABLE learned_nodes (owner TEXT NOT NULL, ascended_id TEXT NOT NULL, node_id TEXT NOT NULL,
                            PRIMARY KEY (owner, ascended_id, node_id));
CREATE TABLE loadouts (owner TEXT NOT NULL, ascended_id TEXT NOT NULL, slot TEXT NOT NULL, node_id TEXT NOT NULL,
                       PRIMARY KEY (owner, ascended_id, slot));  -- slot: a1, a2, a3, p1
```

No `loadouts` rows means the default loadout (the three catalog abilities in their slots, the catalog passive). Learned
roots are implied and never stored. `delete_player_data` removes both tables' rows.

## Service

`TreeService` (new `trees.py`), built with the repository, the writer and the catalog, like `UpgradeService`:
- `view(owner, ascended_id)` returns every node with its state (`root`, `learned`, `learnable`, `locked` and why), the
  learned set, the loadout, and the essence the player holds.
- `learn(owner, key, ascended_id, node_id)` checks level, prerequisites and essence, spends the essence, stores the node.
  Errors: 404 unknown or not owned, 409 `UpgradeNotReady`, `InsufficientEssence`. Idempotent by key.
- `set_loadout(owner, key, ascended_id, abilities, passive)` replaces the whole loadout. Rules: up to 3 distinct learned
  ability nodes (fewer is allowed, but at least 1), at most 1 learned passive node, each node of the right kind. A battle
  with that Ascended in the active battle gives 409 (`WrongPhase`), like the shop.

`RoundCoordinator.start` asks the tree service for the loadout and hands it to `engine.build_fighter`, which builds
`Fighter.abilities` and `Fighter.passive` from it instead of reading the catalog's fixed lists. `Fighter` keeps its
shape, so saved battles still load. Level gating in the engine keeps using `AbilitySpec.unlock_level`.

## API

| Route | Purpose |
|---|---|
| `GET /ascension/ascendeds/{id}/tree` | The tree view for the signed-in player. |
| `POST /ascension/ascendeds/{id}/tree/{node}/learn` | Learn a node. |
| `PUT /ascension/ascendeds/{id}/loadout` | Body `{abilities: [node ids], passive: node id or null}`. |
| `GET /ascension/catalog` | Each Ascended also lists its `tree` nodes (public data) so the UI can draw them. |

## UI

A "Tree" tab in the collection details. A canvas draws nodes at their `x`/`y` with prerequisite lines. Node states:
learned, learnable (outline, shows cost), locked (shows the missing level, prerequisite or essence). Clicking a node
shows its numbers and a Learn button. A slot bar (3 ability slots, 1 passive slot) sits under the canvas: pick a slot,
pick a learned node. The equipped nodes show a slot badge. The layout works at phone width by scrolling the canvas.

## Content

Each of the 7 Ascended gets 6 to 8 nodes: the 3 roots and the root passive, plus 2 to 4 new abilities or passives that
reuse existing categories and passive kinds with different numbers. Numbers are balance placeholders (?). The Twoychi
tree waits until Twoychi has a `catalog.json`.

## Tests

- catalog validation: cycle, missing prerequisite, unreachable node, unknown root, duplicate id, bad category or passive;
- learn: level, prerequisite and essence refusals leave state unchanged; success spends essence once; idempotent;
- loadout: slot limits, duplicates, unlearned node, wrong kind, active-battle refusal, default when none saved;
- the fighter of a started battle uses the equipped loadout, and a later change does not alter it;
- migration 4 to 5; reset removes the new rows;
- API routes (status codes) and web tests for the tree tab and the slot bar.

## Open questions

- Should essence of the Ascended's own tier be required for a node, or is `cost.tier` always set by the node (as drafted)?
- Should unlearning or respec exist? Not in this spec.
- A loadout with no DEFENSE has no `Bulwark`-style defense, and the basic attack still works. Balance may need a rule later.
