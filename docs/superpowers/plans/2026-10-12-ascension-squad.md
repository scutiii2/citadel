# Ascension Squad Implementation Plan

> **For agentic workers:** Use Superpowers execution and test-driven development. Steps use checkboxes for tracking.

**Goal:** Equip a configurable squad, share victory XP with its bench, and choose fighters through an animated squad picker.

**Architecture:** Store ordered squad membership in SQLite schema 6. SquadService owns edits and automatic equipment; existing transactional progression pays shared XP. Vue derives squad membership from the profile and shares the starter's selection component.

**Tech Stack:** Python, SQLite, FastAPI, Vue 3, TypeScript, Pinia, pytest, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-12-ascension-squad-design.md`

## Global Constraints

- Squad size is configured by economy.squad_size, default 5; at least one member.
- Other squad members only receive floor(floor(R * 0.5) / bench_count) XP by default. Owner confirmed this scope.
- No mid-battle squad edits, switching fighters, encounter roll changes, or Ember changes.
- Keep fighter result fields and fainting rules unchanged; only wins and captures pay XP.
- Use existing theme tokens and respect reduced motion.

## Review Focus

- Migration respects nondefault squad sizes and runs every intermediate schema upgrade.
- Automatic equipment does not pay capture XP to the newly captured member retroactively.
- A member becoming fainted while setup is open cannot submit a battle.
- Collection actions cannot remove the last member or edit while a battle is active.
- Disabled picker cards reject both clicks and keyboard selection.

### Task 1: Backend squad and rewards

**Files:** catalog/configs, repository.py, new squad.py, collection.py, progression.py, shop.py, composition.py, coordinator.py, api.py and backend tests under apps/ascension.

**Interfaces:** get_squad(owner) -> tuple[str, ...]; set_squad(owner, Sequence[str]); GET/PUT /ascension/squad -> {ascended_ids, size}; profile adds squad, squad_size, in_squad; terminal result adds squad_xp.

- [x] Add failing tests for config validation, ordered membership, migration v2/v5 with custom size, validation/idempotency, automatic equipment, coordinator membership and shared XP including capture, cap, fainting and no-reward terminals.
- [x] Run pytest and verify missing feature failures.
- [x] Implement the transactional backend design and preserve existing tests.
- [x] Run the complete backend pytest suite and commit backend changes.

### Task 2: Client, store and collection

**Files:** AscensionClient.ts, fixtures, stores/ascension.ts, CollectionPanel.vue, e2e/fakeApi.ts and associated tests.

**Interfaces:** squadIds -> string[]; squadMembers -> OwnedAscended[] in squad order; setSquad(ids), addToSquad(id), removeFromSquad(id). Battle result squad_xp is optional for compatibility.

- [x] Add failing tests for ordered squad state, actions/error handling, strip slots and detail action disabled reasons.
- [x] Implement client methods, profile fields, store actions and collection equipment controls.
- [x] Run scoped Vitest suites and commit these changes.

### Task 3: Shared picker, battle preparation and results

**Files:** new ui/EmPickCard.vue/test, StarterPick.vue, EncounterPanel.vue/test, BattleResult.vue, BattlePanels.test.ts and e2e/ascension.spec.ts.

**Interfaces:** EmPickCard selected/disabled props and select event; EncounterPanel submits selected squad member with the unchanged battle payload.

- [x] Add failing picker tests for selection, keyboard and disabled behavior; setup tests for squad order, placeholders, ready selection and selected fighter submission; result tests for shared XP and level-up text.
- [x] Extract starter selection styles into EmPickCard, implement responsive squad preparation and bench reward rows.
- [x] Run Vitest including StarterPick regression tests and update the first-visit e2e to inspect the squad picker.
- [x] Commit these changes after green verification.

### Task 4: Documentation and whole-feature verification

**Files:** apps/ascension/README.md, web/README.md; Ascension vault note via project-sync.

- [x] Document squad rules, migration and UI controls.
- [x] Run pytest, full Vitest, Playwright and the build_ui.bat build commands.
- [x] Review the combined diff, fix material findings, record verification and commit documentation.

## Execution record

- Existing isolated worktree verified; initial git status clean.
- Backend and client/collection implementations run independently under the parallel-agent skill, with exact shared interfaces above. Battle picker/results run in the primary agent.
- Owner confirmed squad-only XP sharing.

## Final verification

- Backend: `python -m pytest -q --basetemp=<artifact-root>/backend-final` -> 1023 passed, 6 pre-existing failures. The same six failed in a pristine HEAD archive: cooldown default expectation, guardian crop focus, bruiser sprite presence, and cindrax PNG content under a WebP filename. No unrelated content was changed.
- Frontend: `npm test` -> 233 passed across 28 files.
- Browser: `ASCENSION_WEB_PORT=5194 PLAYWRIGHT_CHANNEL=chrome npm run test:e2e -- --workers=2` -> 10 passed. Checked widths 1280, 768 and 390 for the squad picker, plus existing details and shell checks. Verified normal and reduced-motion animation duration. Inspected desktop and mobile screenshots with shipped sprite art.
- Build: `npm run build` (the build command in build_ui.bat) -> TypeScript and Vite pass.
- Vault: project-sync updated the Python-game portion of Brain/Projects/Ascension.md; `validate_vault.py --all` -> vault OK. Vault changes are uncommitted.
- Final independent review: no remaining material issues; reviewed migration, rewards, client state, collection controls, picker accessibility and responsive behavior.
- Ruling: first purchases that would auto-equip are rejected during active battles; otherwise they would bypass the squad lock. Purchases that do not alter membership remain allowed.
- Ruling: kept the six verified baseline failures outside this feature's scope.
- Execution: grouped the spec's ten ordering steps into four coherent commits so backend integration, client/collection, picker/results and documentation travel with their tests.
- Test fixes: the HTTP win test uses ScriptedPolicy so wild fleeing cannot make it flaky; the fake API ignores Vite dependency URLs and serves shipped sprites for visual checks.