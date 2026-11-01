# Skills workspace implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement these steps inline.

**Goal:** Implement the approved Skills mockup with a searchable list, document editor and independent visible scrollbars.

**Architecture:** Reuse PageLayout wide fill and ListEditorLayout from Memory and Notes. Extend ListRow with an optional actions slot so the selected outline encloses Approve without nested buttons. Existing rows retain their button root. Use the existing unsaved guard for editor navigation and ConfirmModal for deletion.

**Tech Stack:** Vue 3, TypeScript, Vitest, Playwright; existing dependencies only.

**Spec:** Approved v7 mockup and constraints in this chat. The approved workspace supersedes the original BaseModal editor requirement. The removed sample row does not filter production data.

## Constraints

- Preserve all API calls, statuses, notices, confirmation text and accessible action names.
- Reuse shared states, search, counters, rows, layout and DangerZone; keep management collapsed.
- Retain all production skills and existing ordering; optional search covers title and when_to_use.
- Use existing theme and radius tokens; leave ember_admin untouched.
- Keep separate mobile touch targets and reachable Save/Back actions above the app rail.
- Update skills only in .agents/skills; the existing symlink requires no sync.

## Steps

- [x] Adapt existing Skills tests for the workspace; add coverage for search, selection/action independence, draft protection and delete/save failure recovery.
- [x] Extend ListRow actions with focused interaction coverage; add opt-in workspace scrollbar styling and correct SearchField's inherited input styling.
- [x] Implement SkillsView with the existing APIs, grouped rows, Notes-style editor, counters, tools disclosure, management and delete confirmation.
- [x] Update the frontend skill to describe the proven workspace, complete-row selection and scrollbar pattern.
- [x] Run vue-tsc, npm test and npm run test:e2e; check desktop, 768, 767 and 375 in both themes with mocked API data.
- [x] Review the diff for contract preservation and shared-component compatibility; commit on codex/skills-workspace-restyle.

## Review focus

Approval must not select the row; selection must not approve. Status changes must preserve drafts. Unsaved Back and row switches require a discard decision. Failed saves/deletes retain content and recovery controls. Long titles must wrap without clipping; search and Save remain fixed while their panes scroll.

## Execution record

Baseline: 15 tests passed across SkillsView, ListRow and SearchField. Work proceeds in the clean current checkout on the requested new branch; no additional worktree or dependency installation is needed.


Completed: shared action frame and footer/scrollbar opt-ins retain the existing defaults. SearchField and quiet destructive links are protected from legacy information-page styling. Skills preserves all original API methods, statuses, notices and confirmation text; production data is not filtered except by the requested search.

Review found missing focus transfer after replacing the modal. A failing regression test demonstrated it; the fix focuses the title on entry and restores the row or search on return. Long titles also resize through the existing growToContent helper and an element ResizeObserver.

Verification: vue-tsc passed; 185 unit files / 2,222 tests passed with four workers; the full 99-test browser suite passed, followed by the final two Skills tests with keyboard focus assertions and visible scrollbar captures. Screenshots were inspected at desktop and mobile; browser assertions cover 1440, 768, 767 and 375 in both themes. Physical-device keyboard and rotation checks remain manual.

The first full unit run also exposed a pre-existing literal 999px radius in ChatInput's live badge. It was replaced with --radius-full. An unrelated chat-store timeout did not recur with bounded workers. No ember_admin files were changed.
