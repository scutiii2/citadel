# Brains workspace implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline.

**Goal:** Implement the approved Brains v2 mockup with scope and search inside the sidebar, aligned with the completed Skills workspace.

**Architecture:** Keep PageLayout wide fill and WorkspaceLayout. Reuse SegmentedControl, SearchField, ListRow, MarkdownContent, StateMessage, BackButton and the existing personal-connection form and BaseModal. Reuse pane-scroll from the Skills change. Keep the reader mounted when changing browse/search presentation; existing API operations and originating-scope behavior remain intact.

**Tech stack:** Existing Vue 3, TypeScript, Vitest and Playwright dependencies.

**Spec:** Approved Brains v2 light/dark desktop and mobile mockups in this chat. Sample document content and connection status are not production fixtures.

## Constraints

- Preserve browse/search/read/status API calls, deep links, privacy clearing on scope changes, partial search failures, retries and connection-form drafts.
- Put scope and explicit-submit search in the sidebar, with readable rows and visible independent scrollers.
- Put path controls and Personal connection / Check connection in disclosures; leave the real connection form mounted outside hidden mobile ancestors.
- Use tokens and shared component styling; change only ember_web and its frontend skill.
- Keep Back, focus, footer, and dialogs reachable on mobile above the existing rail.

## Steps

- [x] Verify the existing Brains tests before edits.
- [x] Add regression tests for sidebar ownership, document preservation through search, focus transitions and original-scope navigation.
- [x] Restructure BrainsView around a persistent browser/reader workspace and shared status components; remove local copies of shared control and spinner styling.
- [x] Adapt e2e selectors only for moved controls; check desktop, 768, 767 and 375 in both themes, connection drafts and scope privacy.
- [x] Update the frontend skill with sidebar-owned discovery and read-only reader guidance.
- [x] Run vue-tsc, unit and browser suites, inspect screenshots, review and commit on codex/brains-workspace-restyle.

## Execution notes

The original checkout contains unrelated Legion edits on feat/legion-gateways. Work is isolated at .worktrees/brains-workspace, based on main, with the completed Skills commit carried forward as ed41a84e. Existing dependencies are linked through a local node_modules junction. Do not stage or modify the original checkout's Legion files.


Baseline: seven existing Brains and connection-form tests passed. The three added regression tests failed against the old structure, then passed after implementation. The final unit suite passes 185 files / 2,225 tests; TypeScript passes.

The browser checks cover 1440, 768, 767, 375 and 320px in light and dark, scoped search and partial failures, deep links, failed-read recovery, keyboard focus and pane scrollbars. They also reproduce and fix a native-dialog close race: restore reader focus after BaseModal finishes its close ticks. Connection drafts survive desktop-to-mobile dialog transitions, and sheets stay above the rail.

Read-only code review found no additional actionable findings. Physical-device keyboard and rotation checks remain manual.


Final verification: npx vue-tsc -b passed; npm test -- --maxWorkers=4 passed all 2,225 tests in 185 files; npm run test:e2e passed all 100 browser tests. The original Personal Brain test required one additional step to open the moved connection disclosure; all its save/test assertions were retained. No ember_admin files or unrelated Legion working files were edited.
