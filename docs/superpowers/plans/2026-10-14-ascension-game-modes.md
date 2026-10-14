# Ascension Game Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship Wild Hunts, six type-restricted Ascension Trials, and offline Expeditions inside Ascension's existing Battle tab.

**Architecture:** Reuse the existing combat engine, coordinator, reward helpers, and transactional repository. Add immutable activity context, catalog-driven activity rules, owner-scoped trial progress, and timestamp-based expeditions. Keep activity selection independent from Manual/Autonomous control and reuse the current header and preview-card components unchanged.

**Tech Stack:** Python 3.11+, FastAPI, standard-library SQLite, pytest; Vue 3, TypeScript, Pinia, Vitest, Playwright, Vite. No new product dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-ascension-game-modes-design.md` (approved 2026-10-14).

## Global Constraints

- Read the approved spec, root/project `AGENTS.md`, and `apps/ascension/DESIGN.md` before execution.
- Reuse `EmShell`, the current navigation in `App.vue`, and `AscendedPreviewCard`, including its existing art selection, typography, frame assets, metadata, proportions, and size rules.
- Do not restyle these components or replace their sprites. Display overall rating outside cards.
- No changes to Ember navigation, permissions, or game launch are required.
- `BattleRecord.mode` remains `manual` or `autonomous`.
- Overall rating is `catalog HP + catalog Power + catalog Speed` at the current level/effective tier.
- Hunt bands are 100–299, 300–599, and 600–1599; reward penalties stop at 75% and never modify capture odds/copies/personality awards.
- Six trial types, four stages per type; first victory doubles XP/Insignia/essence. Trial CATCH is prohibited and only matching squad members receive bench XP.
- One unclaimed expedition slot per owner; durations 2/4/8 hours, hourly rewards 100 XP and 25 Insignia. No early recall or automatic squad restoration.
- Server determines ownership, time, eligibility, and rewards. Every mutation uses the existing idempotent writer and transactional storage.
- Existing encounters/battles keep legacy rewards/capture behavior after migration.
- All three modes are in scope. Do not stop after the first working milestone.

## Review Focus

1. Two tabs depart/upgrade/start simultaneously: transactions permit one coherent outcome, with no dispatched fighter in a battle or squad (Tasks 4–5).
2. A client changes activity parameters or omits its body: strict choices reject forged rewards and new fields while legacy bodyless encounter rolls still work (Task 6).
3. A reload/account switch arrives during a mutation: discard the old account's response and recover the activity from persisted battle/encounter context (Tasks 7–8).
4. Device time differs from server time or jumps: the timer remains usable, but early reward claims always fail server-side (Tasks 4 and 8).
5. Capturing/buying a duplicate of a dispatched species: preserve its owned record and expedition lock and do not auto-enroll it (Task 5).

## File responsibilities and execution setup

All application paths below are relative to `apps/ascension/`; docs paths are relative to the repository root. Run Python commands from `apps/ascension` and frontend commands from `apps/ascension/web`. Use the existing isolated worktree; verify its branch/status before execution. Git metadata is outside the sandbox writable root, so use the standard escalation mechanism for local Git writes when needed.

- New `src/ascension/activity_rules.py`: activity definitions, rating, eligible hunt combinations, and pure penalty calculation. Keep SQL and service writes out.
- New `src/ascension/trials.py`: progress views and transaction-local eligibility; terminal grants remain in `progression.py`.
- New `src/ascension/expeditions.py`: departure/read/claim and shared transaction-local availability guard.
- Extend `records.py`/`repository.py`: immutable records, serialization, version-8 migration, trial clears and expedition receipts.
- Extend existing `encounters.py`, `coordinator.py`, `battle_view.py`, and `progression.py`: activity-specific behavior on the current battle lifecycle.
- Extend `api.py`/`composition.py`: thin route adapters and shared services, with no Ember changes.
- Extend `web/src/api/AscensionClient.ts` and the existing Pinia store: typed contracts, new calls, activity state, restoration and refresh.
- New `GameModesPanel.vue`, `TrialsPanel.vue`, `ExpeditionsPanel.vue`, and `gameModes.css` under `web/src/components/`: new mode content using existing UI primitives.
- Extend `EncounterPanel.vue` for Hunt selection and shared Trial preparation; extend Collection/progression/tree/preset controls only for expedition status and locks.
- Extend existing tests/fake APIs and add focused activity/service/browser suites. Do not introduce new sprites, header styling, or preview-card styling.

## Task 1: Catalog-driven activity rules

**Files:** Create `src/ascension/activity_rules.py`, `tests/ascension/test_activity_rules.py`; modify `src/ascension/catalog.py`, `configs/ascension_catalog.json`.

**Interfaces:** Produce frozen `HuntSpec(id, name, recommended_min, recommended_max, enemy_min, enemy_max)`, `TrialStageSpec(stage, ascended_id, tier_id, level)`, `ExpeditionSpec(durations_hours, xp_per_hour, insignia_per_hour)`, and `ActivityRules(catalog, raw_activities)`. Catalog exposes `activities: ActivityRules` after its existing character validation. Use TYPE_CHECKING for Catalog references to avoid an import cycle.

`ActivityRules.overall(ascended_id: str, tier_id: str, level: int) -> int`; `hunt(difficulty_id: str) -> HuntSpec`; `candidates(difficulty_id: str) -> dict[str, dict[str, tuple[int, ...]]]` keyed by tier then Ascended; `trial_stage(stage: int) -> TrialStageSpec`; `to_public() -> dict[str, Any]`; property `expeditions: ExpeditionSpec`. Module function `hunt_multiplier(overall: int, upper: int) -> float` applies the spec's fixed 75% cap.

- [x] Write failing `test_overall_uses_catalog_integer_stats`, `test_penalty_boundaries`, `test_hunt_candidates_respect_tier_ladders_and_caps`, and `test_activity_config_validation`. Exact assertions:

```python
assert rules.overall("guardian", "common", 1) == 185
assert rules.overall("cindrax", "forbidden", 1) == 1080
assert hunt_multiplier(299, 299) == 1.0
assert hunt_multiplier(720, 599) == pytest.approx(1 - 121 / 599)
assert hunt_multiplier(1049, 599) == 0.25
assert rules.expeditions.durations_hours == (2, 4, 8)
assert rules.expeditions.xp_per_hour == 100
assert rules.expeditions.insignia_per_hour == 25
```

Assert every enumerated combination is legal/in-band; Cindrax occurs in Forbidden Grounds only. Reject duplicate difficulty ids, boolean/fractional bounds or durations, inverted bands, empty candidate sets, no positive eligible tier weight, invalid stage ids/opponents/tiers/levels, and negative rates. Existing fixture catalogs lacking `activities` receive the shipped defaults for compatibility.
- [x] Run `python -m pytest tests/ascension/test_activity_rules.py -q`; expect failures before implementation.
- [x] Implement rules and catalog parsing. Configure `outskirts`, `frontier`, `forbidden_grounds` and the four stage tuples from the approved spec. Enumerate all legal levels once at catalog construction; do not reroll until an enemy happens to fit. Expose `max_hunt_penalty: 0.75`, six type ids, trial first-clear multiplier 2, and expedition settings in public definitions.
- [x] Run the new tests plus `tests/ascension/test_catalog.py` and `test_catalog_hardening.py`; expect passes. Commit `feat: define Ascension activity rules`.

## Task 2: Durable activity, trial, and expedition records

**Files:** Modify `src/ascension/records.py`, `repository.py`, `tests/ascension/test_repository.py`, `test_reset.py`; create `tests/ascension/test_activity_storage.py`.

**Interfaces:** Append `activity: ActivityContext = field(default_factory=ActivityContext)` to EncounterRecord/BattleRecord to preserve positional constructors. Frozen context fields: `kind="legacy"`, `difficulty_id=None`, `trial_type=None`, `trial_stage=None`, `overall=None`, `reward_multiplier=1.0`, `recommended_min=None`, `recommended_max=None`. Give it `to_dict()` and `from_dict(raw)`.

Frozen `ExpeditionRecord`: `id`, `owner`, `ascended_id`, `started_at`, `ends_at`, `duration_hours`, `xp_reward`, `insignia_reward`, `claimed_at: float | None = None`, `receipt: dict[str, Any] | None = None`.

Extend transaction protocol/SQLite implementation with `trial_clears(owner: str, type_id: str) -> set[int]`, `mark_trial_clear(owner: str, type_id: str, stage: int) -> bool` (true only on insertion), `get_expedition(owner: str, expedition_id: str) -> ExpeditionRecord | None`, `unclaimed_expedition(owner: str) -> ExpeditionRecord | None`, `add_expedition(record: ExpeditionRecord) -> None`, and `claim_expedition(owner: str, expedition_id: str, claimed_at: float, receipt: dict[str, Any]) -> None`.

- [x] Write failing `test_v7_upgrade_preserves_active_legacy_battle`, `test_fresh_activity_roundtrip`, `test_expedition_uniqueness_owner_isolation_and_receipt`, and `test_reset_removes_activity_state`. Assert legacy context defaults/multiplier 1, unchanged setup/RNG/pending prompt/wallet, context preserved on `save_battle`, unclaimed uniqueness even after `ends_at`, a new expedition allowed after claim, duplicate trial clear returns false, and owner B survives owner A reset. Cover an older supported schema migration too.
- [x] Run `python -m pytest tests/ascension/test_activity_storage.py -q`; expect failures.
- [x] Raise schema version to 8. Add JSON `activity` columns with legacy defaults; owner/type/stage primary-key trial clear table; expedition table with a partial unique index on owner where `claimed_at IS NULL`. Add activity schema after existing incremental migrations and to fresh schema. Update encounter/battle read/write SQL together, preserving revision checks. Reset deletes new owner state. No destructive table rebuild.
- [x] Run `python -m pytest tests/ascension/test_activity_storage.py tests/ascension/test_repository.py tests/ascension/test_repository_hardening.py tests/ascension/test_reset.py -q`; expect passes. Commit `feat: persist Ascension activities and expeditions`.

## Task 3: Wild Hunt selection and frozen rewards

**Files:** Modify `src/ascension/encounters.py`, `coordinator.py`, `progression.py`, `battle_view.py`, `collection.py`, `tests/ascension/env.py`; create `tests/ascension/test_hunts.py`; extend `test_progression.py`.

**Interfaces:** `EncounterService.roll(owner: str, key: str, difficulty_id: str | None = None) -> dict[str, Any]` preserves legacy behavior when omitted. `EncounterRoller.roll_hunt(difficulty_id: str, rng: RandomSource) -> RolledEncounter` uses Task 1 candidates. Extend public encounter/profile/fighter fields with `overall` and persisted `activity`. Existing coordinator `start(...)` reads context exclusively from the encounter and freezes rating/multiplier/range into the battle.

- [x] Write failing `test_hunt_roll_stays_in_band_without_scaling_to_collection`, `test_hunt_penalty_freezes_at_start`, `test_hunt_penalty_rewards_and_bench_pool`, `test_capture_awards_and_odds_are_unpenalized`, and `test_bodyless_legacy_roll_unchanged`.
- [x] Pin rewards: for a rating-720 fighter in Frontier and a level-10 Common target, assert XP 159, Insignia 79, essence 0, and two bench members offered 39 XP each. For the same target HP and EMBLEM, assert equal `engine.capture_chance` across contexts. Successful capture grants the same copy/personality awards. At cap multiplier 0.25, assert base XP 200 becomes 50. Rating below the lower bound gets multiplier 1. Include cooldown, decline, retry, and resumed battle coverage.
- [x] Run `python -m pytest tests/ascension/test_hunts.py -q`; expect failures.
- [x] Implement weighted tier selection over valid candidates, uniform species/eligible level selection, and reuse personality generation without changing legacy draw order. Apply multiplier to XP/currency/essence only, floor once, then use reduced XP for bench shares. Keep `_collect` and capture engine unchanged. Expose enough context for preparation/results to explain the frozen penalty.
- [x] Run Hunt tests plus `test_encounters.py`, `test_progression.py`, and existing coordinator/view tests; expect passes. Commit `feat: add three Wild Hunt difficulties`.

## Task 4: Offline expedition lifecycle

**Files:** Create `src/ascension/expeditions.py`, `tests/ascension/test_expeditions.py`; modify `src/ascension/errors.py`, `tests/ascension/env.py`.

**Interfaces:** `ExpeditionService(repo, writer, catalog, progression, clock)` exposes `get(owner: str) -> dict[str, Any]`, `start(owner: str, key: str, ascended_id: str, duration_hours: int) -> dict[str, Any]`, `claim(owner: str, key: str, expedition_id: str) -> dict[str, Any]`. Module helper `require_available(tx: AscendedTransaction, owner: str, ascended_id: str) -> None` raises `AscendedOnExpedition(Conflict)` for the owner's dispatched species. Additional conflicts: `ExpeditionSlotOccupied` and `ExpeditionNotReady`.

GET response is `{server_now, expedition: ExpeditionView | None}`. View fields mirror record rewards/times plus `state: "on_expedition" | "ready_to_claim"`, `can_claim`, `seconds_remaining`. Claim receipt includes id, Ascended id, XP, Insignia, level_before/after, and claimed_at. Return the recorded receipt for an already-claimed id, even under a new key.

- [x] Write failing departure, early/exact-time claim, persistence/restart, cap, ownership, and replay tests. For 4 hours assert `ends_at - started_at == 14400`, `xp_reward == 400`, `insignia_reward == 100`; for 2/8 hours assert 200/800 XP and 50/200 currency. After sending the only squad member, assert an empty squad. After sending a middle member, assert remaining order unchanged. Non-squad departure works; fainted and active-battle departure fail without partial changes.
- [x] Cover zero/negative/3/fractional/boolean durations; occupied slot includes ready-but-unclaimed; no bench XP; changed catalog reward rates after departure do not change receipt; two concurrent departures yield one success. `test_early_claim_ignores_client_clock` asserts server time alone governs eligibility. Completion exactly at ends_at succeeds; waiting longer pays the same fixed total.
- [x] Run `python -m pytest tests/ascension/test_expeditions.py -q`; expect failures.
- [x] Implement with the existing writer and clock. Start inserts expedition and removes squad membership in one transaction; claim pays frozen rewards, applies `ProgressionService.add_xp`, and saves receipt/claimed_at in one transaction. No scheduler/worker. The guard looks up the unclaimed record in the caller's transaction; it does not open its own transaction.
- [x] Run expedition/idempotency/storage tests; expect passes. Commit `feat: add offline expedition rewards`.

## Task 5: Expedition locks across existing mutations

**Files:** Modify `src/ascension/squad.py`, `upgrades.py`, `trees.py`, `collection.py`, `coordinator.py`; create `tests/ascension/test_expedition_locks.py`; extend squad/shop/progression/reset tests.

**Interfaces:** Consume Task 4 `require_available`. Expose profile-owned fields `on_expedition: bool`, `expedition_id: str | None`, `availability_reason: str | None`, plus profile `expedition: ExpeditionView | None` and `server_now`. Keep existing eligibility flags and costs intact; expedition availability is an additional guard.

- [x] Write failing parametrized tests for squad put, battle start, add_star, raise_tier, TreeService.learn, TreeService.set_loadout, put_preset, and set_default_preset while unclaimed. Assert each is rejected without spending copies/essence or saving anything; assert auto-enrollment skips the dispatched species without aborting a capture/purchase. Reads and duplicate purchases/captures remain allowed, preserving level/stars/loadout and lock. Test expiry alone does not release locks; claim does. Test another species remains editable and an expedition claim can succeed during its battle.
- [x] Add concurrent start-vs-departure, squad-vs-departure, upgrade-vs-departure scenarios using `asyncio.gather(..., return_exceptions=True)`. Inspect final rows: an expedition Ascended is never in squad/active setup and balances remain consistent. Capture/purchase duplicates must not auto-enroll the dispatched species, even into a free slot.
- [x] Run `python -m pytest tests/ascension/test_expedition_locks.py -q`; expect failures.
- [x] Add guards inside each existing mutation transaction after ownership validation. `SquadService.auto_equip` skips dispatched species rather than raising and aborting a capture. Update profile projection to expose availability without adding state fields to AscendedRecord. Do not forbid buying/selling spare copies. Existing active-battle guards remain in force.
- [x] Run expedition lock, squad, upgrades, trees, collection, shop, progression, and reset suites; expect passes. Commit `feat: enforce expedition availability locks`.

## Task 6: Trials and authenticated activity API

**Files:** Create `src/ascension/trials.py`, `tests/ascension/test_trials.py`, `test_activity_api.py`; modify `coordinator.py`, `progression.py`, `battle_view.py`, `api.py`, `composition.py`, `tests/ascension/env.py`, and existing API fixtures.

**Interfaces:** `TrialService(repo, catalog, clock)` exposes `progress(owner: str) -> dict[str, Any]`, `prepare(owner: str, type_id: str, stage: int) -> dict[str, Any]`, `validate_in(tx: AscendedTransaction, owner: str, type_id: str, stage: int, ascended_id: str) -> TrialStageSpec`. Responses include six types and per-stage cleared/unlocked/first-clear flags plus eligible fighter ids and explanatory reasons.

Coordinator adds `start_trial(owner: str, key: str, *, type_id: str, stage: int, ascended_id: str, preset_slot: int | None, mode: str) -> dict[str, Any]`. Extract `_start_in(tx, owner, encounter, ascended_id, preset_slot, mode, emblem_limit, now) -> BattleRecord` from current start, retaining validation/seed/view behavior. Trial start validates and creates its internal encounter plus battle in the same writer transaction; never chain two externally committed service mutations. Construct trial enemy with fixed stage parameters and normally generated hidden personalities.

Public routes (relative to existing `/ascension` router):

| Method/path | Choices / response |
| --- | --- |
| GET `/activities` | Public catalog activity definitions |
| GET `/activities/hunts/{difficulty_id}/prepare` | Query `ascended_id`; return overall, recommended range, exact reward_multiplier, penalty_percent, below_range; validate ownership |
| POST `/encounters` | Optional `{difficulty_id}` body; omitted or `{}` retains legacy roll |
| GET `/trials` | Owner progress for all six types |
| GET `/trials/{type_id}/stages/{stage}/prepare` | Eligibility, opponent preview, progress and reward preview |
| POST `/trials/{type_id}/stages/{stage}/battles` | `{ascended_id, preset_slot, mode}`; BattleView |
| GET `/expeditions` | Task 4 status plus server_now |
| POST `/expeditions` | `{ascended_id, duration_hours}`; expedition status |
| POST `/expeditions/{id}/claim` | No body; frozen receipt |

- [x] Write failing trial tests for all six labels, matching/multi-type fighter, non-squad/fainted/dispatched rejection, stage lock/replay, first-clear grant once, matching-only bench pool, defeat/escape/forfeit, and progress isolation. Enchant Guardian at stage 1 victory yields 120 XP, 60 Insignia, 2 Common essence on first clear; replay yields 60/30/1. Guardian is not eligible for Pure. Twoychi qualifies for Enchant and Divine. Include a manually seeded other-type bench member to prove exclusion without changing shipped character types.
- [x] Add manual action, autonomous decision, in-battle mode switch, and EMBLEM route tests: trial action lists exclude catch; a forced catch selection cannot open a prompt/spend an EMBLEM; autonomous works with a populated preset and no limit; switching a trial to autonomous does not introduce a limit requirement. Hunt/legacy requirements stay unchanged. Reject forged `captured` trial terminal grants defensively.
- [x] Write API assertions for no body legacy compatibility, strict integer choices, unknown fields/reward/time/owner spoofing, unauthenticated access, foreign ids, expired claims, and missing Idempotency-Key. Wrong choices fail without writes; legacy bodies/routes still work.
- [x] Run `python -m pytest tests/ascension/test_trials.py tests/ascension/test_activity_api.py -q`; expect failures.
- [x] Implement type/stage validation and extract transaction-local battle creation. Gate all player `can_collect` paths, prompt handling, and mode validation by persisted activity, including `set_mode`. At terminal victory atomically `mark_trial_clear` and calculate its one-time multiplier before reward grants; filter bench before calculating divisor. Include activity origin/first-clear details in views/results. Wire shared TrialService/ExpeditionService into composition and service dataclass; routes remain adapters with strict Pydantic bodies and authenticated owner dependencies.
- [x] Run trial/activity API plus existing coordinator/API/progression tests; expect passes. Commit `feat: add type trials and activity endpoints`.

## Task 7: Typed client and restorable mode state

**Files:** Modify `web/src/api/AscensionClient.ts`, `AscensionClient.fixtures.ts`, `AscensionClient.test.ts`, `web/src/stores/ascension.ts`, `ascension.test.ts`.

**Interfaces:** Export matching TS `ActivityContext`, `ActivityDefinitions`, `HuntPreparation`, `TrialProgress`, `TrialPreparation`, `ExpeditionView`, `ExpeditionStatus`, and `ExpeditionReceipt`. Extend existing Profile/OwnedAscended/EncounterPreview/BattleView/Result with Task 3/5/6 fields. Client methods: `activities()`, `prepareHunt(difficultyId, ascendedId)`, `trialProgress()`, `prepareTrial(typeId, stage)`, `startTrial(typeId, stage, input, key?)`, `expedition()`, `startExpedition(ascendedId, durationHours, key?)`, `claimExpedition(id, key?)`. Extend `rollEncounter(key?, difficultyId?)` without breaking existing first-argument retry keys.

Store produces `activitySelection: "hub" | "hunt" | "trial" | "expedition"`, `huntDifficultyId`, `trialTypeId`, `trialStage`, definitions/progress/status, and action methods matching the client calls. `returnToActivity()` clears terminal battle/playback state and opens its originating hunt/trial using persisted context; legacy results return to Hunts. Resume active battles directly into the arena; resume pending Hunts into preview with persisted difficulty.

- [x] Write client tests asserting routes, choice-only bodies, encoded ids, and keys. Write store tests asserting restoration from pending/active context, refreshed wallet/squad/locks after departure/claim, unlocked stages after victory, and account reset clears all activity state. A deferred response from owner A after switching to owner B must not change owner B state. Failures keep selected duration/fighter and permit retry with the original key when an outcome is uncertain.
- [x] Run `npm test -- src/api/AscensionClient.test.ts src/stores/ascension.test.ts`; expect failures.
- [x] Implement using existing `mutate`, `generation`, and lifecycle helpers. Store expedition server_now with local monotonic receipt time to derive countdowns without trusting device wall time. Refresh activity data on attach/visibility return, relevant mutations, and completed trial, without adding a perpetual expedition polling loop. At predicted expiry enable a status refresh and let the server decide claim eligibility. Preserve existing autonomous round timers.
- [x] Run the focused tests and `npm run build`; expect passes. Commit `feat: connect game mode state to Ascension client`.

## Task 8: Mode screens and expedition status in current UI

**Files:** Create `web/src/components/GameModesPanel.vue`, `TrialsPanel.vue`, `ExpeditionsPanel.vue`, `gameModes.css`, `GameModesPanel.test.ts`, `TrialsPanel.test.ts`, `ExpeditionsPanel.test.ts`; modify `EncounterPanel.vue`, `CollectionPanel.vue`, `AscendedProgression.vue`, `TreeTab.vue`, `PresetEditor.vue`, `BattleResult.vue`, `App.vue` content integration, and affected component tests.

**Interfaces:** GameModesPanel emits `collection: []` to the existing App tab switch for empty-squad guidance. TrialsPanel selects type/stage then reuses EncounterPanel preparation via optional `trial: TrialPreparation | null` prop (default null), plus `prepared`/back handling local to panel. ExpeditionsPanel uses store definitions/status and the monotonic server-time anchor. New UI does not calculate overall or rewards from client-side character stats.

- [x] Write failing component tests for three destinations, three Hunt ranges, server-returned penalty and below-range warning, six type choices, stage locks, empty eligible list, Manual/Autonomous trial setup without EMBLEM limit, and disabled repeat submissions. Assert original AscendedPreviewCard renders for all fighter selections; ratings/status appear in adjacent UI, not inside cards.
- [x] Test expedition duration totals, explicit squad-removal/lock notice before send, countdown/ready/claim receipt, blocked slot, unavailable/fainted selection, empty-squad Collection action, and failure messages inside their panel. Advance fake monotonic time while changing device wall time; displayed remaining time must not jump. A server early-claim conflict refreshes status and retains the expedition.
- [x] Extend Collection/progression/tree/preset tests: dispatched species remains viewable with On expedition/Ready to claim subtitle, cannot drag into squad, cannot upgrade/learn/equip/save/default-switch; other species remains usable. Read-only exploration and existing preset unsaved-change handling remain intact.
- [x] Run new/affected component tests; expect failures before implementation.
- [x] Implement hub and mode content using EmButton/EmTabs/EmNotice/EmBar/TypeSymbol and the existing sanctuary. Hunt preparation calls the authoritative preview endpoint when fighter changes and ignores stale previews. Keep original Hunt encounter Fight/Decline behavior. For Trial preparation show the stage opponent and matching squad members; use `startTrial` instead of ordinary battle start. Integrate only App's content area and navigation event logic. Do not edit header template/styles, EmShell, EmTabs, AscendedPreviewCard, card assets, or sprite utility defaults.
- [x] Add profile-availability disabling at mutation controls; do not globally block reading tabs. In BattleResult route Back to hunts/Back to trials through `returnToActivity`. New CSS uses existing tokens and wraps/scrolls without shrinking preview cards below 160 px. Preserve battle arena, playback, focus, and busy-state behavior.
- [x] Run affected Vitest suites and `npm run build`; expect passes. Commit `feat: add Ascension mode screens`.

## Task 9: End-to-end acceptance and final review

**Files:** Create `web/e2e/game-modes.spec.ts`; modify `web/e2e/fakeApi.ts`, existing encounter-flow browser tests, and `apps/ascension/DESIGN.md` to record approved mode content rules while retaining header/card rules.

**Interfaces:** Extend FakeGameApi with activity routes/progress/expedition status and choice tracking matching Task 6. Browser tests prove UI behavior; real temporary-database Python tests remain the proof of server reward/locking correctness.

- [x] Add browser scenarios for hub→Hunt→encounter→preparation→result→origin, type trial eligibility/stages, and expedition send→Collection lock→reload→claim→manual equip. Use existing fake auth and real repo art routes. At 1440, 768, and 375 widths assert no page horizontal overflow, reachable controls, visible restrictions, and no altered preview aspect ratio. Run existing header and card artwork checks unchanged.
- [x] Run `python -m pytest tests -q` from the backend and `npm test`, `npm run build`, `npm run test:e2e` from the web project. Expected: all tests pass and production bundle builds. If tooling is missing, use the project's existing environment and report the exact unavailable check; do not silently count it as passed.
- [x] Inspect screenshots for each mode and expedition state at desktop/portrait sizes; compare header and preview-card asset usage against the pre-change implementation. Confirm `git diff` contains no changes to protected header/card components or art. Fix only failures within agreed scope and rerun affected checks.
- [x] Update DESIGN.md with the three-mode content flow, ratings outside cards, and expedition status wording. No speculative extra modes or settings. Commit `test: verify Ascension game modes`.
- [x] Perform a whole-change review against the approved spec, migrations, concurrency guards, reward claims, legacy battle compatibility, and unchanged header/cards. Follow the selected execution skill for reviewer use. Report delivered behavior, validation evidence, and any remaining limitation; no completion claim while any of the three modes is unfinished.

## Plan self-review

- Coverage: every approved-spec acceptance condition maps to Tasks 1–9; the initial rates, stages, bands, and unavailable-type behavior are explicit.
- Interfaces: activity context is separate from control mode; no frontend field supplies authoritative reward/timing values; helper guards stay inside caller transactions.
- Compatibility: default legacy context, positional record constructors, optional encounter body, and unchanged first-argument client retry keys preserve existing flows.
- Critical paths: trial mode-switch capture guards, duplicate capture/shop auto-enrollment, different-key expedition claim retries, empty squad, account-generation races, clock skew, and owner reset have named tests.
- Scope: no new combat engine, scheduler, dependency, character art, Ember feature, header design, or preview-card design.

## Execution handoff

Owner reviews this plan and selects **Native** (implement in this session, then a whole-change reviewer) or **Subagent-driven** (implement/review each task with fresh agents). Recommend Native: the nine tasks share catalog, repository, coordinator, and store interfaces, so keeping implementation in one session reduces handoff overhead. The owner authorized implementation on 2026-10-15. Native execution completed; final independent review findings were fixed and verified. Final checks: 1061 backend tests passed (1 existing skip), 319 frontend tests passed, 32 browser tests passed, production build passed.
