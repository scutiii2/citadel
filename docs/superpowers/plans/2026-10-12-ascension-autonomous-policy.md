# Ascension Autonomous Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign how an Ascended picks its action on its own: choose a category first (so the number of abilities in a category no longer skews it), then an action inside it; let personalities read the match (winning, losing, streaks, damage taken), keep hidden mood meters, and add 14 new personalities.

**Architecture:** Two new pure modules, `match_state.py` (derives `MatchState` and `MoodMeters` from the battle history, nothing stored) and `personality_rules.py` (rule parsing and conditions). `policy.py` becomes two-stage and applies the rules that fire. `ActionDecider` builds the match state and passes it in. Personality rules live in `configs/ascension_catalog.json`, so balance is data.

**Tech Stack:** Python 3.14, pytest.

**Spec:** `docs/superpowers/specs/2026-10-12-ascension-autonomous-policy-design.md`. This plan makes two decisions the spec left open (see Global Constraints).

## Global Constraints

- Work in `apps/ascension`. Run Python tests with `.venv_ascension\Scripts\python -m pytest -q`.
- Known baseline: 8 Python tests fail only because of sprite files (test_api sprite tests, test_ascended_layout, two sprite tests in test_catalog). Ignore exactly those.
- The policy stays pure and synchronous. No new random draws: the decider keeps drawing exactly twice (mood lead, final choice) when it has personalities, because many tests script the draws. Anything "random" in a rule is a deterministic function of the match.
- Nothing new is saved. `MatchState` and `MoodMeters` are recomputed from `state.history` on every decision, so a restarted battle decides identically.
- Laya or heuristic situation reads, the mood-lead draw and `Mood.weights` are unchanged.
- **Decision 1 (spec open question):** the per-ability `style` tags are dropped. Within-category variety comes from `pick_by_percentage`, `repeat` and the potency term.
- **Decision 2 (spec amendment):** rules also support a `stay` effect (multiplier on the category the Ascended chose last). Stubborn needs it. The effects are `multiply`, `chaos`, `counter`, `copy_enemy`, `break_streak`, `stay`, `repeat`, `pick_by_percentage`.
- A rule's strength is `tier / 3`, times the off-mood factor for instances that are not leading this round.
- All rule numbers are first guesses (?).
- Never commit the unrelated dirty files in the working tree (Ember web, sprites). Add only the files each task names.
- Commit messages end with: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

## File Structure

| File | Change |
|---|---|
| `src/ascension/match_state.py` | New. `MoodConstants`, `MatchState`, `MoodMeters`, `MatchReader`. |
| `src/ascension/personality_rules.py` | New. `Rule`, `ActiveRule`, `parse_rules`, `holds`. |
| `src/ascension/catalog.py` | Policy gets new fields and `mood`; personalities get `rules`; validation. |
| `src/ascension/policy.py` | Two-stage `explain`, rule effects, `Mood.active_rules`, `PolicyContext` gets `match`, `meters`, `rules`. |
| `src/ascension/decider.py` | Build match and meters, pass rules, richer audit. |
| `src/ascension/simulation.py` | `Combatant.loadout`. |
| `configs/ascension_catalog.json` | Policy constants and 14 new personalities. |
| `tests/ascension/...` | `test_personality_rules.py`, `test_match_state.py`, `test_policy.py` (edit), `test_decider_match.py`, `test_new_personalities.py`, edits to `helpers.py`, `test_api.py`, `test_encounters.py`, `test_collection.py`, `test_simulation.py`. |

---

### Task 1: Rules and catalog support

**Files:**
- Create: `src/ascension/match_state.py` (only `MoodConstants`, `MatchState`, `MoodMeters` in this task)
- Create: `src/ascension/personality_rules.py`
- Modify: `src/ascension/catalog.py`
- Test: `tests/ascension/test_personality_rules.py`

**Interfaces:**
- Produces:
  - `MoodConstants(rage_decay=0.5, rage_gain=4.0, confidence_step=0.2, nerves_follow=0.5, enemy_low=0.3, streak_base=2, streak_span=3)` (frozen dataclass)
  - `MatchState(own_hp=1.0, enemy_hp=1.0, lead=0.0, trend=0.0, round=1, own_streak=0, own_last=None, enemy_last=None, hit_taken=0.0, enemy_low=False)` with `to_dict()`
  - `MoodMeters(rage=0.0, confidence=0.5, nerves=0.0)` with `to_dict()`
  - `Rule(when: Mapping, effects: Mapping)`, `ActiveRule(name: str, rule: Rule, strength: float)`
  - `parse_rules(raw, where) -> tuple[Rule, ...]` (raises `ValueError`), `holds(when, match, meters) -> bool`
  - `PolicySpec` new fields (all with defaults): `potency_weight=0.3`, `pick_weight=1.5`, `temperature=0.7`, `counter_boost=3.0`, `mood=MoodConstants()`
  - `PersonalitySpec.rules: tuple[Rule, ...] = ()`; a personality may now have no categories.

- [ ] **Step 1: Write the failing tests**

Create `tests/ascension/test_personality_rules.py`:

```python
import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.personality_rules import holds, parse_rules
from tests.ascension.env import load_raw


def test_a_valid_rule_list_parses():
    rules = parse_rules([
        {"when": {"nerves_over": 0.5, "enemy_low": False}, "chaos": 0.6},
        {"multiply": {"ATTACK": 1.5, "FEAR": 0.5}, "stay": 2.0, "repeat": 1.0, "pick_by_percentage": "high"},
        {"counter": True}, {"copy_enemy": True}, {"break_streak": True},
    ], "personality 'X'")
    assert len(rules) == 5 and rules[0].when == {"nerves_over": 0.5, "enemy_low": False} and rules[0].effects == {"chaos": 0.6}
    assert rules[2].when == {} and rules[2].effects == {"counter": True}


@pytest.mark.parametrize("raw,message", [
    ("nope", "must be a list"),
    ([5], "must be an object"),
    ([{"chaos": 0.5, "color": "red"}], "unknown key 'color'"),
    ([{"when": {"mood_over": 1}, "chaos": 0.5}], "unknown condition"),
    ([{"when": {"lead_over": "high"}, "chaos": 0.5}], "lead_over needs a number"),
    ([{"when": {"enemy_low": 1}, "chaos": 0.5}], "enemy_low needs true or false"),
    ([{"when": {"enemy_last_is": "DANCE"}, "chaos": 0.5}], "enemy_last_is needs a category"),
    ([{"when": {"lead_over": 0}}], "at least one effect"),
    ([{"multiply": {"DANCE": 2}}], "multiply"),
    ([{"multiply": {"ATTACK": 0}}], "multiply"),
    ([{"chaos": 1.5}], "chaos"),
    ([{"counter": False}], "counter"),
    ([{"stay": -1}], "stay"),
    ([{"repeat": 1.5}], "repeat"),
    ([{"pick_by_percentage": "middle"}], "pick_by_percentage"),
])
def test_a_bad_rule_is_rejected_with_a_clear_message(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_rules(raw, "personality 'X'")


M = MatchState(own_hp=0.4, enemy_hp=0.2, lead=0.2, round=5, own_streak=3, own_last="ATTACK", enemy_last="SUPPORT", hit_taken=0.2, enemy_low=True)
K = MoodMeters(rage=0.7, confidence=0.9, nerves=0.1)


@pytest.mark.parametrize("when,expected", [
    ({}, True),
    ({"lead_over": 0.1}, True), ({"lead_over": 0.2}, False), ({"lead_under": 0.3}, True), ({"lead_under": 0.2}, False),
    ({"own_hp_under": 0.5}, True), ({"own_hp_under": 0.4}, False),
    ({"enemy_low": True}, True), ({"enemy_low": False}, False),
    ({"rage_over": 0.6}, True), ({"rage_over": 0.7}, False),
    ({"confidence_over": 0.8}, True), ({"nerves_over": 0.5}, False),
    ({"hit_taken_over": 0.1}, True), ({"streak_over": 2}, True), ({"streak_over": 3}, False),
    ({"round_under": 6}, True), ({"round_under": 5}, False), ({"round_over": 4}, True),
    ({"enemy_last_is": "SUPPORT"}, True), ({"enemy_last_is": "ATTACK"}, False),
    ({"lead_over": 0.1, "nerves_over": 0.5}, False),  # every condition must hold
])
def test_conditions_read_the_match_and_the_mood(when, expected):
    assert holds(when, M, K) is expected


def build(raw_personality):
    data = copy.deepcopy(load_raw())
    data["personalities"].append(raw_personality)
    return Catalog(data)


def test_a_personality_may_have_rules_and_no_categories():
    catalog = build({"id": "TESTY", "categories": [], "rules": [{"counter": True}]})
    spec = catalog.personalities["TESTY"]
    assert spec.categories == () and spec.rules[0].effects == {"counter": True}


def test_the_catalog_rejects_a_bad_rule_and_bad_policy_numbers():
    with pytest.raises(CatalogError, match="unknown condition"):
        build({"id": "TESTY", "categories": [], "rules": [{"when": {"x": 1}, "chaos": 0.5}]})
    data = copy.deepcopy(load_raw())
    data["policy"]["temperature"] = 0
    with pytest.raises(CatalogError, match="temperature"):
        Catalog(data)
    data = copy.deepcopy(load_raw())
    data["policy"]["mood"] = {"rage_decay": 2.0}
    with pytest.raises(CatalogError, match="mood"):
        Catalog(data)


def test_the_shipped_policy_has_the_defaults():
    policy = Catalog(load_raw()).policy
    assert (policy.potency_weight, policy.pick_weight, policy.temperature, policy.counter_boost) == (0.3, 1.5, 0.7, 3.0)
    assert policy.mood.streak_base == 2 and policy.mood.streak_span == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_personality_rules.py -q`
Expected: FAIL (`ModuleNotFoundError: src.ascension.match_state`).

- [ ] **Step 3: Write the implementation**

Create `src/ascension/match_state.py` (the reader comes in Task 2):

```python
"""What an Ascended can read about the match, and the hidden mood it builds.

Both are derived from public battle state and its history, so nothing is saved and a
restarted battle decides identically. Pure: no database, clock or model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MoodConstants:
    """How fast the mood meters move. Set under `policy.mood` in the catalog."""

    rage_decay: float = 0.5  # share of rage kept each round
    rage_gain: float = 4.0  # rage per fraction of max HP lost in a round
    confidence_step: float = 0.2  # confidence change when the HP lead grows or shrinks
    nerves_follow: float = 0.5  # share of the gap to the target that nerves closes each round
    enemy_low: float = 0.3  # enemy HP fraction below which it counts as low
    streak_base: int = 2  # a hidden streak limit of streak_base to streak_base + streak_span - 1 rounds
    streak_span: int = 3


@dataclass(frozen=True)
class MatchState:
    own_hp: float = 1.0  # HP fractions
    enemy_hp: float = 1.0
    lead: float = 0.0  # own_hp - enemy_hp, from -1 to 1
    trend: float = 0.0  # change of lead over the last two rounds
    round: int = 1
    own_streak: int = 0  # how many rounds in a row it chose its last category
    own_last: str | None = None
    enemy_last: str | None = None
    hit_taken: float = 0.0  # own HP lost last round, as a fraction of max HP
    enemy_low: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class MoodMeters:
    rage: float = 0.0
    confidence: float = 0.5
    nerves: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in self.__dict__.items()}
```

Create `src/ascension/personality_rules.py`:

```python
"""Personality rules: a condition on the match, and an effect on the choice.

A rule is data from the catalog. `holds` decides whether its condition is met;
the policy applies the effects of every rule that holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.models import CATEGORIES

NUMBER_CONDITIONS = (
    "lead_over", "lead_under", "own_hp_under", "rage_over", "confidence_over", "nerves_over",
    "hit_taken_over", "streak_over", "round_under", "round_over",
)
EFFECTS = ("multiply", "chaos", "counter", "copy_enemy", "break_streak", "stay", "repeat", "pick_by_percentage")


@dataclass(frozen=True)
class Rule:
    when: Mapping[str, Any]
    effects: Mapping[str, Any]


@dataclass(frozen=True)
class ActiveRule:
    """A rule of one personality instance this round, with its strength (tier / 3, less if it is not leading)."""

    name: str
    rule: Rule
    strength: float


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_effects(effects: Mapping[str, Any], at: str) -> None:
    for key, value in effects.items():
        if key == "multiply":
            ok = isinstance(value, Mapping) and value and all(c in CATEGORIES and _number(f) and f > 0 for c, f in value.items())
        elif key == "chaos":
            ok = _number(value) and 0 < value <= 1
        elif key in ("counter", "copy_enemy", "break_streak"):
            ok = value is True
        elif key == "stay":
            ok = _number(value) and value > 0
        elif key == "repeat":
            ok = _number(value) and 0 < value <= 1
        else:  # pick_by_percentage
            ok = value in ("high", "low")
        if not ok:
            raise ValueError(f"{at}: bad value for {key}")


def parse_rules(raw: Any, where: str) -> tuple[Rule, ...]:
    """Validate a personality's rules. Raises ValueError with the place and the problem."""
    if not isinstance(raw, list):
        raise ValueError(f"{where}: rules must be a list")
    rules = []
    for index, item in enumerate(raw):
        at = f"{where} rule {index}"
        if not isinstance(item, Mapping):
            raise ValueError(f"{at}: must be an object")
        unknown = set(item) - {"when"} - set(EFFECTS)
        if unknown:
            raise ValueError(f"{at}: unknown key {sorted(unknown)[0]!r}")
        when = item.get("when", {})
        if not isinstance(when, Mapping):
            raise ValueError(f"{at}: when must be an object")
        for key, value in when.items():
            if key in NUMBER_CONDITIONS:
                if not _number(value):
                    raise ValueError(f"{at}: {key} needs a number")
            elif key == "enemy_low":
                if not isinstance(value, bool):
                    raise ValueError(f"{at}: enemy_low needs true or false")
            elif key == "enemy_last_is":
                if value not in CATEGORIES:
                    raise ValueError(f"{at}: enemy_last_is needs a category")
            else:
                raise ValueError(f"{at}: unknown condition {key!r}")
        effects = {k: v for k, v in item.items() if k != "when"}
        if not effects:
            raise ValueError(f"{at}: needs at least one effect")
        _check_effects(effects, at)
        rules.append(Rule(dict(when), effects))
    return tuple(rules)


def holds(when: Mapping[str, Any], match: MatchState, meters: MoodMeters) -> bool:
    """True when every condition is met. An empty condition always holds."""
    checks = {
        "lead_over": lambda v: match.lead > v, "lead_under": lambda v: match.lead < v,
        "own_hp_under": lambda v: match.own_hp < v, "enemy_low": lambda v: match.enemy_low is v,
        "rage_over": lambda v: meters.rage > v, "confidence_over": lambda v: meters.confidence > v,
        "nerves_over": lambda v: meters.nerves > v, "hit_taken_over": lambda v: match.hit_taken > v,
        "streak_over": lambda v: match.own_streak > v, "round_under": lambda v: match.round < v,
        "round_over": lambda v: match.round > v, "enemy_last_is": lambda v: match.enemy_last == v,
    }
    return all(checks[key](value) for key, value in when.items())
```

In `src/ascension/catalog.py`:
1. Imports: `from src.ascension.match_state import MoodConstants` and `from src.ascension.personality_rules import Rule, parse_rules`.
2. `PolicySpec`: add after `coefficients`:

```python
    potency_weight: float = 0.3  # stage 2: weight of how strong an ability is inside its category
    pick_weight: float = 1.5  # stage 2: weight of pick_by_percentage rules
    temperature: float = 0.7  # stage 2: softmax temperature
    counter_boost: float = 3.0  # stage 1: boost of the counter or copied category at full strength
    mood: MoodConstants = MoodConstants()
```
3. `PersonalitySpec`: add `rules: tuple[Rule, ...] = ()`.
4. In `_build`, replace the personalities construction:

```python
        personalities = [PersonalitySpec(p["id"], tuple(p["categories"]), self._rules(p)) for p in _require(raw, "personalities", "catalog")]
```
   and the policy construction:

```python
        policy = dict(_require(raw, "policy", "catalog"))
        policy["mood"] = MoodConstants(**policy.get("mood", {}))
        self.policy = PolicySpec(**policy)
```
   and add this method on `Catalog`:

```python
    @staticmethod
    def _rules(raw_personality: Mapping[str, Any]) -> tuple[Rule, ...]:
        try:
            return parse_rules(raw_personality.get("rules", []), f"personality {raw_personality['id']!r}")
        except ValueError as error:
            raise CatalogError(str(error)) from error
```
5. In `_validate`, replace the personality loop and add the policy checks:

```python
        for personality in self.personalities.values():
            if any(c not in CATEGORIES for c in personality.categories):
                raise CatalogError(f"personality {personality.id!r} has invalid categories")
        p, m = self.policy, self.policy.mood
        if p.temperature <= 0 or p.potency_weight < 0 or p.pick_weight < 0 or p.counter_boost < 1 or not 0 < p.repeat_factor <= 1:
            raise CatalogError("policy needs temperature > 0, potency_weight and pick_weight >= 0, counter_boost >= 1 and 0 < repeat_factor <= 1")
        if not (0 <= m.rage_decay <= 1 and m.rage_gain >= 0 and m.confidence_step >= 0 and 0 <= m.nerves_follow <= 1
                and 0 <= m.enemy_low <= 1 and m.streak_base >= 1 and m.streak_span >= 1):
            raise CatalogError("policy mood numbers are out of range")
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension -q`
Expected: the new tests pass; only the 8 sprite failures remain.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/match_state.py apps/ascension/src/ascension/personality_rules.py apps/ascension/src/ascension/catalog.py apps/ascension/tests/ascension/test_personality_rules.py
git commit -m "feat(ascension): personality rules and policy constants in the catalog"
```

---

### Task 2: Match reading and mood meters

**Files:**
- Modify: `src/ascension/match_state.py` (add `MatchReader`)
- Modify: `tests/ascension/helpers.py` (add `revealed_round`)
- Test: `tests/ascension/test_match_state.py`

**Interfaces:**
- Consumes: `MoodConstants`, `MatchState`, `MoodMeters`.
- Produces: `MatchReader(constants: MoodConstants)` with `read(setup: BattleSetup, state: BattleState, side: str) -> tuple[MatchState, MoodMeters]`. Attack events (`type == "attack"`, `side` is the attacker, `damage`) in `state.history` drive everything. Helper `revealed_round(number, player=("attack","ATTACK"), wild=("attack","ATTACK"), hits=())` in `tests/ascension/helpers.py` where `hits` is `(attacker_side, damage)` pairs.

**Formulas (exact):** replay the history round by round with both HPs starting at `max_hp`. For each round: `taken` and `dealt` are the damage summed from attack events; update both HPs (floor at 0); `lead = own_frac - enemy_frac`; `hit = taken / own_max_hp`; `rage = clamp(rage * rage_decay + hit * rage_gain)`; if `lead` grew by more than 1e-9 `confidence = clamp(confidence + confidence_step)`, if it shrank `confidence = clamp(confidence - confidence_step)`; `target = clamp(max(0, -lead) + max(0, 0.5 - own_frac))`; `nerves = clamp(nerves + nerves_follow * (target - nerves))`. `clamp` is to 0 to 1; confidence starts at 0.5. The `MatchState` uses the current `state` HP, `trend = leads[-1] - leads[max(0, len(leads) - 3)]` (leads starts as `[0.0]`), and the last round's `hit`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/ascension/helpers.py` (after `battle_record`):

```python
def revealed_round(number, player=("attack", "ATTACK"), wild=("attack", "ATTACK"), hits=()):
    """A finished round for history. `hits` is (attacker side, damage) pairs; they become public attack events."""
    from src.ascension.models import RevealedRound

    events = tuple({"type": "attack", "side": side, "damage": damage, "protected": False, "target_hp": 0} for side, damage in hits)
    return RevealedRound(number, {PLAYER: player, WILD: wild}, events)
```

Create `tests/ascension/test_match_state.py`:

```python
import pytest

from src.ascension.match_state import MatchReader, MoodConstants
from src.ascension.models import PLAYER, WILD, BattleState, FighterState
from tests.ascension.helpers import revealed_round as rnd, setup

reader = MatchReader(MoodConstants())
SETUP = setup()  # both fighters have 100 HP


def read(history, player_hp=100, wild_hp=100, side=PLAYER):
    state = BattleState(len(history) + 1, FighterState(player_hp), FighterState(wild_hp), tuple(history))
    return reader.read(SETUP, state, side)


def test_a_fresh_battle_reads_neutral():
    match, meters = read([])
    assert (match.own_hp, match.enemy_hp, match.lead, match.trend, match.round) == (1.0, 1.0, 0.0, 0.0, 1)
    assert (match.own_streak, match.own_last, match.enemy_last, match.hit_taken, match.enemy_low) == (0, None, None, 0.0, False)
    assert (meters.rage, meters.confidence, meters.nerves) == (0.0, 0.5, 0.0)


def test_rage_jumps_with_a_hit_and_halves_each_quiet_round():
    _, hit = read([rnd(1, hits=[(WILD, 10)])], player_hp=90)
    assert hit.rage == pytest.approx(0.4)
    _, quiet = read([rnd(1, hits=[(WILD, 10)]), rnd(2)], player_hp=90)
    assert quiet.rage == pytest.approx(0.2)
    _, big = read([rnd(1, hits=[(WILD, 40)])], player_hp=60)
    assert big.rage == 1.0  # clamped


def test_confidence_rises_when_the_lead_grows_and_falls_when_it_shrinks():
    _, up = read([rnd(1, hits=[(PLAYER, 30)])], wild_hp=70)
    assert up.confidence == pytest.approx(0.7)
    _, down = read([rnd(1, hits=[(PLAYER, 30)]), rnd(2, hits=[(WILD, 50)])], player_hp=50, wild_hp=70)
    assert down.confidence == pytest.approx(0.5)
    _, flat = read([rnd(1), rnd(2)])
    assert flat.confidence == 0.5


def test_nerves_follow_the_lead_and_low_hp():
    _, one = read([rnd(1, hits=[(WILD, 60)])], player_hp=40)
    assert one.nerves == pytest.approx(0.35)  # target 0.6 + 0.1, half way
    _, two = read([rnd(1, hits=[(WILD, 60)]), rnd(2)], player_hp=40)
    assert two.nerves == pytest.approx(0.525)
    _, winning = read([rnd(1, hits=[(PLAYER, 60)])], wild_hp=40)
    assert winning.nerves == 0.0


def test_match_state_reads_hp_lead_trend_streak_and_the_enemy():
    history = [
        rnd(1, player=("attack", "ATTACK"), wild=("attack", "ATTACK"), hits=[(PLAYER, 30)]),
        rnd(2, player=("ability:g", "DEFENSE"), wild=("ability:s", "SUPPORT"), hits=[(WILD, 20)]),
        rnd(3, player=("ability:g", "DEFENSE"), wild=("attack", "ATTACK")),
    ]
    match, _ = read(history, player_hp=80, wild_hp=70)
    assert (match.own_hp, match.enemy_hp) == (0.8, 0.7)
    assert match.lead == pytest.approx(0.1) and match.trend == pytest.approx(-0.2)  # leads 0, 0.3, 0.1, 0.1
    assert (match.own_last, match.own_streak, match.enemy_last, match.round) == ("DEFENSE", 2, "ATTACK", 4)
    assert match.hit_taken == 0.0  # nothing last round


def test_the_last_rounds_damage_is_the_hit_taken_and_a_low_enemy_is_flagged():
    match, _ = read([rnd(1, hits=[(WILD, 25)])], player_hp=75, wild_hp=20)
    assert match.hit_taken == pytest.approx(0.25) and match.enemy_low is True


def test_the_wild_side_reads_the_same_battle_from_its_own_seat():
    history = [rnd(1, hits=[(PLAYER, 30)])]
    mine, _ = read(history, wild_hp=70, side=PLAYER)
    theirs, meters = read(history, wild_hp=70, side=WILD)
    assert mine.lead == pytest.approx(0.3) and theirs.lead == pytest.approx(-0.3)
    assert theirs.hit_taken == pytest.approx(0.3) and meters.rage == 1.0  # 0.3 * 4 clamps


def test_reading_twice_gives_the_same_answer():
    history = [rnd(1, hits=[(WILD, 12)]), rnd(2, hits=[(PLAYER, 5)])]
    assert read(history, player_hp=88, wild_hp=95) == read(history, player_hp=88, wild_hp=95)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_match_state.py -q`
Expected: FAIL (`ImportError: cannot import name 'MatchReader'`).

- [ ] **Step 3: Write the implementation**

In `src/ascension/match_state.py` add the imports `from src.ascension.models import BattleSetup, BattleState, other` and append:

```python
def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class MatchReader:
    """Reads one side's view of the match, and replays the history to get its mood meters."""

    def __init__(self, constants: MoodConstants) -> None:
        self._c = constants

    def read(self, setup: BattleSetup, state: BattleState, side: str) -> tuple[MatchState, MoodMeters]:
        foe = other(side)
        own, enemy = setup.of(side), setup.of(foe)
        c = self._c
        own_hp, enemy_hp = float(own.max_hp), float(enemy.max_hp)
        rage, confidence, nerves, hit = 0.0, 0.5, 0.0, 0.0
        leads = [0.0]
        for revealed in state.history:
            attacks = [e for e in revealed.events if e.get("type") == "attack"]
            taken = sum(e["damage"] for e in attacks if e["side"] == foe)
            dealt = sum(e["damage"] for e in attacks if e["side"] == side)
            own_hp, enemy_hp = max(0.0, own_hp - taken), max(0.0, enemy_hp - dealt)
            own_fraction, enemy_fraction = own_hp / own.max_hp, enemy_hp / enemy.max_hp
            lead = own_fraction - enemy_fraction
            hit = taken / own.max_hp
            rage = _clamp(rage * c.rage_decay + hit * c.rage_gain)
            if lead > leads[-1] + 1e-9:
                confidence = _clamp(confidence + c.confidence_step)
            elif lead < leads[-1] - 1e-9:
                confidence = _clamp(confidence - c.confidence_step)
            target = _clamp(max(0.0, -lead) + max(0.0, 0.5 - own_fraction))
            nerves = _clamp(nerves + c.nerves_follow * (target - nerves))
            leads.append(lead)
        own_now, enemy_now = state.of(side).hp / own.max_hp, state.of(foe).hp / enemy.max_hp
        mine = [r.actions[side][1] for r in state.history]
        theirs = [r.actions[foe][1] for r in state.history]
        streak = 0
        for category in reversed(mine):
            if category != mine[-1]:
                break
            streak += 1
        match = MatchState(
            own_hp=own_now, enemy_hp=enemy_now, lead=own_now - enemy_now,
            trend=leads[-1] - leads[max(0, len(leads) - 3)], round=state.round, own_streak=streak,
            own_last=mine[-1] if mine else None, enemy_last=theirs[-1] if theirs else None,
            hit_taken=hit, enemy_low=enemy_now < c.enemy_low,
        )
        return match, MoodMeters(rage, confidence, nerves)
```

(`state.of(foe)` is the opponent's `FighterState`; `BattleState.of` already exists.)

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_match_state.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/match_state.py apps/ascension/tests/ascension/helpers.py apps/ascension/tests/ascension/test_match_state.py
git commit -m "feat(ascension): read the match and replay the mood meters from history"
```

---

### Task 3: Two-stage policy with rule effects

**Files:**
- Modify: `src/ascension/policy.py` (rewrite as below)
- Test: `tests/ascension/test_policy.py` (edit two tests, add the new ones)

**Interfaces:**
- Consumes: Tasks 1 and 2 (`MatchState`, `MoodMeters`, `ActiveRule`, `holds`, `PolicySpec` new fields).
- Produces:
  - `PolicyContext(situation, enemy_hp_fraction, enemy_flee_share, collector, recent_keys, weights, match=None, meters=None, rules=())` (the first six fields keep their order).
  - `PolicyDecision(action, probabilities, details=None)`.
  - `Explanation(probabilities: list[float], categories: dict[str, float], fired: list[str])` with `audit() -> dict`.
  - `ActionPolicy.explain(actions, ctx) -> Explanation`; `probabilities` and `choose` use it. `choose` puts `explanation.audit()` in `PolicyDecision.details`.
  - `Mood.active_rules(instances, lead) -> tuple[ActiveRule, ...]` (names `"<TYPE>#<index>"`, strength `tier / 3`, times `off_mood_factor` when the instance is not the lead).

- [ ] **Step 1: Write the failing tests**

In `tests/ascension/test_policy.py`:

1. Change the imports to add `MatchState, MoodMeters, ActiveRule, Rule`:

```python
from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.personality_rules import ActiveRule, Rule
```
2. Replace the two tests `test_each_repeat_halves_an_actions_weight_until_another_action_breaks_the_run` and `test_stronger_abilities_are_preferred_within_a_category` with:

```python
def test_a_repeat_lowers_an_action_inside_its_category_and_leaves_other_categories_alone():
    first, second = Action("ability", "ATTACK", "first", 100), Action("ability", "ATTACK", "second", 100)
    actions = [first, second, DEFEND, FLEE]
    calm = dict(zip([a.key for a in actions], policy.probabilities(actions, ctx())))
    tired = dict(zip([a.key for a in actions], policy.probabilities(actions, ctx(recent=["ability:first", "ability:first"]))))
    assert tired["ability:first"] < calm["ability:first"] and tired["ability:second"] > calm["ability:second"]
    assert tired["ability:first"] + tired["ability:second"] == pytest.approx(calm["ability:first"] + calm["ability:second"])
    assert tired["ability:guard"] == pytest.approx(calm["ability:guard"])
    ended = dict(zip([a.key for a in actions], policy.probabilities(actions, ctx(recent=["ability:first", "ability:first", "flee"]))))
    assert ended["ability:first"] == pytest.approx(calm["ability:first"])  # the run ended at flee


def test_stronger_abilities_are_preferred_within_a_category_by_the_potency_weight():
    weak, strong = Action("ability", "ATTACK", "weak", 100), Action("ability", "ATTACK", "strong", 200)
    p = probs([weak, strong, FLEE])
    spec = CATALOG.policy
    assert p["ability:strong"] / p["ability:weak"] == pytest.approx(2 ** (spec.potency_weight / spec.temperature))


def test_the_number_of_actions_in_a_category_does_not_change_the_category():
    one = policy.explain([ATTACK, DEFEND, FLEE], ctx()).categories
    three_attacks = [ATTACK, Action("ability", "ATTACK", "a2", 150), Action("ability", "ATTACK", "a3", 120), DEFEND, FLEE]
    many = policy.explain(three_attacks, ctx()).categories
    assert many == pytest.approx(one)
    p = dict(zip([a.key for a in three_attacks], policy.probabilities(three_attacks, ctx())))
    assert p["attack"] + p["ability:a2"] + p["ability:a3"] == pytest.approx(one["ATTACK"])


def test_a_missing_category_is_not_offered_and_the_rest_share_the_mass():
    only_attacks = [ATTACK, Action("ability", "ATTACK", "a2", 150), Action("ability", "ATTACK", "a3", 150)]
    p = policy.probabilities(only_attacks, ctx())
    assert sum(p) == pytest.approx(1.0) and all(v > 0 for v in p)
```

3. Append the rule tests at the end of the file:

```python
# -- personality rules ---------------------------------------------------------------

def rule(name="R#0", strength=1.0, **effects):
    when = effects.pop("when", {})
    return ActiveRule(name, Rule(when, effects), strength)


def ruled(rules, match=None, meters=None, actions=ACTIONS, **kwargs):
    base = ctx(**kwargs)
    return PolicyContext(base.situation, base.enemy_hp_fraction, base.enemy_flee_share, base.collector, base.recent_keys, base.weights,
                         match or MatchState(), meters or MoodMeters(), tuple(rules))


def cats(rules, **kwargs):
    return policy.explain(ACTIONS, ruled(rules, **kwargs)).categories


def ratio(c, a, b):
    return c[a] / c[b]


CALM = cats([])


def test_a_rule_whose_condition_fails_changes_nothing_and_a_missing_match_ignores_rules():
    never = rule(when={"lead_over": 0.9}, multiply={"ATTACK": 5.0})
    assert cats([never]) == pytest.approx(CALM)
    no_match = PolicyContext(Situation(0.3, 0.5, 0.5), 1.0, 0.1, False, (), {}, None, None, (rule(multiply={"ATTACK": 5.0}),))
    assert policy.explain(ACTIONS, no_match).categories == pytest.approx(CALM)


def test_multiply_scales_with_strength():
    full, half = cats([rule(multiply={"ATTACK": 2.0})]), cats([rule(strength=0.5, multiply={"ATTACK": 2.0})])
    base = ratio(CALM, "ATTACK", "DEFENSE")
    assert ratio(full, "ATTACK", "DEFENSE") == pytest.approx(base * 2.0)
    assert ratio(half, "ATTACK", "DEFENSE") == pytest.approx(base * 1.5)


def test_two_firing_rules_stack_and_report_their_names():
    explanation = policy.explain(ACTIONS, ruled([rule("A#0", multiply={"ATTACK": 2.0}), rule("B#1", multiply={"ATTACK": 2.0})]))
    assert ratio(explanation.categories, "ATTACK", "DEFENSE") == pytest.approx(ratio(CALM, "ATTACK", "DEFENSE") * 4.0)
    assert explanation.fired == ["A#0", "B#1"] and explanation.audit()["fired"] == ["A#0", "B#1"]


def test_chaos_flattens_the_categories_toward_the_unlikely():
    chaotic = cats([rule(chaos=1.0)])
    most = max(CALM, key=CALM.get)
    least = min(CALM, key=CALM.get)
    assert chaotic[most] < CALM[most] and chaotic[least] > CALM[least]
    assert sum(chaotic.values()) == pytest.approx(1.0)
    assert max(chaotic.values()) - min(chaotic.values()) < max(CALM.values()) - min(CALM.values())


def test_counter_and_copy_enemy_lift_the_right_category():
    counter = cats([rule(counter=True)], match=MatchState(enemy_last="ATTACK"))
    assert ratio(counter, "DEFENSE", "SUPPORT") == pytest.approx(ratio(CALM, "DEFENSE", "SUPPORT") * CATALOG.policy.counter_boost)
    after_support = cats([rule(counter=True)], match=MatchState(enemy_last="SUPPORT"))
    assert ratio(after_support, "ATTACK", "DEFENSE") == pytest.approx(ratio(CALM, "ATTACK", "DEFENSE") * CATALOG.policy.counter_boost)
    assert cats([rule(counter=True)], match=MatchState(enemy_last="FEAR")) == pytest.approx(CALM)  # nothing counters a flee
    copy = cats([rule(copy_enemy=True)], match=MatchState(enemy_last="SUPPORT"))
    assert ratio(copy, "SUPPORT", "DEFENSE") == pytest.approx(ratio(CALM, "SUPPORT", "DEFENSE") * CATALOG.policy.counter_boost)


def test_stay_lifts_the_category_it_chose_last():
    stay = cats([rule(stay=3.0)], match=MatchState(own_last="DEFENSE", own_streak=1))
    assert ratio(stay, "DEFENSE", "SUPPORT") == pytest.approx(ratio(CALM, "DEFENSE", "SUPPORT") * 3.0)


def test_break_streak_leaves_the_streak_for_the_least_likely_category_only_after_the_hidden_limit():
    limit = CATALOG.policy.mood.streak_base + (1 * 7) % CATALOG.policy.mood.streak_span  # round 1
    early = cats([rule(break_streak=True)], match=MatchState(round=1, own_last="ATTACK", own_streak=limit - 1))
    assert early == pytest.approx(CALM)
    broken = cats([rule(break_streak=True)], match=MatchState(round=1, own_last="ATTACK", own_streak=limit))
    least = min((c for c in CALM if c != "ATTACK"), key=CALM.get)
    assert broken[least] == pytest.approx(1.0) and broken["ATTACK"] == pytest.approx(0.0)
    half = cats([rule(strength=0.5, break_streak=True)], match=MatchState(round=1, own_last="ATTACK", own_streak=limit))
    assert half[least] == pytest.approx(0.5 + 0.5 * CALM[least])


def test_the_hidden_streak_limit_varies_between_two_and_four_rounds():
    mood_c = CATALOG.policy.mood
    limits = {mood_c.streak_base + (r * 7) % mood_c.streak_span for r in range(1, 20)}
    assert limits == {2, 3, 4}


def test_a_repeat_rule_replaces_the_repeat_factor():
    a, b = Action("ability", "ATTACK", "a", 100), Action("ability", "ATTACK", "b", 100)
    actions = [a, b, FLEE]
    repeated = ctx(recent=["ability:a", "ability:a"])
    plain = dict(zip(["a", "b", "flee"], policy.probabilities(actions, repeated)))
    stubborn_ctx = PolicyContext(repeated.situation, 1.0, 0.1, False, repeated.recent_keys, {}, MatchState(), MoodMeters(), (rule(repeat=1.0),))
    stubborn = dict(zip(["a", "b", "flee"], policy.probabilities(actions, stubborn_ctx)))
    assert plain["a"] < plain["b"] and stubborn["a"] == pytest.approx(stubborn["b"])


def test_pick_by_percentage_prefers_the_strong_or_the_weak_inside_a_category():
    weak, strong = Action("ability", "ATTACK", "weak", 100), Action("ability", "ATTACK", "strong", 200)
    actions = [weak, strong, FLEE]
    high = dict(zip(["weak", "strong", "flee"], policy.explain(actions, ruled([rule(pick_by_percentage="high")], actions=actions)).probabilities))
    low = dict(zip(["weak", "strong", "flee"], policy.explain(actions, ruled([rule(pick_by_percentage="low")], actions=actions)).probabilities))
    assert high["strong"] > high["weak"] and low["weak"] > low["strong"]
    assert high["strong"] / high["weak"] == pytest.approx(low["weak"] / low["strong"])


def test_choose_carries_the_audit_details():
    decision = policy.choose(ACTIONS, ruled([rule("R#0", multiply={"ATTACK": 2.0})]), 0.0)
    assert decision.details["fired"] == ["R#0"] and set(decision.details["categories"]) == {"ATTACK", "DEFENSE", "SUPPORT", "FEAR", "INTERCEPT"}


def test_active_rules_scale_with_tier_and_the_leading_instance():
    from src.ascension.catalog import Catalog
    from tests.ascension.env import load_raw
    import copy

    data = copy.deepcopy(load_raw())
    data["personalities"].append({"id": "TESTY", "categories": [], "rules": [{"chaos": 0.5}, {"stay": 2.0}]})
    local = Mood(Catalog(data))
    lead, other = PersonalityInstance("a", "TESTY", 3), PersonalityInstance("b", "TESTY", 1)
    rules = local.active_rules([lead, other], 0)
    assert [(r.name, round(r.strength, 4)) for r in rules] == [
        ("TESTY#0", 1.0), ("TESTY#1", 1.0),
        ("TESTY#0", round(1 / 3 * CATALOG.policy.off_mood_factor, 4)), ("TESTY#1", round(1 / 3 * CATALOG.policy.off_mood_factor, 4))]
    assert local.active_rules([], None) == ()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_policy.py -q`
Expected: FAIL (`explain` missing, `PolicyContext` takes 6 arguments).

- [ ] **Step 3: Write the implementation**

Replace `src/ascension/policy.py` with:

```python
"""The action policy: how an Ascended picks its action when it plays on its own.

Pure and synchronous, in two stages. First a category (ATTACK, DEFENSE, SUPPORT,
FEAR, INTERCEPT) from the situation read, the round's personality weights and
the personality rules that fire for the current match; the number of actions in a
category does not change it. Then an action inside the chosen category from a
softmax over a small utility. The engine's seeded draw picks one action, so a
personality biases behaviour without making it predictable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.ascension.catalog import Catalog, PolicySpec
from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.models import CATEGORIES, Action, PersonalityInstance
from src.ascension.personality_rules import ActiveRule, holds

# What the Cunning personality answers with: DEFENSE after an ATTACK, ATTACK after SUPPORT or DEFENSE.
COUNTERS: dict[str, tuple[str, ...]] = {"ATTACK": ("DEFENSE",), "SUPPORT": ("ATTACK",), "DEFENSE": ("ATTACK",)}


@dataclass(frozen=True)
class Situation:
    """Each value is 0 to 1."""

    danger: float
    aggression: float  # how aggressively the enemy has acted
    advantage: float  # does this Ascended have the upper hand


@dataclass(frozen=True)
class PolicyContext:
    situation: Situation
    enemy_hp_fraction: float
    enemy_flee_share: float  # share of revealed rounds the enemy chose FLEE
    collector: bool  # True for the player's Ascended: CATCH can collect
    recent_keys: tuple[str, ...]  # this Ascended's own previous action keys, oldest first
    weights: Mapping[str, float]  # round personality weights per category
    match: MatchState | None = None  # None: no personality rule can fire
    meters: MoodMeters | None = None
    rules: tuple[ActiveRule, ...] = ()


@dataclass(frozen=True)
class PolicyDecision:
    action: Action
    probabilities: tuple[float, ...]  # same order as the actions passed in
    details: dict[str, Any] | None = None  # category probabilities and fired rules, for the private audit


@dataclass(frozen=True)
class Explanation:
    probabilities: list[float]
    categories: dict[str, float]  # stage 1, only categories that have a legal action
    fired: list[str]  # names of the rules that fired

    def audit(self) -> dict[str, Any]:
        return {"categories": {c: round(p, 4) for c, p in self.categories.items()}, "fired": list(self.fired)}


class Mood:
    """Which equipped personality leads this round, and the resulting weights and rules."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._off = catalog.policy.off_mood_factor

    @staticmethod
    def pick(count: int, u: float) -> int:
        """Uniform index of the leading instance for one draw u in [0, 1)."""
        return min(int(u * count), count - 1)

    def weights(self, instances: Sequence[PersonalityInstance], lead: int) -> dict[str, float]:
        """The lead instance counts fully, the others at the off-mood factor;
        weights add per category. A personality gives its tier as the weight for
        each of its categories."""
        totals = {category: 0.0 for category in CATEGORIES}
        for index, instance in enumerate(instances):
            factor = 1.0 if index == lead else self._off
            for category in self._catalog.personalities[instance.type_id].categories:
                totals[category] += instance.tier * factor
        return totals

    def active_rules(self, instances: Sequence[PersonalityInstance], lead: int | None) -> tuple[ActiveRule, ...]:
        """Every rule of every instance, with its strength: tier / 3, times the off-mood factor when not leading."""
        active = []
        for index, instance in enumerate(instances):
            factor = 1.0 if index == lead else self._off
            for number, rule in enumerate(self._catalog.personalities[instance.type_id].rules):
                active.append(ActiveRule(f"{instance.type_id}#{number}", rule, instance.tier / 3 * factor))
        return tuple(active)


class ActionPolicy:
    def __init__(self, spec: PolicySpec) -> None:
        self._spec = spec

    def situation_value(self, category: str, ctx: PolicyContext) -> float:
        s, c = ctx.situation, self._spec.coefficients[category]
        if category == "ATTACK":
            value = c["base"] + c["advantage"] * s.advantage + c["safety"] * (1 - s.danger)
        elif category == "DEFENSE":
            value = c["base"] + c["danger"] * s.danger + c["aggression"] * s.aggression
        elif category == "SUPPORT":
            value = c["base"] + c["safety"] * (1 - s.danger) + c["passivity"] * (1 - s.aggression)
        elif category == "FEAR":
            value = c["base"] + c["escape_pressure"] * s.danger * (1 - s.advantage)
        elif ctx.collector:
            value = c["collector_base"] + c["collector_weakness"] * (1 - ctx.enemy_hp_fraction) * (1 - s.danger)
        else:
            value = c["wild_base"] + c["wild_flee_share"] * ctx.enemy_flee_share
        return max(value, self._spec.floor)

    # -- stage 1: the category -----------------------------------------------------

    @staticmethod
    def _fired(ctx: PolicyContext) -> list[ActiveRule]:
        if ctx.match is None or ctx.meters is None:
            return []
        return [a for a in ctx.rules if holds(a.rule.when, ctx.match, ctx.meters)]

    def _category_probabilities(self, present: list[str], ctx: PolicyContext, fired: list[ActiveRule]) -> dict[str, float]:
        spec, match = self._spec, ctx.match
        base = {c: self.situation_value(c, ctx) * (1 + spec.gain * ctx.weights.get(c, 0.0)) for c in present}
        for active in fired:
            effects, k = active.rule.effects, active.strength
            for category, factor in effects.get("multiply", {}).items():
                if category in base:
                    base[category] *= 1 + (factor - 1) * k
            if "stay" in effects and match.own_last in base:
                base[match.own_last] *= 1 + (effects["stay"] - 1) * k
            boosted: tuple[str, ...] = ()
            if effects.get("counter") and match.enemy_last:
                boosted = COUNTERS.get(match.enemy_last, ())
            elif effects.get("copy_enemy") and match.enemy_last:
                boosted = (match.enemy_last,)
            for category in boosted:
                if category in base:
                    base[category] *= 1 + (spec.counter_boost - 1) * k
        total = sum(base.values())
        shares = {c: v / total for c, v in base.items()}
        return self._chaos(self._break_streak(shares, ctx, fired), fired)

    def _break_streak(self, shares: dict[str, float], ctx: PolicyContext, fired: list[ActiveRule]) -> dict[str, float]:
        """After a hidden streak limit the Ascended jumps to its least likely other category."""
        strength = max((a.strength for a in fired if a.rule.effects.get("break_streak")), default=0.0)
        match, mood = ctx.match, self._spec.mood
        if not strength or match.own_last not in shares or len(shares) < 2:
            return shares
        if match.own_streak < mood.streak_base + (match.round * 7) % mood.streak_span:
            return shares
        target = min((c for c in shares if c != match.own_last), key=lambda c: shares[c])
        blend = min(1.0, strength)
        return {c: (1 - blend) * v + (blend if c == target else 0.0) for c, v in shares.items()}

    @staticmethod
    def _chaos(shares: dict[str, float], fired: list[ActiveRule]) -> dict[str, float]:
        """Blend toward the inverse: the unlikely categories gain, the likely ones lose."""
        amount = min(1.0, sum(a.rule.effects.get("chaos", 0.0) * a.strength for a in fired))
        if amount <= 0 or len(shares) < 2:
            return shares
        spread = sum(1 - v for v in shares.values())
        return {c: (1 - amount) * v + amount * (1 - v) / spread for c, v in shares.items()}

    # -- stage 2: the action inside a category --------------------------------------

    def _within(self, members: list[Action], ctx: PolicyContext, fired: list[ActiveRule]) -> list[float]:
        if len(members) == 1:
            return [1.0]
        spec = self._spec
        mean = sum(a.percentage for a in members) / len(members)
        weight = spec.potency_weight
        for active in fired:
            pick = active.rule.effects.get("pick_by_percentage")
            if pick:
                weight = spec.pick_weight if pick == "high" else -spec.pick_weight
        overrides = [a.rule.effects["repeat"] for a in fired if "repeat" in a.rule.effects]
        repeat_factor = max(overrides) if overrides else spec.repeat_factor
        scores = []
        for action in members:
            repeats = 0
            for key in reversed(ctx.recent_keys):
                if key != action.key:
                    break
                repeats += 1
            potency = math.log(action.percentage / mean) if mean > 0 and action.percentage > 0 else 0.0
            scores.append(math.exp((weight * potency + repeats * math.log(repeat_factor)) / spec.temperature))
        total = sum(scores)
        return [s / total for s in scores]

    # -- public --------------------------------------------------------------------

    def explain(self, actions: Sequence[Action], ctx: PolicyContext) -> Explanation:
        if not actions:
            raise ValueError("no legal actions to choose from")
        members: dict[str, list[int]] = {}
        for index, action in enumerate(actions):
            members.setdefault(action.category, []).append(index)
        present = [c for c in CATEGORIES if c in members]
        fired = self._fired(ctx)
        categories = self._category_probabilities(present, ctx, fired)
        probabilities = [0.0] * len(actions)
        for category, indexes in members.items():
            shares = self._within([actions[i] for i in indexes], ctx, fired)
            for index, share in zip(indexes, shares):
                probabilities[index] = categories[category] * share
        return Explanation(probabilities, categories, [a.name for a in fired])

    def probabilities(self, actions: Sequence[Action], ctx: PolicyContext) -> list[float]:
        return self.explain(actions, ctx).probabilities

    def choose(self, actions: Sequence[Action], ctx: PolicyContext, u: float) -> PolicyDecision:
        explanation = self.explain(actions, ctx)
        cumulative = 0.0
        for action, probability in zip(actions, explanation.probabilities):
            cumulative += probability
            if u < cumulative:
                return PolicyDecision(action, tuple(explanation.probabilities), explanation.audit())
        return PolicyDecision(actions[-1], tuple(explanation.probabilities), explanation.audit())  # u rounding past the last bucket
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_policy.py tests/ascension/test_simulation.py -q`
Expected: all pass. The old tests that use one action per category (`ACTIONS`) are unchanged by design. If a simulation threshold fails, the cause is the changed repeat penalty (it now acts only inside a category): print the shares, and only if the intent of the test still holds, relax that one threshold and say so in the commit message.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/policy.py apps/ascension/tests/ascension/test_policy.py
git commit -m "feat(ascension): two-stage action policy with personality rules"
```

---

### Task 4: The decider reads the match

**Files:**
- Modify: `src/ascension/decider.py`
- Test: `tests/ascension/test_decider_match.py`

**Interfaces:**
- Consumes: `MatchReader`, `Mood.active_rules`, `PolicyContext` new fields, `PolicyDecision.details`.
- Produces: `Decision.audit` gains `match` (a `MatchState.to_dict()`), `mood_meters` (a `MoodMeters.to_dict()`), `categories` and `fired` (from `details`, empty when the policy gives none, as with the scripted test policy). Existing audit keys stay. The decider still draws exactly once for the mood lead (only with personalities) and once for the choice.

- [ ] **Step 1: Write the failing test**

Create `tests/ascension/test_decider_match.py`:

```python
import pytest

from src.ascension.decider import ActionDecider
from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, BattleState, FighterState, PersonalityInstance
from src.ascension.policy import ActionPolicy, Mood
from src.ascension.situation import HeuristicSituationReader, SituationViewBuilder
from tests.ascension.env import CATALOG, run
from tests.ascension.helpers import ScriptedPolicy, ScriptedRandom, revealed_round, setup

engine = BattleEngine(CATALOG)
views = SituationViewBuilder(engine)
reader = HeuristicSituationReader(CATALOG.policy.default_aggression)
SETUP = setup()
STATE = BattleState(2, FighterState(70), FighterState(100), (revealed_round(1, hits=[(WILD, 30)]),))
AGGRESSIVE = (PersonalityInstance("p1", "AGGRESSIVE", 2),)


def decider(policy=None):
    return ActionDecider(CATALOG, engine, policy or ActionPolicy(CATALOG.policy), Mood(CATALOG), reader, views)


def test_the_audit_records_the_match_the_mood_and_the_categories():
    decision = run(decider().decide(SETUP, STATE, PLAYER, AGGRESSIVE, ScriptedRandom(0.0, 0.0), can_collect=False))
    audit = decision.audit
    assert audit["match"]["own_hp"] == 0.7 and audit["match"]["lead"] == pytest.approx(-0.3, abs=1e-3)
    assert audit["match"]["hit_taken"] == pytest.approx(0.3, abs=1e-3) and audit["match"]["own_last"] == "ATTACK"
    assert set(audit["mood_meters"]) == {"rage", "confidence", "nerves"} and audit["mood_meters"]["rage"] == 1.0
    assert audit["fired"] == [] and set(audit["categories"]) == {"ATTACK", "FEAR"}
    assert audit["mood"] == "p1" and audit["chosen"] in audit["probabilities"]


def test_it_still_draws_only_for_the_mood_and_the_choice():
    random = ScriptedRandom(0.5, 0.5)
    run(decider().decide(SETUP, STATE, PLAYER, AGGRESSIVE, random, can_collect=False))
    assert random.used == 2
    random = ScriptedRandom(0.5)
    run(decider().decide(SETUP, STATE, PLAYER, (), random, can_collect=False))
    assert random.used == 1


def test_a_scripted_policy_without_details_still_gets_an_audit():
    decision = run(decider(ScriptedPolicy(player=["flee"])).decide(SETUP, STATE, PLAYER, AGGRESSIVE, ScriptedRandom(0.0, 0.0), can_collect=False))
    assert decision.action.key == "flee" and decision.audit["fired"] == [] and decision.audit["categories"] == {}
    assert "match" in decision.audit and "mood_meters" in decision.audit


def test_the_wild_side_reads_its_own_seat():
    decision = run(decider().decide(SETUP, STATE, WILD, (), ScriptedRandom(0.0), can_collect=False))
    assert decision.audit["match"]["lead"] == pytest.approx(0.3, abs=1e-3) and decision.audit["match"]["hit_taken"] == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_decider_match.py -q`
Expected: FAIL (`KeyError: 'match'`).

- [ ] **Step 3: Write the implementation**

In `src/ascension/decider.py`: add `from src.ascension.match_state import MatchReader`; in `__init__` add `self._matches = MatchReader(catalog.policy.mood)`; in `decide`, after `view = ...` and the situation read, replace the context and audit:

```python
        match, meters = self._matches.read(setup, state, side)
        rules = self._mood.active_rules(instances, lead) if instances else ()
        context = PolicyContext(
            situation=situation, enemy_hp_fraction=view.enemy_hp_fraction, enemy_flee_share=flee_share,
            collector=side == PLAYER, recent_keys=tuple(r.actions[side][0] for r in state.history), weights=weights,
            match=match, meters=meters, rules=rules,
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
```
(keep the existing `lead`, `weights`, `history`, `flee_share` lines above, and the module docstring accurate: "situation read, mood draw, match and mood, rules, probabilities, seeded draw").

- [ ] **Step 4: Run the whole suite**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: only the 8 sprite failures. In particular `test_a_restart_between_rounds_gives_the_same_battle_as_not_restarting` and the coordinator tests that check no private data leaks into public views must pass.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/decider.py apps/ascension/tests/ascension/test_decider_match.py
git commit -m "feat(ascension): the decider reads the match and audits the mood"
```

---

### Task 5: Simulate any loadout

**Files:**
- Modify: `src/ascension/simulation.py` (`Combatant.loadout`)
- Test: `tests/ascension/test_simulation.py`

**Interfaces:**
- Produces: `Combatant(ascended_id, tier_id, level, personalities, reader, loadout: Loadout | None = None)`; `BattleSimulator.run` passes `player.loadout` and `wild.loadout` to `build_fighter`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ascension/test_simulation.py` (add `from src.ascension.models import AbilitySpec, Loadout, PassiveSpec` to the imports):

```python
ATTACKS = Loadout(
    tuple(AbilitySpec(f"fury_{n}", f"Fury {n}", 1, "ATTACK", 100.0 + 25 * n, 1) for n in range(3)),
    PassiveSpec("none", {}),
)


def with_attacks(personality):
    return Combatant("sentinel", "common", 20, personality_set(CATALOG, personality), reader, ATTACKS)


def test_a_loadout_of_three_attacks_still_follows_the_personality():
    other = with_attacks(("DISCIPLINED", 2))
    coward = [run(sim.run(with_attacks(("COWARD", 3)), other, seed=s, max_rounds=30)) for s in range(40)]
    aggressive = [run(sim.run(with_attacks(("AGGRESSIVE", 3)), other, seed=s, max_rounds=30)) for s in range(40)]
    flee = lambda reports: sum(r.share(PLAYER, "FEAR") for r in reports) / len(reports)  # noqa: E731
    assert flee(coward) > flee(aggressive)
    assert all("DEFENSE" not in r.actions[PLAYER] for r in coward)  # the loadout has none, so none is ever chosen
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_simulation.py -q -k three_attacks`
Expected: FAIL (`Combatant` takes 5 arguments).

- [ ] **Step 3: Write the implementation**

In `src/ascension/simulation.py` import `Loadout` from `src.ascension.models`, add to `Combatant` the field `loadout: Loadout | None = None` (last), and use it:

```python
        setup = BattleSetup(
            self._engine.build_fighter(PLAYER, player.ascended_id, player.tier_id, player.level, player.loadout),
            self._engine.build_fighter(WILD, wild.ascended_id, wild.tier_id, wild.level, wild.loadout),
        )
```

- [ ] **Step 4: Run tests**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_simulation.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/src/ascension/simulation.py apps/ascension/tests/ascension/test_simulation.py
git commit -m "feat(ascension): simulate any loadout"
```

---

### Task 6: The 14 new personalities and the policy constants

**Files:**
- Modify: `configs/ascension_catalog.json` (`policy` and `personalities`)
- Modify: `tests/ascension/test_api.py`, `tests/ascension/test_encounters.py`, `tests/ascension/test_collection.py`
- Test: `tests/ascension/test_new_personalities.py`

**Interfaces:**
- Produces: 22 personalities; the first 8 are unchanged and keep their order, the 14 new ones follow. New ones have `"categories": []` and act only through `rules`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ascension/test_new_personalities.py`:

```python
import pytest

from src.ascension.match_state import MatchState, MoodMeters
from src.ascension.models import Action, PersonalityInstance
from src.ascension.policy import ActionPolicy, Mood, PolicyContext, Situation
from tests.ascension.env import CATALOG

policy, mood = ActionPolicy(CATALOG.policy), Mood(CATALOG)
ACTIONS = [Action("attack", "ATTACK"), Action("ability", "DEFENSE", "guard", 200), Action("ability", "SUPPORT", "rally", 50),
           Action("flee", "FEAR"), Action("catch", "INTERCEPT")]

NEW = ["WEIRD", "ANXIOUS", "RECKLESS", "VENGEFUL", "BERSERKER", "COCKY", "COMEBACK", "CUNNING", "MIMIC", "PATIENT",
       "OPPORTUNIST", "STUBBORN", "GAMBLER", "STOIC"]


def ctx(personality=None, tier=3, actions=ACTIONS, match=None, meters=None):
    instances = [PersonalityInstance("p", personality, tier)] if personality else []
    return PolicyContext(Situation(0.3, 0.5, 0.5), 1.0, 0.1, False, (), mood.weights(instances, 0) if instances else {},
                         match or MatchState(round=6), meters or MoodMeters(), mood.active_rules(instances, 0) if instances else ())


def cats(personality=None, **kwargs):
    return policy.explain(ACTIONS, ctx(personality, **kwargs)).categories


CALM = cats()


def test_there_are_22_personalities_and_the_first_8_keep_their_order():
    ids = list(CATALOG.personalities)
    assert ids[:8] == ["AGGRESSIVE", "DEFENSIVE", "SUPPORTIVE", "COWARD", "TENACIOUS", "BOLD", "CAUTIOUS", "DISCIPLINED"]
    assert ids[8:] == NEW and len(ids) == 22
    assert all(CATALOG.personalities[p].categories == () for p in NEW)


@pytest.mark.parametrize("personality", [p for p in NEW if p not in ("PATIENT", "OPPORTUNIST")])
def test_a_new_personality_is_calm_in_a_calm_match(personality):
    """In an even, quiet round with a fresh mood no new personality changes the odds. Patient and Opportunist
    read the round number and the enemy HP even then, so they have their own tests below."""
    assert cats(personality, match=MatchState(round=6), meters=MoodMeters()) == pytest.approx(CALM)


@pytest.mark.parametrize("personality,match,meters,up,down", [
    ("RECKLESS", MatchState(own_hp=0.3, lead=-0.3), None, ["ATTACK"], []),
    ("VENGEFUL", None, MoodMeters(rage=0.6), ["ATTACK"], []),
    ("BERSERKER", None, MoodMeters(rage=0.7), ["ATTACK"], ["FEAR"]),
    ("COCKY", None, MoodMeters(confidence=0.8), ["ATTACK"], ["DEFENSE"]),
    ("COMEBACK", MatchState(lead=-0.4), None, ["ATTACK", "SUPPORT"], []),
    ("CUNNING", MatchState(enemy_last="ATTACK"), None, ["DEFENSE"], []),
    ("MIMIC", MatchState(enemy_last="SUPPORT"), None, ["SUPPORT"], []),
    ("PATIENT", MatchState(round=1), None, ["SUPPORT", "DEFENSE"], []),
    ("OPPORTUNIST", MatchState(round=6, enemy_hp=0.2, enemy_low=True), None, ["ATTACK", "INTERCEPT"], []),
    ("STUBBORN", MatchState(own_last="DEFENSE", own_streak=1), None, ["DEFENSE"], []),
])
def test_each_personality_shifts_the_odds_the_way_its_rule_says(personality, match, meters, up, down):
    fired = cats(personality, match=match, meters=meters)
    plain = cats(personality=None, match=match, meters=meters)  # the same match, no personality
    for category in up:
        assert fired[category] > plain[category], (personality, category)
    for category in down:
        assert fired[category] < plain[category], (personality, category)


def test_patient_turns_to_attack_later_in_the_battle():
    early, late = cats("PATIENT", match=MatchState(round=1)), cats("PATIENT", match=MatchState(round=6))
    assert late["ATTACK"] > early["ATTACK"] and early["SUPPORT"] > late["SUPPORT"]


def test_opportunist_defends_a_little_more_while_the_enemy_is_healthy():
    healthy = cats("OPPORTUNIST", match=MatchState(round=6, enemy_low=False))
    assert healthy["DEFENSE"] > CALM["DEFENSE"]
    assert healthy["DEFENSE"] / healthy["SUPPORT"] == pytest.approx(CALM["DEFENSE"] / CALM["SUPPORT"] * 1.2)


def test_tier_scales_the_strength_of_a_personality():
    weak = cats("RECKLESS", tier=1, match=MatchState(own_hp=0.3))
    strong = cats("RECKLESS", tier=3, match=MatchState(own_hp=0.3))
    assert CALM["ATTACK"] < weak["ATTACK"] < strong["ATTACK"]


def test_anxious_is_plain_while_winning_and_chaotic_when_nervous():
    winning = cats("ANXIOUS", match=MatchState(lead=0.4), meters=MoodMeters(nerves=0.1))
    assert winning == pytest.approx(CALM)
    nervous = cats("ANXIOUS", match=MatchState(lead=-0.4), meters=MoodMeters(nerves=0.8))
    assert max(nervous.values()) < max(CALM.values()) and nervous["FEAR"] > CALM["FEAR"]
    assert sum(nervous.values()) == pytest.approx(1.0)


def test_weird_leaves_a_long_streak_and_only_a_long_one():
    limit = CATALOG.policy.mood.streak_base + (6 * 7) % CATALOG.policy.mood.streak_span  # round 6
    short = cats("WEIRD", match=MatchState(round=6, own_last="ATTACK", own_streak=limit - 1))
    long = cats("WEIRD", match=MatchState(round=6, own_last="ATTACK", own_streak=limit))
    assert short == pytest.approx(CALM) and long["ATTACK"] == pytest.approx(0.0)
    reset = cats("WEIRD", match=MatchState(round=6, own_last="DEFENSE", own_streak=1))  # the jump reset the streak
    assert reset == pytest.approx(CALM)


def test_stubborn_ignores_repeats_and_gambler_swings_with_the_score():
    weak, strong = Action("ability", "ATTACK", "weak", 100), Action("ability", "ATTACK", "strong", 200)
    actions = [weak, strong, Action("flee", "FEAR")]
    base = ctx("STUBBORN", actions=actions, match=MatchState(own_last="ATTACK", own_streak=2))
    repeated = PolicyContext(base.situation, 1.0, 0.1, False, ("ability:weak", "ability:weak"), base.weights, base.match, base.meters, base.rules)
    p = policy.probabilities(actions, repeated)
    assert p[0] / p[1] == pytest.approx(2 ** (-CATALOG.policy.potency_weight / CATALOG.policy.temperature))  # no repeat penalty

    def pair(match):
        values = policy.probabilities(actions, ctx("GAMBLER", actions=actions, match=match))
        return values[0], values[1]

    losing_weak, losing_strong = pair(MatchState(lead=-0.4))
    winning_weak, winning_strong = pair(MatchState(lead=0.5))
    assert losing_strong > losing_weak and winning_weak > winning_strong


def test_stoic_never_reacts():
    for match, meters in ((MatchState(own_hp=0.1, lead=-0.8, enemy_last="ATTACK"), MoodMeters(rage=1, nerves=1)),
                          (MatchState(enemy_low=True, lead=0.9, own_streak=9, own_last="ATTACK"), MoodMeters(confidence=1))):
        assert cats("STOIC", match=match, meters=meters) == pytest.approx(cats(None, match=match, meters=meters))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_new_personalities.py -q`
Expected: FAIL (`KeyError: 'WEIRD'`).

- [ ] **Step 3: Write the config**

In `configs/ascension_catalog.json`:

1. In `policy`, after `default_flee_share`, add:

```json
    "potency_weight": 0.3,
    "pick_weight": 1.5,
    "temperature": 0.7,
    "counter_boost": 3.0,
    "mood": {
      "rage_decay": 0.5,
      "rage_gain": 4.0,
      "confidence_step": 0.2,
      "nerves_follow": 0.5,
      "enemy_low": 0.3,
      "streak_base": 2,
      "streak_span": 3
    },
```
2. Append these 14 objects to the end of `personalities` (after `DISCIPLINED`, in this order):

```json
    { "id": "WEIRD", "categories": [], "rules": [ { "break_streak": true } ] },
    { "id": "ANXIOUS", "categories": [], "rules": [ { "when": { "nerves_over": 0.5 }, "chaos": 0.6 } ] },
    { "id": "RECKLESS", "categories": [], "rules": [
        { "when": { "own_hp_under": 0.5 }, "multiply": { "ATTACK": 1.6, "DEFENSE": 0.7, "FEAR": 0.5 } } ] },
    { "id": "VENGEFUL", "categories": [], "rules": [ { "when": { "rage_over": 0.3 }, "multiply": { "ATTACK": 1.8 } } ] },
    { "id": "BERSERKER", "categories": [], "rules": [
        { "when": { "rage_over": 0.2 }, "multiply": { "ATTACK": 1.5 } },
        { "when": { "rage_over": 0.6 }, "multiply": { "FEAR": 0.1 } },
        { "when": { "own_hp_under": 0.25 }, "multiply": { "ATTACK": 1.6 } } ] },
    { "id": "COCKY", "categories": [], "rules": [
        { "when": { "confidence_over": 0.6 }, "multiply": { "ATTACK": 1.4, "DEFENSE": 0.6 } },
        { "when": { "lead_under": 0.0 }, "chaos": 0.3 } ] },
    { "id": "COMEBACK", "categories": [], "rules": [
        { "when": { "lead_under": 0.0 }, "multiply": { "ATTACK": 1.4, "SUPPORT": 1.4 } } ] },
    { "id": "CUNNING", "categories": [], "rules": [ { "counter": true } ] },
    { "id": "MIMIC", "categories": [], "rules": [ { "copy_enemy": true } ] },
    { "id": "PATIENT", "categories": [], "rules": [
        { "when": { "round_under": 4 }, "multiply": { "SUPPORT": 1.5, "DEFENSE": 1.5 } },
        { "when": { "round_over": 3 }, "multiply": { "ATTACK": 1.5 } },
        { "when": { "enemy_low": true }, "multiply": { "ATTACK": 1.5 } } ] },
    { "id": "OPPORTUNIST", "categories": [], "rules": [
        { "when": { "enemy_low": true }, "multiply": { "ATTACK": 1.8, "INTERCEPT": 1.8 } },
        { "when": { "enemy_low": false }, "multiply": { "DEFENSE": 1.2 } } ] },
    { "id": "STUBBORN", "categories": [], "rules": [ { "repeat": 1.0, "stay": 2.0 } ] },
    { "id": "GAMBLER", "categories": [], "rules": [
        { "when": { "lead_under": 0.0 }, "pick_by_percentage": "high" },
        { "when": { "lead_over": 0.3 }, "pick_by_percentage": "low" } ] },
    { "id": "STOIC", "categories": [] }
```

   Patient's `round_over: 3` rule fires from round 4 and Opportunist's `enemy_low: false` rule fires whenever the enemy is healthy, so both are excluded from the calm test and have their own tests.

3. Fix the tests that assumed 8 personalities:
   - `tests/ascension/test_api.py`: `assert len(data["personalities"]) == 8` becomes `== 22`.
   - `tests/ascension/test_encounters.py` line with `("DISCIPLINED", 3)`: use `(list(CATALOG.personalities)[-1], 3)`; import `CATALOG` from `tests.ascension.env` if the file does not already.
   - `tests/ascension/test_collection.py`: the parameter `(0.99, "DISCIPLINED")` becomes `(0.99, list(CATALOG.personalities)[-1])`; import `CATALOG` the same way.

- [ ] **Step 4: Run the whole suite**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: only the 8 sprite failures. If a test fails because it assumed a specific personality from a scripted draw, fix that test by mapping the draw through `list(CATALOG.personalities)`; do not reorder the personalities.

- [ ] **Step 5: Commit**

```bash
git add apps/ascension/configs/ascension_catalog.json apps/ascension/tests/ascension/test_new_personalities.py apps/ascension/tests/ascension/test_api.py apps/ascension/tests/ascension/test_encounters.py apps/ascension/tests/ascension/test_collection.py
git commit -m "feat(ascension): 14 new personalities that read the match"
```

---

### Task 7: Docs and vault

**Files:**
- Modify: `apps/ascension/README.md`
- Modify: `docs/superpowers/specs/2026-10-12-ascension-autonomous-policy-design.md`
- Create: vault `Brain/Notes/Decision - The autonomous policy reads the match and keeps a hidden mood.md`
- Modify: vault `Brain/Projects/Ascension.md`

- [ ] **Step 1: README.** Replace the section "How an Ascended chooses on its own" body so it describes the two stages (category, then action), the situation read (unchanged), the match state and the three mood meters (rage, confidence, nerves; recomputed from history, nothing stored), the rule format (conditions and the eight effects), and the list of 22 personalities with one line each. Keep the existing text about Laya and the heuristic fallback.
- [ ] **Step 2: Spec.** In the policy spec: replace the sentence about `style` tags with "Decided: no style tags; `pick_by_percentage`, `repeat` and the potency term give the variety", add `stay` to the list of effects (Stubborn uses it), and mark the status "built".
- [ ] **Step 3: Vault.** In `Brain/Notes/` create the decision note (frontmatter `type: note`, `status: active`, `tags: [decision, games]`, `created`, with the template sections; link `[[Ascension]]` and `[[MCPServer]]`). In `Brain/Projects/Ascension.md` add one bullet under "Python game (MCPServer)" linking the new note, and set `last_synced`. Run `py ../.claude/hooks/validate_vault.py --all` from `Brain`.
- [ ] **Step 4: Run everything and commit**

Run: `.venv_ascension\Scripts\python -m pytest -q` and, in `web`, `npx vitest run` (no web change is expected).
Expected: only the 8 sprite failures; web unchanged.

```bash
git add apps/ascension/README.md docs/superpowers/specs/2026-10-12-ascension-autonomous-policy-design.md
git commit -m "docs(ascension): the autonomous policy and the new personalities"
```
and, in `Brain`: `git add Notes Projects/Ascension.md && git commit -m "docs: Ascension autonomous policy decision"`.

---

## Self-review against the spec

- Two stages, category independent of action count: Task 3 (`test_the_number_of_actions_in_a_category_does_not_change_the_category`), Task 5 (3-attack simulation).
- Match state (all nine fields) and the three mood meters, derived from history, nothing saved: Task 2.
- Rule format, conditions, effects, strength by tier and by lead, validation: Tasks 1 and 3.
- 14 new personalities with the spec's behaviours: Task 6 (each has a test). The spec's "danger is ignored" for Reckless is approximated by lowering DEFENSE and FEAR when its HP is low, since no rule can zero the situation read.
- Audit with match, meters, categories and fired rules: Task 4.
- No extra random draws (scripted tests stay exact): Task 4 asserts the draw counts; Weird's streak limit is a function of the round.
- Config keys for the mood and policy constants: Tasks 1 and 6.
- Decisions left open in the spec are decided in Global Constraints (no style tags, a `stay` effect).
- Type names match across tasks: `MatchState`, `MoodMeters`, `MoodConstants`, `MatchReader`, `Rule`, `ActiveRule`, `Explanation`, `PolicyDecision.details`, `Mood.active_rules`, `revealed_round`.
