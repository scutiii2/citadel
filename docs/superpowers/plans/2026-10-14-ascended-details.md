# Ascended details implementation plan

**Goal:** Implement the approved Overview, Ability Tree and Personality mockup.

**Architecture:** Keep collection operations in CollectionPanel and reuse TreeTab and PresetEditor. Add shared shaped ability slots. Store the per-Ascended battle default on the server and initialize the existing battle setup selector from it; setup overrides do not change that default.

**Tech stack:** Vue 3, TypeScript, Pinia, FastAPI, SQLite.

**Spec:** The three-tab mockup approved in this chat, with each Ascended's main card art on Overview, a generated shared navy cavern background on the other tabs, and no underline on the name.

## Constraints

- Per-character assets remain in ascended/<id>; use the existing main_card URL directly without changing other sprite consumers.
- Preserve squad controls, star/tier progression, personality tiers/pagination/save, and tree learning/equipping/pan/zoom.
- Exactly two passive circles, four active octagons, five presets, and up to three personalities per preset.
- Personality descriptions reflect the real catalog; the mockup's names were illustrative.
- Server persistence must isolate owners and validate slots. Battle overrides must not overwrite the default.

## Tasks

- [x] Add regression tests for persisted, owner-scoped default presets and Overview main-card art/preset previews.
- [x] Add schema migration, collection/API/client support for default preset selection; return resolved selected personalities alongside preset IDs for paged libraries.
- [x] Implement the modal header, full artwork Overview, shaped loadout and default selector; retain progression controls in an expandable panel.
- [x] Rework TreeTab into left equipment/detail rail and large graph with right zoom controls; add generated background.
- [x] Rework PresetEditor into left preset rail, middle equipped personalities, searchable/filterable library; preserve explicit save and pagination.
- [x] Initialize battle setup from the selected Ascended's saved default and preserve temporary overrides.
- [x] Run focused tests, complete frontend suite/build and backend regressions; visually inspect desktop and narrow layouts.

## Review focus

Stale responses when switching Ascended or presets; selected personalities outside the first library page; empty presets; migration from schema 6 and older; mobile scrolling; existing game operations remain reachable.

## Execution notes

Implementation runs inline in the existing isolated worktree. No commits or external checkout edits requested. Shared background generated with the built-in image tool; source prompt retained beside the asset.

Completed all tasks. Schema 7 adds an owner-scoped default slot, initially 1, without rewriting presets, collection values, or squad order. Migration runs atomically from versions 2–6. To run a pre-version-7 server again, restore its pre-upgrade database backup; no destructive downgrade is included.

Actual catalogs sometimes expose fewer than six usable ability slots. The modal displays all six shapes and disables unsupported slots, preserving catalog rules.

Review found and fixed stale Overview loadout responses, inspector selection reset after learning/equipping, and repeated Overview ability selection. Regression tests cover these cases.

Validation: production build passed; 4 browser scenarios passed (Twoychi artwork/default interactions and 1440/768/375px layouts). Frontend suite: 281 passed, 7 unrelated existing preview-card artwork expectation failures. Full backend suite before updating four schema-version assertions: 893 passed, 9 failed (four assertions updated for schema 7; five unchanged cooldown/artwork expectations). Final focused storage/collection/API/squad suite: 98 passed, 10 deselected. The new migration/default tests pass. Review screenshots are copied to the chat's visualization directory.
