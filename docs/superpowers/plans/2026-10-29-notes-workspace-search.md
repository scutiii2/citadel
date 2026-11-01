# Notes workspace search implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline.

**Goal:** Implement the approved Notes mockup with draft-safe sidebar search, the shared workspace styling and one scrolling editor body.

**Architecture:** Keep NotesView's existing CRUD, conflict handling, tag suggestions, access controls and promotion panel. Add a computed filter over the already-loaded notes, using SearchField and title/body/tags. Reuse ListEditorLayout, pane-scroll, CharacterCount, shared states and existing browser helpers. Keep the editor and publishing flow mounted through search changes.

**Tech stack:** Existing Vue 3, TypeScript, Vitest and Playwright dependencies only.

**Spec:** Approved Notes light/dark desktop and mobile mockup in this chat. Mock content and dates remain sample data.

## Constraints

- Preserve API requests, latest-edit ordering, limits, notices, unsaved guards, stale tag-response handling and save conflicts.
- Search filters saved title/body/tags, case-insensitively by whitespace-separated terms; blank search restores the list. The current editor and new-note draft survive no results.
- Keep secondary tools collapsed individually, with DangerZone and confirmation last. Preserve the real publishing panel and dialogs.
- Use existing shared controls and tokens; leave ember_admin unchanged.
- Preserve effective 44px mobile targets, focus transfer, fixed Save and independent visible pane scrollbars.

## Steps

- [x] Establish the Notes baseline: 53 existing tests pass.
- [x] Add search, draft preservation and keyboard-focus regression tests; verify they fail first.
- [x] Implement sidebar search, shared counters/states, workspace spacing and auto-growing note text using existing components and helpers.
- [x] Adapt only moved-control selectors and add browser search/responsive checks in both themes.
- [x] Update the frontend skill with draft-safe local search and the Notes reference.
- [x] Run vue-tsc, unit/browser suites, inspect screenshots, review and commit.

## Execution notes

Work is isolated at .worktrees/notes-workspace on codex/notes-workspace-search, based on 39af6e76 so the completed Skills and Brains redesigns are included. Dependencies use a junction to the existing installation. No changes to the original checkout are needed.


The original 53 Notes tests remain intact; five new cases cover full-text/tag/title filtering, ordering, empty-result draft preservation, new drafts, focus return and load retry. All 2,230 unit tests in 185 files pass. TypeScript passes. Focused browser checks cover Notes CRUD, conflicts, tag suggestions/generation, publishing, search and draft safety.

The body uses the existing growToContent helper and a width-only ResizeObserver with cleanup, so the editor pane owns scrolling. Mobile tools retain individual disclosures. Search and New note / Clear search touch targets are checked at narrow widths; the browser matrix includes desktop, 768, 767, 375 and 320px in both themes.

Read-only code review found no actionable issues. A verification-only overlap of browser runs collided in Playwright's shared trace directory; the final browser run is serialized. Physical-device keyboard and rotation checks remain manual.


Final verification: npx vue-tsc -b passed; npm test -- --maxWorkers=4 passed 185 files / 2,230 tests; the final serial npm run test:e2e passed all 101 browser tests. Mobile New note and Clear search controls meet the 44px target. Desktop and mobile screenshots were visually inspected and saved outside the repository. No ember_admin or original-checkout application files were changed.
