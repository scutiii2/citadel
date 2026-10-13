# Ascension UI Redesign Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement scoped tasks and review the integrated result.

**Goal:** Implement the approved Ascension UI using existing battle sprites and preserved symbol assets.

**Architecture:** Keep Vue/Pinia/API boundaries and game rules. Replace presentation components and layout while using the existing mutations; the shop adds an in-memory basket over those APIs.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, Playwright, Vite.

**Spec:** `docs/superpowers/specs/2026-10-13-ascension-ui-redesign.md`

## Global constraints
- Battle sprites only; preserve old files and user edits.
- Preserve EMBLEMs and Ascension Type symbols; Tavern disabled.
- Existing game rules override illustrative prices/stats; no backend gacha.
- Work in the current linked worktree; do not commit or overwrite unrelated work.

## Review focus
- Missing battle art must not reveal old portraits.
- Navigation from an active battle must never forfeit it.
- Batch failure/rotation changes must preserve unprocessed basket items without replaying completed trades.
- Mobile layouts must avoid horizontal overflow and preserve touch controls.
- Squad/full/resting states and progression requirements must remain honest.

## Task 1: Navigation and shared cards
- Files: `MainMenu.vue`, `EmShell.vue`, `App.vue`, `AscendedPreviewCard.vue`, `AscendedTemplateCard.vue`, `utils/sprites.ts`, theme/UI primitives and their focused tests.
- [x] Add failing tests for explicit primary battle navigation, Collection, locked Tavern, back navigation and battle-only sprite selection.
- [x] Redesign menu/header/cards; keep existing component contracts or document changes to other implementers.
- [x] Run focused unit tests.

## Task 2: Collection and progression
- Files: `CollectionPanel.vue`, `AscendedCard.vue`, `TreeTab.vue`, `PresetEditor.vue` and focused tests.
- [x] Add regressions for selecting an inspector, retaining detail operations and battle-only portraits.
- [x] Add filter rail, squad/grid/inspector layout and details/progression panels. Restyle tree and preset inspector without changing rules.
- [x] Run focused unit tests.

## Task 3: Encounter and battle flow
- Files: `StarterPick.vue`, `EncounterPanel.vue`, `BattleMatchup.vue`, `BattleArena.vue`, `BattleControls.vue`, `BattleResult.vue`, `ActionBar.vue`, `RoundLog.vue` and focused tests.
- [x] Add/update behavior tests for battle-only sprites and preserved controls.
- [x] Restyle starter, planning, arena/actions/log and results with responsive layouts.
- [x] Run focused unit tests.

## Task 4: Shop basket
- Files: `ShopPanel.vue`, `ShopPanel.test.ts`, shop-basket composable/helpers as needed, and store/client only if existing APIs require it.
- [x] Write failing tests for multi-item quantities, totals, sell review, stock/budget, interrupted batches and expired offers.
- [x] Implement modes, filters, grid and basket using existing mutations; successful quantities are removed immediately, failed/unprocessed quantities retained.
- [x] Run focused unit tests.

## Task 5: Integrate and verify
- [x] Run all unit tests and production build; resolve integration failures.
- [x] Review approved reference sheets and inspect desktop/mobile browser screenshots with fixtures.
- [x] Run relevant Playwright flows; document environment blockers precisely.
- [x] Request independent review; fix meaningful findings and repeat affected checks.

## Verification results

- Frontend: 258 unit tests pass; TypeScript/Vite production build passes.
- Browser: 7 Playwright tests pass with Edge, covering desktop, tablet and mobile.
- Backend: 212 focused profile/shop tests pass. Full Ascension suite: 891 pass, 5 existing failures. The same failures were reproduced with the original HEAD collection service loaded in memory, without modifying files. Those tests expect an outdated 30-second cooldown, Guardian crop focus 21 instead of 50, or missing Bruiser battle art despite its existing sprite.
- Independent review: fixed basket persistence across navigation, shared in-flight ownership and retries with original idempotency keys/rotation. Final review found no remaining major issues.
- Character files and existing EMBLEM/type artwork were preserved. The generated asset is a forge environment background containing no characters or symbols.
