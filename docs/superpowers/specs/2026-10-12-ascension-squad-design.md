# Ascension: a squad of five, shared XP, and a squad-based battle preparation screen

Date: 2026-10-12. Status: ready to build. Audience: the coding agent (Codex) that implements it.
Builds on the loadout slots design (`2026-10-12-ascension-loadout-slots-design.md`) and the rotating shop design.
Rules in `apps/ascension/AGENTS.md` and the monorepo `AGENTS.md` apply.

## Goal

1. A player equips up to 5 Ascended into a **squad**. Only squad members can fight.
2. When a battle is won (or the wild Ascended is captured), the Ascended that fought gets the full XP reward, and the
   other squad members share a smaller pool equally.
3. The battle preparation screen shows the squad on the left. The player selects one member to fight with. The
   selection animates like the starter choice screen.

Out of scope: reordering the squad (order is fill order), switching Ascended mid-battle, multi-fighter battles, XP for
Ascended outside the squad, changing encounter level rolls, changing the fainting rules, changes to ember_api,
ember_web or ember_admin.

## Decisions

| Question | Decision |
|---|---|
| Who shares the pool | The other members of the squad (up to 4). Ascended outside the squad get nothing. **Confirmed by the owner on 2026-10-12.** The one-line alternative is "every owned Ascended except the fighter"; only `ProgressionService.squad_share` changes. |
| Fighter XP | Unchanged: `rewards_for(enemy).xp`. Call it `R`. |
| Pool | `floor(R * bench_xp_pool_factor)`, default `0.5`. Split equally: each bench member gets `floor(pool / bench_count)`. The remainder is discarded. |
| Fighter always gets more | `bench_xp_pool_factor` must be `>= 0` and `< 1`, so a share is always below `R`. The catalog loader rejects other values. |
| Fainted bench members | Still get their share. Fainting only blocks fighting. |
| Members at the level cap | `add_xp` already discards the XP. Reported share is the XP offered; `level_after` shows no change. |
| When XP is paid | Only for `won` and `captured`, as today. Knock-out and forfeit give no XP to anyone. |
| Squad size | `economy.squad_size`, default `5`. Never hard-code 5 in code. |
| Minimum | At least 1 member. The squad is never empty. |
| Starter | The starter is the first member from profile creation. |
| New Ascended | A newly owned Ascended joins the first free squad position automatically, if the squad has room. Otherwise it stays out. Applies to the starter, a capture and a first shop purchase. |
| Edits during a battle | Rejected while the owner has an active battle (`BattleInProgress`), like loadout edits. This stops swapping members to farm the pool. |
| Starting a battle | `ascended_id` must be in the squad (`InvalidRequest`, "that Ascended is not in your squad"). Fainting rules are unchanged. |
| Existing players | Schema upgrade fills the squad with up to `squad_size` of their Ascended, highest level first, ties by `ascended_id`. |

## Backend (`apps/ascension/src`)

### Config and catalog

- `configs/ascension_catalog.json`, section `economy`: add `"squad_size": 5` and `"bench_xp_pool_factor": 0.5`.
- `src/ascension/catalog.py`, `Economy`: add `squad_size: int` and `bench_xp_pool_factor: float`. Validation: `squad_size >= 1`
  and `0 <= bench_xp_pool_factor < 1`; raise `CatalogError` otherwise. Update any fixture catalogs in `tests/ascension/`.
- `src/ascension/models.py` or `records.py`: no new battle fields. The squad is not frozen into the battle; edits are
  blocked while a battle is active, so reading it at the end is safe.

### Storage (`repository.py`)

- `SCHEMA_VERSION = 6`. New schema:
  ```sql
  CREATE TABLE squad (
      owner TEXT NOT NULL, ascended_id TEXT NOT NULL, position INTEGER NOT NULL CHECK (position >= 1),
      PRIMARY KEY (owner, ascended_id), UNIQUE (owner, position));
  ```
  Add as `SQUAD_SCHEMA`, include it in `SCHEMA` (fresh databases).
- Upgrade in `_open`: versions 2, 3, 4 and 5 all end at 6. Rework the existing branch so each older step still runs,
  then `SQUAD_SCHEMA` plus a backfill run last. Backfill (SQL, per owner, rank by `level DESC, ascended_id ASC`, keep
  rank `<= squad_size`; the size is passed in, not hard-coded). Test the upgrade from a v5 database, and from a v2 one.
- `AscendedTransaction` protocol and the SQLite implementation gain:
  - `async def get_squad(owner) -> tuple[str, ...]`: ascended ids ordered by `position`.
  - `async def set_squad(owner, ascended_ids: Sequence[str]) -> None`: delete the owner's rows, insert positions `1..n`.
- `delete_player_data` also deletes the owner's `squad` rows.

### Squad service (new file `squad.py`, one responsibility)

```python
class SquadService:
    def __init__(self, repository, writer, catalog) -> None: ...
    async def get(self, owner) -> dict            # {"ascended_ids": [...], "size": N}
    async def put(self, owner, key, ascended_ids: list[str]) -> dict   # idempotent
    @staticmethod
    async def auto_equip(tx, owner, ascended_id, size) -> None         # join first free position if room
```

- `put` rules, in order: list of strings; length `1..squad_size` (`InvalidRequest` naming the limit); no duplicates;
  every id is a catalog Ascended the owner owns (`NotFound`, "you do not own that Ascended"); no active battle
  (`BattleInProgress`). Replaces the whole squad; order of the list is the position order. Commit through
  `IdempotentWriter` with operation `squad.put`.
- `auto_equip` is a no-op when the Ascended is already in the squad or the squad is full.
- Call `auto_equip` in the three places that create a new `AscendedRecord`: `collection.py` `initialize` (after the
  starter row), `progression.py` `_collect` (the `owned is None` branch), `shop.py` buy (the first-ownership branch,
  `shop.py:108`). Pass `catalog.economy.squad_size`.
- Wire `SquadService` where the other services are built (see `composition.py`), and expose it on `services`.

### Progression (`progression.py`)

- `ProgressionService.__init__` is unchanged. `apply_terminal` for `REWARDED` terminals, after the fighter's XP:
  ```python
  squad = await tx.get_squad(owner)
  bench = [a for a in squad if a != fighter.ascended_id]
  shares = self.squad_share(xp, len(bench))          # int, 0 when the bench is empty
  for ascended_id in bench:
      member = await tx.get_ascended(owner, ascended_id)
      level, new_xp = self.add_xp(ascended_id, member.level, member.xp, shares)
      await tx.put_ascended(replace(member, level=level, xp=new_xp))
  result["squad_xp"] = [{"ascended_id": ..., "name": ..., "xp": shares, "level_before": ..., "level_after": ...}, ...]
  ```
- `squad_share(fighter_xp, bench_count) -> int`: `0` if `bench_count == 0`, else
  `floor(fighter_xp * bench_xp_pool_factor / bench_count + _EPS)`. Pure, unit-tested.
- Keep the existing result keys (`xp`, `level_before`, `level_after`, ...) untouched for the fighter. Add `squad_xp`
  (an empty list when there is no bench). Skip bench members that no longer exist (defensive; none should).
- `battle_view.py` passes `result` through already; confirm `squad_xp` reaches the response.

### API (`api.py`)

- `GET /ascension/squad` -> `{"ascended_ids": [...], "size": 5}`.
- `PUT /ascension/squad`, body `{"ascended_ids": ["...", ...]}`, `Idempotency-Key` header, same auth dependency as
  the other owner routes. Returns the same shape as GET.
- `GET /ascension/profile` gains `"squad": [...ids]` and `"squad_size": N` (build in `CollectionService.profile_view`
  via `tx.get_squad`). Each entry of `ascendeds` also gets `"in_squad": bool`.
- `StartBody` is unchanged. The squad check lives in `RoundCoordinator.start` (read `tx.get_squad` inside `work`).
- Error mapping: reuse existing error classes. No new class is needed.

## Web (`apps/ascension/web/src`)

### Client, types, store

- `api/AscensionClient.ts`: `Profile` gets `squad: string[]`, `squad_size: number`; `OwnedAscended` gets `in_squad: boolean`.
  Add `getSquad()` and `putSquad(ids, key)` following the existing request helpers. The battle result type gets
  `squad_xp?: { ascended_id: string; name: string; xp: number; level_before: number; level_after: number }[]`.
- `api/AscensionClient.fixtures.ts`, `e2e/fakeApi.ts`: add the squad fields and a `PUT /squad` handler.
- `stores/ascension.ts`: `squadIds` and `squadMembers` computed from the profile; `setSquad(ids)` (busy flag, error
  notice, refresh profile, same pattern as other actions); `addToSquad(id)`, `removeFromSquad(id)` helpers that build
  the new list (append / filter) and call `setSquad`.

### Equip UI (Collection tab)

- `CollectionPanel.vue`: a **Squad** strip above the cards: `squad_size` slots in a row. Filled slot = small card plus a
  remove button (disabled when it is the last member). Empty slot = dashed placeholder, "Empty slot".
- In the Ascended detail dialog (Overview tab): one button, "Add to squad" or "Remove from squad". Disabled with a
  reason caption when the squad is full ("Squad full. Remove a member first."), when removing the last member
  ("Keep at least one Ascended."), or when a battle is active ("Finish your battle first.").
- Owned cards show a small "Squad" marker when `in_squad`.

### Battle preparation screen (`EncounterPanel.vue`, stage `setup`)

Replace the `<select>` and single "Choose your Ascended" panel. New layout mirrors `StarterPick.vue`:

```
[ squad column 190px ] [ big card 440px ] [ battle plan panel 1fr ]
```

- **Left column** (`role="radiogroup"`, aria-label "Your squad"): one compact `AscendedTemplateCard` per squad member in
  squad order, `show-level`, plus a dashed "Empty slot" placeholder for each unused position, so the column always shows
  `squad_size` rows. A caption under each card: tier and level, and for a fainted member "Fainted, ready in mm:ss".
- **Selection**: click, Enter or Space selects (same handlers as `StarterPick.vue`). The selected card gets the
  copper outline, `em-glow` and the `breathe` keyframes. Fainted members are visible but not selectable
  (`aria-disabled`, dimmed). The first ready member is selected on open; if none is ready, "Begin battle" is disabled and
  the notice says so (the preview stage already blocks Fight when `ready.length === 0`; keep that rule, computed from the
  squad instead of all Ascended).
- **Center**: large `AscendedTemplateCard` of the selected member (not compact), the same `detail` styling as the
  starter screen.
- **Right**: "Battle plan" panel, unchanged content (preset tabs, Who plays, EMBLEM limit, Begin battle, Back).
  Add a line under the heading: "Fighting: <name>. The rest of your squad shares XP if you win."
- **Animation**: do not copy the CSS. Extract it. New `components/ui/EmPickCard.vue` (or `SelectableCard.vue`): wraps a
  slot, takes `selected` and `disabled`, owns the radio semantics, `em-lift`, `em-glow`, outline and the `breathe`
  keyframes (including the `prefers-reduced-motion` rule). Switch `StarterPick.vue` to it and keep its tests green.
- **Responsive**: same breakpoints as `StarterPick.vue` (two columns under 1100px, stacked under 700px with the
  squad shown as a horizontal wrap of cards above the big card). Use the existing tokens (`--em-space-*`, `--em-radius`).
- Remove now-dead code in `EncounterPanel.vue` (the `ascendedId` select, `resting` list if unused, matching CSS).
  The `fight()` payload is unchanged (`ascended_id` is the selected member).
- The `look` stage "Ready for battle?" panel: count squad members that are ready, not all Ascended.

### Battle result (`BattleResult.vue`)

Under the fighter's XP line, when `result.squad_xp` is non-empty, show "Squad XP" with one row per member:
`+<xp> XP · <name>` and "now level N" when `level_after > level_before`. Keep the existing fighter row as the
visually larger one.

## Tests

Backend (`apps/ascension/tests/ascension/`, follow the existing helpers in `helpers.py` and `env.py`):

- `test_squad.py`: put replaces the squad and keeps order; rejects empty, over size, duplicates, unowned, unknown ids;
  rejects during an active battle; idempotent replay returns the same response; `auto_equip` joins a free slot, does
  nothing when full or already in.
- `test_progression.py`: win with a bench of 4 gives the fighter `R` and each other member `floor(R*0.5/4)`; bench
  of 0 gives `squad_xp == []`; a member at the cap gains nothing; a fainted member still gets its share; knock-out and
  forfeit give no XP; capture also shares; non-squad Ascended get nothing; fighter share is always larger than any
  bench share. Unit-test `squad_share` for rounding (remainder discarded).
- `test_coordinator.py`: start with a non-squad Ascended is rejected; start with a squad member works.
- `test_collection.py`, `test_shop.py`: the starter, a captured Ascended and a first purchase auto-join; the sixth does not.
- `test_repository.py`: v5 -> v6 upgrade backfills (highest level first, capped at `squad_size`, never empty for
  an owner with Ascended); v2 -> v6 chain works; `delete_player_data` clears `squad`.
- `test_catalog.py`: `bench_xp_pool_factor` of `1` and `-0.1`, and `squad_size` of `0`, are rejected.
- `test_api.py`: `GET/PUT /squad`, the profile fields, and the `squad_xp` key in a finished battle.

Web (Vitest, plus the Playwright e2e that uses `e2e/fakeApi.ts`):

- `stores/ascension.test.ts`: `addToSquad`, `removeFromSquad`, `setSquad` error path.
- `EncounterPanel.test.ts`: the setup stage lists squad members in order plus empty placeholders; a fainted member is not
  selectable; selecting changes the big card; `fight()` sends the selected `ascended_id`; the first ready member is
  preselected.
- `CollectionPanel.test.ts`: strip renders slots; add/remove buttons and their disabled reasons.
- `BattlePanels.test.ts` or a new `BattleResult` test: squad XP rows render.
- `StarterPick.test.ts` stays green after the `EmPickCard` extraction; add a small test for `EmPickCard`
  (selected, disabled, keyboard).
- E2E: choose a starter, fight, check the squad column on the setup screen.

## Implementation order

Each step leaves the test suite green and is a separate commit.

1. Config, `Economy` fields and catalog validation, with tests.
2. Schema v6, repository methods, upgrade and backfill, with tests.
3. `SquadService`, composition wiring, `auto_equip` in the three creation sites, API routes, profile fields.
4. Coordinator start check and progression XP sharing, with tests.
5. Web client, types, fixtures, store.
6. `EmPickCard` extraction and the `StarterPick.vue` switch.
7. Battle preparation redesign in `EncounterPanel.vue`.
8. Collection squad strip and the detail dialog button.
9. `BattleResult.vue` squad XP.
10. Update `apps/ascension/README.md` and `web/README.md`, and the vault note `Brain/Projects/` for Ascension (project sync).

## Verification before calling it done

- `pytest` in `apps/ascension` passes; Vitest passes; the e2e specs pass; the web build (`build_ui.bat`) succeeds.
- By hand: a new profile has the starter in the squad; capture a second Ascended and see it join; fill five; the sixth
  stays out; a battle won gives the fighter more XP than each bench member; the setup screen selection breathes like the
  starter screen and respects reduced motion.
