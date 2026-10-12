# Loadout Slots and Twoychi Branches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Twoychi fights with 4 active and 2 passive abilities, each slot taking only its own tree branch; the seven existing Ascended stay at 3 active, 1 passive and one free tree.

**Architecture:** A tree may declare `slots` (slot id to branch names) and give every node a `branch`. A tree without them behaves exactly as today. The loadout API becomes a slot map. The engine learns to combine two passives through one `CombinedPassive`; `Loadout` and `Fighter` carry the second passive as `extra_passives`.

**Tech Stack:** Python 3, FastAPI, SQLite (aiosqlite style repository), pytest; Vue 3 + TypeScript + Pinia, vitest, vue-tsc.

**Spec:** `docs/superpowers/specs/2026-10-12-ascension-loadout-slots-design.md`

## Global Constraints

- All paths are relative to `apps/ascension/` unless they start with `docs/`. Python tests run with `.venv_ascension\Scripts\python -m pytest -q` from `apps/ascension`; web checks run in `web` with `npx vue-tsc --noEmit` and `npx vitest run`.
- The seven existing Ascended (bruiser, channeler, forbidden, guardian, scout, sentinel, striker) keep 3 active slots (`a1` to `a3`), 1 passive slot (`p1`) and 4 roots. Their `catalog.json` and `tree.json` are not touched.
- Only a tree that declares `slots` may have `a4` or `p2`. Declared slots are the Ascended's slots and must include `a1` and `p1`. A 4th catalog ability or a `passive_2` without the matching declared slot is a `CatalogError`.
- Slot ids: active `a1` to `a4`, passive `p1` and `p2`. Branch names are lowercase letters and underscores.
- Twoychi slots: `a1` wolf, `a2` bear, `a3` dog, `a4` aya, `p1` wolf+bear+dog, `p2` aya.
- No form bonus and no Water mechanic. All numbers are placeholders (?).
- `Fighter.to_dict` stays readable for old saved battles: a missing `extra_passives` is empty.
- Ability root unlock levels are `(1, 10, 20)` for 3 abilities and `(1, 10, 20, 30)` for 4.
- Text of this work is committed in small commits that end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not touch the user's uncommitted sprite, Ember or `assets/` files.
- Windows git-bash: write multi-line Python scripts to a file with the Write tool, not a heredoc with triple quotes.

---

## File Structure

- Modify `src/ascension/passives.py`: `CombinedPassive`.
- Modify `src/ascension/models.py`: `Loadout.extra_passives`, `Fighter.extra_passives`.
- Modify `src/ascension/engine.py`: `build_fighter`, `start_state`, the places that create a passive.
- Modify `src/ascension/tree.py`: `branch`, `slots`, slot helpers, validation.
- Modify `src/ascension/catalog.py`: parse `branch` and `slots`, 4th ability, `passive_2`, default loadout.
- Modify `src/ascension/trees.py`, `src/ascension/api.py`: slot-map loadout.
- Modify `ascended/twoychi/catalog.json`, regenerate `ascended/twoychi/tree.json`, update `ascended/twoychi/ability_design.md`.
- Modify `web/src/api/AscensionClient.ts`, `web/src/stores/ascension.ts`, `web/src/components/TreeTab.vue` and their tests.
- Tests: `tests/ascension/test_passives_combined.py` (new), `test_tree_slots.py` (new), plus updates to `test_trees.py`, `test_tree_catalog.py`, `test_tree_content.py`, `test_api.py` and others that call the old loadout shape.

---

### Task 1: Two passives in a battle

**Files:**
- Modify: `src/ascension/passives.py`, `src/ascension/models.py`, `src/ascension/engine.py`
- Test: `tests/ascension/test_passives_combined.py` (new), `tests/ascension/test_models_effects.py` (round trip)

**Interfaces:**
- Produces: `CombinedPassive(passives: Sequence[Passive])` in `passives.py`; `PassiveFactory.create_all(specs: Sequence[PassiveSpec]) -> Passive` (one spec returns that passive, several return a `CombinedPassive`); `Loadout.extra_passives: tuple[PassiveSpec, ...] = ()`; `Fighter.extra_passives: tuple[PassiveSpec, ...] = ()`.

- [ ] **Step 1: Write the failing tests** in `tests/ascension/test_passives_combined.py`

```python
from src.ascension.models import PassiveSpec
from src.ascension.passives import CombinedPassive, PassiveFactory

FACTORY = PassiveFactory()


def both(*specs):
    return FACTORY.create_all(specs)


def test_one_spec_is_that_passive_and_none_is_neutral():
    assert both().attack_bonus(100, 50, 100, False) == 0.0
    assert both(PassiveSpec("battle_start_speed", {"power_fraction": 0.5})).start_buffs(20) == [("speed", 10)]


def test_bonuses_add_and_multipliers_multiply():
    combined = both(PassiveSpec("low_hp_attack_bonus", {"hp_below": 0.5, "power_fraction": 0.25}),
                    PassiveSpec("attack_bonus_vs_defense", {"power_fraction": 0.2}))
    assert isinstance(combined, CombinedPassive)
    assert combined.attack_bonus(100, 10, 100, True) == 45.0
    assert combined.attack_bonus(100, 90, 100, True) == 20.0
    heals = both(PassiveSpec("heal_bonus", {"fraction": 0.5}), PassiveSpec("heal_bonus", {"fraction": 0.2}))
    assert abs(heals.heal_multiplier(10, 100) - 1.8) < 1e-9


def test_buffs_and_ratings_combine_and_defense_takes_the_best_of_each_limit():
    combined = both(PassiveSpec("defense_extension", {"protected_attacks": 2, "rounds": 1}),
                    PassiveSpec("defense_extension", {"protected_attacks": 1, "rounds": 3}),
                    )
    assert combined.defense_limits() == (2, 3)
    mixed = both(PassiveSpec("defense_rating_bonus", {"power_fraction": 0.3}), PassiveSpec("defense_rating_bonus", {"power_fraction": 0.1}))
    assert abs(mixed.defense_rating_bonus(100) - 40.0) < 1e-9
    support = both(PassiveSpec("support_duration_bonus", {"rounds": 1}), PassiveSpec("support_duration_bonus", {"rounds": 2}))
    assert support.support_extra_rounds() == 3


def test_cooldown_reductions_chain():
    combined = both(PassiveSpec("cooldown_reduction", {"rounds": 1, "minimum": 1}), PassiveSpec("cooldown_reduction", {"rounds": 1, "minimum": 1}))
    assert combined.cooldown(4) == 2 and combined.cooldown(2) == 1


def test_marked_bonus_adds():
    combined = both(PassiveSpec("attack_bonus_vs_marked", {"mark": "prey", "power_fraction": 0.3}),
                    PassiveSpec("attack_bonus_vs_marked", {"mark": "soaked", "power_fraction": 0.1}))
    assert abs(combined.marked_bonus(100, frozenset({"prey", "soaked"})) - 40.0) < 1e-9
    assert combined.marked_bonus(100, frozenset({"prey"})) == 30.0
```

And append to `tests/ascension/test_models_effects.py`:

```python
def test_fighter_extra_passives_round_trip_and_old_saves_load():
    from src.ascension.models import Fighter, PassiveSpec

    fighter = Fighter("player", "x", "common", 1, 10, 5, 5, (), PassiveSpec("none"), (PassiveSpec("heal_bonus", {"fraction": 0.1}),))
    assert Fighter.from_dict(fighter.to_dict()) == fighter
    old = fighter.to_dict()
    del old["extra_passives"]
    assert Fighter.from_dict(old).extra_passives == ()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv_ascension\Scripts\python -m pytest -q tests/ascension/test_passives_combined.py tests/ascension/test_models_effects.py`
Expected: FAIL (`create_all` and `extra_passives` do not exist).

- [ ] **Step 3: Implement**

`src/ascension/passives.py`: add `from typing import Callable, Sequence`, then after `HealBonus`:

```python
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
```

and in `PassiveFactory`:

```python
    def create_all(self, specs: Sequence[PassiveSpec]) -> Passive:
        """One passive for a whole equipped set: neutral for none, that passive for one, a combination for several."""
        built = [self.create(s) for s in specs]
        if not built:
            return Passive()
        return built[0] if len(built) == 1 else CombinedPassive(built)
```

`src/ascension/models.py`: `Loadout` gets `extra_passives: tuple[PassiveSpec, ...] = ()`. `Fighter` gets `extra_passives: tuple[PassiveSpec, ...] = ()` as the last field; `to_dict` adds `"extra_passives": [p.to_dict() for p in self.extra_passives]`; `from_dict` passes `tuple(PassiveSpec.from_dict(p) for p in raw.get("extra_passives", []))` as the last argument.

`src/ascension/engine.py`:
- `build_fighter`: add `extra_passives=kit.extra_passives` to the `Fighter(...)` call.
- `start_state.fresh`: replace the `kind`/`buffs` lines with

```python
            specs = (fighter.passive, *fighter.extra_passives)
            buffs = tuple(Buff(f"passive:{spec.kind}", stat, amount, None)
                          for spec in specs for stat, amount in self._passives.create(spec).start_buffs(fighter.power))
            return FighterState(hp=fighter.max_hp, buffs=buffs)
```

- In `resolve_round` (the `sides = {...}` line, near engine.py:157) replace `self._passives.create(setup.of(s).passive)` with `self._passives.create_all((setup.of(s).passive, *setup.of(s).extra_passives))`.
- `grep -n "_passives.create" src/ascension/*.py` must then show only `create` used inside `start_state`.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: only the 7 known sprite failures; everything else passes (a single passive behaves exactly as before).

- [ ] **Step 5: Commit**

```bash
git add src/ascension/passives.py src/ascension/models.py src/ascension/engine.py tests/ascension/test_passives_combined.py tests/ascension/test_models_effects.py
git commit -m "feat(ascension): a fighter may carry two passives"
```

---

### Task 2: Branches and slots in the tree and the catalog

**Files:**
- Modify: `src/ascension/tree.py`, `src/ascension/catalog.py`
- Test: `tests/ascension/test_tree_slots.py` (new), `tests/ascension/test_tree_catalog.py`, `tests/ascension/test_tree_content.py`

**Interfaces:**
- Produces in `tree.py`: constants `ACTIVE_SLOTS = ("a1", "a2", "a3", "a4")`, `PASSIVE_SLOTS = ("p1", "p2")`, `DEFAULT_SLOTS = ("a1", "a2", "a3", "p1")`; `TreeNode.branch: str | None = None` (public dict key `branch`); `AbilityTree(nodes, slots: Mapping[str, tuple[str, ...]] | None = None)` with properties `slot_ids: tuple[str, ...]` and `declared: bool`, and `accepts(slot: str, node: TreeNode) -> bool`; `passive_root_id(ascended_id, number=1)` returning `<id>_passive` for 1 and `<id>_passive_2` for 2.
- Produces in `catalog.py`: `AscendedSpec.passive_2: PassiveSpec | None = None`; `Catalog.default_loadout` fills extra passives; `ABILITY_UNLOCK_LEVELS = (1, 10, 20, 30)`; `Catalog.default_slots(ascended_id) -> dict[str, str]`.
- `AscendedSpec.slot_ids` property is not needed: use `spec.tree.slot_ids`.

Rules the code must enforce (each has a test below):
1. `slots` is a mapping from a valid slot id to a non-empty list of lowercase branch names; it must contain `a1` and `p1`, at most one entry per id, and no unknown id. Active ids must be consecutive from `a1` (a2 needs a1, and so on); `p2` needs `p1`.
2. With `slots`, every node (roots too) needs a `branch` that matches `[a-z_]+`. Without `slots`, `branch` on a node is allowed and ignored (stored but unused).
3. With `slots`, every node must have at least one slot of its kind (`a*` for ability, `p*` for passive) that lists its branch, else `TreeError` "has no slot".
4. `AscendedSpec`: abilities count equals the number of active slots (3 when no `slots`); `passive_2` present iff `p2` is declared; ability unlock levels equal `ABILITY_UNLOCK_LEVELS[:count]`.
5. Roots listed in tree.json must equal `[*ability ids, passive_root_id(sid, 1)]` plus `passive_root_id(sid, 2)` when `passive_2` exists.
6. Default root tree (no tree.json) puts the root nodes in a column as today, including the second passive root.

- [ ] **Step 1: Write the failing tests** in `tests/ascension/test_tree_slots.py`

```python
import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.tree import AbilityTree, NodeCost, TreeError, TreeNode, passive_root_id
from tests.ascension.env import load_raw


def node(node_id, kind="ability", branch=None, requires=(), root=False, x=0, y=0):
    return TreeNode(node_id, kind, node_id, x, y, tuple(requires), 1, None if root else NodeCost("common", 1), root=root, branch=branch)


def test_passive_root_ids():
    assert passive_root_id("twoychi") == "twoychi_passive"
    assert passive_root_id("twoychi", 2) == "twoychi_passive_2"


def test_a_tree_without_slots_has_the_default_slots_and_accepts_any_node_of_the_kind():
    tree = AbilityTree([node("a", root=True), node("p", "passive", root=True, x=1)])
    assert tree.slot_ids == ("a1", "a2", "a3", "p1") and tree.declared is False
    assert tree.accepts("a2", tree.node("a")) and not tree.accepts("p1", tree.node("a")) and tree.accepts("p1", tree.node("p"))


def test_declared_slots_accept_only_their_branches():
    tree = AbilityTree(
        [node("w", branch="wolf", root=True), node("b", branch="bear", root=True, x=1), node("pw", "passive", "wolf", root=True, x=2)],
        {"a1": ("wolf",), "a2": ("bear",), "p1": ("wolf",)},
    )
    assert tree.slot_ids == ("a1", "a2", "p1") and tree.declared
    assert tree.accepts("a1", tree.node("w")) and not tree.accepts("a2", tree.node("w")) and not tree.accepts("a1", tree.node("pw"))


@pytest.mark.parametrize("slots,nodes,message", [
    ({"a1": ("x",), "p1": ("x",), "a3": ("x",)}, [node("a", branch="x", root=True), node("p", "passive", "x", root=True, x=1)], "consecutive"),
    ({"a1": ("x",)}, [node("a", branch="x", root=True)], "a1 and p1"),
    ({"a1": ("x",), "p1": ("x",), "z9": ("x",)}, [node("a", branch="x", root=True), node("p", "passive", "x", root=True, x=1)], "unknown slot"),
    ({"a1": ("x",), "p1": ("x",)}, [node("a", root=True), node("p", "passive", "x", root=True, x=1)], "needs a branch"),
    ({"a1": ("x",), "p1": ("x",)}, [node("a", branch="y", root=True), node("p", "passive", "x", root=True, x=1)], "has no slot"),
    ({"a1": (), "p1": ("x",)}, [node("a", branch="x", root=True), node("p", "passive", "x", root=True, x=1)], "at least one branch"),
])
def test_bad_slot_declarations_are_refused(slots, nodes, message):
    with pytest.raises(TreeError, match=message):
        AbilityTree(nodes, slots)


def twoychi_raw(**change):
    raw = copy.deepcopy(load_raw())
    spec = next(s for s in raw["ascendeds"] if s["id"] == "guardian")
    spec.update(change)
    return raw


def test_a_basic_ascended_cannot_have_a_fourth_ability_or_a_second_passive():
    raw = load_raw()
    spec = next(s for s in raw["ascendeds"] if s["id"] == "guardian")
    extra = copy.deepcopy(spec["abilities"][0])
    extra["id"], extra["unlock_level"] = "guardian_extra", 30
    with pytest.raises(CatalogError, match="abilities"):
        Catalog(twoychi_raw(abilities=[*spec["abilities"], extra]))
    with pytest.raises(CatalogError, match="passive_2"):
        Catalog(twoychi_raw(passive_2=spec["passive"]))


def test_the_seven_basic_ascended_keep_three_and_one():
    catalog = Catalog(load_raw())
    for sid in ("bruiser", "channeler", "forbidden", "guardian", "scout", "sentinel", "striker"):
        tree = catalog.ascended(sid).tree
        assert tree.slot_ids == ("a1", "a2", "a3", "p1") and len(tree.roots) == 4
        assert catalog.default_loadout(sid).extra_passives == ()
```

In `tests/ascension/test_tree_content.py`, change the roots assertion `len(tree.roots) == 4` to `len(tree.roots) == (6 if ascended_id == "twoychi" else 4)` (this passes only after Task 4; skip with `pytest.mark.skip` is NOT allowed: leave the line unchanged in this task and change it in Task 4).

- [ ] **Step 2: Run to verify they fail**

Run: `.venv_ascension\Scripts\python -m pytest -q tests/ascension/test_tree_slots.py`
Expected: FAIL (names do not exist).

- [ ] **Step 3: Implement `tree.py`**

```python
import re
from typing import Mapping

ACTIVE_SLOTS = ("a1", "a2", "a3", "a4")
PASSIVE_SLOTS = ("p1", "p2")
DEFAULT_SLOTS = ("a1", "a2", "a3", "p1")
BRANCH = re.compile(r"[a-z_]+")


def passive_root_id(ascended_id: str, number: int = 1) -> str:
    """The id of a root node that holds an Ascended's own passive (the second one ends in `_2`)."""
    return f"{ascended_id}_passive" if number == 1 else f"{ascended_id}_passive_{number}"
```

Add `branch: str | None = None` as the last field of `TreeNode` and `"branch": self.branch` to the dict in `to_public`. `AbilityTree.__init__(self, nodes, slots: Mapping[str, tuple[str, ...]] | None = None)` stores `self._slots = dict(slots) if slots else None`, then calls `_validate()`, then `_validate_slots()`:

```python
    @property
    def declared(self) -> bool:
        return self._slots is not None

    @property
    def slot_ids(self) -> tuple[str, ...]:
        return tuple(self._slots) if self._slots is not None else DEFAULT_SLOTS

    def accepts(self, slot: str, node: TreeNode) -> bool:
        """Can this node sit in this slot? The kind must match; a declared slot also needs the node's branch."""
        if slot not in self.slot_ids or node.kind != ("ability" if slot in ACTIVE_SLOTS else "passive"):
            return False
        return self._slots is None or node.branch in self._slots[slot]

    def _validate_slots(self) -> None:
        if self._slots is None:
            return
        slots = self._slots
        for slot, branches in slots.items():
            if slot not in (*ACTIVE_SLOTS, *PASSIVE_SLOTS):
                raise TreeError(f"unknown slot {slot!r}")
            if not branches or any(not BRANCH.fullmatch(b) for b in branches):
                raise TreeError(f"slot {slot!r} needs at least one branch of lowercase letters and underscores")
        if "a1" not in slots or "p1" not in slots:
            raise TreeError("slots must include a1 and p1")
        actives = [s for s in ACTIVE_SLOTS if s in slots]
        if actives != list(ACTIVE_SLOTS[: len(actives)]) or ("p2" in slots and "p1" not in slots):
            raise TreeError("active slots must be consecutive from a1")
        for node in self.nodes:
            if node.branch is None:
                raise TreeError(f"node {node.id!r} needs a branch")
            if not any(self.accepts(slot, node) for slot in slots):
                raise TreeError(f"node {node.id!r} has no slot that takes branch {node.branch!r}")
```

Order inside `_validate_slots`: the "unknown slot", "at least one branch", "a1 and p1", "consecutive" checks first, then the node loop. The test messages must match: "unknown slot", "at least one branch", "a1 and p1", "consecutive", "needs a branch", "has no slot".

- [ ] **Step 4: Implement `catalog.py`**
  - `ABILITY_UNLOCK_LEVELS = (1, 10, 20, 30)`; replace the check in `_ascended_spec` with: after building the tree (move the tree build before the check), `count = len([s for s in tree.slot_ids if s.startswith("a")])`; raise `CatalogError(f"{where}: needs {count} abilities (one per active slot)")` when `len(abilities) != count`; raise when `tuple(a.unlock_level for a in abilities) != ABILITY_UNLOCK_LEVELS[:count]`; parse `passive_2` (same shape as `passive`) and raise `CatalogError(f"{where}: passive_2 and the p2 slot go together")` unless `(passive_2 is not None) == ("p2" in tree.slot_ids)`.
  - Because `_tree` needs the slot count before the checks, change `_tree(raw, spec_id, abilities, passive, passive_2)` to accept `passive_2`, and let the abilities-count check happen inside `_ascended_spec` after `_tree` returns. The default tree (raw None) uses the passive ids `[passive_root_id(sid), *([passive_root_id(sid, 2)] if passive_2 else [])]`.
  - In `_tree`: read `slots_raw = raw.get("slots")` (allowed keys of `raw` become `{"nodes", "slots"}`); validate it is a mapping of str to list of str, convert to `{k: tuple(v)}`; for each node read `branch = item.get("branch")` and require `branch is None or isinstance(branch, str)` else `CatalogError(f"{at}: branch must be a string")`; pass `branch=branch` into every `TreeNode(...)` (roots too); the passive root for `passive_2` is `passive_root_id(spec_id, 2)` with `PassiveSpec` `passive_2` and name from its kind; the final root check lists `[*root_abilities, *passive_ids]`; build `AbilityTree(nodes, slots)`. The default-tree node dicts need no branch (no `slots` there).
  - `AscendedSpec` gets `passive_2: PassiveSpec | None = None`.
  - `default_loadout`: `Loadout(spec.abilities, spec.passive, (spec.passive_2,) if spec.passive_2 else ())`.
  - `default_slots(ascended_id)`: for a tree that is not declared: `{slot: ability.id for slot, ability in zip(("a1","a2","a3"), spec.abilities)} | {"p1": passive_root_id(id)}`. For a declared tree: for each root of kind ability, the first active slot that `accepts` it; each passive root (in the order `<id>_passive`, `<id>_passive_2`) to the first passive slot that accepts it and is still free (if none free, omit). Any root that finds no free slot is left out.

- [ ] **Step 5: Run to verify they pass**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: only the 7 known sprite failures.

- [ ] **Step 6: Commit**

```bash
git add src/ascension/tree.py src/ascension/catalog.py tests/ascension/test_tree_slots.py
git commit -m "feat(ascension): tree branches and declared loadout slots"
```

---

### Task 3: Loadout service and API with slot maps

**Files:**
- Modify: `src/ascension/trees.py`, `src/ascension/api.py`
- Test: `tests/ascension/test_trees.py` (update), `tests/ascension/test_api.py` (update), `tests/ascension/test_tree_slots_service.py` (new)

**Interfaces:**
- Consumes: Task 2 (`tree.slot_ids`, `tree.accepts`, `Catalog.default_slots`, `Loadout.extra_passives`).
- Produces: `TreeService.set_loadout(owner, key, ascended_id, slots: dict[str, str | None]) -> dict` returning `{"ascended_id", "slots": {slot_id: node_id | None}}`; `TreeService.view` returns `slots: [{"id", "kind", "branches": list[str] | None}]` and `loadout` keyed by every slot id of the Ascended; `LoadoutBody.slots: dict[str, str | None]`.

Rules for `set_loadout`, checked in this order, each raising `InvalidRequest` with the slot and node in the message:
1. `slots` is a dict of str to str-or-None; every key is in the Ascended's `tree.slot_ids` (else `"that Ascended has no slot 'a4'"`).
2. No node id appears in two slots (`"... is in two slots"`).
3. Each node is learned, and `tree.accepts(slot, node)` (else `"'<node>' cannot go in slot '<slot>'"`).
4. At least one active slot is filled (`"equip at least one active ability"`).
5. The Ascended is not in the active battle (existing `_reject_if_fighting`, raises `WrongPhase`).
The stored loadout is exactly the non-null entries. A slot omitted or null is empty.

`loadout_in` (battle start): read stored slots; if none, `default_loadout`. Otherwise keep a slot only if its node exists, is learned and `tree.accepts(slot, node)` (a stale or foreign node is ignored); abilities = the kept active nodes' abilities in slot order; if there are none, `default_loadout`; passives = the kept passive nodes' specs in slot order: first is `passive`, the rest `extra_passives`; no kept passive means `NO_PASSIVE` and no extras.

`_default_slots(ascended_id)` becomes `self._catalog.default_slots(ascended_id)`; `ABILITY_SLOTS` and `PASSIVE_SLOT` constants are removed from `trees.py` (grep for other users and import from `tree.py` instead).

- [ ] **Step 1: Write the failing tests**

Create `tests/ascension/test_tree_slots_service.py`. It reuses the guardian tree of `test_trees.py` but declares slots and a branch per node:

```python
import copy

import pytest

from src.ascension.catalog import Catalog
from src.ascension.errors import InvalidRequest
from src.ascension.records import AscendedRecord
from src.ascension.tree import passive_root_id
from src.ascension.trees import TreeService
from tests.ascension.env import Env, load_raw, run
from tests.ascension.test_trees import TREE

PASSIVE = passive_root_id("guardian")
BRANCHES = {"guardian_bulwark": "def", "guardian_rally": "def", "guardian_heavy_blow": "att", PASSIVE: "att",
            "guardian_iron_wall": "def", "guardian_stoneskin": "def", "guardian_shield_slam": "att"}
SLOTS = {"a1": ["att"], "a2": ["def"], "a3": ["att", "def"], "p1": ["att", "def"]}


def make(tmp_path):
    tree = copy.deepcopy(TREE)
    for item in tree["nodes"]:
        item["branch"] = BRANCHES[item["id"]]
    tree["slots"] = SLOTS
    raw = copy.deepcopy(load_raw())
    next(s for s in raw["ascendeds"] if s["id"] == "guardian")["tree"] = tree
    env = Env(tmp_path / "t.sqlite3")
    env.catalog = Catalog(raw)
    env.trees = TreeService(env.repo, env.writer, env.catalog)
    return env


async def owned(env):
    await env.start_player()
    await env.give(guardian=AscendedRecord("ann", "guardian", 0, 20, 0, tier_id="common"))


def test_a_node_goes_only_in_a_slot_that_takes_its_branch(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest, match="'guardian_bulwark' cannot go in slot 'a1'"):
            await env.trees.set_loadout("ann", "l1", "guardian", {"a1": "guardian_bulwark"})
        saved = await env.trees.set_loadout("ann", "l2", "guardian", {"a2": "guardian_bulwark", "a3": "guardian_heavy_blow"})
        await env.close()
        return saved

    assert run(scenario())["slots"] == {"a2": "guardian_bulwark", "a3": "guardian_heavy_blow"}


def test_a_slot_the_ascended_does_not_have_is_refused(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest, match="no slot 'a4'"):
            await env.trees.set_loadout("ann", "l1", "guardian", {"a1": "guardian_heavy_blow", "a4": "guardian_rally"})
        await env.close()

    run(scenario())


def test_a_node_in_two_slots_and_an_empty_active_loadout_are_refused(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest, match="in two slots"):
            await env.trees.set_loadout("ann", "l1", "guardian", {"a2": "guardian_bulwark", "a3": "guardian_bulwark"})
        with pytest.raises(InvalidRequest, match="at least one active"):
            await env.trees.set_loadout("ann", "l2", "guardian", {"p1": PASSIVE})
        with pytest.raises(InvalidRequest, match="at least one active"):
            await env.trees.set_loadout("ann", "l3", "guardian", {"a1": None})
        async with env.repo.transaction() as tx:
            stored = await tx.get_loadout("ann", "guardian")
        await env.close()
        return stored

    assert run(scenario()) == {}


def test_the_view_lists_the_slots_with_their_branches_and_the_loadout_by_slot(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        view = await env.trees.view("ann", "guardian")
        await env.close()
        return view

    view = run(scenario())
    assert view["slots"] == [
        {"id": "a1", "kind": "ability", "branches": ["att"]}, {"id": "a2", "kind": "ability", "branches": ["def"]},
        {"id": "a3", "kind": "ability", "branches": ["att", "def"]}, {"id": "p1", "kind": "passive", "branches": ["att", "def"]},
    ]
    assert list(view["loadout"]) == ["a1", "a2", "a3", "p1"]
    assert view["loadout"]["a1"] == "guardian_heavy_blow" and view["loadout"]["a2"] == "guardian_bulwark"


def test_a_stale_slot_is_ignored_at_battle_start(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        async with env.repo.transaction() as tx:
            await tx.put_loadout("ann", "guardian", {"a1": "guardian_bulwark", "a2": "guardian_rally"})
            kept = await env.trees.loadout_in(tx, "ann", "guardian")
            await tx.put_loadout("ann", "guardian", {"a1": "guardian_bulwark"})
            fallback = await env.trees.loadout_in(tx, "ann", "guardian")
        await env.close()
        return kept, fallback

    kept, fallback = run(scenario())
    assert [a.id for a in kept.abilities] == ["guardian_rally"]  # a1 holds a node of the wrong branch and is dropped
    assert [a.id for a in fallback.abilities] == ["guardian_bulwark", "guardian_rally", "guardian_heavy_blow"]
```

Update every existing call in `test_trees.py`, `test_api.py`, `test_coordinator.py`, `test_engine.py`, `test_simulation.py` and `test_repository.py` that uses the old shape:
- `set_loadout(owner, key, id, ["a", "b"], "p")` becomes `set_loadout(owner, key, id, {"a1": "a", "a2": "b", "p1": "p"})`, and `passive=None` simply omits `p1`.
- The API test body `{"abilities": [...], "passive": ...}` becomes `{"slots": {...}}`, and the "bad loadout" parametrization maps each old case to the new rule it breaks.
- The view test checks `loadout` has the keys `a1, a2, a3, p1` for the guardian.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv_ascension\Scripts\python -m pytest -q tests/ascension/test_tree_slots_service.py tests/ascension/test_trees.py tests/ascension/test_api.py`
Expected: FAIL.

- [ ] **Step 3: Implement** the rules above in `src/ascension/trees.py` (`view`, `loadout_in`, `set_loadout`, `_slots`) and in `src/ascension/api.py`:

```python
class LoadoutBody(_Body):
    slots: dict[str, str | None]
```

and `return await services.trees.set_loadout(owner, key, ascended_id, body.slots)`. In `view`, add `"slots": [{"id": s, "kind": "ability" if s.startswith("a") else "passive", "branches": list(tree._slots[s]) if declared else None}]`: expose it through a public `AbilityTree.branches(slot) -> tuple[str, ...] | None` (add that accessor in `tree.py`; `None` when the tree does not declare slots) rather than reading `_slots`. The idempotency payload for `set_loadout` is `{"ascended": ascended_id, "slots": slots}`.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: only the 7 known sprite failures.

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "feat(ascension): the loadout is a slot map; slots take only their branches"
```

(Stage only files this task changed; check `git status` first so the user's sprite and Ember files stay out.)

---

### Task 4: Twoychi's four forms and two passives

**Files:**
- Modify: `ascended/twoychi/catalog.json`, `ascended/twoychi/tree.json` (regenerated), `ascended/twoychi/ability_design.md`
- Scratch: a generator script in the scratchpad (not committed), derived from `gen_twoychi.py` in the scratchpad directory (it exists: `C:\Users\User\AppData\Local\Temp\claude\D--User-Documents-Programming-Python-MCPServer\0760b559-f401-4964-8b72-d693bf6d86e8\scratchpad\gen_twoychi.py`); if it is gone, edit `tree.json` directly.
- Test: `tests/ascension/test_tree_content.py`, `tests/ascension/test_twoychi_slots.py` (new), plus any test that counts Twoychi's abilities.

**Interfaces:**
- Consumes: Tasks 1 to 3.

Content changes:
1. `catalog.json` for Twoychi: `abilities` becomes four, in this order: `twoychi_tidecall` (unlock 1), `twoychi_mournful_veil` (10), `twoychi_troys_hunt` (20), and a new SUPPORT root `twoychi_comforting_presence` (unlock 30, name "Comforting Presence", category SUPPORT, percentage 50, cooldown 3, stat power, duration 4, effects `[{"kind":"regen","percentage":10,"rounds":4}]`; copy the exact JSON shape of the existing abilities in that file). Add `"passive_2": {"kind": "heal_bonus", "params": {"fraction": 0.15}}` (Waterbound, flavour only; Water has no mechanic). The first passive stays `support_duration_bonus`.
2. `tree.json`: add the top-level `slots`:
   `{"a1": ["wolf"], "a2": ["bear"], "a3": ["dog"], "a4": ["aya"], "p1": ["wolf", "bear", "dog"], "p2": ["aya"]}`.
3. Roots (all need `branch`): `twoychi_troys_hunt` wolf, `twoychi_mournful_veil` bear, `twoychi_comforting_presence` dog, `twoychi_tidecall` aya, `twoychi_passive` wolf (Troy's passive root), `twoychi_passive_2` aya. Roots list now has 6 entries. Remove the old node `twoychi_comforting_presence` (it is the root now) and re-point its dependents (`twoychi_guard`, `twoychi_shake_it_off`, `twoychi_quiet_river`'s requirement `faithful_companion` is not affected) to require `twoychi_comforting_presence` as before, which now means the root.
4. Branch of every non-root node: aya list nodes (mending_current, tidal_mend, flowing_veil, give_until_empty, healing_rain, borrowed_breath, mercys_current, purifying_water) `aya`; wolf list nodes `wolf`; bear list nodes `bear`; dog list nodes `dog`; cross nodes: blood_in_the_water `wolf`, breakwater `bear`, quiet_river `dog`, scent_of_danger `wolf`, loyal_guardian `bear`, two_hearts_one_soul `dog`.
5. A passive node's branch must match a passive slot: `give_until_empty` is Aya's and goes in `p2`; every Wolf, Bear and Dog passive goes in `p1` (their branches are in `p1`'s list). A passive node must not have a branch absent from every `p` slot (the loader's "has no slot" check enforces it).
6. New Aya passives so `p2` is a real choice (kind and params from the existing kinds; placeholders): `twoychi_still_water` "Still Water" `defense_rating_bonus` `{"power_fraction": 0.25}` unlock 13 requires `twoychi_mending_current` cost common 2; `twoychi_tidal_focus` "Tidal Focus" `cooldown_reduction` `{"rounds": 1, "minimum": 1}` unlock 22 requires `twoychi_flowing_veil` cost rare 3; `twoychi_deep_current` "Deep Current" `heal_bonus` `{"fraction": 0.3, "hp_below": 0.5}` unlock 26 requires `twoychi_give_until_empty` cost rare 4. Give each a unique `x`/`y` not used by another node.
7. Keep every node's position unique (the loader rejects shared points). `twoychi_comforting_presence` as a root takes the old Dog root position `(480, 680)`'s place: use `{"x": 400, "y": 480, "root": true}`... choose a free point and check uniqueness with the generator's assertion; move `twoychi_passive_2` to a free point near Aya (for example `{"x": 160, "y": 480}`).
8. `ability_design.md`: replace the intro paragraph about the tree with the slot table from the spec and say that Water has no mechanic. Keep the status tables.

Tests (write first, in `tests/ascension/test_twoychi_slots.py`):

```python
from tests.ascension.env import CATALOG

TWOYCHI = CATALOG.ascended("twoychi")


def test_twoychi_has_four_active_and_two_passive_slots_by_branch():
    tree = TWOYCHI.tree
    assert tree.slot_ids == ("a1", "a2", "a3", "a4", "p1", "p2")
    assert [tree.branches(s) for s in tree.slot_ids] == [("wolf",), ("bear",), ("dog",), ("aya",), ("wolf", "bear", "dog"), ("aya",)]
    assert len(TWOYCHI.abilities) == 4 and TWOYCHI.passive_2 is not None and len(tree.roots) == 6


def test_every_twoychi_node_can_be_equipped_somewhere():
    tree = TWOYCHI.tree
    for node in tree.nodes:
        assert any(tree.accepts(slot, node) for slot in tree.slot_ids), node.id


def test_each_branch_has_passives_for_its_slot():
    tree = TWOYCHI.tree
    for slot in ("p1", "p2"):
        assert sum(1 for n in tree.nodes if tree.accepts(slot, n)) >= 3


def test_the_default_slots_put_each_root_in_its_own_branch_slot():
    slots = CATALOG.default_slots("twoychi")
    assert slots == {"a1": "twoychi_troys_hunt", "a2": "twoychi_mournful_veil", "a3": "twoychi_comforting_presence",
                     "a4": "twoychi_tidecall", "p1": "twoychi_passive", "p2": "twoychi_passive_2"}


def test_the_default_loadout_has_both_passives():
    kit = CATALOG.default_loadout("twoychi")
    assert len(kit.abilities) == 4 and len(kit.extra_passives) == 1
```

In `test_tree_content.py` change the roots count assertion to `len(tree.roots) == (6 if ascended_id == "twoychi" else 4)` and the cap to `<= 50`. Fix every other test that counted Twoychi's abilities as 3 (run the suite and fix; the encounter and layout tests may list abilities).

- [ ] **Step 1:** write the tests above (Fail: Twoychi still has 3 abilities).
- [ ] **Step 2:** run them, expect FAIL.
- [ ] **Step 3:** make the content changes (use a scratch Python script for `tree.json`; keep CRLF/LF as in the file).
- [ ] **Step 4:** `.venv_ascension\Scripts\python -m pytest -q` (only the 7 sprite failures remain).
- [ ] **Step 5:** commit `feat(ascension): Twoychi's four forms and two passive slots` with `ascended/twoychi/catalog.json`, `tree.json`, `ability_design.md` and the tests.

---

### Task 5: Web: six slots in the tree tab

**Files:**
- Modify: `web/src/api/AscensionClient.ts`, `web/src/stores/ascension.ts`, `web/src/components/TreeTab.vue`, `web/src/api/AscensionClient.fixtures.ts` (if it holds a tree fixture)
- Test: `web/src/components/TreeTab.test.ts`, `web/src/stores/ascension.test.ts` (if it covers `saveLoadout`)

**Interfaces:**
- Consumes: the Task 3 API: `GET .../tree` returns `slots: [{id, kind, branches}]`, nodes with `branch`, and `loadout` keyed by slot id; `PUT .../loadout` takes `{slots}` and returns `{ascended_id, slots}`.

Changes:
- `AscensionClient.ts`: `export type LoadoutSlot = "a1" | "a2" | "a3" | "a4" | "p1" | "p2";` `TreeNodeView.branch?: string | null`; `export interface SlotInfo { id: LoadoutSlot; kind: "ability" | "passive"; branches: string[] | null }`; `TreeView.slots: SlotInfo[]` and `loadout: Partial<Record<LoadoutSlot, string | null>>`; `LoadoutResult { ascended_id: string; slots: Record<string, string | null> }`; `saveLoadout = (ascendedId, slots: Partial<Record<LoadoutSlot, string | null>>, key = newIdempotencyKey()) => this.http.request<LoadoutResult>("PUT", ..., { slots }, withKey(key))`.
- `stores/ascension.ts`: `saveLoadout(ascendedId, slots)`.
- `TreeTab.vue`: remove `ABILITY_SLOTS`; compute `slotList = tree.slots`; the slots strip shows one chip per slot with its label (`A1` to `A4`, `P1`, `P2`) and, when `branches` is set, a small branch hint (for example "wolf"); `slotLabel(slot)`; `equippedSlot(node)` as before; the equip buttons for the selected learned node are one button per slot where `slot.kind === node.kind` and (`slot.branches === null` or `node.branch` in `slot.branches`), labelled `Equip A1` or `Equip P2`; `equip` and `unequip` build the next map from `tree.loadout` and call `store.saveLoadout(id, next)` with only the non-null entries sent as given (null entries kept as `null`). Keep the learn flow, the error display and the node detail text.
- Test (write first, then implement): update the `TREE` fixture with `slots: [{id:"a1",kind:"ability",branches:null},{id:"a2",kind:"ability",branches:null},{id:"a3",kind:"ability",branches:null},{id:"p1",kind:"passive",branches:null}]` and keep existing assertions (button names `Equip A1` and so on, the unequip case, error display). Add:
  - a Twoychi-style tree fixture (`slots` with branches, nodes with `branch`): a wolf ability node offers `Equip A1` only; an aya passive node offers only `Equip P2`; the strip shows six chips with branch hints.
  - `saveLoadout` is called with the full slot map (`{ a1: "g_a", a2: "g_b", a3: null, p1: "g_pass" }` style) after an equip.

- [ ] **Step 1:** update/add the tests; run `npx vitest run src/components/TreeTab.test.ts` in `web` and see them fail.
- [ ] **Step 2:** implement.
- [ ] **Step 3:** `npx vue-tsc --noEmit` and `npx vitest run` in `web`: both clean.
- [ ] **Step 4:** commit `feat(ascension): the tree tab shows the loadout slots of each Ascended`.

---

### Task 6: Docs, vault and final check

**Files:**
- Modify: `README.md` (the ability tree and loadout section), `docs/superpowers/specs/2026-10-12-ascension-loadout-slots-design.md` (status: built; note the declared-slots-are-the-slots rule and the 4th-root unlock levels), the vault `Projects/Ascension.md` and a decision note.

- [ ] **Step 1:** In `README.md` describe: slots per Ascended (3+1 for the seven, 4+2 for Twoychi), `branch` and `slots` in `tree.json`, `passive_2`, the slot-map loadout API, and that two passives combine (bonuses add, multipliers multiply, limits take the best).
- [ ] **Step 2:** Vault (`D:\User\Documents\Programming\Brain`, its own repo; follow `Brain/AGENTS.md`): add one bullet to `Projects/Ascension.md` and a short note `Notes/Decision - Twoychi's slots follow the branches of her tree.md` (why: Troy's forms are loadout slots, Water is identity only, others stay 3+1). Commit in that repo.
- [ ] **Step 3:** Run the full checks: `.venv_ascension\Scripts\python -m pytest -q` (only the 7 sprite failures), in `web` `npx vue-tsc --noEmit` and `npx vitest run`.
- [ ] **Step 4:** Commit `docs(ascension): loadout slots`. Do not push.

---

## Self-Review

- **Spec coverage:** slots 3+1 and 4+2 (Tasks 2 and 4), Twoychi branch slots (2, 4), no form bonus and no Water (Global Constraints, Task 4 passive_2 as flavour), cross-tree home branches (Task 4 item 4), Dog root (Task 4 item 1), loadout API body (3), old loadouts ignored (3, `loadout_in`), tests per the spec's list (each task), README and vault (6). Aya extra passives (Task 4 item 6).
- **Gaps closed here:** the engine had one passive per fighter, so Task 1 adds `CombinedPassive` (not in the spec; it is required for two passives to act together).
- **Type consistency:** `passive_root_id(id, number)`, `AbilityTree.slot_ids/declared/accepts/branches`, `Catalog.default_slots`, `Loadout.extra_passives`, `Fighter.extra_passives`, `set_loadout(owner, key, id, slots)`, web `LoadoutSlot`/`SlotInfo`/`saveLoadout(id, slots)` are used the same way in every task.
