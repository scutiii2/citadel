# Ascension Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Abilities can heal, regenerate, put lasting statuses on the enemy (bleed, slow, weaken, exposed, named marks), cleanse, and ward off one lethal hit. An ability with no effects behaves exactly as today.

**Architecture:** `EffectSpec` and `Status` are new frozen values in `models.py`; `effects.py` validates the `effects` list of an ability (catalog and tree nodes). `FighterState` gains `statuses`. `BattleEngine` applies effects in the ability's own phase, ticks regen and bleed at the end of a surviving round, and reads statuses in `stat`, the shield and the ward. Two new passive kinds read marks and heals. The public battle view, the catalog and tree summaries and the web UI show statuses and effect text.

**Tech Stack:** Python 3.14, pytest; Vue 3, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-12-ascension-effects-design.md`.

## Global Constraints

- Work in `apps/ascension`. Run Python tests with `.venv_ascension\Scripts\python -m pytest -q`; web tests in `web` with `npx vue-tsc --noEmit` and `npx vitest run`.
- Known baseline: 7 Python tests fail only because of sprite files (test_api sprite tests, test_ascended_layout, two sprite tests in test_catalog). Ignore exactly those.
- An ability with no `effects` must resolve exactly as before. Old saved battles (no `statuses`, no `effects`) must load. The engine stays pure: no new random draws, so scripted-draw tests keep their counts.
- Status ids: `bleed`, `slow`, `weaken`, `exposed`, `regen`, `ward`, and `mark:<name>`. One status per id per fighter; applying it again replaces it. Harmful ids that `cleanse` removes: `bleed`, `slow`, `weaken`, `exposed`.
- `percentage` is of the user's power: the unbuffed power for a SUPPORT ability, the current power for DEFENSE and ATTACK abilities. `slow` and `weaken` use `percentage` of the target's current speed or power instead.
- Tick order at the end of a surviving round: wild side then player side; for each side regen first, then bleed. A ward rescues a bleed once. If the wild side died the result is `won`, else if the player died `knocked_out`.
- Numbers in tests and `tree.json` are placeholders (?). This plan does not change `tree.json`; converting Twoychi's nodes is a later plan.
- Never commit the unrelated dirty files (Ember web, sprites). Add only the files each task names.
- Commit messages end with: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

## File Structure

| File | Change |
|---|---|
| `src/ascension/models.py` | `EffectSpec`, `Status`, constants; `AbilitySpec.effects`; `FighterState.statuses`. |
| `src/ascension/effects.py` | New. `parse_effects`. |
| `src/ascension/catalog.py` | `_ability` parses `effects`. |
| `src/ascension/tree.py` | `to_public` carries `effects`. |
| `src/ascension/engine.py` | Statuses in `_Side` and `stat`, `_apply_effects`, ward, tick, expiry, exposed, marked bonus. |
| `src/ascension/passives.py` | Hooks `marked_bonus`, `heal_multiplier`; kinds `attack_bonus_vs_marked`, `heal_bonus`. |
| `src/ascension/battle_view.py` | `statuses` and ability `effects` in the public view. |
| `web/src/...` | Types, `effectText`, `statusText`, `describeEvent`, `passiveText`, arena, tree detail, card line. |
| `tests/ascension/...` | `test_models_effects.py`, `test_effects_catalog.py`, `test_engine_effects.py`, `test_passives_effects.py`, `test_battle_view_effects.py`; `helpers.py`. |

---

### Task 1: Effect values, validation and saved-state compatibility

**Files:**
- Modify: `src/ascension/models.py`, `src/ascension/catalog.py`, `src/ascension/tree.py`
- Create: `src/ascension/effects.py`
- Modify: `tests/ascension/helpers.py` (`ability` gets `effects`)
- Test: `tests/ascension/test_models_effects.py`, `tests/ascension/test_effects_catalog.py`

**Interfaces:**
- Produces in `models.py`:
  - `EffectSpec(kind: str, percentage: float | None = None, rounds: int | None = None, name: str | None = None, target: str | None = None)` with `to_dict()` (only non-None fields) and `from_dict(raw)`.
  - `Status(id: str, amount: int, rounds_left: int)` with `to_dict()` and `from_dict(raw)`.
  - `AbilitySpec.effects: tuple[EffectSpec, ...] = ()` (last field); `to_dict` writes `effects` as a list of dicts; `from_dict` reads a missing `effects` as empty and keeps the legacy `stat` fix.
  - `FighterState.statuses: tuple[Status, ...] = ()` (last field); `to_dict` writes `statuses`; `from_dict` reads a missing one as empty.
  - `STAT_STATUS = {"slow": "speed", "weaken": "power"}` and `HARMFUL = ("bleed", "slow", "weaken", "exposed")`.
- Produces in `effects.py`: `parse_effects(raw, where) -> tuple[EffectSpec, ...]` (raises `ValueError`).
- `_ability` in `catalog.py` fills `AbilitySpec.effects`; `TreeNode.to_public` adds `"effects": [e.to_dict() ...]` for ability nodes.

- [ ] **Step 1: Write the failing tests**

In `tests/ascension/helpers.py` change `ability` to accept and pass `effects`:

```python
def ability(
    id: str = "a1", category: str = "ATTACK", percentage: float = 150, cooldown: int = 1,
    stat: str | None = None, duration: int | None = None, unlock_level: int = 1, effects: tuple = (),
) -> AbilitySpec:
    return AbilitySpec(id, id, unlock_level, category, percentage, cooldown, stat, duration, effects)
```

Create `tests/ascension/test_models_effects.py`:

```python
from src.ascension.models import AbilitySpec, EffectSpec, FighterState, Status


def test_old_saved_states_and_abilities_load_without_statuses_or_effects():
    assert FighterState.from_dict({"hp": 10, "buffs": [], "defense": None, "cooldowns": []}).statuses == ()
    legacy = {"id": "a", "name": "A", "unlock_level": 1, "category": "ATTACK", "percentage": 100.0, "cooldown": 1,
              "stat": None, "duration": None}
    assert AbilitySpec.from_dict(legacy).effects == ()


def test_effects_and_statuses_round_trip():
    ability = AbilitySpec("a", "A", 1, "ATTACK", 100.0, 1, effects=(
        EffectSpec("bleed", percentage=20.0, rounds=3), EffectSpec("mark", rounds=2, name="prey", target="foe"), EffectSpec("cleanse")))
    assert AbilitySpec.from_dict(ability.to_dict()) == ability
    assert ability.to_dict()["effects"][0] == {"kind": "bleed", "percentage": 20.0, "rounds": 3}
    assert ability.to_dict()["effects"][2] == {"kind": "cleanse"}
    state = FighterState(5, statuses=(Status("bleed", 4, 2), Status("mark:prey", 0, 3)))
    assert FighterState.from_dict(state.to_dict()) == state
    assert state.to_dict()["statuses"][0] == {"id": "bleed", "amount": 4, "rounds_left": 2}


def test_a_legacy_essence_stat_still_becomes_power():
    legacy = {"id": "a", "name": "A", "unlock_level": 1, "category": "SUPPORT", "percentage": 50.0, "cooldown": 2,
              "stat": "essence", "duration": 2}
    assert AbilitySpec.from_dict(legacy).stat == "power"
```

Create `tests/ascension/test_effects_catalog.py`:

```python
import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.models import EffectSpec
from tests.ascension.env import load_raw

RAW = load_raw()


def build(mutate):
    data = copy.deepcopy(RAW)
    mutate(next(s for s in data["ascendeds"] if s["id"] == "guardian"))
    return Catalog(data)


def with_effects(effects):
    return lambda s: s["abilities"][2].update(effects=effects)


def test_a_valid_effects_list_parses_with_defaults():
    catalog = build(with_effects([{"kind": "bleed", "percentage": 20, "rounds": 3}, {"kind": "mark", "name": "prey", "rounds": 3},
                                  {"kind": "heal", "percentage": 50}, {"kind": "cleanse"}, {"kind": "ward", "rounds": 2}]))
    assert catalog.ascended("guardian").abilities[2].effects == (
        EffectSpec("bleed", percentage=20.0, rounds=3), EffectSpec("mark", rounds=3, name="prey", target="foe"),
        EffectSpec("heal", percentage=50.0), EffectSpec("cleanse"), EffectSpec("ward", rounds=2))


def test_an_ability_without_effects_has_none():
    assert Catalog(copy.deepcopy(RAW)).ascended("guardian").abilities[2].effects == ()


@pytest.mark.parametrize("effects,message", [
    ("nope", "effects must be a list"),
    ([{"kind": "heal", "percentage": 5}] * 4, "at most 3"),
    (["x"], "must be an object"),
    ([{"kind": "teleport"}], "unknown effect kind"),
    ([{"kind": "heal", "percentage": 5, "color": "red"}], "unknown field"),
    ([{"kind": "heal"}], "positive percentage"),
    ([{"kind": "heal", "percentage": 0}], "positive percentage"),
    ([{"kind": "bleed", "percentage": 20}], "rounds of at least 1"),
    ([{"kind": "bleed", "percentage": 20, "rounds": 0}], "rounds of at least 1"),
    ([{"kind": "ward"}], "rounds of at least 1"),
    ([{"kind": "mark", "rounds": 2}], "lowercase name"),
    ([{"kind": "mark", "rounds": 2, "name": "Prey"}], "lowercase name"),
    ([{"kind": "mark", "rounds": 2, "name": "prey", "target": "both"}], "foe or self"),
    ([{"kind": "heal", "percentage": 5, "name": "prey"}], "only a mark"),
])
def test_a_bad_effect_is_a_catalog_error(effects, message):
    with pytest.raises(CatalogError, match=message):
        build(with_effects(effects))


def test_a_tree_node_may_carry_effects_and_shows_them_publicly():
    node = {"id": "guardian_bite", "kind": "ability", "name": "Bite", "category": "ATTACK", "percentage": 120, "cooldown": 2,
            "unlock_level": 12, "requires": ["guardian_bulwark"], "cost": {"tier": "common", "amount": 2}, "x": 900, "y": 900,
            "effects": [{"kind": "bleed", "percentage": 20, "rounds": 3}]}
    catalog = build(lambda s: s.update(tree={"nodes": [dict(n) for n in s["tree"]["nodes"]] + [node]}))
    shown = catalog.ascended("guardian").tree.node("guardian_bite").to_public()
    assert shown["effects"] == [{"kind": "bleed", "percentage": 20.0, "rounds": 3}]
```

(`s["tree"]` exists for guardian because `load_raw()` merges the shipped `tree.json`.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_models_effects.py tests/ascension/test_effects_catalog.py -q`
Expected: FAIL (`ImportError: cannot import name 'EffectSpec'`).

- [ ] **Step 3: Write the implementation**

In `src/ascension/models.py`:

1. Add constants near `CATEGORIES`:

```python
STAT_STATUS = {"slow": "speed", "weaken": "power"}  # statuses that move a stat, with a negative amount
HARMFUL = ("bleed", "slow", "weaken", "exposed")  # what cleanse removes
```
2. Add before `AbilitySpec`:

```python
@dataclass(frozen=True)
class EffectSpec:
    """One extra thing an ability does. See effects.py for the rules per kind."""

    kind: str
    percentage: float | None = None
    rounds: int | None = None
    name: str | None = None  # marks only
    target: str | None = None  # marks only: "foe" or "self"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EffectSpec":
        return cls(**raw)
```
3. `AbilitySpec`: add the last field `effects: tuple["EffectSpec", ...] = ()` and replace its `to_dict`/`from_dict`:

```python
    def to_dict(self) -> dict[str, Any]:
        raw = dict(self.__dict__)
        raw["effects"] = [e.to_dict() for e in self.effects]
        return raw

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AbilitySpec":
        data = {**raw, "stat": _legacy_stat(raw.get("stat")), "effects": tuple(EffectSpec.from_dict(e) for e in raw.get("effects", []))}
        return cls(**data)
```
4. Add `Status` after `Buff`:

```python
@dataclass(frozen=True)
class Status:
    """A lasting effect on a fighter: bleed, slow, weaken, exposed, regen, ward or a mark (`mark:<name>`)."""

    id: str
    amount: int
    rounds_left: int

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Status":
        return cls(**raw)
```
5. `FighterState`: add the last field `statuses: tuple[Status, ...] = ()`, put `"statuses": [s.to_dict() for s in self.statuses]` in `to_dict`, and in `from_dict` pass `tuple(Status.from_dict(s) for s in raw.get("statuses", []))` as the fifth argument.

Create `src/ascension/effects.py`:

```python
"""Validation of an ability's `effects` list (catalog abilities and tree nodes)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.ascension.models import EffectSpec

KINDS = ("heal", "regen", "bleed", "slow", "weaken", "exposed", "mark", "cleanse", "ward")
PERCENT_KINDS = ("heal", "regen", "bleed", "slow", "weaken", "exposed")
ROUND_KINDS = ("regen", "bleed", "slow", "weaken", "exposed", "mark", "ward")
FIELDS = {"kind", "percentage", "rounds", "name", "target"}
MAX_EFFECTS = 3


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_effects(raw: Any, where: str) -> tuple[EffectSpec, ...]:
    """The effects of one ability. Raises ValueError with the place and the problem."""
    if not isinstance(raw, list):
        raise ValueError(f"{where}: effects must be a list")
    if len(raw) > MAX_EFFECTS:
        raise ValueError(f"{where}: at most {MAX_EFFECTS} effects")
    parsed = []
    for index, item in enumerate(raw):
        at = f"{where} effect {index}"
        if not isinstance(item, Mapping):
            raise ValueError(f"{at}: must be an object")
        extra = set(item) - FIELDS
        if extra:
            raise ValueError(f"{at}: unknown field {sorted(extra)[0]!r}")
        kind = item.get("kind")
        if kind not in KINDS:
            raise ValueError(f"{at}: unknown effect kind {kind!r}")
        percentage, rounds = item.get("percentage"), item.get("rounds")
        if kind in PERCENT_KINDS and not (_number(percentage) and percentage > 0):
            raise ValueError(f"{at}: {kind} needs a positive percentage")
        if kind in ROUND_KINDS and (isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1):
            raise ValueError(f"{at}: {kind} needs rounds of at least 1")
        name, target = item.get("name"), item.get("target")
        if kind == "mark":
            if not isinstance(name, str) or not re.fullmatch(r"[a-z_]+", name):
                raise ValueError(f"{at}: a mark needs a lowercase name (letters and underscores)")
            target = target or "foe"
            if target not in ("foe", "self"):
                raise ValueError(f"{at}: a mark target must be foe or self")
        elif name is not None or target is not None:
            raise ValueError(f"{at}: only a mark has a name or a target")
        parsed.append(EffectSpec(
            kind, float(percentage) if kind in PERCENT_KINDS else None, rounds if kind in ROUND_KINDS else None, name, target))
    return tuple(parsed)
```

In `catalog.py`: `from src.ascension.effects import parse_effects`; in `_ability`, parse before building and pass it:

```python
    try:
        effects = parse_effects(raw.get("effects", []), where)
    except ValueError as error:
        raise CatalogError(str(error)) from error
    ability = AbilitySpec(
        id=..., ..., stat=raw.get("stat"), duration=raw.get("duration"), effects=effects,
    )
```
In `tree.py` `TreeNode.to_public`, in the ability branch add `effects=[e.to_dict() for e in a.effects]` to the `shown.update(...)` call.

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: the new tests pass. A few existing tests may compare a whole ability dict (`to_dict` now carries `"effects": []`); fix those by adding `"effects": []` to the expected dict. Only the 7 sprite failures may remain.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/models.py apps/ascension/src/ascension/effects.py apps/ascension/src/ascension/catalog.py apps/ascension/src/ascension/tree.py apps/ascension/tests/ascension
git commit -m "feat(ascension): effect and status values with validation"
```
(Stage only the test files this task changed or created under `tests/ascension`.)

---

### Task 2: The engine applies effects

**Files:**
- Modify: `src/ascension/engine.py`
- Test: `tests/ascension/test_engine_effects.py`

**Interfaces:**
- Consumes: Task 1 (`EffectSpec`, `Status`, `STAT_STATUS`, `HARMFUL`, `FighterState.statuses`, `AbilitySpec.effects`).
- Produces: engine behaviour exactly as in the spec: `heal`, `regen`, `bleed`, `slow`, `weaken`, `exposed`, `mark`, `cleanse`, `ward`, ticks, expiry, the ward, `BattleEngine.stat` with statuses and a floor of 1. New events (all with a `side`): `heal {amount}`, `status {target, status, amount, rounds}`, `cleanse {removed}`, `tick {kind, amount, hp}`, `ward_triggered {}`.
- Hooks used here that Task 3 adds on `Passive`: `marked_bonus(power, marks)` and `heal_multiplier(hp, max_hp)`. This task adds them as neutral defaults on the base `Passive` class so the engine can call them (Task 3 adds the real kinds).

- [ ] **Step 1: Write the failing tests**

Create `tests/ascension/test_engine_effects.py`:

```python
from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, Action, BattleState, EffectSpec, FighterState, Status
from tests.ascension.env import CATALOG
from tests.ascension.helpers import ScriptedRandom, ability, fighter, setup

engine = BattleEngine(CATALOG)
ATTACK = Action("attack", "ATTACK")
FLEE = Action("flee", "FEAR")
IDLE = (0.0, 0.99, 0.99)  # the player moves first and both flee attempts fail


def use(spec):
    return Action("ability", spec.category, spec.id, spec.percentage)


def fx(kind, **fields):
    return EffectSpec(kind, **fields)


def state_of(s, player=None, wild=None, rnd=1):
    return BattleState(rnd, player or FighterState(s.player.max_hp), wild or FighterState(s.wild.max_hp))


def step(s, state, player_action, wild_action, *draws):
    return engine.resolve_round(s, state, player_action, wild_action, ScriptedRandom(*draws))


def ids(fstate):
    return {st.id for st in fstate.statuses}


def get(fstate, status_id):
    return next(st for st in fstate.statuses if st.id == status_id)


def test_heal_restores_hp_up_to_the_maximum():
    spec = ability("mend", "DEFENSE", 100, effects=(fx("heal", percentage=50),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s, player=FighterState(50)), use(spec), FLEE, 0.0, 0.99)
    assert out.state.player.hp == 70 and {"type": "heal", "side": "player", "amount": 20} in out.events
    near = step(s, state_of(s, player=FighterState(90)), use(spec), FLEE, 0.0, 0.99)
    assert near.state.player.hp == 100 and {"type": "heal", "side": "player", "amount": 10} in near.events


def test_regen_heals_at_the_end_of_each_round_then_ends():
    spec = ability("flow", "SUPPORT", 10, stat="power", duration=1, effects=(fx("regen", percentage=25, rounds=3),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s, player=FighterState(50)), use(spec), FLEE, 0.0, 0.99)
    assert out.state.player.hp == 60 and {"type": "tick", "side": "player", "kind": "regen", "amount": 10, "hp": 60} in out.events
    state = out.state
    for expected in (70, 80, 80):
        state = step(s, state, FLEE, FLEE, *IDLE).state
        assert state.player.hp == expected
    assert state.player.statuses == ()


def test_bleed_hurts_at_the_end_of_each_round_and_expires():
    spec = ability("bite", "ATTACK", 100, effects=(fx("bleed", percentage=25, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert out.state.wild.hp == 100 - 40 - 10 and get(out.state.wild, "bleed").amount == 10
    assert {"type": "status", "side": "player", "target": "wild", "status": "bleed", "amount": 10, "rounds": 2} in out.events
    second = step(s, out.state, FLEE, FLEE, *IDLE)
    assert second.state.wild.hp == 40 and second.state.wild.statuses == ()
    assert step(s, second.state, FLEE, FLEE, *IDLE).state.wild.hp == 40


def test_a_bleed_that_kills_ends_the_battle_and_the_wild_side_is_checked_first():
    s = setup()

    def bleeding(hp):
        return FighterState(hp, statuses=(Status("bleed", 10, 2),))

    wild = step(s, state_of(s, wild=bleeding(8)), FLEE, FLEE, *IDLE)
    assert wild.terminal == "won" and wild.state.round == 1
    assert step(s, state_of(s, player=bleeding(8)), FLEE, FLEE, *IDLE).terminal == "knocked_out"
    assert step(s, state_of(s, player=bleeding(8), wild=bleeding(8)), FLEE, FLEE, *IDLE).terminal == "won"


def test_a_ward_leaves_one_hp_once():
    s = setup()
    warded = FighterState(30, statuses=(Status("ward", 0, 2),))
    out = step(s, state_of(s, player=warded), FLEE, ATTACK, 0.99, 0.99)  # the wild attacks first; the player's flee fails
    assert out.state.player.hp == 1 and out.terminal is None and "ward" not in ids(out.state.player)
    assert {"type": "ward_triggered", "side": "player"} in out.events
    assert step(s, out.state, FLEE, ATTACK, 0.99, 0.99).terminal == "knocked_out"


def test_a_ward_also_saves_from_a_bleed_and_is_used_up():
    s = setup()
    state = state_of(s, player=FighterState(5, statuses=(Status("bleed", 10, 3), Status("ward", 0, 3))))
    out = step(s, state, FLEE, FLEE, *IDLE)
    assert out.terminal is None and out.state.player.hp == 1 and "ward" not in ids(out.state.player)
    assert step(s, out.state, FLEE, FLEE, *IDLE).terminal == "knocked_out"


def test_slow_and_weaken_lower_speed_and_power_with_a_floor_of_one():
    spec = ability("chill", "ATTACK", 100, effects=(fx("slow", percentage=50, rounds=2), fx("weaken", percentage=25, rounds=2)))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert engine.stat(s.wild, out.state.wild, "speed") == 10 and engine.stat(s.wild, out.state.wild, "power") == 30
    harsh = ability("freeze", "ATTACK", 100, effects=(fx("slow", percentage=900, rounds=2),))
    s2 = setup(fighter(PLAYER, abilities=(harsh,)), fighter(WILD))
    out2 = step(s2, state_of(s2), use(harsh), FLEE, 0.0, 0.99)
    assert engine.stat(s2.wild, out2.state.wild, "speed") == 1


def test_exposed_weakens_the_targets_shield():
    shield = ability("wall", "DEFENSE", 100)
    s = setup(fighter(PLAYER), fighter(WILD, abilities=(shield,)))
    plain = step(s, state_of(s), ATTACK, use(shield), 0.0)
    exposed = step(s, state_of(s, wild=FighterState(100, statuses=(Status("exposed", 20, 2),))), ATTACK, use(shield), 0.0)
    assert 100 - plain.state.wild.hp == 28 and 100 - exposed.state.wild.hp == 33


def test_an_exposed_effect_puts_the_status_on_the_target():
    spec = ability("break", "ATTACK", 100, effects=(fx("exposed", percentage=50, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert get(out.state.wild, "exposed").amount == 20


def test_marks_sit_on_the_chosen_target_and_expire():
    spec = ability("brand", "ATTACK", 100, effects=(fx("mark", name="prey", rounds=3, target="foe"),
                                                    fx("mark", name="soaked", rounds=2, target="self")))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert get(out.state.wild, "mark:prey").rounds_left == 2 and get(out.state.player, "mark:soaked").rounds_left == 1
    later = step(s, step(s, out.state, FLEE, FLEE, *IDLE).state, FLEE, FLEE, *IDLE).state
    assert "mark:soaked" not in ids(later.player) and "mark:prey" not in ids(later.wild)


def test_cleanse_removes_the_four_harmful_statuses_only():
    spec = ability("clear", "DEFENSE", 100, effects=(fx("cleanse"),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    statuses = (Status("bleed", 5, 3), Status("slow", -3, 3), Status("weaken", -3, 3), Status("exposed", 4, 3),
                Status("mark:prey", 0, 3), Status("regen", 5, 3), Status("ward", 0, 3))
    out = step(s, state_of(s, player=FighterState(50, statuses=statuses)), use(spec), FLEE, 0.0, 0.99)
    assert ids(out.state.player) == {"mark:prey", "regen", "ward"}
    assert {"type": "cleanse", "side": "player", "removed": ["bleed", "slow", "weaken", "exposed"]} in out.events


def test_applying_a_status_again_refreshes_it_instead_of_stacking():
    spec = ability("bite", "ATTACK", 100, effects=(fx("bleed", percentage=25, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    old = FighterState(100, statuses=(Status("bleed", 3, 1),))
    out = step(s, state_of(s, wild=old), use(spec), FLEE, 0.0, 0.99)
    bleeds = [st for st in out.state.wild.statuses if st.id == "bleed"]
    assert len(bleeds) == 1 and bleeds[0].amount == 10 and bleeds[0].rounds_left == 1  # two rounds, one tick done


def test_attack_effects_do_not_apply_when_the_attack_wins_the_battle():
    spec = ability("bite", "ATTACK", 100, effects=(fx("bleed", percentage=25, rounds=2),))
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s, wild=FighterState(30)), use(spec), FLEE, 0.0, 0.99)
    assert out.terminal == "won" and not any(e["type"] == "status" for e in out.events)


def test_an_ability_without_effects_changes_no_statuses():
    spec = ability("plain", "ATTACK", 100)
    s = setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD))
    out = step(s, state_of(s), use(spec), FLEE, 0.0, 0.99)
    assert out.state.player.statuses == () and out.state.wild.statuses == () and out.state.wild.hp == 60
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_engine_effects.py -q`
Expected: FAIL (no effect is applied; some tests error on `FighterState` statuses being ignored).

- [ ] **Step 3: Write the implementation**

In `src/ascension/passives.py`, add two neutral hooks to the base `Passive` class (Task 3 adds the real kinds):

```python
    def marked_bonus(self, power: int, marks: frozenset[str]) -> float:
        """Raw damage added to an attack against a target carrying one of these marks."""
        return 0.0

    def heal_multiplier(self, hp: int, max_hp: int) -> float:
        return 1.0
```

In `src/ascension/engine.py`:

1. Add `HARMFUL, STAT_STATUS, Status` to the `models` import.
2. Replace `_Side` with:

```python
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
```
3. Replace `BattleEngine.stat`:

```python
    def stat(self, fighter: Fighter, fstate: FighterState, name: str) -> int:
        """Current POWER or SPEED including temporary buffs and slow or weaken."""
        value = getattr(fighter, name) + sum(b.amount for b in fstate.buffs if b.stat == name)
        value += sum(s.amount for s in fstate.statuses if STAT_STATUS.get(s.id) == name)
        return max(1, value)
```
4. In `resolve_round`, replace the SUPPORT and DEFENSE loops:

```python
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
```
   and the ATTACK branch of the order loop:

```python
            if action.category == "ATTACK":
                terminal = self._attack(sides, actions, side, events)
                if not terminal and action.kind == "ability":  # an ability's effects land after its hit
                    spec = self._ability(sides[side].fighter, action.ability_id)
                    self._apply_effects(sides[side], sides[other(side)], spec, sides[side].stat("power"), events)
```
   and, before `revealed = RevealedRound(...)`:

```python
        if not terminal:
            terminal = self._tick(sides, events)
```
   (the existing `if not terminal: for side_obj ... self._expire(side_obj)` stays after the `revealed` line and now also skips expiry when a bleed ended the battle).
5. Replace `_attack`:

```python
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
```
6. Add these methods to `BattleEngine` (next to `_defense`):

```python
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
```
7. Extend `_expire` (keep the existing buff and defense code) with the status countdown at the end:

```python
        me.statuses = [replace(s, rounds_left=s.rounds_left - 1) for s in me.statuses]
        me.statuses = [s for s in me.statuses if s.rounds_left > 0]
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: the new engine tests pass and every existing test is unchanged (no existing ability has effects). Only the 7 sprite failures may remain.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/engine.py apps/ascension/src/ascension/passives.py apps/ascension/tests/ascension/test_engine_effects.py
git commit -m "feat(ascension): the engine heals, bleeds, slows, marks, cleanses and wards"
```

---

### Task 3: Passives that read marks and heals

**Files:**
- Modify: `src/ascension/passives.py`
- Test: `tests/ascension/test_passives_effects.py`

**Interfaces:**
- Consumes: the `marked_bonus` and `heal_multiplier` hooks from Task 2.
- Produces: kinds `attack_bonus_vs_marked` `{mark, power_fraction}` and `heal_bonus` `{fraction, hp_below=None}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ascension/test_passives_effects.py`:

```python
import pytest

from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, Action, BattleState, EffectSpec, FighterState, PassiveSpec, Status
from src.ascension.passives import PassiveFactory
from tests.ascension.env import CATALOG
from tests.ascension.helpers import ScriptedRandom, ability, fighter, setup

engine = BattleEngine(CATALOG)
ATTACK = Action("attack", "ATTACK")
FLEE = Action("flee", "FEAR")


def damage_dealt(passive, wild_statuses):
    s = setup(fighter(PLAYER, passive=passive), fighter(WILD))
    state = BattleState(1, FighterState(100), FighterState(100, statuses=wild_statuses))
    out = engine.resolve_round(s, state, ATTACK, FLEE, ScriptedRandom(0.0, 0.99))
    return 100 - out.state.wild.hp


def test_attack_bonus_vs_marked_only_counts_its_own_mark():
    passive = PassiveSpec("attack_bonus_vs_marked", {"mark": "prey", "power_fraction": 0.5})
    assert damage_dealt(passive, ()) == 40
    assert damage_dealt(passive, (Status("mark:prey", 0, 3),)) == 60  # 40 + 50% of 40
    assert damage_dealt(passive, (Status("mark:soaked", 0, 3),)) == 40


def heal_result(passive, hp, max_hp=200):
    spec = ability("mend", "DEFENSE", 100, effects=(EffectSpec("heal", percentage=50),))
    s = setup(fighter(PLAYER, hp=max_hp, abilities=(spec,), passive=passive), fighter(WILD))
    state = BattleState(1, FighterState(hp), FighterState(100))
    out = engine.resolve_round(s, state, Action("ability", "DEFENSE", "mend", 100), FLEE, ScriptedRandom(0.0, 0.99))
    return out.state.player.hp - hp


def test_heal_bonus_always_or_only_when_low():
    assert heal_result(PassiveSpec("none"), 100) == 20
    always = PassiveSpec("heal_bonus", {"fraction": 0.5})
    assert heal_result(always, 100) == 30
    low = PassiveSpec("heal_bonus", {"fraction": 0.5, "hp_below": 0.5})
    assert heal_result(low, 150) == 20 and heal_result(low, 60) == 30


def test_the_new_kinds_are_registered_and_bad_params_fail():
    factory = PassiveFactory()
    assert factory.create(PassiveSpec("attack_bonus_vs_marked", {"mark": "prey", "power_fraction": 0.2})).marked_bonus(40, frozenset({"prey"})) == 8
    assert factory.create(PassiveSpec("heal_bonus", {"fraction": 0.25})).heal_multiplier(10, 100) == pytest.approx(1.25)
    with pytest.raises(TypeError):
        factory.create(PassiveSpec("heal_bonus", {}))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_passives_effects.py -q`
Expected: FAIL (`unknown passive kind 'attack_bonus_vs_marked'`).

- [ ] **Step 3: Write the implementation**

In `src/ascension/passives.py` add the classes (before `PassiveFactory`):

```python
class AttackBonusVersusMarked(Passive):
    def __init__(self, mark: str, power_fraction: float) -> None:
        self._mark, self._fraction = mark, power_fraction

    def marked_bonus(self, power: int, marks: frozenset[str]) -> float:
        return power * self._fraction if self._mark in marks else 0.0


class HealBonus(Passive):
    """Heals and regeneration grow by `fraction`; with `hp_below` only while own HP is below that share of max HP."""

    def __init__(self, fraction: float, hp_below: float | None = None) -> None:
        self._fraction, self._below = fraction, hp_below

    def heal_multiplier(self, hp: int, max_hp: int) -> float:
        return 1 + self._fraction if self._below is None or hp < max_hp * self._below else 1.0
```
and register them in `PassiveFactory.__init__`:

```python
            "attack_bonus_vs_marked": AttackBonusVersusMarked,
            "heal_bonus": HealBonus,
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: only the 7 sprite failures.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/passives.py apps/ascension/tests/ascension/test_passives_effects.py
git commit -m "feat(ascension): passives that read marks and heal bonuses"
```

---

### Task 4: Public view and summaries

**Files:**
- Modify: `src/ascension/battle_view.py`
- Test: `tests/ascension/test_battle_view_effects.py`

**Interfaces:**
- Produces: each fighter in the public view gets `"statuses": [{"id", "amount", "rounds_left"}...]`, and each ability in that fighter's `abilities` gets `"effects": [...]`. The catalog summary and tree summary already carry effects (`AbilitySpec.to_dict`, `TreeNode.to_public` from Task 1).

- [ ] **Step 1: Write the failing test**

Create `tests/ascension/test_battle_view_effects.py`:

```python
from dataclasses import replace

from src.ascension.battle_view import BattleViewBuilder
from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, BattleState, EffectSpec, FighterState, Status
from tests.ascension.env import CATALOG
from tests.ascension.helpers import ability, battle_record, fighter, setup


def test_the_public_view_shows_statuses_and_ability_effects():
    spec = ability("bite", "ATTACK", 100, effects=(EffectSpec("bleed", percentage=20.0, rounds=3),))
    record = replace(
        battle_record(),
        setup=setup(fighter(PLAYER, abilities=(spec,)), fighter(WILD)),
        state=BattleState(1, FighterState(100, statuses=(Status("mark:prey", 0, 2),)), FighterState(100, statuses=(Status("bleed", 5, 3),))),
    )
    view = BattleViewBuilder(BattleEngine(CATALOG), CATALOG).build(record, {}, 0.0)
    assert view["player"]["statuses"] == [{"id": "mark:prey", "amount": 0, "rounds_left": 2}]
    assert view["wild"]["statuses"] == [{"id": "bleed", "amount": 5, "rounds_left": 3}]
    assert view["player"]["abilities"][0]["effects"] == [{"kind": "bleed", "percentage": 20.0, "rounds": 3}]
    assert view["wild"]["abilities"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_battle_view_effects.py -q`
Expected: FAIL (`KeyError: 'statuses'`).

- [ ] **Step 3: Write the implementation**

In `BattleViewBuilder._fighter` add `"statuses": [s.to_dict() for s in state.statuses],` after the `"defense"` entry, and add `"effects": [e.to_dict() for e in a.effects],` inside each ability dict (before `"ready"`).

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: only the 7 sprite failures. If an existing test compares a whole fighter or ability dict of the view, add the new keys to its expected value.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/battle_view.py apps/ascension/tests/ascension/test_battle_view_effects.py
git commit -m "feat(ascension): statuses and effects in the public battle view"
```

---

### Task 5: Web: types, text and arena

**Files:**
- Modify: `web/src/api/AscensionClient.ts`, `web/src/utils/ascension.ts`, `web/src/components/BattleArena.vue`, `web/src/components/TreeTab.vue`
- Test: `web/src/utils/ascension.test.ts`, `web/src/components/BattlePanels.test.ts`, `web/src/components/TreeTab.test.ts`

**Interfaces:**
- Produces (types in `AscensionClient.ts`):

```ts
export interface EffectInfo { kind: string; percentage?: number; rounds?: number; name?: string; target?: string }
export interface Status { id: string; amount: number; rounds_left: number }
```
  `AbilityInfo`, `FighterAbility` and `TreeNodeView` get `effects?: EffectInfo[]`; `Fighter` gets `statuses?: Status[]`.
- Produces (in `utils/ascension.ts`): `effectText(effects: readonly EffectInfo[] | undefined): string` (sentences joined by ", ", empty for none), `statusText(status: Status): string`, `abilityEffect` appends ` · ` and the effect text when there are effects, `passiveText` gains the two new kinds, `describeEvent` gains `heal`, `status`, `cleanse`, `tick`, `ward_triggered`.

- [ ] **Step 1: Write the failing tests**

Add to `web/src/utils/ascension.test.ts` (import `effectText, statusText` from `./ascension`; reuse the file's `NAMES`):

```ts
describe("effects in words", () => {
  it("writes each effect kind", () => {
    expect(effectText(undefined)).toBe("");
    expect(effectText([])).toBe("");
    expect(effectText([{ kind: "heal", percentage: 50 }])).toBe("Heals 50% of power");
    expect(effectText([{ kind: "regen", percentage: 25, rounds: 3 }])).toBe("Regenerates 25% for 3 rounds");
    expect(effectText([{ kind: "bleed", percentage: 20, rounds: 1 }])).toBe("Bleeds 20% for 1 round");
    expect(effectText([{ kind: "slow", percentage: 30, rounds: 2 }, { kind: "weaken", percentage: 10, rounds: 2 }])).toBe(
      "Slows 30% for 2 rounds, Weakens 10% for 2 rounds",
    );
    expect(effectText([{ kind: "exposed", percentage: 40, rounds: 2 }])).toBe("Exposes 40% for 2 rounds");
    expect(effectText([{ kind: "mark", name: "prey", rounds: 3 }])).toBe("Marks prey for 3 rounds");
    expect(effectText([{ kind: "mark", name: "soaked", rounds: 2, target: "self" }])).toBe("Gains the soaked mark for 2 rounds");
    expect(effectText([{ kind: "cleanse" }, { kind: "ward", rounds: 2 }])).toBe("Cleanses, Wards one lethal hit for 2 rounds");
  });

  it("appends effects to the ability line only when there are some", () => {
    expect(abilityEffect({ category: "ATTACK", percentage: 150, cooldown: 1 })).toBe("Attack 150% · cd 1");
    expect(abilityEffect({ category: "ATTACK", percentage: 150, cooldown: 1, effects: [{ kind: "bleed", percentage: 20, rounds: 3 }] })).toBe(
      "Attack 150% · cd 1 · Bleeds 20% for 3 rounds",
    );
  });

  it("writes statuses and the new passives and events", () => {
    expect(statusText({ id: "bleed", amount: 5, rounds_left: 2 })).toBe("bleeding 5 a round, 2 rounds left");
    expect(statusText({ id: "slow", amount: -10, rounds_left: 1 })).toBe("slowed by 10, 1 round left");
    expect(statusText({ id: "weaken", amount: -4, rounds_left: 2 })).toBe("weakened by 4, 2 rounds left");
    expect(statusText({ id: "exposed", amount: 20, rounds_left: 2 })).toBe("exposed, defense down 20, 2 rounds left");
    expect(statusText({ id: "regen", amount: 7, rounds_left: 3 })).toBe("regenerating 7 a round, 3 rounds left");
    expect(statusText({ id: "ward", amount: 0, rounds_left: 2 })).toBe("warded, 2 rounds left");
    expect(statusText({ id: "mark:prey", amount: 0, rounds_left: 1 })).toBe("marked prey, 1 round left");
    expect(passiveText("attack_bonus_vs_marked", { mark: "prey", power_fraction: 0.2 })).toBe(
      "Attacks deal extra damage equal to 20% of its Power against a target marked prey.",
    );
    expect(passiveText("heal_bonus", { fraction: 0.5 })).toBe("Heals are 50% stronger.");
    expect(passiveText("heal_bonus", { fraction: 0.5, hp_below: 0.5 })).toBe("Below 50% HP, heals are 50% stronger.");
    expect(describeEvent({ type: "heal", side: "player", amount: 12 }, NAMES)).toBe("Guardian heals 12");
    expect(describeEvent({ type: "status", side: "player", target: "wild", status: "bleed", amount: 5, rounds: 2 }, NAMES)).toBe(
      "Guardian puts bleed on Bruiser for 2 rounds",
    );
    expect(describeEvent({ type: "status", side: "player", target: "wild", status: "mark:prey", amount: 0, rounds: 1 }, NAMES)).toBe(
      "Guardian puts a prey mark on Bruiser for 1 round",
    );
    expect(describeEvent({ type: "cleanse", side: "wild", removed: ["bleed", "slow"] }, NAMES)).toBe("Bruiser cleanses bleed, slow");
    expect(describeEvent({ type: "tick", side: "wild", kind: "bleed", amount: 5, hp: 30 }, NAMES)).toBe("Bruiser bleeds for 5; 30 HP left");
    expect(describeEvent({ type: "tick", side: "player", kind: "regen", amount: 7, hp: 60 }, NAMES)).toBe("Guardian recovers 7; 60 HP");
    expect(describeEvent({ type: "ward_triggered", side: "player" }, NAMES)).toBe("Guardian is saved by a ward at 1 HP");
  });
});
```

Add to `web/src/components/BattlePanels.test.ts` (in the `BattleArena` section, using the file's existing mount helpers; follow the neighbouring arena test that sets `buffs`):

```ts
  it("lists statuses beside buffs", () => {
    const view = battleView({
      player: fighter("guardian", { statuses: [{ id: "mark:prey", amount: 0, rounds_left: 2 }] }),
      wild: fighter("bruiser", { statuses: [{ id: "bleed", amount: 5, rounds_left: 3 }] }),
    });
    const wrapper = mount(BattleArena, { props: { battle: view } });
    expect(wrapper.text()).toContain("marked prey, 2 rounds left");
    expect(wrapper.text()).toContain("bleeding 5 a round, 3 rounds left");
  });
```
(Use the same imports, `mount` call style and any required `global` plugins as the existing `BattleArena` test in that file; the assertion text is what matters.)

Add to `web/src/components/TreeTab.test.ts`:

```ts
  it("shows an ability's effects in the node detail", async () => {
    const tree = structuredClone(TREE);
    tree.nodes[3] = { ...tree.nodes[3]!, effects: [{ kind: "bleed", percentage: 20, rounds: 3 }] };
    client.tree.mockResolvedValue(tree);
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_wall"]').trigger("click");

    expect(wrapper.find(".node-detail").text()).toContain("Bleeds 20% for 3 rounds");
  });
```

- [ ] **Step 2: Run to verify failure**

Run (in `web`): `npx vitest run src/utils/ascension.test.ts src/components/BattlePanels.test.ts src/components/TreeTab.test.ts`
Expected: FAIL (`effectText` is not exported).

- [ ] **Step 3: Write the implementation**

1. `AscensionClient.ts`: add `EffectInfo` and `Status`; add `effects?: EffectInfo[]` to `AbilityInfo`, `FighterAbility` and `TreeNodeView`; add `statuses?: Status[]` to `Fighter`.
2. `utils/ascension.ts`:
   - import `EffectInfo, Status` types;
   - `passiveText`: add

```ts
    case "attack_bonus_vs_marked":
      return `Attacks deal extra damage equal to ${percent(params.power_fraction)} of its Power against a target marked ${String(params.mark)}.`;
    case "heal_bonus":
      return `${params.hp_below === undefined ? "" : `Below ${percent(params.hp_below)} HP, `}${params.hp_below === undefined ? "Heals" : "heals"} are ${percent(params.fraction)} stronger.`;
```
   - add

```ts
function rounds(effect: EffectInfo): string {
  return count(effect.rounds, 1, "round");
}

/** An ability's effects in words, joined by commas; empty when it has none. */
export function effectText(effects: readonly EffectInfo[] | undefined): string {
  return (effects ?? [])
    .map((e) => {
      switch (e.kind) {
        case "heal": return `Heals ${e.percentage}% of power`;
        case "regen": return `Regenerates ${e.percentage}% for ${rounds(e)}`;
        case "bleed": return `Bleeds ${e.percentage}% for ${rounds(e)}`;
        case "slow": return `Slows ${e.percentage}% for ${rounds(e)}`;
        case "weaken": return `Weakens ${e.percentage}% for ${rounds(e)}`;
        case "exposed": return `Exposes ${e.percentage}% for ${rounds(e)}`;
        case "mark": return e.target === "self" ? `Gains the ${e.name} mark for ${rounds(e)}` : `Marks ${e.name} for ${rounds(e)}`;
        case "cleanse": return "Cleanses";
        case "ward": return `Wards one lethal hit for ${rounds(e)}`;
        default: return titleCase(e.kind);
      }
    })
    .join(", ");
}

/** One status on a fighter, in words. */
export function statusText(status: Status): string {
  const left = `${count(status.rounds_left, 1, "round")} left`;
  if (status.id.startsWith("mark:")) return `marked ${status.id.slice("mark:".length)}, ${left}`;
  switch (status.id) {
    case "bleed": return `bleeding ${status.amount} a round, ${left}`;
    case "slow": return `slowed by ${Math.abs(status.amount)}, ${left}`;
    case "weaken": return `weakened by ${Math.abs(status.amount)}, ${left}`;
    case "exposed": return `exposed, defense down ${status.amount}, ${left}`;
    case "regen": return `regenerating ${status.amount} a round, ${left}`;
    case "ward": return `warded, ${left}`;
    default: return `${titleCase(status.id)}, ${left}`;
  }
}
```
   - `abilityEffect`:

```ts
export function abilityEffect(ability: Pick<AbilityInfo, "category" | "percentage" | "cooldown" | "effects">): string {
  const base = `${titleCase(ability.category)} ${ability.percentage}% · cd ${ability.cooldown}`;
  const extra = effectText(ability.effects);
  return extra ? `${base} · ${extra}` : base;
}
```
   - `describeEvent`: add these cases before `default`:

```ts
    case "heal":
      return `${who} heals ${String(event.amount)}`;
    case "status": {
      const target = sideName(event.target, names);
      const id = String(event.status);
      const what = id.startsWith("mark:") ? `a ${id.slice("mark:".length)} mark` : id;
      return `${who} puts ${what} on ${target} for ${count(event.rounds, 1, "round")}`;
    }
    case "cleanse":
      return `${who} cleanses ${(event.removed as string[]).join(", ") || "nothing"}`;
    case "tick":
      return event.kind === "bleed"
        ? `${who} bleeds for ${String(event.amount)}; ${String(event.hp)} HP left`
        : `${who} recovers ${String(event.amount)}; ${String(event.hp)} HP`;
    case "ward_triggered":
      return `${who} is saved by a ward at 1 HP`;
```
   (`who` is the side that holds the status for `tick`, `heal`, `cleanse` and `ward_triggered`, and the caster for `status`, which the engine events already do.)
3. `BattleArena.vue`: import `statusText` from `../utils/ascension` and `Status` is not needed; in `effects(fighter)` add before `return list`:

```ts
  for (const status of fighter.statuses ?? []) list.push(statusText(status));
```
4. `TreeTab.vue`: in `detail()` for ability nodes, append the effect text:

```ts
  const effect = effectText(node.effects);
  return effect ? `${bits.join(", ")}. ${effect}.` : bits.join(", ");
```
   (import `effectText` next to `passiveText`).

- [ ] **Step 4: Run all web checks**

Run (in `web`): `npx vue-tsc --noEmit` then `npx vitest run`
Expected: type check clean; all tests pass. If an existing test asserts the exact text of `describeEvent` default or an ability line, it should be unaffected (no effects, no new events).

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/web/src
git commit -m "feat(ascension): show statuses and effects in the web UI"
```

---

### Task 6: Docs and vault

**Files:**
- Modify: `apps/ascension/README.md`, `apps/ascension/ascended/twoychi/ability_design.md`, `docs/superpowers/specs/2026-10-12-ascension-effects-design.md` (status line)
- Create: vault `Brain/Notes/Decision - Abilities get effects and fighters get statuses.md`
- Modify: vault `Brain/Projects/Ascension.md`

- [ ] **Step 1: README.** Add a section "Effects" after "Ability trees": the effect kinds and their fields, the phases (SUPPORT, DEFENSE, ATTACK on hit), the end-of-round tick order, statuses and stacking, the ward and cleanse rules, the two passive kinds, and one worked JSON example. Add `effects` to the ability fields wherever the README lists them.
- [ ] **Step 2: Twoychi design doc.** At the top of `ability_design.md` add a short note: "Healing, bleed, slow, weaken, exposed, marks, cleanse and ward now exist in the engine (see the README, Effects). The tree has not been converted yet; the rows marked later that need only these mechanics can now become real." Do not change the table rows.
- [ ] **Step 3: Spec.** Change the spec's status line to `Status: built.`
- [ ] **Step 4: Vault.** Create the decision note (frontmatter `type: note`, `status: active`, `tags: [decision, games]`, `created`; sections from the Decision template; link `[[Ascension]]` and `[[MCPServer]]`), add one bullet to `Brain/Projects/Ascension.md` under "Python game (MCPServer)" linking it, and set `last_synced`. Run `py ../.claude/hooks/validate_vault.py --all` from `Brain`.
- [ ] **Step 5: Run everything and commit**

Run: `.venv_ascension\Scripts\python -m pytest -q` and, in `web`, `npx vitest run`.
Expected: only the 7 sprite failures; web green.

```bash
git add apps/ascension/README.md apps/ascension/ascended/twoychi/ability_design.md docs/superpowers/specs/2026-10-12-ascension-effects-design.md
git commit -m "docs(ascension): effects"
```
and, in `Brain`: `git add Notes Projects/Ascension.md && git commit -m "docs: Ascension effects decision"`.

---

## Self-review against the spec

- Effect kinds, fields and validation: Task 1 (`parse_effects`, catalog and tree nodes, at most 3, marks need a name).
- State: `FighterState.statuses`, old saves load: Task 1 tests; slow and weaken in `stat` with the floor: Task 2.
- Phases (SUPPORT unbuffed power, DEFENSE and ATTACK current power; ATTACK effects only on a non-lethal hit): Task 2.
- Tick order, bleed kill, tie rule, ward from attack and bleed, cleanse set, refresh not stack, exposed shield: Task 2 tests.
- Passives `attack_bonus_vs_marked` and `heal_bonus` with `hp_below`: Task 3.
- Public view statuses and ability effects, catalog and tree summaries: Tasks 1 and 4.
- UI: statuses in the arena, `effectText` in the tree detail and ability lines, event log lines: Task 5.
- "No effects means identical behaviour" is held by every existing test staying green after each task.
- Mood meters ignoring bleed ticks and the policy not knowing about heals are left as follow-ups, as the spec says.
- Type and name consistency: `EffectSpec`, `Status`, `STAT_STATUS`, `HARMFUL`, `parse_effects`, `marked_bonus`, `heal_multiplier`, `_apply_effects`, `_tick`, `_ward`, `EffectInfo`, `effectText`, `statusText`.
