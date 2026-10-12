# Ascension: four active slots, two passive slots, and Twoychi's branch slots

Date: 2026-10-12. Status: built.
Builds on the ability trees (`2026-10-12-ascension-ability-trees-design.md`) and the effects design.

## Goal

Twoychi fights with up to 4 active abilities and 2 passives. The seven existing Ascended (bruiser, channeler, forbidden, guardian, scout, sentinel, striker) stay basic characters: 3 active
abilities, 1 passive and a single tree, exactly as today. Twoychi is the one Ascended whose
slots are tied to the branches of her tree: each slot takes only nodes of its own branch. Troy's three forms and Aya are
those branches, so a form is just "the slot an ability sits in"; it changes no stats and no abilities.

Out of scope: a Water resource (Water is Aya's animation and identity only, never a mechanic), form stances, form
multipliers, and any change to the other Ascended (their kit, slots and trees stay as they are).

## Decisions

| Question | Decision |
|---|---|
| Slots | An Ascended without `slots` in its tree has `a1` to `a3` and `p1`; any learned node of the right kind goes in any slot. Only a tree that declares `slots` can have `a4` or `p2`. Today only Twoychi does; a future special Ascended may declare its own. |
| Twoychi's slots | Declared in her `tree.json`: `a1` Wolf, `a2` Bear, `a3` Dog, `a4` Aya; `p1` Troy (Wolf, Bear and Dog passives), `p2` Aya. A slot takes only learned nodes of its own branches. |
| Form bonus | None. An ability is authored with its own numbers, and it can only sit in its own form's slot, so "the stats follow the form" holds by construction. |
| Cross-tree nodes | A node needing two branches still has one home `branch` (written in the node). It sits in that branch's slot. |
| Empty slots | Allowed, except that at least one active ability must be equipped. A battle uses the equipped abilities in slot order. |
| Old saved loadouts | Stay valid. A slot whose node does not belong there (a Twoychi loadout saved before this change) is ignored when a battle starts; if no active slot is left the default kit is used. |

## Tree format

`tree.json` gains optional fields. An Ascended without them behaves exactly as today: 3 active slots, 1 passive slot, free choice, one tree.

```json
{"slots": {"a1": ["wolf"], "a2": ["bear"], "a3": ["dog"], "a4": ["aya"], "p1": ["wolf", "bear", "dog"], "p2": ["aya"]},
 "nodes": [{"id": "twoychi_rending_bite", "branch": "wolf", ...}]}
```

- `slots` maps a slot id (`a1` to `a4`, `p1`, `p2`) to the branch names it takes. The declared slots are the Ascended's slots: they must include `a1` and `p1`,
  the active ones run consecutively from `a1`, and each lists at least one branch; a branch used in `nodes` must appear in at least one slot
  of the matching kind (an ability branch in an `a` slot, a passive node's branch in a `p` slot), or it is unequippable
  and the loader rejects the tree.
- Every node of a tree that declares `slots` needs a `branch` (a lowercase name). Roots too. Without `slots`, `branch`
  is optional and ignored.
- **Roots.** A root is a catalog ability, the first passive (`<id>_passive`) or the second passive (`<id>_passive_2`).
  The catalog kit holds 3 abilities and 1 passive; only an Ascended whose tree declares `a4` and `p2` may list a 4th
  ability and a `passive_2` (the loader rejects them otherwise). The catalog ability roots unlock at levels 1, 10, 20 and (for the fourth) 30. For everyone else there are 4 roots as today.
- Validation: every node's `branch` is known; a node must have a slot that can take it; the existing checks (no cycles, no
  unreachable nodes, no shared points, a root cannot have `requires`) stay.

## Catalog

`ascended/<id>/catalog.json` lists 3 `abilities` and one `passive`. Twoychi lists 4 `abilities` and adds `passive_2` (same
shape as `passive`). The default loadout fills the slots the Ascended has, in order: `a1` to `a3` or `a4`, `p1`, and `p2` if present.
The AI-controlled wild Ascended use the same default loadout as today.

## Twoychi

- Roots: four abilities and two passives, one of each per branch group. New root for the Dog branch: Comforting Presence
  (SUPPORT), which leaves its place as a Dog node. Tidecall stays Aya's root, Troy's Hunt the Wolf root, Mournful Veil
  the Bear root. Passive roots: `twoychi_passive` (Troy's, as now) and `twoychi_passive_2` (Aya's, a flavour passive named
  Waterbound that adds a small heal bonus; Water has no mechanic).
- Every existing node gets a `branch`. Wolf, Bear and Dog nodes take their own tree's name. The five cross-tree nodes get
  the home branch: Blood in the Water `wolf`, Breakwater `bear`, Quiet River `dog`, Scent of Danger `wolf`, Loyal Guardian
  `bear`; Two Hearts, One Soul `dog` (a passive, so it goes in `p1`). Aya's nodes take `aya`.
- Aya needs more passives so `p2` is a real choice: new Aya-branch passives built from the existing kinds
  (`heal_bonus`, `low_hp_attack_bonus`, `defense_rating_bonus`, `cooldown_reduction`). Numbers are placeholders (?).

## Loadout API

`PUT /ascension/ascendeds/{id}/loadout` takes `{"slots": {"a1": "<node id>", "a3": "<node id>", "p1": "<node id>"}}`.
Each value is a learned node of the right kind; a slot may be left out or null. The old body (`abilities`, `passive`)
is no longer accepted. A slot the Ascended does not have (`a4` on a basic one) is an error. Rules, in order: known slot ids only; no node in two slots; each node learned, of the right kind
and allowed by the tree's `slots`; at least one `a` slot filled; and the Ascended is not in the active battle. Errors
name the slot and the node.

`GET .../tree` returns `slots` (each with its kind and branches), each node's `branch` and the `loadout` as a map of every
slot the Ascended has (four for a basic tree, six for Twoychi). The web `TreeTab` shows those slots, filtered to the branch a slot takes, and the arena and action bar
simply show however many abilities the loadout has.

## Engine and policy

The engine takes any number of abilities. Equipped passives combine through `CombinedPassive`: bonuses add,
multipliers multiply and defense limits take the best of each limit. The battle freezes its loadout at start as today. The
autonomous policy and the personalities work per category, so a fourth ability changes nothing in them.

## Tests

- catalog: Twoychi's 4 abilities and second passive load; a 4th ability or `passive_2` without `a4`/`p2` slots is rejected; `slots` validated (unknown branch, branch without a matching slot,
  node without a branch, wrong slot kind); a tree without `slots` still loads with 3 active slots and 1 passive slot; default loadout fills
  the Ascended's own slots.
- trees service: a node outside the slot's branches is rejected, naming slot and node; the free slots accept any learned
  node; at least one active ability; no repeats; fighting Ascended refused; a stored loadout with a stale slot is ignored
  when the battle starts and the default kit fills in when nothing is left.
- Twoychi content: every node has a branch; her four ability roots and two passive roots exist; every node can be equipped
  in some slot; each branch has at least one passive node where `p1` or `p2` needs one.
- API and web: the new body and the six-slot response; `TreeTab` shows the six slots and rejects an off-branch drop with
  the server's error; `vue-tsc` and `vitest` green.
- A battle with a 4-ability loadout resolves (the engine and the action bar list all four).

## Open questions

- All numbers, the Aya passives and the Waterbound bonus are placeholders (?).
- None for the other Ascended: they stay 3 + 1 with one tree each.
