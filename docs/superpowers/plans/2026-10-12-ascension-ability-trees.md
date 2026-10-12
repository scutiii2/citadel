# Ascension Ability Trees Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each Ascended gets its own hand-placed ability tree. The player learns nodes (level, prerequisites, essence), equips 3 abilities and 1 passive, and the battle uses that loadout.

**Architecture:** A pure `tree.py` holds the validated node graph. `catalog.py` loads `ascended/<id>/tree.json` into each `AscendedSpec`. Two tables (`learned_nodes`, `loadouts`) hold the player's choices. A new `TreeService` (view, learn, set loadout, resolve loadout) feeds `RoundCoordinator.start`, which passes the loadout to `BattleEngine.build_fighter`. The Vue UI gets a tree tab in the collection details.

**Tech Stack:** Python 3.14, FastAPI, SQLite, pytest; Vue 3, TypeScript, Pinia, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-12-ascension-ability-trees-design.md`. The policy redesign (`2026-10-12-ascension-autonomous-policy-design.md`) is a separate plan, built after this one.

## Global Constraints

- Work in `apps/ascension`. Run Python tests with `.venv_ascension\Scripts\python -m pytest` and web tests with `npx vitest run` inside `web`.
- 3 ability slots (`a1`, `a2`, `a3`) and 1 passive slot (`p1`). No duplicate nodes in the loadout. At least 1 ability.
- The passive root id is `<ascended id>_passive`. Root nodes cost nothing and are always learned.
- No new passive kinds and no new ability categories.
- A battle freezes its loadout when it starts. A loadout change during that Ascended's active battle is a 409 (`WrongPhase`).
- Database version 5 adds two tables and changes no data. No `loadouts` rows means the default loadout.
- Idempotency keys on every mutation. Errors reuse `NotFound`, `InvalidRequest`, `UpgradeNotReady`, `InsufficientEssence`, `WrongPhase`.
- Tree numbers are balance placeholders (?).
- Never commit the unrelated dirty files in the working tree (Ember web, sprites). Add only the files named in each task.
- Commit messages end with: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- The 8 existing Python tests that fail on sprite files are not part of this work.

---

## File Structure

| File | Change |
|---|---|
| `src/ascension/tree.py` | New. `NodeCost`, `TreeNode`, `AbilityTree`, `TreeError`, `passive_root_id`. Pure graph validation. |
| `src/ascension/models.py` | Add `Loadout`. |
| `src/ascension/catalog.py` | Parse `tree` into `AscendedSpec.tree`; load `tree.json`; validate costs and ids. |
| `src/ascension/engine.py` | `build_fighter(..., loadout=None)`. |
| `src/ascension/repository.py` | Schema v5, four tree methods, reset. |
| `src/ascension/trees.py` | New. `TreeService`. |
| `src/ascension/coordinator.py` | Optional `trees`; use the loadout in `start`. |
| `src/ascension/api.py`, `composition.py` | Routes, catalog summary, wiring. |
| `ascended/<id>/tree.json` | New, 7 files (guardian, striker, scout, sentinel, channeler, bruiser, forbidden). |
| `web/src/...` | Types, client, store, `TreeTab.vue`, `CollectionPanel.vue`, tests. |
| `tests/ascension/...` | `test_tree.py`, `test_tree_catalog.py`, `test_trees.py`, updates to `env.py`, `test_repository.py`, `test_engine.py`, `test_api.py`, `test_coordinator.py`. |

---

### Task 1: The tree graph (`tree.py`)

**Files:**
- Create: `src/ascension/tree.py`
- Test: `tests/ascension/test_tree.py`

**Interfaces:**
- Produces:
  - `TreeError(ValueError)`
  - `NodeCost(tier: str, amount: int)`
  - `TreeNode(id, kind, name, x, y, requires=(), unlock_level=1, cost=None, root=False, ability=None, passive=None)` with `to_public() -> dict`
  - `AbilityTree(nodes)` with `.nodes`, `.node(id) -> TreeNode | None`, `.roots`
  - `passive_root_id(ascended_id) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/ascension/test_tree.py`:

```python
import pytest

from src.ascension.models import AbilitySpec, PassiveSpec
from src.ascension.tree import AbilityTree, NodeCost, TreeError, TreeNode, passive_root_id


def ability(node_id, requires=(), root=False, x=0.0, y=0.0, level=1):
    spec = AbilitySpec(node_id, node_id.title(), level, "ATTACK", 100.0, 1)
    return TreeNode(node_id, "ability", spec.name, x, y, tuple(requires), level,
                    None if root else NodeCost("common", 1), root, ability=spec)


def test_a_valid_tree_is_found_by_node_id():
    tree = AbilityTree([ability("r", root=True), ability("a", ["r"], x=1), ability("b", ["a"], x=2)])
    assert tree.node("b").requires == ("a",) and tree.node("zzz") is None
    assert [n.id for n in tree.roots] == ["r"]


def test_node_ids_must_be_unique():
    with pytest.raises(TreeError, match="unique"):
        AbilityTree([ability("r", root=True), ability("r", x=1)])


def test_a_requirement_must_exist():
    with pytest.raises(TreeError, match="unknown node"):
        AbilityTree([ability("r", root=True), ability("a", ["ghost"], x=1)])


def test_a_cycle_or_an_unreachable_node_is_rejected():
    with pytest.raises(TreeError, match="unreachable"):
        AbilityTree([ability("r", root=True), ability("a", ["b"], x=1), ability("b", ["a"], x=2)])
    with pytest.raises(TreeError, match="unreachable"):
        AbilityTree([ability("r", root=True), ability("a", [], x=1)])


def test_roots_have_no_requirements_and_a_tree_needs_a_root():
    with pytest.raises(TreeError, match="root"):
        AbilityTree([ability("a", x=1)])
    with pytest.raises(TreeError, match="root"):
        AbilityTree([ability("r", root=True), ability("r2", ["r"], root=True, x=1)])


def test_two_nodes_cannot_share_a_point():
    with pytest.raises(TreeError, match="same point"):
        AbilityTree([ability("r", root=True), ability("a", ["r"])])


def test_the_public_form_hides_nothing_secret_and_carries_the_numbers():
    node = ability("a", ["r"], x=5, y=6, level=12)
    shown = node.to_public()
    assert shown["id"] == "a" and shown["kind"] == "ability" and shown["requires"] == ["r"]
    assert shown["unlock_level"] == 12 and shown["cost"] == {"tier": "common", "amount": 1}
    assert (shown["x"], shown["y"], shown["category"], shown["percentage"], shown["cooldown"]) == (5, 6, "ATTACK", 100.0, 1)
    passive = TreeNode("p", "passive", "P", 1, 1, passive=PassiveSpec("none", {}))
    assert passive.to_public()["passive"] == {"kind": "none", "params": {}} and passive.to_public()["cost"] is None


def test_the_passive_root_id_follows_the_ascended():
    assert passive_root_id("guardian") == "guardian_passive"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_tree.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ascension.tree'`

- [ ] **Step 3: Write the implementation**

Create `src/ascension/tree.py`:

```python
"""Ability trees: the nodes one Ascended can learn, as a validated graph.

A node is an ability or a passive. Roots are the Ascended's starting kit: always
learned, no cost. Every other node needs its prerequisites, a level and essence.
Pure: no database, files or HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.ascension.models import AbilitySpec, PassiveSpec


class TreeError(ValueError):
    """The tree is not a valid graph."""


def passive_root_id(ascended_id: str) -> str:
    """The id of the root node that holds an Ascended's own passive."""
    return f"{ascended_id}_passive"


@dataclass(frozen=True)
class NodeCost:
    tier: str  # the essence tier spent
    amount: int


@dataclass(frozen=True)
class TreeNode:
    id: str
    kind: str  # "ability" or "passive"
    name: str
    x: float
    y: float
    requires: tuple[str, ...] = ()
    unlock_level: int = 1
    cost: NodeCost | None = None  # None for roots
    root: bool = False
    ability: AbilitySpec | None = None
    passive: PassiveSpec | None = None

    def to_public(self) -> dict[str, Any]:
        """The node as the API shows it (public data, no player state)."""
        shown: dict[str, Any] = {
            "id": self.id, "kind": self.kind, "name": self.name, "x": self.x, "y": self.y,
            "requires": list(self.requires), "unlock_level": self.unlock_level, "root": self.root,
            "cost": {"tier": self.cost.tier, "amount": self.cost.amount} if self.cost else None,
        }
        if self.ability is not None:
            a = self.ability
            shown.update(category=a.category, percentage=a.percentage, cooldown=a.cooldown, stat=a.stat, duration=a.duration)
        if self.passive is not None:
            shown["passive"] = self.passive.to_dict()
        return shown


class AbilityTree:
    def __init__(self, nodes: Iterable[TreeNode]) -> None:
        self.nodes: tuple[TreeNode, ...] = tuple(nodes)
        self._by_id = {n.id: n for n in self.nodes}
        self._validate()

    def node(self, node_id: str) -> TreeNode | None:
        return self._by_id.get(node_id)

    @property
    def roots(self) -> tuple[TreeNode, ...]:
        return tuple(n for n in self.nodes if n.root)

    def _validate(self) -> None:
        if len(self._by_id) != len(self.nodes):
            raise TreeError("node ids must be unique")
        if not self.roots:
            raise TreeError("a tree needs at least one root node")
        points: set[tuple[float, float]] = set()
        for node in self.nodes:
            for required in node.requires:
                if required not in self._by_id:
                    raise TreeError(f"node {node.id!r} requires unknown node {required!r}")
            if node.root and node.requires:
                raise TreeError(f"root node {node.id!r} cannot have requirements")
            if not node.root and not node.requires:
                raise TreeError(f"node {node.id!r} is unreachable: it has no requirements and is not a root")
            if (node.x, node.y) in points:
                raise TreeError(f"node {node.id!r} sits on the same point as another node")
            points.add((node.x, node.y))
        reached = {n.id for n in self.roots}
        grew = True
        while grew:
            grew = False
            for node in self.nodes:
                if node.id not in reached and all(r in reached for r in node.requires):
                    reached.add(node.id)
                    grew = True
        stranded = [n.id for n in self.nodes if n.id not in reached]
        if stranded:
            raise TreeError(f"nodes unreachable from a root (or in a cycle): {', '.join(stranded)}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_tree.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/tree.py apps/ascension/tests/ascension/test_tree.py
git commit -m "feat(ascension): ability tree graph with validation"
```

---

### Task 2: Load trees in the catalog

**Files:**
- Modify: `src/ascension/models.py` (add `Loadout` after `PassiveSpec`)
- Modify: `src/ascension/catalog.py`
- Modify: `tests/ascension/env.py` (`load_raw`)
- Test: `tests/ascension/test_tree_catalog.py`

**Interfaces:**
- Consumes: Task 1 `AbilityTree`, `TreeNode`, `NodeCost`, `TreeError`, `passive_root_id`.
- Produces:
  - `models.Loadout(abilities: tuple[AbilitySpec, ...], passive: PassiveSpec)`
  - `AscendedSpec.tree: AbilityTree` (default tree = the roots only, when no `tree` key)
  - The catalog loader merges `ascended/<id>/tree.json` into the Ascended dict under the key `tree`.
  - `Catalog.default_loadout(ascended_id) -> Loadout`

- [ ] **Step 1: Write the failing test**

Create `tests/ascension/test_tree_catalog.py`:

```python
import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.tree import passive_root_id
from tests.ascension.env import load_raw


@pytest.fixture(scope="module")
def raw():
    return load_raw()


def build(raw, mutate):
    data = copy.deepcopy(raw)
    mutate(next(s for s in data["ascendeds"] if s["id"] == "guardian"))
    return Catalog(data)


def tree_of(**extra):
    roots = [
        {"id": "guardian_bulwark", "root": True, "x": 0, "y": 0},
        {"id": "guardian_rally", "root": True, "x": 0, "y": 100},
        {"id": "guardian_heavy_blow", "root": True, "x": 0, "y": 200},
        {"id": passive_root_id("guardian"), "root": True, "x": 100, "y": 100},
    ]
    return {"nodes": roots + extra.get("nodes", [])}


ABILITY = {"id": "guardian_iron_wall", "kind": "ability", "name": "Iron Wall", "category": "DEFENSE", "percentage": 260,
           "cooldown": 3, "unlock_level": 12, "requires": ["guardian_bulwark"],
           "cost": {"tier": "common", "amount": 3}, "x": 200, "y": 0}
PASSIVE = {"id": "guardian_stoneskin", "kind": "passive", "name": "Stoneskin", "unlock_level": 15,
           "passive": {"kind": "defense_rating_bonus", "params": {"power_fraction": 0.4}},
           "requires": ["guardian_iron_wall"], "cost": {"tier": "rare", "amount": 3}, "x": 300, "y": 0}


def test_an_ascended_without_a_tree_has_only_its_roots(raw):
    catalog = build(raw, lambda s: s.pop("tree", None))
    tree = catalog.ascended("guardian").tree
    assert [n.id for n in tree.nodes] == ["guardian_bulwark", "guardian_rally", "guardian_heavy_blow", "guardian_passive"]
    assert all(n.root and n.cost is None for n in tree.nodes)
    assert tree.node("guardian_passive").passive == catalog.ascended("guardian").passive
    assert tree.node("guardian_rally").ability == catalog.ascended("guardian").abilities[1]


def test_a_tree_adds_abilities_and_passives(raw):
    catalog = build(raw, lambda s: s.update(tree=tree_of(nodes=[ABILITY, PASSIVE])))
    tree = catalog.ascended("guardian").tree
    wall, skin = tree.node("guardian_iron_wall"), tree.node("guardian_stoneskin")
    assert (wall.ability.category, wall.ability.percentage, wall.unlock_level, wall.cost.tier, wall.cost.amount) == ("DEFENSE", 260.0, 12, "common", 3)
    assert (skin.passive.kind, skin.unlock_level, skin.requires) == ("defense_rating_bonus", 15, ("guardian_iron_wall",))


def test_the_default_loadout_is_the_catalog_kit(raw):
    catalog = build(raw, lambda s: None)
    kit = catalog.default_loadout("guardian")
    assert [a.id for a in kit.abilities] == ["guardian_bulwark", "guardian_rally", "guardian_heavy_blow"]
    assert kit.passive.kind == "defense_extension"


@pytest.mark.parametrize("mutate,message", [
    (lambda s: s.update(tree={"nodes": tree_of()["nodes"][:3]}), "every root"),
    (lambda s: s.update(tree={"nodes": tree_of()["nodes"] + [{"id": "ghost", "root": True, "x": 9, "y": 9}]}), "a root must be one of"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "requires": ["nope"]}])), "unknown node"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "category": "HEAL"}])), "category must be"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "cost": {"tier": "forbidden", "amount": 1}}])), "regular tier"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "cost": {"tier": "common", "amount": 0}}])), "amount"),
    (lambda s: s.update(tree=tree_of(nodes=[{k: v for k, v in ABILITY.items() if k != "cost"}])), "needs a cost"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "x": "far"}])), "x and y"),
    (lambda s: s.update(tree=tree_of(nodes=[{**PASSIVE, "passive": {"kind": "teleport", "params": {}}}, ABILITY])), "unknown passive"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "kind": "spell"}])), "kind must be"),
    (lambda s: s.update(tree=tree_of(nodes=[ABILITY, {**ABILITY, "x": 250}])), "unique"),
    (lambda s: s.update(tree=tree_of(nodes=[{**ABILITY, "requires": []}])), "unreachable"),
    (lambda s: s.update(tree={"nodes": tree_of()["nodes"], "extra": 1}), "only nodes"),
])
def test_a_broken_tree_is_a_catalog_error(raw, mutate, message):
    with pytest.raises(CatalogError, match=message):
        build(raw, mutate)


def test_node_ids_are_unique_across_all_ascended(raw):
    data = copy.deepcopy(raw)
    next(s for s in data["ascendeds"] if s["id"] == "guardian")["tree"] = tree_of(nodes=[ABILITY])
    scout = next(s for s in data["ascendeds"] if s["id"] == "scout")
    scout["tree"] = {"nodes": [
        {"id": "scout_quickstep", "root": True, "x": 0, "y": 0}, {"id": "scout_swift_slash", "root": True, "x": 0, "y": 100},
        {"id": "scout_evade", "root": True, "x": 0, "y": 200}, {"id": "scout_passive", "root": True, "x": 100, "y": 100},
        {**ABILITY, "requires": ["scout_evade"]}]}
    with pytest.raises(CatalogError, match="unique across all Ascended"):
        Catalog(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_tree_catalog.py -q`
Expected: FAIL (`AscendedSpec` has no `tree`).

- [ ] **Step 3: Write the implementation**

In `src/ascension/models.py`, after `PassiveSpec`, add:

```python
@dataclass(frozen=True)
class Loadout:
    """The abilities and passive an Ascended fights with: its equipped tree nodes."""

    abilities: tuple[AbilitySpec, ...]
    passive: PassiveSpec
```

In `src/ascension/catalog.py`:

1. Imports: change `from src.ascension.models import ABILITY_CATEGORIES, CATEGORIES, AbilitySpec, PassiveSpec` to also import `Loadout`, and add
```python
from src.ascension.passives import PassiveFactory
from src.ascension.tree import AbilityTree, NodeCost, TreeError, TreeNode, passive_root_id
```
2. Constants: `TREE_FILE = "tree.json"` next to `ASCENDED_FILE`.
3. `AscendedSpec`: add field `tree: AbilityTree | None = None  # always set by _ascended_spec: the roots only when the Ascended has no tree.json` after `art`.
4. Add these helpers above `_ascended_spec`:

```python
def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tree(raw: Any, spec_id: str, abilities: tuple[AbilitySpec, ...], passive: PassiveSpec) -> AbilityTree:
    """The Ascended's tree: its roots (the catalog kit) plus any nodes in tree.json."""
    where = f"ascended {spec_id!r} tree"
    root_abilities = {a.id: a for a in abilities}
    passive_id = passive_root_id(spec_id)
    if raw is None:
        raw = {"nodes": [{"id": i, "root": True, "x": 40, "y": 60 + 110 * n}
                         for n, i in enumerate([*root_abilities, passive_id])]}
    if not isinstance(raw, Mapping) or set(raw) - {"nodes"} or not isinstance(raw.get("nodes", []), list):
        raise CatalogError(f"{where}: only nodes is allowed, as a list")
    nodes: list[TreeNode] = []
    listed_roots: list[str] = []
    for item in raw.get("nodes", []):
        node_id = item.get("id") if isinstance(item, Mapping) else None
        if not isinstance(node_id, str):
            raise CatalogError(f"{where}: every node needs an id")
        at = f"{where} node {node_id!r}"
        if not _number(item.get("x")) or not _number(item.get("y")):
            raise CatalogError(f"{at}: x and y must be numbers")
        x, y = item["x"], item["y"]
        if item.get("root"):
            listed_roots.append(node_id)
            if node_id == passive_id:
                nodes.append(TreeNode(node_id, "passive", passive.kind.replace("_", " ").title(), x, y, root=True, passive=passive))
            elif node_id in root_abilities:
                a = root_abilities[node_id]
                nodes.append(TreeNode(node_id, "ability", a.name, x, y, unlock_level=a.unlock_level, root=True, ability=a))
            else:
                raise CatalogError(f"{at}: a root must be one of the catalog abilities or {passive_id!r}")
            continue
        requires = item.get("requires", [])
        if not isinstance(requires, list) or any(not isinstance(r, str) for r in requires):
            raise CatalogError(f"{at}: requires must be a list of node ids")
        cost_raw = item.get("cost")
        if not isinstance(cost_raw, Mapping):
            raise CatalogError(f"{at}: needs a cost with a tier and an amount")
        amount = cost_raw.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1 or not isinstance(cost_raw.get("tier"), str):
            raise CatalogError(f"{at}: cost needs a tier and a whole amount of at least 1")
        cost = NodeCost(cost_raw["tier"], amount)
        kind = item.get("kind")
        if kind == "ability":
            a = _ability(item, spec_id)
            nodes.append(TreeNode(node_id, "ability", a.name, x, y, tuple(requires), a.unlock_level, cost, ability=a))
        elif kind == "passive":
            body = item.get("passive")
            level = item.get("unlock_level")
            if not isinstance(body, Mapping) or "kind" not in body or isinstance(level, bool) or not isinstance(level, int) or level < 1:
                raise CatalogError(f"{at}: a passive node needs a passive (kind, params) and a whole unlock_level of at least 1")
            spec = PassiveSpec(body["kind"], dict(body.get("params", {})))
            try:
                PassiveFactory().create(spec)
            except (ValueError, TypeError) as error:
                raise CatalogError(f"{at}: unknown passive or bad params ({error})") from error
            nodes.append(TreeNode(node_id, "passive", str(item.get("name", node_id)), x, y, tuple(requires), level, cost, passive=spec))
        else:
            raise CatalogError(f"{at}: kind must be ability or passive")
    if raw.get("nodes") and sorted(listed_roots) != sorted([*root_abilities, passive_id]):
        raise CatalogError(f"{where}: must list every root: {', '.join([*root_abilities, passive_id])}")
    try:
        return AbilityTree(nodes)
    except TreeError as error:
        raise CatalogError(f"{where}: {error}") from error
```

Expected failure messages used by the tests: `"every root"`, `"unknown node"` (from `TreeError`), `"category must be"` (from `_ability`), `"regular tier"` (Step 3.7), `"amount"`, `"needs a cost"`, `"x and y"`, `"unknown passive"`, `"kind must be"`, `"unique"` (TreeError "node ids must be unique" for the same-tree duplicate), `"unreachable"`, `"only nodes"`.

5. In `_ascended_spec`, build the tree right before the `return AscendedSpec(...)` (after the existing level check on the abilities, so that error still comes first). Make the call pass `tree=_tree(raw.get("tree"), sid, abilities, passive_spec)` where `passive_spec = PassiveSpec(_require(passive, "kind", f"{where} passive"), dict(passive.get("params", {})))` (reuse it for the existing `passive=` argument).
6. In `Catalog._build`, replace the ability-id uniqueness block with:

```python
        # Action keys and cooldowns key on the ability id, so it is unique across Ascended, and tree nodes share the id space.
        node_ids = [n.id for s in specs for n in s.tree.nodes]
        ability_ids = [n.id for s in specs for n in s.tree.nodes if n.kind == "ability"]
        if len(set(ability_ids)) != len(ability_ids):
            raise CatalogError("ability ids must be unique across all Ascended")
        if len(set(node_ids)) != len(node_ids):
            raise CatalogError("tree node ids must be unique across all Ascended")
```

   The test above expects the message `unique across all Ascended`; both messages contain it.
7. In `Catalog._validate`, extend the per-Ascended loop (already there for `base_price`/`start_tier`) with:

```python
            for node in spec.tree.nodes:
                if node.cost is not None and node.cost.tier not in regular_tier_ids:
                    raise CatalogError(f"ascended {spec.id!r} tree node {node.id!r}: cost tier must be a regular tier")
```
8. Add to `Catalog`:

```python
    def default_loadout(self, ascended_id: str) -> Loadout:
        """The starting kit: the catalog abilities in order and the catalog passive."""
        spec = self.ascended(ascended_id)
        return Loadout(spec.abilities, spec.passive)
```
9. In `_load_ascendeds`, after `ascended["sprites"] = ...`, add:

```python
            tree_file = folder / TREE_FILE
            if tree_file.is_file():
                try:
                    ascended["tree"] = json.loads(tree_file.read_text(encoding="utf-8"))
                except (OSError, ValueError) as error:
                    raise CatalogError(f"cannot load tree file {folder.name}/{TREE_FILE}: {error}") from error
```

In `tests/ascension/env.py`, change `load_raw` so each Ascended dict also gets its `tree.json`:

```python
def load_raw() -> dict:
    """The shipped catalog as the raw dict Catalog() takes: the rules plus the Ascended (and their trees), by folder name."""
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    raw["ascendeds"] = []
    for f in sorted(ASCENDEDS_PATH.glob("*/catalog.json"), key=lambda f: f.parent.name):
        ascended = json.loads(f.read_text(encoding="utf-8"))
        tree_file = f.parent / "tree.json"
        if tree_file.is_file():
            ascended["tree"] = json.loads(tree_file.read_text(encoding="utf-8"))
        raw["ascendeds"].append(ascended)
    return raw
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_tree_catalog.py tests/ascension/test_catalog.py tests/ascension/test_catalog_hardening.py -q`
Expected: new tests pass; the two sprite tests in `test_catalog.py` may still fail as before (not part of this work).

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/models.py apps/ascension/src/ascension/catalog.py apps/ascension/tests/ascension/env.py apps/ascension/tests/ascension/test_tree_catalog.py
git commit -m "feat(ascension): load and validate each Ascended's tree"
```

---

### Task 3: Fighters built from a loadout

**Files:**
- Modify: `src/ascension/engine.py` (`build_fighter`, imports)
- Test: `tests/ascension/test_engine.py`

**Interfaces:**
- Consumes: `models.Loadout`.
- Produces: `BattleEngine.build_fighter(side, ascended_id, tier_id, level, loadout: Loadout | None = None) -> Fighter`. `None` keeps today's kit. Abilities above `level` are still dropped.

- [ ] **Step 1: Write the failing test**

Append to `tests/ascension/test_engine.py` (it already defines `engine` and imports `PLAYER`; add `AbilitySpec, Loadout, PassiveSpec` to its `from src.ascension.models import ...` line):

```python
def test_a_loadout_replaces_the_default_kit_and_still_obeys_levels():
    attack = lambda n, level: AbilitySpec(f"x_{n}", f"X{n}", level, "ATTACK", 100.0 + n, 1)  # noqa: E731
    loadout = Loadout((attack(1, 1), attack(2, 10), attack(3, 40)), PassiveSpec("battle_start_speed", {"power_fraction": 0.5}))
    fighter = engine.build_fighter(PLAYER, "guardian", "common", 20, loadout)
    assert [a.id for a in fighter.abilities] == ["x_1", "x_2"]  # level 40 stays locked
    assert all(a.category == "ATTACK" for a in fighter.abilities)
    assert fighter.passive.kind == "battle_start_speed"


def test_without_a_loadout_the_default_kit_is_used():
    fighter = engine.build_fighter(PLAYER, "guardian", "common", 30)
    assert [a.id for a in fighter.abilities] == ["guardian_bulwark", "guardian_rally", "guardian_heavy_blow"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_engine.py -q -k loadout`
Expected: FAIL (`build_fighter() takes 5 positional arguments`).

- [ ] **Step 3: Write the implementation**

In `src/ascension/engine.py` add `Loadout` to the `models` import and replace `build_fighter`:

```python
    def build_fighter(self, side: str, ascended_id: str, tier_id: str, level: int, loadout: Loadout | None = None) -> Fighter:
        kit = loadout or self._catalog.default_loadout(ascended_id)
        stat = lambda name: self._catalog.stat_value(ascended_id, level, tier_id, name)  # noqa: E731
        return Fighter(
            side=side, ascended_id=ascended_id, tier_id=tier_id, level=level,
            max_hp=stat("hp"), power=stat("power"), speed=stat("speed"),
            abilities=tuple(a for a in kit.abilities if a.unlock_level <= level), passive=kit.passive,
        )
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_engine.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/engine.py apps/ascension/tests/ascension/test_engine.py
git commit -m "feat(ascension): build fighters from a loadout"
```

---

### Task 4: Storage for learned nodes and loadouts

**Files:**
- Modify: `src/ascension/repository.py`
- Test: `tests/ascension/test_repository.py`

**Interfaces:**
- Produces on `AscendedTransaction` (Protocol and `_SqliteTransaction`):
  - `learned_nodes(owner, ascended_id) -> set[str]`
  - `add_learned_node(owner, ascended_id, node_id) -> None` (ignores a repeat)
  - `get_loadout(owner, ascended_id) -> dict[str, str]` (slot to node id; empty when never saved)
  - `put_loadout(owner, ascended_id, slots: dict[str, str]) -> None` (replaces every row)
- `SCHEMA_VERSION = 5`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ascension/test_repository.py`:

```python
def test_learned_nodes_and_loadouts_round_trip_and_reset(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.create_player("ann", 1.0)
            await tx.add_learned_node("ann", "guardian", "g_wall")
            await tx.add_learned_node("ann", "guardian", "g_wall")  # a repeat changes nothing
            await tx.add_learned_node("bob", "guardian", "g_other")
            await tx.put_loadout("ann", "guardian", {"a1": "g_wall", "p1": "g_skin"})
            await tx.put_loadout("ann", "guardian", {"a1": "g_a", "a2": "g_b"})  # replaces the old rows
            learned, loadout, none = (await tx.learned_nodes("ann", "guardian"), await tx.get_loadout("ann", "guardian"),
                                      await tx.get_loadout("ann", "scout"))
        async with repo.transaction() as tx:
            await tx.delete_player_data("ann")
            gone = (await tx.learned_nodes("ann", "guardian"), await tx.get_loadout("ann", "guardian"))
            bob = await tx.learned_nodes("bob", "guardian")
        await repo.close()
        return learned, loadout, none, gone, bob

    learned, loadout, none, gone, bob = run(scenario())
    assert learned == {"g_wall"} and loadout == {"a1": "g_a", "a2": "g_b"} and none == {}
    assert gone == (set(), {}) and bob == {"g_other"}


def test_a_version_4_database_gets_the_tree_tables(db_path):
    from src.ascension.repository import BASE_SCHEMA, SHOP_SCHEMA, STAR_MIGRATION, SCHEMA_VERSION

    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(f"{BASE_SCHEMA} {SHOP_SCHEMA} {STAR_MIGRATION} PRAGMA user_version = 4;")
    conn.execute("INSERT INTO ascendeds (owner, ascended_id, copies, level, xp, tier_id) VALUES ('ann', 'guardian', 2, 5, 0, 'rare')")
    conn.commit()
    conn.close()

    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            kept = await tx.get_ascended("ann", "guardian")
            await tx.add_learned_node("ann", "guardian", "g_wall")
            learned = await tx.learned_nodes("ann", "guardian")
        await repo.close()
        return kept, learned

    kept, learned = run(scenario())
    check = sqlite3.connect(str(db_path))
    version = check.execute("PRAGMA user_version").fetchone()[0]
    check.close()
    assert (kept.tier_id, kept.copies) == ("rare", 2) and learned == {"g_wall"} and version == SCHEMA_VERSION == 5
```

The existing `test_a_version_3_database_keeps_each_ascended_tier_and_spends_the_absorbed_copies` and `test_a_version_2_database_is_upgraded_to_the_current_version` must keep passing: they build old schemas by hand, so the migration chain must create the tree tables for versions 2, 3 and 4.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_repository.py -q -k "learned or version_4"`
Expected: FAIL (`add_learned_node` missing).

- [ ] **Step 3: Write the implementation**

In `src/ascension/repository.py`:

1. `SCHEMA_VERSION = 5`.
2. After `STAR_MIGRATION` add:

```python
TREE_SCHEMA = """
CREATE TABLE learned_nodes (
    owner TEXT NOT NULL, ascended_id TEXT NOT NULL, node_id TEXT NOT NULL,
    PRIMARY KEY (owner, ascended_id, node_id));
CREATE TABLE loadouts (
    owner TEXT NOT NULL, ascended_id TEXT NOT NULL, slot TEXT NOT NULL, node_id TEXT NOT NULL,
    PRIMARY KEY (owner, ascended_id, slot));
"""
```
   and change `SCHEMA = BASE_SCHEMA + SHOP_SCHEMA + STAR_MIGRATION` to `SCHEMA = BASE_SCHEMA + SHOP_SCHEMA + STAR_MIGRATION + TREE_SCHEMA`.
3. Add the four methods to the `AscendedTransaction` Protocol:

```python
    async def learned_nodes(self, owner: str, ascended_id: str) -> set[str]: ...
    async def add_learned_node(self, owner: str, ascended_id: str, node_id: str) -> None: ...
    async def get_loadout(self, owner: str, ascended_id: str) -> dict[str, str]: ...
    async def put_loadout(self, owner: str, ascended_id: str, slots: dict[str, str]) -> None: ...
```
4. Implement them in `_SqliteTransaction` after `put_ascended`:

```python
    async def learned_nodes(self, owner: str, ascended_id: str) -> set[str]:
        rows = await self._run("SELECT node_id FROM learned_nodes WHERE owner = ? AND ascended_id = ?", (owner, ascended_id), "all")
        return {row["node_id"] for row in rows}

    async def add_learned_node(self, owner: str, ascended_id: str, node_id: str) -> None:
        await self._run("INSERT OR IGNORE INTO learned_nodes (owner, ascended_id, node_id) VALUES (?, ?, ?)",
                        (owner, ascended_id, node_id))

    async def get_loadout(self, owner: str, ascended_id: str) -> dict[str, str]:
        rows = await self._run("SELECT slot, node_id FROM loadouts WHERE owner = ? AND ascended_id = ?", (owner, ascended_id), "all")
        return {row["slot"]: row["node_id"] for row in rows}

    async def put_loadout(self, owner: str, ascended_id: str, slots: dict[str, str]) -> None:
        await self._run("DELETE FROM loadouts WHERE owner = ? AND ascended_id = ?", (owner, ascended_id))
        for slot, node_id in slots.items():
            await self._run("INSERT INTO loadouts (owner, ascended_id, slot, node_id) VALUES (?, ?, ?, ?)",
                            (owner, ascended_id, slot, node_id))
```
5. In `delete_player_data`, before `DELETE FROM ascendeds`, add:

```python
        await self._run("DELETE FROM learned_nodes WHERE owner = ?", (owner,))
        await self._run("DELETE FROM loadouts WHERE owner = ?", (owner,))
```
6. Replace the migration branch in `_open`:

```python
            elif version in (2, 3, 4):
                shop = SHOP_SCHEMA if version == 2 else ""
                stars = STAR_MIGRATION if version in (2, 3) else ""
                conn.executescript(f"BEGIN; {shop} {stars} {TREE_SCHEMA} PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_repository.py -q`
Expected: all pass (including the old migration tests).

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/repository.py apps/ascension/tests/ascension/test_repository.py
git commit -m "feat(ascension): store learned nodes and loadouts (database v5)"
```

---

### Task 5: `TreeService`

**Files:**
- Create: `src/ascension/trees.py`
- Modify: `tests/ascension/env.py` (add `self.trees`)
- Test: `tests/ascension/test_trees.py`

**Interfaces:**
- Consumes: Tasks 1 to 4 (`AbilityTree`, `Catalog.default_loadout`, `Loadout`, the four repository methods, `essence_counts`/`add_essence`, `get_ascended`, `active_battle`).
- Produces `TreeService(repository, writer, catalog)`:
  - `async view(owner, ascended_id) -> dict` with keys `ascended_id`, `level`, `essences`, `nodes` (each `to_public()` plus `state` in `learned|learnable|locked` and `reason` `str|None`), `loadout` (`{"a1","a2","a3","p1"}` to a node id or `None`).
  - `async learn(owner, key, ascended_id, node_id) -> dict` with keys `kind: "learn"`, `ascended_id`, `node_id`, `essence_tier`, `essence_spent`.
  - `async set_loadout(owner, key, ascended_id, abilities: list[str], passive: str | None) -> dict` with keys `ascended_id`, `abilities`, `passive`.
  - `async loadout_in(tx, owner, ascended_id) -> Loadout` (used by the coordinator, inside its own transaction).
- Constants: `ABILITY_SLOTS = ("a1", "a2", "a3")`, `PASSIVE_SLOT = "p1"`.

**Rules (copy into code):** learning needs the Ascended owned, node known and not root or already learned, `level >= unlock_level`, every prerequisite learned (roots count as learned), and `essence >= cost.amount` of `cost.tier`. A loadout needs 1 to 3 distinct learned ability nodes and at most 1 learned passive node, and the Ascended must not be in the active battle.

- [ ] **Step 1: Write the failing tests**

Add to `tests/ascension/env.py`: import `from src.ascension.trees import TreeService` and in `Env.__init__` after `self.upgrades = ...`:

```python
        self.trees = TreeService(self.repo, self.writer, CATALOG)
```
Also change `coordinator()` to pass `trees=self.trees` as the last argument of `RoundCoordinator(...)` (Task 6 adds the parameter; do that edit in Task 6, not here).

Create `tests/ascension/test_trees.py`. The tests build their own catalog so they do not depend on shipped content:

```python
import copy

import pytest

from src.ascension.catalog import Catalog
from src.ascension.errors import InsufficientEssence, InvalidRequest, NotFound, UpgradeNotReady, WrongPhase
from src.ascension.records import AscendedRecord
from src.ascension.tree import passive_root_id
from src.ascension.trees import TreeService
from tests.ascension.env import Env, load_raw, run
from tests.ascension.helpers import battle_record

TREE = {"nodes": [
    {"id": "guardian_bulwark", "root": True, "x": 0, "y": 0}, {"id": "guardian_rally", "root": True, "x": 0, "y": 100},
    {"id": "guardian_heavy_blow", "root": True, "x": 0, "y": 200}, {"id": passive_root_id("guardian"), "root": True, "x": 100, "y": 100},
    {"id": "guardian_iron_wall", "kind": "ability", "name": "Iron Wall", "category": "DEFENSE", "percentage": 260, "cooldown": 3,
     "unlock_level": 12, "requires": ["guardian_bulwark"], "cost": {"tier": "common", "amount": 3}, "x": 200, "y": 0},
    {"id": "guardian_stoneskin", "kind": "passive", "name": "Stoneskin", "unlock_level": 15,
     "passive": {"kind": "defense_rating_bonus", "params": {"power_fraction": 0.4}},
     "requires": ["guardian_iron_wall"], "cost": {"tier": "rare", "amount": 2}, "x": 300, "y": 0},
    {"id": "guardian_shield_slam", "kind": "ability", "name": "Shield Slam", "category": "ATTACK", "percentage": 190, "cooldown": 2,
     "unlock_level": 5, "requires": ["guardian_heavy_blow"], "cost": {"tier": "common", "amount": 1}, "x": 200, "y": 200},
]}


def make(tmp_path):
    raw = copy.deepcopy(load_raw())
    next(s for s in raw["ascendeds"] if s["id"] == "guardian")["tree"] = TREE
    env = Env(tmp_path / "t.sqlite3")
    env.catalog = Catalog(raw)
    env.trees = TreeService(env.repo, env.writer, env.catalog)
    return env


async def owned(env, level=20):
    await env.start_player()
    await env.give(guardian=AscendedRecord("ann", "guardian", 0, level, 0, tier_id="common"))


def states(view):
    return {n["id"]: (n["state"], n["reason"]) for n in view["nodes"]}


def test_the_view_shows_roots_learned_and_why_other_nodes_are_locked(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env, level=3)
        view = await env.trees.view("ann", "guardian")
        await env.close()
        return view

    view = run(scenario())
    s = states(view)
    assert s["guardian_bulwark"] == ("learned", None) and s[passive_root_id("guardian")][0] == "learned"
    assert s["guardian_iron_wall"] == ("locked", "needs level 12")
    assert s["guardian_stoneskin"] == ("locked", "needs Iron Wall")
    assert s["guardian_shield_slam"] == ("locked", "needs level 5")
    assert view["loadout"] == {"a1": "guardian_bulwark", "a2": "guardian_rally", "a3": "guardian_heavy_blow",
                               "p1": passive_root_id("guardian")}
    assert view["level"] == 3 and view["essences"] == {}


def test_a_node_without_the_essence_says_so_and_then_becomes_learnable(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        before = states(await env.trees.view("ann", "guardian"))
        await env.give_essence("common", 3)
        after = states(await env.trees.view("ann", "guardian"))
        await env.close()
        return before, after

    before, after = run(scenario())
    assert before["guardian_iron_wall"] == ("locked", "needs 3 common essence")
    assert after["guardian_iron_wall"] == ("learnable", None)


def test_learning_spends_the_essence_once_and_unlocks_the_next_node(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        await env.give_essence("common", 4)
        first = await env.trees.learn("ann", "k1", "guardian", "guardian_iron_wall")
        again = await env.trees.learn("ann", "k1", "guardian", "guardian_iron_wall")  # same key: replayed
        view = await env.trees.view("ann", "guardian")
        async with env.repo.transaction() as tx:
            essences = await tx.essence_counts("ann")
        await env.close()
        return first, again, view, essences

    first, again, view, essences = run(scenario())
    assert first == again and (first["node_id"], first["essence_tier"], first["essence_spent"]) == ("guardian_iron_wall", "common", 3)
    assert essences == {"common": 1} and states(view)["guardian_iron_wall"][0] == "learned"
    assert states(view)["guardian_stoneskin"] == ("locked", "needs 2 rare essence")


@pytest.mark.parametrize("node,level,essence,error", [
    ("guardian_iron_wall", 5, 9, UpgradeNotReady),   # level
    ("guardian_stoneskin", 20, 9, UpgradeNotReady),  # prerequisite
    ("guardian_iron_wall", 20, 2, InsufficientEssence),
    ("guardian_bulwark", 20, 9, UpgradeNotReady),    # a root is already learned
    ("nope", 20, 9, InvalidRequest),
])
def test_learning_refusals_change_nothing(tmp_path, node, level, essence, error):
    async def scenario():
        env = make(tmp_path)
        await owned(env, level=level)
        await env.give_essence("common", essence)
        with pytest.raises(error):
            await env.trees.learn("ann", "k1", "guardian", node)
        async with env.repo.transaction() as tx:
            return await tx.learned_nodes("ann", "guardian"), await tx.essence_counts("ann")

    learned, essences = run(scenario())
    assert learned == set() and essences == {"common": essence}


def test_you_cannot_learn_for_an_ascended_you_do_not_own(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        for call in (lambda: env.trees.learn("ann", "k1", "scout", "scout_quickstep"), lambda: env.trees.view("ann", "scout"),
                     lambda: env.trees.learn("ann", "k2", "dragon", "x")):
            with pytest.raises(NotFound):
                await call()
        await env.close()

    run(scenario())


def test_a_loadout_swaps_in_learned_nodes_and_is_what_a_battle_resolves(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        await env.give_essence("common", 9)
        await env.give_essence("rare", 9)
        for key, node in (("a", "guardian_iron_wall"), ("b", "guardian_stoneskin"), ("c", "guardian_shield_slam")):
            await env.trees.learn("ann", key, "guardian", node)
        saved = await env.trees.set_loadout("ann", "l1", "guardian",
                                            ["guardian_shield_slam", "guardian_iron_wall", "guardian_heavy_blow"], "guardian_stoneskin")
        view = await env.trees.view("ann", "guardian")
        async with env.repo.transaction() as tx:
            kit = await env.trees.loadout_in(tx, "ann", "guardian")
        await env.close()
        return saved, view, kit

    saved, view, kit = run(scenario())
    assert saved["abilities"] == ["guardian_shield_slam", "guardian_iron_wall", "guardian_heavy_blow"] and saved["passive"] == "guardian_stoneskin"
    assert view["loadout"] == {"a1": "guardian_shield_slam", "a2": "guardian_iron_wall", "a3": "guardian_heavy_blow", "p1": "guardian_stoneskin"}
    assert [a.id for a in kit.abilities] == ["guardian_shield_slam", "guardian_iron_wall", "guardian_heavy_blow"]
    assert kit.passive.kind == "defense_rating_bonus"


def test_a_loadout_may_be_all_attack_and_have_no_passive(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        await env.give_essence("common", 5)
        await env.trees.learn("ann", "a", "guardian", "guardian_shield_slam")
        await env.trees.set_loadout("ann", "l1", "guardian", ["guardian_shield_slam", "guardian_heavy_blow"], None)
        async with env.repo.transaction() as tx:
            kit = await env.trees.loadout_in(tx, "ann", "guardian")
        await env.close()
        return kit

    kit = run(scenario())
    assert [a.category for a in kit.abilities] == ["ATTACK", "ATTACK"] and kit.passive.kind == "none"


@pytest.mark.parametrize("abilities,passive", [
    ([], None),                                                                              # at least one
    (["guardian_bulwark"] * 2, None),                                                         # duplicates
    (["guardian_bulwark", "guardian_rally", "guardian_heavy_blow", "guardian_shield_slam"], None),  # too many
    (["guardian_iron_wall"], None),                                                           # not learned
    (["guardian_passive"], None),                                                             # a passive in an ability slot
    (["guardian_bulwark"], "guardian_rally"),                                                 # an ability in the passive slot
    (["guardian_bulwark"], "guardian_stoneskin"),                                             # passive not learned
    (["ghost"], None),
])
def test_a_bad_loadout_is_refused_and_changes_nothing(tmp_path, abilities, passive):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        with pytest.raises(InvalidRequest):
            await env.trees.set_loadout("ann", "l1", "guardian", abilities, passive)
        async with env.repo.transaction() as tx:
            return await tx.get_loadout("ann", "guardian")

    assert run(scenario()) == {}


def test_the_loadout_cannot_change_while_that_ascended_fights(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await owned(env)
        async with env.repo.transaction() as tx:
            await tx.add_battle(battle_record())  # an active battle for ann whose fighter is the guardian
        with pytest.raises(WrongPhase):
            await env.trees.set_loadout("ann", "l1", "guardian", ["guardian_bulwark"], None)
        await env.close()

    run(scenario())
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_trees.py -q`
Expected: FAIL (`ModuleNotFoundError: src.ascension.trees`).

- [ ] **Step 3: Write the implementation**

Create `src/ascension/trees.py`:

```python
"""Ability trees in play: what an Ascended can learn, what it learned, what it equips."""

from __future__ import annotations

from typing import Any

from src.ascension.catalog import Catalog
from src.ascension.errors import InsufficientEssence, InvalidRequest, NotFound, UpgradeNotReady, WrongPhase
from src.ascension.idempotency import IdempotentWriter
from src.ascension.models import Loadout, PassiveSpec
from src.ascension.records import AscendedRecord
from src.ascension.repository import AscendedRepository, AscendedTransaction
from src.ascension.tree import TreeNode, passive_root_id

ABILITY_SLOTS = ("a1", "a2", "a3")
PASSIVE_SLOT = "p1"
NO_PASSIVE = PassiveSpec("none", {})


class TreeService:
    def __init__(self, repository: AscendedRepository, writer: IdempotentWriter, catalog: Catalog) -> None:
        self._repository, self._writer, self._catalog = repository, writer, catalog

    # -- helpers -------------------------------------------------------------------

    async def _owned(self, tx: AscendedTransaction, owner: str, ascended_id: str) -> AscendedRecord:
        record = await tx.get_ascended(owner, ascended_id) if self._catalog.has_ascended(ascended_id) else None
        if record is None:
            raise NotFound("you do not own that Ascended")
        return record

    def _learned(self, ascended_id: str, stored: set[str]) -> set[str]:
        return {n.id for n in self._catalog.ascended(ascended_id).tree.roots} | stored

    def _default_slots(self, ascended_id: str) -> dict[str, str]:
        spec = self._catalog.ascended(ascended_id)
        slots = {slot: a.id for slot, a in zip(ABILITY_SLOTS, spec.abilities)}
        slots[PASSIVE_SLOT] = passive_root_id(ascended_id)
        return slots

    def _slots(self, ascended_id: str, stored: dict[str, str]) -> dict[str, str]:
        return stored if stored else self._default_slots(ascended_id)

    def _state(self, node: TreeNode, record: AscendedRecord, learned: set[str], essences: dict[str, int], tree) -> tuple[str, str | None]:
        if node.id in learned:
            return "learned", None
        for required in node.requires:
            if required not in learned:
                return "locked", f"needs {tree.node(required).name}"
        if record.level < node.unlock_level:
            return "locked", f"needs level {node.unlock_level}"
        have = essences.get(node.cost.tier, 0)
        if have < node.cost.amount:
            return "locked", f"needs {node.cost.amount} {node.cost.tier} essence"
        return "learnable", None

    @staticmethod
    async def _reject_if_fighting(tx: AscendedTransaction, owner: str, ascended_id: str) -> None:
        battle = await tx.active_battle(owner)
        if battle is not None and battle.setup.player.ascended_id == ascended_id:
            raise WrongPhase("that Ascended is fighting in the active battle")

    # -- reads ---------------------------------------------------------------------

    async def view(self, owner: str, ascended_id: str) -> dict[str, Any]:
        async with self._repository.transaction() as tx:
            record = await self._owned(tx, owner, ascended_id)
            learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))
            essences = await tx.essence_counts(owner)
            stored = await tx.get_loadout(owner, ascended_id)
        tree = self._catalog.ascended(ascended_id).tree
        nodes = []
        for node in tree.nodes:
            state, reason = self._state(node, record, learned, essences, tree)
            nodes.append({**node.to_public(), "state": state, "reason": reason})
        slots = self._slots(ascended_id, stored)
        loadout = {slot: slots.get(slot) for slot in (*ABILITY_SLOTS, PASSIVE_SLOT)}
        return {"ascended_id": ascended_id, "level": record.level, "essences": essences, "nodes": nodes, "loadout": loadout}

    async def loadout_in(self, tx: AscendedTransaction, owner: str, ascended_id: str) -> Loadout:
        """The kit a battle starts with, read inside the caller's transaction."""
        stored = await tx.get_loadout(owner, ascended_id)
        if not stored:
            return self._catalog.default_loadout(ascended_id)
        tree = self._catalog.ascended(ascended_id).tree
        learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))
        abilities = []
        for slot in ABILITY_SLOTS:
            node = tree.node(stored.get(slot, ""))
            if node is not None and node.kind == "ability" and node.id in learned:
                abilities.append(node.ability)
        if not abilities:
            return self._catalog.default_loadout(ascended_id)
        passive_node = tree.node(stored.get(PASSIVE_SLOT, ""))
        passive = passive_node.passive if passive_node is not None and passive_node.kind == "passive" and passive_node.id in learned else NO_PASSIVE
        return Loadout(tuple(abilities), passive)

    # -- writes --------------------------------------------------------------------

    async def learn(self, owner: str, key: str, ascended_id: str, node_id: str) -> dict[str, Any]:
        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            record = await self._owned(tx, owner, ascended_id)
            tree = self._catalog.ascended(ascended_id).tree
            node = tree.node(node_id)
            if node is None:
                raise InvalidRequest("there is no such node")
            learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))
            essences = await tx.essence_counts(owner)
            if node.id in learned:
                raise UpgradeNotReady("that node is already learned")
            state, reason = self._state(node, record, learned, essences, tree)
            if state != "learnable":
                if reason and reason.endswith("essence"):
                    raise InsufficientEssence(f"{node.name} {reason}")
                raise UpgradeNotReady(f"{node.name} {reason}")
            await tx.add_essence(owner, node.cost.tier, -node.cost.amount)
            await tx.add_learned_node(owner, ascended_id, node.id)
            return {"kind": "learn", "ascended_id": ascended_id, "node_id": node.id,
                    "essence_tier": node.cost.tier, "essence_spent": node.cost.amount}

        return await self._writer.commit(owner, key, "tree.learn", {"ascended": ascended_id, "node": node_id}, work)

    async def set_loadout(self, owner: str, key: str, ascended_id: str, abilities: list[str], passive: str | None) -> dict[str, Any]:
        if not isinstance(abilities, list) or any(not isinstance(a, str) for a in abilities) or not (passive is None or isinstance(passive, str)):
            raise InvalidRequest("abilities must be a list of node ids and passive a node id or null")
        if not 1 <= len(abilities) <= len(ABILITY_SLOTS) or len(set(abilities)) != len(abilities):
            raise InvalidRequest(f"equip 1 to {len(ABILITY_SLOTS)} different abilities")

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            await self._owned(tx, owner, ascended_id)
            await self._reject_if_fighting(tx, owner, ascended_id)
            tree = self._catalog.ascended(ascended_id).tree
            learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))

            def need(node_id: str, kind: str) -> None:
                node = tree.node(node_id)
                if node is None or node.kind != kind or node_id not in learned:
                    raise InvalidRequest(f"{node_id!r} is not a learned {kind} node of this Ascended")

            for node_id in abilities:
                need(node_id, "ability")
            if passive is not None:
                need(passive, "passive")
            slots = dict(zip(ABILITY_SLOTS, abilities))
            if passive is not None:
                slots[PASSIVE_SLOT] = passive
            await tx.put_loadout(owner, ascended_id, slots)
            return {"ascended_id": ascended_id, "abilities": list(abilities), "passive": passive}

        return await self._writer.commit(owner, key, "tree.loadout", {"ascended": ascended_id, "abilities": abilities, "passive": passive}, work)
```

Prerequisites are checked before level, and level before essence, so a locked node always shows the first thing that blocks it.

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_trees.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/trees.py apps/ascension/tests/ascension/env.py apps/ascension/tests/ascension/test_trees.py
git commit -m "feat(ascension): TreeService (view, learn, loadout)"
```

---

### Task 6: Battles use the equipped loadout

**Files:**
- Modify: `src/ascension/coordinator.py` (constructor, `start`)
- Modify: `src/ascension/composition.py`, `src/ascension/api.py` (`AscendedServices.trees`)
- Modify: `tests/ascension/env.py` (`coordinator()` passes `trees`)
- Test: `tests/ascension/test_coordinator.py`

**Interfaces:**
- Consumes: `TreeService.loadout_in(tx, owner, ascended_id) -> Loadout`; `engine.build_fighter(..., loadout)`.
- Produces: `RoundCoordinator(..., settings, trees: TreeService | None = None)`; `AscendedServices.trees: TreeService`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ascension/test_coordinator.py` (it already has `make`, `strong_guardian`, `begin` and `run`):

```python
def test_a_battle_starts_with_the_equipped_loadout_and_keeps_it(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await strong_guardian(env)
        async with env.repo.transaction() as tx:
            await tx.put_loadout("ann", "guardian", {"a1": "guardian_bulwark", "a2": "guardian_heavy_blow"})
        coord = env.coordinator()
        await begin(env, coord)
        async with env.repo.transaction() as tx:
            battle = await tx.active_battle("ann")
        await env.close()
        return battle

    battle = run(scenario())
    assert [a.id for a in battle.setup.player.abilities] == ["guardian_bulwark", "guardian_heavy_blow"]
    assert battle.setup.player.passive.kind == "none"  # no p1 row: the player equipped no passive
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_coordinator.py -q -k equipped_loadout`
Expected: FAIL (the fighter still has all three catalog abilities).

- [ ] **Step 3: Write the implementation**

In `coordinator.py` constructor add the keyword `trees: "TreeService | None" = None` as the last parameter (import under `TYPE_CHECKING`, or import `TreeService` directly if there is no import cycle; `trees.py` imports only catalog, errors, idempotency, models, records, repository, tree) and store `self._trees = trees`. In `start`, replace the `PLAYER` `build_fighter` call:

```python
            loadout = await self._trees.loadout_in(tx, owner, ascended_id) if self._trees else None
            setup = BattleSetup(
                self._engine.build_fighter(PLAYER, ascended_id, self._catalog.tier_of(ascended_id, ascended.tier_id), ascended.level, loadout),
                self._engine.build_fighter(WILD, encounter.ascended_id, encounter.tier_id, encounter.level),
            )
```
In `tests/ascension/env.py` pass `trees=self.trees` to `RoundCoordinator(...)` in `coordinator()`. In `api.py` add `trees: TreeService` to `AscendedServices` (after `upgrades`) with `from src.ascension.trees import TreeService`. In `composition.py` build `trees = TreeService(repository, writer, catalog)` before the coordinator, pass `trees=trees` to `RoundCoordinator(...)` and `trees=trees` to `AscendedServices(...)`.

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension -q`
Expected: only the 8 sprite failures remain.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/coordinator.py apps/ascension/src/ascension/composition.py apps/ascension/src/ascension/api.py apps/ascension/tests/ascension/env.py apps/ascension/tests/ascension/test_coordinator.py
git commit -m "feat(ascension): battles start with the equipped loadout"
```

---

### Task 7: API routes and catalog summary

**Files:**
- Modify: `src/ascension/api.py`
- Test: `tests/ascension/test_api.py`

**Interfaces:**
- Produces routes: `GET /ascension/ascendeds/{id}/tree`, `POST /ascension/ascendeds/{id}/tree/{node}/learn` (201), `PUT /ascension/ascendeds/{id}/loadout`; catalog summary adds `tree: [node.to_public()...]` to every Ascended.
- Body model: `LoadoutBody(abilities: list[str], passive: str | None = None)`, extra fields forbidden.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ascension/test_api.py`:

```python
# -- ability trees -------------------------------------------------------------------

def test_the_catalog_lists_every_tree(client):
    data = client.get("/ascension/catalog", headers=headers(client, owner="anyone")).json()
    guardian = next(s for s in data["ascendeds"] if s["id"] == "guardian")
    ids = {n["id"] for n in guardian["tree"]}
    assert {"guardian_bulwark", "guardian_passive"} <= ids
    assert all({"id", "kind", "x", "y", "requires", "unlock_level", "cost", "root"} <= set(n) for n in guardian["tree"])


def test_trees_and_loadouts_over_http(client):
    start_profile(client)
    h = lambda: headers(client)  # noqa: E731
    tree = client.get("/ascension/ascendeds/guardian/tree", headers=headers(client, key=False)).json()
    assert tree["loadout"]["a1"] == "guardian_bulwark" and tree["loadout"]["p1"] == "guardian_passive"
    assert all(n["state"] in ("learned", "learnable", "locked") for n in tree["nodes"])
    assert client.get("/ascension/ascendeds/sentinel/tree", headers=headers(client, key=False)).status_code == 404
    assert client.post("/ascension/ascendeds/guardian/tree/nope/learn", headers=h()).status_code == 400
    assert client.post("/ascension/ascendeds/guardian/tree/guardian_bulwark/learn", headers=h()).status_code == 409  # a root
    locked = next(n["id"] for n in tree["nodes"] if n["state"] == "locked")
    assert client.post(f"/ascension/ascendeds/guardian/tree/{locked}/learn", headers=h()).status_code == 409
    saved = client.put("/ascension/ascendeds/guardian/loadout", json={"abilities": ["guardian_heavy_blow", "guardian_bulwark"], "passive": None}, headers=h())
    assert saved.status_code == 200 and saved.json()["abilities"] == ["guardian_heavy_blow", "guardian_bulwark"]
    again = client.get("/ascension/ascendeds/guardian/tree", headers=headers(client, key=False)).json()
    assert again["loadout"] == {"a1": "guardian_heavy_blow", "a2": "guardian_bulwark", "a3": None, "p1": None}
    assert client.put("/ascension/ascendeds/guardian/loadout", json={"abilities": []}, headers=h()).status_code == 400
    assert client.put("/ascension/ascendeds/guardian/loadout", json={"abilities": ["x"], "extra": 1}, headers=h()).status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_api.py -q -k "tree"`
Expected: FAIL (404 on the new routes, no `tree` key).

- [ ] **Step 3: Write the implementation**

In `api.py`:
- Add the body model next to `PresetBody`:

```python
class LoadoutBody(_Body):
    abilities: list[str]
    passive: str | None = None
```
- In `catalog_summary`, add `"tree": [n.to_public() for n in s.tree.nodes]` to each Ascended dict.
- In `build_router`, before the `sales` route:

```python
    @router.get("/ascendeds/{ascended_id}/tree")
    async def get_tree(ascended_id: str, owner: str = Depends(requester)):
        return await services.trees.view(owner, ascended_id)

    @router.post("/ascendeds/{ascended_id}/tree/{node_id}/learn", status_code=201)
    async def learn_node(ascended_id: str, node_id: str, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await services.trees.learn(owner, key, ascended_id, node_id)

    @router.put("/ascendeds/{ascended_id}/loadout")
    async def put_loadout(ascended_id: str, body: LoadoutBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await services.trees.set_loadout(owner, key, ascended_id, body.abilities, body.passive)
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_api.py -q`
Expected: all pass except the sprite tests.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/api.py apps/ascension/tests/ascension/test_api.py
git commit -m "feat(ascension): tree, learn and loadout routes"
```

---

### Task 8: Tree content for the seven Ascended

**Files:**
- Create: `ascended/{guardian,striker,scout,sentinel,channeler,bruiser,forbidden}/tree.json`
- Test: `tests/ascension/test_tree_content.py`

All numbers are placeholders (?). Every file lists the four roots (3 catalog abilities and `<id>_passive`) and adds its own nodes. The shapes differ on purpose.

- [ ] **Step 1: Write the failing test**

Create `tests/ascension/test_tree_content.py`:

```python
import pytest

from tests.ascension.env import CATALOG

IDS = [s.id for s in CATALOG.all_ascendeds()]


@pytest.mark.parametrize("ascended_id", [i for i in IDS if i != "twoychi"])
def test_each_shipped_ascended_has_a_real_tree(ascended_id):
    tree = CATALOG.ascended(ascended_id).tree
    extra = [n for n in tree.nodes if not n.root]
    assert len(tree.roots) == 4 and 3 <= len(extra) <= 5
    assert any(n.kind == "passive" for n in extra) and any(n.kind == "ability" for n in extra)
    assert all(n.cost.amount >= 1 for n in extra)


def test_every_tree_has_its_own_shape():
    shapes = {s.id: frozenset((n.x, n.y) for n in s.tree.nodes) for s in CATALOG.all_ascendeds()}
    assert len(set(shapes.values())) == len(shapes)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_tree_content.py -q`
Expected: FAIL (no extra nodes yet).

- [ ] **Step 3: Write the files**

Create each file exactly as below (2-space JSON). Costs: `c` = common, `r` = rare, `u` = unique.

`ascended/guardian/tree.json`:
```json
{"nodes": [
  {"id": "guardian_heavy_blow", "root": true, "x": 60, "y": 60},
  {"id": "guardian_rally", "root": true, "x": 60, "y": 180},
  {"id": "guardian_bulwark", "root": true, "x": 60, "y": 300},
  {"id": "guardian_passive", "root": true, "x": 220, "y": 180},
  {"id": "guardian_shield_slam", "kind": "ability", "name": "Shield Slam", "category": "ATTACK", "percentage": 190, "cooldown": 2, "unlock_level": 18, "requires": ["guardian_heavy_blow"], "cost": {"tier": "common", "amount": 4}, "x": 220, "y": 60},
  {"id": "guardian_iron_wall", "kind": "ability", "name": "Iron Wall", "category": "DEFENSE", "percentage": 260, "cooldown": 3, "unlock_level": 12, "requires": ["guardian_bulwark"], "cost": {"tier": "common", "amount": 3}, "x": 220, "y": 300},
  {"id": "guardian_unyielding", "kind": "ability", "name": "Unyielding", "category": "SUPPORT", "stat": "power", "duration": 3, "percentage": 75, "cooldown": 3, "unlock_level": 22, "requires": ["guardian_rally"], "cost": {"tier": "rare", "amount": 3}, "x": 380, "y": 120},
  {"id": "guardian_stoneskin", "kind": "passive", "name": "Stoneskin", "unlock_level": 15, "passive": {"kind": "defense_rating_bonus", "params": {"power_fraction": 0.4}}, "requires": ["guardian_iron_wall"], "cost": {"tier": "rare", "amount": 3}, "x": 380, "y": 300}
]}
```

`ascended/striker/tree.json`:
```json
{"nodes": [
  {"id": "striker_rending_strike", "root": true, "x": 40, "y": 40},
  {"id": "striker_battle_focus", "root": true, "x": 40, "y": 160},
  {"id": "striker_brace", "root": true, "x": 40, "y": 280},
  {"id": "striker_passive", "root": true, "x": 180, "y": 100},
  {"id": "striker_flurry", "kind": "ability", "name": "Flurry", "category": "ATTACK", "percentage": 110, "cooldown": 1, "unlock_level": 8, "requires": ["striker_rending_strike"], "cost": {"tier": "common", "amount": 2}, "x": 180, "y": 20},
  {"id": "striker_execution", "kind": "ability", "name": "Execution", "category": "ATTACK", "percentage": 260, "cooldown": 3, "unlock_level": 20, "requires": ["striker_flurry"], "cost": {"tier": "rare", "amount": 4}, "x": 320, "y": 20},
  {"id": "striker_bloodlust", "kind": "ability", "name": "Bloodlust", "category": "SUPPORT", "stat": "power", "duration": 2, "percentage": 90, "cooldown": 3, "unlock_level": 14, "requires": ["striker_battle_focus"], "cost": {"tier": "common", "amount": 3}, "x": 180, "y": 220},
  {"id": "striker_desperation", "kind": "passive", "name": "Desperation", "unlock_level": 18, "passive": {"kind": "low_hp_attack_bonus", "params": {"hp_below": 0.7, "power_fraction": 0.25}}, "requires": ["striker_passive"], "cost": {"tier": "rare", "amount": 3}, "x": 320, "y": 140}
]}
```

`ascended/scout/tree.json`:
```json
{"nodes": [
  {"id": "scout_quickstep", "root": true, "x": 40, "y": 160},
  {"id": "scout_swift_slash", "root": true, "x": 140, "y": 60},
  {"id": "scout_evade", "root": true, "x": 140, "y": 260},
  {"id": "scout_passive", "root": true, "x": 260, "y": 160},
  {"id": "scout_gale_step", "kind": "ability", "name": "Gale Step", "category": "SUPPORT", "stat": "speed", "duration": 3, "percentage": 140, "cooldown": 3, "unlock_level": 12, "requires": ["scout_quickstep"], "cost": {"tier": "common", "amount": 3}, "x": 40, "y": 20},
  {"id": "scout_twin_cuts", "kind": "ability", "name": "Twin Cuts", "category": "ATTACK", "percentage": 90, "cooldown": 1, "unlock_level": 9, "requires": ["scout_swift_slash"], "cost": {"tier": "common", "amount": 2}, "x": 260, "y": 40},
  {"id": "scout_mirage", "kind": "ability", "name": "Mirage", "category": "DEFENSE", "percentage": 200, "cooldown": 2, "unlock_level": 16, "requires": ["scout_evade"], "cost": {"tier": "rare", "amount": 3}, "x": 260, "y": 280},
  {"id": "scout_fleet_footed", "kind": "passive", "name": "Fleet Footed", "unlock_level": 14, "passive": {"kind": "support_duration_bonus", "params": {"rounds": 1}}, "requires": ["scout_gale_step"], "cost": {"tier": "rare", "amount": 3}, "x": 380, "y": 100},
  {"id": "scout_headstart", "kind": "passive", "name": "Headstart", "unlock_level": 20, "passive": {"kind": "battle_start_speed", "params": {"power_fraction": 0.8}}, "requires": ["scout_passive"], "cost": {"tier": "rare", "amount": 4}, "x": 380, "y": 220}
]}
```

`ascended/sentinel/tree.json`:
```json
{"nodes": [
  {"id": "sentinel_stone_guard", "root": true, "x": 200, "y": 300},
  {"id": "sentinel_hold_fast", "root": true, "x": 60, "y": 200},
  {"id": "sentinel_shield_bash", "root": true, "x": 340, "y": 200},
  {"id": "sentinel_passive", "root": true, "x": 200, "y": 180},
  {"id": "sentinel_bastion", "kind": "ability", "name": "Bastion", "category": "DEFENSE", "percentage": 400, "cooldown": 3, "unlock_level": 14, "requires": ["sentinel_stone_guard"], "cost": {"tier": "rare", "amount": 3}, "x": 200, "y": 420},
  {"id": "sentinel_vigil", "kind": "ability", "name": "Vigil", "category": "SUPPORT", "stat": "power", "duration": 3, "percentage": 80, "cooldown": 3, "unlock_level": 12, "requires": ["sentinel_hold_fast"], "cost": {"tier": "common", "amount": 3}, "x": 60, "y": 80},
  {"id": "sentinel_pillar_strike", "kind": "ability", "name": "Pillar Strike", "category": "ATTACK", "percentage": 170, "cooldown": 3, "unlock_level": 20, "requires": ["sentinel_shield_bash"], "cost": {"tier": "rare", "amount": 3}, "x": 340, "y": 80},
  {"id": "sentinel_watchtower", "kind": "passive", "name": "Watchtower", "unlock_level": 16, "passive": {"kind": "defense_extension", "params": {"protected_attacks": 2, "rounds": 1}}, "requires": ["sentinel_bastion"], "cost": {"tier": "rare", "amount": 4}, "x": 340, "y": 420}
]}
```

`ascended/channeler/tree.json`:
```json
{"nodes": [
  {"id": "channeler_focus", "root": true, "x": 40, "y": 100},
  {"id": "channeler_bolt", "root": true, "x": 180, "y": 40},
  {"id": "channeler_ward", "root": true, "x": 180, "y": 220},
  {"id": "channeler_passive", "root": true, "x": 180, "y": 130},
  {"id": "channeler_attunement", "kind": "ability", "name": "Attunement", "category": "SUPPORT", "stat": "power", "duration": 3, "percentage": 110, "cooldown": 3, "unlock_level": 12, "requires": ["channeler_focus"], "cost": {"tier": "common", "amount": 3}, "x": 40, "y": 240},
  {"id": "channeler_overload", "kind": "ability", "name": "Overload", "category": "ATTACK", "percentage": 220, "cooldown": 3, "unlock_level": 16, "requires": ["channeler_bolt"], "cost": {"tier": "rare", "amount": 3}, "x": 320, "y": 40},
  {"id": "channeler_lantern_ward", "kind": "ability", "name": "Lantern Ward", "category": "DEFENSE", "percentage": 160, "cooldown": 2, "unlock_level": 10, "requires": ["channeler_ward"], "cost": {"tier": "common", "amount": 2}, "x": 320, "y": 220},
  {"id": "channeler_afterglow", "kind": "passive", "name": "Afterglow", "unlock_level": 18, "passive": {"kind": "cooldown_reduction", "params": {"rounds": 1, "minimum": 1}}, "requires": ["channeler_passive"], "cost": {"tier": "rare", "amount": 4}, "x": 320, "y": 130}
]}
```

`ascended/bruiser/tree.json`:
```json
{"nodes": [
  {"id": "bruiser_crushing_blow", "root": true, "x": 40, "y": 40},
  {"id": "bruiser_guard_up", "root": true, "x": 40, "y": 160},
  {"id": "bruiser_rage", "root": true, "x": 40, "y": 280},
  {"id": "bruiser_passive", "root": true, "x": 160, "y": 160},
  {"id": "bruiser_haymaker", "kind": "ability", "name": "Haymaker", "category": "ATTACK", "percentage": 240, "cooldown": 3, "unlock_level": 14, "requires": ["bruiser_crushing_blow"], "cost": {"tier": "common", "amount": 4}, "x": 200, "y": 40},
  {"id": "bruiser_iron_hide", "kind": "ability", "name": "Iron Hide", "category": "DEFENSE", "percentage": 180, "cooldown": 2, "unlock_level": 10, "requires": ["bruiser_guard_up"], "cost": {"tier": "common", "amount": 2}, "x": 200, "y": 260},
  {"id": "bruiser_warcry", "kind": "ability", "name": "Warcry", "category": "SUPPORT", "stat": "power", "duration": 3, "percentage": 80, "cooldown": 3, "unlock_level": 18, "requires": ["bruiser_rage"], "cost": {"tier": "rare", "amount": 3}, "x": 200, "y": 340},
  {"id": "bruiser_grudge", "kind": "passive", "name": "Grudge", "unlock_level": 16, "passive": {"kind": "low_hp_attack_bonus", "params": {"hp_below": 0.6, "power_fraction": 0.3}}, "requires": ["bruiser_passive"], "cost": {"tier": "rare", "amount": 3}, "x": 320, "y": 160}
]}
```

`ascended/forbidden/tree.json`:
```json
{"nodes": [
  {"id": "forbidden_ruin", "root": true, "x": 200, "y": 40},
  {"id": "forbidden_dread_ward", "root": true, "x": 60, "y": 180},
  {"id": "forbidden_ascendance", "root": true, "x": 340, "y": 180},
  {"id": "forbidden_passive", "root": true, "x": 200, "y": 180},
  {"id": "forbidden_oblivion", "kind": "ability", "name": "Oblivion", "category": "ATTACK", "percentage": 320, "cooldown": 3, "unlock_level": 30, "requires": ["forbidden_ruin"], "cost": {"tier": "unique", "amount": 4}, "x": 200, "y": -80},
  {"id": "forbidden_void_shroud", "kind": "ability", "name": "Void Shroud", "category": "DEFENSE", "percentage": 400, "cooldown": 3, "unlock_level": 25, "requires": ["forbidden_dread_ward"], "cost": {"tier": "unique", "amount": 3}, "x": 60, "y": 300},
  {"id": "forbidden_hollow_crown", "kind": "ability", "name": "Hollow Crown", "category": "SUPPORT", "stat": "power", "duration": 3, "percentage": 150, "cooldown": 4, "unlock_level": 35, "requires": ["forbidden_ascendance"], "cost": {"tier": "unique", "amount": 5}, "x": 340, "y": 300},
  {"id": "forbidden_rime", "kind": "passive", "name": "Rime", "unlock_level": 40, "passive": {"kind": "support_duration_bonus", "params": {"rounds": 1}}, "requires": ["forbidden_hollow_crown"], "cost": {"tier": "unique", "amount": 5}, "x": 200, "y": 300}
]}
```

- [ ] **Step 4: Run all tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension -q`
Expected: the new content tests pass; only the 8 sprite tests fail. If a catalog error appears, its message names the file and node; fix that JSON.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/ascended/*/tree.json apps/ascension/tests/ascension/test_tree_content.py
git commit -m "feat(ascension): ability trees for the seven Ascended"
```

---

### Task 9: Web client, store and the Tree tab

**Files:**
- Modify: `web/src/api/AscensionClient.ts` (types, methods; add `tree` to `AscendedInfo`)
- Modify: `web/src/api/AscensionClient.fixtures.ts`
- Modify: `web/src/stores/ascension.ts`
- Create: `web/src/components/TreeTab.vue`
- Modify: `web/src/components/CollectionPanel.vue`
- Test: `web/src/components/TreeTab.test.ts`

**Interfaces:**
- Produces (types in `AscensionClient.ts`):

```ts
export interface TreeCost { tier: string; amount: number }
export interface TreeNodeView {
  id: string; kind: "ability" | "passive"; name: string; x: number; y: number; requires: string[];
  unlock_level: number; root: boolean; cost: TreeCost | null;
  category?: string; percentage?: number; cooldown?: number; stat?: string | null; duration?: number | null;
  passive?: { kind: string; params: Record<string, unknown> };
}
export interface TreeNodeState extends TreeNodeView { state: "learned" | "learnable" | "locked"; reason: string | null }
export type LoadoutSlot = "a1" | "a2" | "a3" | "p1";
export interface TreeView {
  ascended_id: string; level: number; essences: Record<string, number>;
  nodes: TreeNodeState[]; loadout: Record<LoadoutSlot, string | null>;
}
export interface LearnResult { kind: "learn"; ascended_id: string; node_id: string; essence_tier: string; essence_spent: number }
export interface LoadoutResult { ascended_id: string; abilities: string[]; passive: string | null }
```
  `AscendedInfo` gets `tree: TreeNodeView[]`. Client methods: `tree(id)`, `learnNode(id, node, key?)`, `saveLoadout(id, abilities, passive, key?)`. Store: `learnNode(ascendedId, nodeId): Promise<LearnResult | null>` and `saveLoadout(ascendedId, abilities, passive): Promise<LoadoutResult | null>`, both via `mutate(..., () => refreshProfile())`.
- `TreeTab.vue` props: `ascended: OwnedAscended`. It loads the tree with the client, draws it, and calls the store.

- [ ] **Step 1: Write the failing test**

Create `web/src/components/TreeTab.test.ts`. Model it on `CollectionPanel.test.ts` (same `vi.mock("../api/AscensionClient", ...)` with a client object, `setActivePinia`, `flushPromises`):

```ts
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient, type TreeView } from "../api/AscensionClient";
import { CATALOG, PROFILE, ownedAscended } from "../api/AscensionClient.fixtures";
import { useAscensionStore } from "../stores/ascension";
import TreeTab from "./TreeTab.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { tree: vi.fn(), learnNode: vi.fn(), saveLoadout: vi.fn(), profile: vi.fn() };
  return { useAscensionClient: () => client };
});

const client = vi.mocked(useAscensionClient());

const node = (id: string, extra = {}) => ({
  id, kind: "ability" as const, name: id.replace("g_", "").toUpperCase(), x: 40, y: 40, requires: [], unlock_level: 1, root: false,
  cost: null, category: "ATTACK", percentage: 100, cooldown: 1, stat: null, duration: null, state: "learned" as const, reason: null, ...extra,
});

const TREE: TreeView = {
  ascended_id: "guardian", level: 12, essences: { common: 3 },
  nodes: [
    node("g_a", { root: true, x: 40, y: 40 }),
    node("g_b", { root: true, x: 40, y: 160, category: "DEFENSE" }),
    node("g_pass", { kind: "passive", root: true, x: 160, y: 100, passive: { kind: "none", params: {} } }),
    node("g_wall", { x: 200, y: 40, requires: ["g_a"], unlock_level: 12, cost: { tier: "common", amount: 3 }, state: "learnable" }),
    node("g_far", { x: 320, y: 40, requires: ["g_wall"], unlock_level: 20, cost: { tier: "rare", amount: 3 }, state: "locked", reason: "needs level 20" }),
  ],
  loadout: { a1: "g_a", a2: "g_b", a3: null, p1: "g_pass" },
};

beforeEach(() => {
  vi.resetAllMocks();
  setActivePinia(createPinia());
  const store = useAscensionStore();
  store.catalog = CATALOG;
  store.profile = PROFILE;
  client.tree.mockResolvedValue(structuredClone(TREE));
  client.profile.mockResolvedValue(PROFILE);
});

const mountTab = async () => {
  const wrapper = mount(TreeTab, { props: { ascended: ownedAscended("guardian", { level: 12 }) } });
  await flushPromises();
  return wrapper;
};

describe("TreeTab", () => {
  it("draws every node at its place with its state and a line per prerequisite", async () => {
    const wrapper = await mountTab();

    expect(client.tree).toHaveBeenCalledWith("guardian");
    const nodes = wrapper.findAll(".tree-node");
    expect(nodes).toHaveLength(5);
    expect(wrapper.find('[data-node="g_wall"]').attributes("data-state")).toBe("learnable");
    expect(wrapper.find('[data-node="g_far"]').attributes("data-state")).toBe("locked");
    expect(wrapper.find('[data-node="g_wall"]').attributes("style")).toContain("left: 200px");
    expect(wrapper.findAll(".tree-line")).toHaveLength(2);
    expect(wrapper.find(".slots").text()).toContain("empty");
  });

  it("learns a node and reloads the tree", async () => {
    client.learnNode.mockResolvedValue({ kind: "learn", ascended_id: "guardian", node_id: "g_wall", essence_tier: "common", essence_spent: 3 });
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_wall"]').trigger("click");
    expect(wrapper.find(".node-detail").text()).toContain("3 common essence");
    await wrapper.find(".node-detail button.learn").trigger("click");
    await flushPromises();

    expect(client.learnNode).toHaveBeenCalledWith("guardian", "g_wall");
    expect(client.tree).toHaveBeenCalledTimes(2);
  });

  it("shows why a locked node cannot be learned and disables Learn", async () => {
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_far"]').trigger("click");
    expect(wrapper.find(".node-detail").text()).toContain("needs level 20");
    expect(wrapper.find(".node-detail button.learn").exists()).toBe(false);
  });

  it("equips a learned ability in a slot and saves the whole loadout", async () => {
    client.saveLoadout.mockResolvedValue({ ascended_id: "guardian", abilities: ["g_b"], passive: "g_pass" });
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_b"]').trigger("click");
    await wrapper.find('.node-detail button[data-slot="a1"]').trigger("click");
    await flushPromises();

    expect(client.saveLoadout).toHaveBeenCalledWith("guardian", ["g_b"], "g_pass");
  });

  it("can unequip the passive", async () => {
    client.saveLoadout.mockResolvedValue({ ascended_id: "guardian", abilities: ["g_a", "g_b"], passive: null });
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_pass"]').trigger("click");
    await wrapper.find(".node-detail button.unequip").trigger("click");
    await flushPromises();

    expect(client.saveLoadout).toHaveBeenCalledWith("guardian", ["g_a", "g_b"], null);
  });
});
```

Equip rule: putting a node in a slot first removes it from any other slot, then sets that slot (the previous holder is replaced, not swapped), then `abilities` is the non-empty slots `a1` to `a3` in order. So `g_b` equipped to `a1` leaves `a2` and replaces `g_a`, giving `["g_b"]`.

- [ ] **Step 2: Run to verify failure**

Run (in `web`): `npx vitest run src/components/TreeTab.test.ts`
Expected: FAIL (`TreeTab.vue` does not exist).

- [ ] **Step 3: Write the implementation**

1. `AscensionClient.ts`: add the types above, `tree: TreeNodeView[]` on `AscendedInfo`, and in the client class (next to `addStar`):

```ts
  tree = (ascendedId: string) => this.http.request<TreeView>("GET", `${BASE}/ascendeds/${part(ascendedId)}/tree`);
  learnNode = (ascendedId: string, nodeId: string, key: string = newIdempotencyKey()) =>
    this.http.request<LearnResult>("POST", `${BASE}/ascendeds/${part(ascendedId)}/tree/${part(nodeId)}/learn`, undefined, withKey(key));
  saveLoadout = (ascendedId: string, abilities: string[], passive: string | null, key: string = newIdempotencyKey()) =>
    this.http.request<LoadoutResult>("PUT", `${BASE}/ascendeds/${part(ascendedId)}/loadout`, { abilities, passive }, withKey(key));
```
2. `AscensionClient.fixtures.ts`: in `ascendedInfo(...)` add `tree: [],` before `art`.
3. `stores/ascension.ts`: import `LearnResult`, `LoadoutResult`; add next to `raiseTier` and export both:

```ts
  function learnNode(ascendedId: string, nodeId: string): Promise<LearnResult | null> {
    return mutate(() => ascensionClient.learnNode(ascendedId, nodeId), () => refreshProfile());
  }

  function saveLoadout(ascendedId: string, abilities: string[], passive: string | null): Promise<LoadoutResult | null> {
    return mutate(() => ascensionClient.saveLoadout(ascendedId, abilities, passive), () => undefined);
  }
```
4. `TreeTab.vue`:

```vue
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAscensionClient, type LoadoutSlot, type OwnedAscended, type TreeNodeState, type TreeView } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { titleCase } from "../utils/ascension";
import EmButton from "./ui/EmButton.vue";
import EmNotice from "./ui/EmNotice.vue";

/** One Ascended's ability tree: nodes at their own places, learn a node, equip it in a slot. */
const props = defineProps<{ ascended: OwnedAscended }>();
const store = useAscensionStore();
const client = useAscensionClient();

const NODE_W = 124;
const NODE_H = 52;
const ABILITY_SLOTS: LoadoutSlot[] = ["a1", "a2", "a3"];

const tree = ref<TreeView | null>(null);
const selectedId = ref<string | null>(null);
const error = ref("");

const selected = computed(() => tree.value?.nodes.find((n) => n.id === selectedId.value) ?? null);
const byId = computed(() => new Map((tree.value?.nodes ?? []).map((n) => [n.id, n])));
const width = computed(() => Math.max(300, ...(tree.value?.nodes ?? []).map((n) => n.x + NODE_W + 24)));
const height = computed(() => Math.max(200, ...(tree.value?.nodes ?? []).map((n) => n.y + NODE_H + 24)));
const minY = computed(() => Math.min(0, ...(tree.value?.nodes ?? []).map((n) => n.y)));
const shiftY = computed(() => (minY.value < 0 ? 24 - minY.value : 0));

const lines = computed(() => {
  const out: { key: string; x1: number; y1: number; x2: number; y2: number }[] = [];
  for (const node of tree.value?.nodes ?? []) {
    for (const required of node.requires) {
      const from = byId.value.get(required);
      if (from) out.push({ key: `${required}>${node.id}`, x1: from.x + NODE_W / 2, y1: from.y + NODE_H / 2 + shiftY.value, x2: node.x + NODE_W / 2, y2: node.y + NODE_H / 2 + shiftY.value });
    }
  }
  return out;
});

async function load(): Promise<void> {
  error.value = "";
  try {
    tree.value = await client.tree(props.ascended.ascended_id);
  } catch (err) {
    error.value = errorMessage(err);
  }
}
watch(() => props.ascended.ascended_id, () => { selectedId.value = null; void load(); }, { immediate: true });

const slotLabel = (slot: LoadoutSlot): string => {
  const id = tree.value?.loadout[slot];
  return id ? (byId.value.get(id)?.name ?? id) : "empty";
};
const equippedSlot = (node: TreeNodeState): LoadoutSlot | null =>
  (Object.entries(tree.value?.loadout ?? {}).find(([, id]) => id === node.id)?.[0] as LoadoutSlot | undefined) ?? null;

const costText = (node: TreeNodeState): string => (node.cost ? `${node.cost.amount} ${node.cost.tier} essence` : "free");
const detail = (node: TreeNodeState): string => {
  if (node.kind === "passive") return `Passive: ${titleCase(node.passive?.kind ?? "none")}`;
  const bits = [`${node.category ?? ""} ${node.percentage ?? 0}%`, `cooldown ${node.cooldown ?? 1}`];
  if (node.stat) bits.push(`+${node.stat} for ${node.duration} rounds`);
  return bits.join(", ");
};

async function learn(node: TreeNodeState): Promise<void> {
  const result = await store.learnNode(props.ascended.ascended_id, node.id);
  if (result) await load();
}

/** The replaced slot loses its node; the node leaves any other slot first. */
async function equip(node: TreeNodeState, slot: LoadoutSlot): Promise<void> {
  const next: Record<LoadoutSlot, string | null> = { ...(tree.value as TreeView).loadout };
  for (const key of Object.keys(next) as LoadoutSlot[]) if (next[key] === node.id) next[key] = null;
  next[slot] = node.id;
  await save(next);
}

async function unequip(node: TreeNodeState): Promise<void> {
  const next: Record<LoadoutSlot, string | null> = { ...(tree.value as TreeView).loadout };
  for (const key of Object.keys(next) as LoadoutSlot[]) if (next[key] === node.id) next[key] = null;
  await save(next);
}

async function save(next: Record<LoadoutSlot, string | null>): Promise<void> {
  const abilities = ABILITY_SLOTS.map((s) => next[s]).filter((id): id is string => id !== null);
  const result = await store.saveLoadout(props.ascended.ascended_id, abilities, next.p1);
  if (result) await load();
}
</script>

<template>
  <section class="tree-tab">
    <EmNotice v-if="error" tone="error">{{ error }}</EmNotice>
    <template v-if="tree">
      <div class="slots" aria-label="Equipped">
        <span v-for="slot in ABILITY_SLOTS" :key="slot" class="slot"><small>{{ slot.toUpperCase() }}</small> {{ slotLabel(slot) }}</span>
        <span class="slot"><small>PASSIVE</small> {{ slotLabel("p1") }}</span>
      </div>
      <div class="scroll">
        <div class="canvas" :style="{ width: `${width}px`, height: `${height + shiftY}px` }">
          <svg class="lines" :width="width" :height="height + shiftY" aria-hidden="true">
            <line v-for="l in lines" :key="l.key" class="tree-line" :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" />
          </svg>
          <button
            v-for="node in tree.nodes"
            :key="node.id"
            type="button"
            class="tree-node"
            :class="{ selected: node.id === selectedId, equipped: equippedSlot(node) !== null }"
            :data-node="node.id"
            :data-state="node.state"
            :data-kind="node.kind"
            :style="{ left: `${node.x}px`, top: `${node.y + shiftY}px`, width: `${NODE_W}px`, height: `${NODE_H}px` }"
            @click="selectedId = node.id"
          >
            <strong>{{ node.name }}</strong>
            <small>{{ node.kind === "passive" ? "Passive" : titleCase(node.category ?? "") }}<template v-if="equippedSlot(node)"> · {{ equippedSlot(node)!.toUpperCase() }}</template></small>
          </button>
        </div>
      </div>
      <div v-if="selected" class="node-detail">
        <h4>{{ selected.name }}</h4>
        <p>{{ detail(selected) }}</p>
        <p class="em-num">Level {{ selected.unlock_level }} · {{ costText(selected) }}</p>
        <p v-if="selected.state === 'locked'" class="reason">{{ selected.reason }}</p>
        <EmButton v-if="selected.state === 'learnable'" class="learn" variant="primary" :disabled="store.busy" @click="learn(selected)">Learn</EmButton>
        <div v-if="selected.state === 'learned'" class="equip">
          <template v-if="selected.kind === 'ability'">
            <EmButton v-for="slot in ABILITY_SLOTS" :key="slot" :data-slot="slot" :disabled="store.busy" @click="equip(selected, slot)">Equip {{ slot.toUpperCase() }}</EmButton>
          </template>
          <EmButton v-else data-slot="p1" :disabled="store.busy" @click="equip(selected, 'p1')">Equip passive</EmButton>
          <EmButton v-if="equippedSlot(selected)" class="unequip" :disabled="store.busy" @click="unequip(selected)">Unequip</EmButton>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.slots { display: flex; flex-wrap: wrap; gap: var(--em-space-2); margin-bottom: var(--em-space-3); }
.slot { padding: 4px 10px; border: 1px solid var(--em-border); border-radius: var(--em-radius); font-size: 12px; }
.slot small { margin-right: 4px; color: var(--em-muted); font-weight: 700; }
.scroll { max-width: 100%; overflow: auto; border: 1px solid var(--em-border); border-radius: var(--em-radius); }
.canvas { position: relative; }
.lines { position: absolute; inset: 0; }
.tree-line { stroke: var(--em-border); stroke-width: 2; }
.tree-node { position: absolute; display: flex; flex-direction: column; justify-content: center; padding: 4px 8px; border: 2px solid var(--em-border); border-radius: var(--em-radius); background: var(--em-panel); color: var(--em-text); font: inherit; text-align: left; cursor: pointer; }
.tree-node strong { font-size: 13px; }
.tree-node small { color: var(--em-muted); font-size: 11px; }
.tree-node[data-state="learned"] { border-color: var(--em-accent); }
.tree-node[data-state="learnable"] { border-style: dashed; border-color: var(--em-accent); }
.tree-node[data-state="locked"] { opacity: 0.55; }
.tree-node.equipped { box-shadow: 0 0 0 2px var(--em-accent); }
.tree-node.selected { outline: 2px solid var(--em-text); }
.node-detail { display: flex; flex-direction: column; gap: 6px; margin-top: var(--em-space-3); font-size: 13px; }
.node-detail h4, .node-detail p { margin: 0; }
.reason { color: var(--em-muted); }
.equip { display: flex; flex-wrap: wrap; gap: var(--em-space-2); }
</style>
```

5. `CollectionPanel.vue`: import `TreeTab`; add `const treeOpen = ref(false);` reset in `show()` (`treeOpen.value = false;`); in the details side column, before the `<div class="people-head">`:

```vue
          <EmButton :aria-expanded="treeOpen" @click="treeOpen = !treeOpen">{{ treeOpen ? "Hide ability tree" : "Ability tree" }}</EmButton>
          <TreeTab v-if="treeOpen" :ascended="open" />
```

   and add `treeOpen` to the `script setup` (it is `ref`, imported already).

- [ ] **Step 4: Run all web checks**

Run (in `web`): `npx vue-tsc --noEmit` then `npx vitest run`
Expected: type check clean; all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/web/src
git commit -m "feat(ascension): ability tree tab with learn and equip"
```

---

### Task 10: Docs and vault

**Files:**
- Modify: `apps/ascension/README.md`, `apps/ascension/AGENTS.md`
- Modify: vault `Brain/Projects/Ascension.md`

- [ ] **Step 1: README.** Add a section "Ability trees" after "Stars and tiers": the `tree.json` format (roots listed with `x`/`y`, ability and passive nodes, `requires`, `cost`, `unlock_level`), the passive root id `<id>_passive`, the 3 plus 1 slots, the learn rules, the default loadout when nothing is saved, battles freeze the loadout, database version 5. Add three rows to the routes table: `GET /ascension/ascendeds/{id}/tree`, `POST /ascension/ascendeds/{id}/tree/{node}/learn`, `PUT /ascension/ascendeds/{id}/loadout`.
- [ ] **Step 2: AGENTS.** In "Where an Ascended's files live", add `tree.json` (nodes and positions) beside `catalog.json`.
- [ ] **Step 3: Vault.** In `Brain/Projects/Ascension.md` under "Python game (MCPServer)" add a bullet: ability trees and loadouts (`tree.json`, 3 abilities and 1 passive, learn with level, prerequisites and essence), with a link to `[[Decision - Ascended tiers rise by stars, not by copies]]` already there. Set `last_synced` to the date. Run `py ../.claude/hooks/validate_vault.py --all` from `Brain`.
- [ ] **Step 4: Run everything and commit**

Run: `.venv_ascension\Scripts\python -m pytest -q` and, in `web`, `npx vitest run`.
Expected: only the 8 sprite failures.

```bash
git add apps/ascension/README.md apps/ascension/AGENTS.md
git commit -m "docs(ascension): ability trees"
```
and, in `Brain`: `git add Projects/Ascension.md && git commit -m "docs: Ascension ability trees"`.

---

## Self-review against the spec

- Slots, learn rules, roots, swap, freeze, mixed loadouts: Tasks 3, 5, 6 (3 attack abilities allowed, tested in Task 5).
- `tree.json` format and every validation bullet: Tasks 1 and 2 (cycles, unknown prerequisite, unreachable, unknown root, bad category, bad passive, cost tier, duplicates across Ascended, unique positions).
- Database v5 and the `no rows means default` rule: Tasks 4 and 5 (`loadout_in`).
- Service, routes, catalog summary: Tasks 5 and 7.
- UI (canvas, states, slot bar, phone-width scroll): Task 9. The catalog `tree` list (public data) is available to the UI through `AscendedInfo.tree`; `TreeTab` reads the player's own state from `GET .../tree`.
- Content for 7 Ascended: Task 8. Twoychi waits for its own `catalog.json`.
- Open questions stay open: `cost.tier` is set per node as drafted; no respec.
- Type names are consistent: `Loadout`, `TreeService.loadout_in`, `ABILITY_SLOTS`/`PASSIVE_SLOT`, `passive_root_id`, `TreeNodeState`, `LoadoutSlot`.
