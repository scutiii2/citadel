# Ember mobile UI instructions

Use with `ember-frontend-design` and `ember-design-system` for both Ember Vue apps. This guide adapts the Brain's UI/UX rules to Citadel's existing frontend. Explicit user requirements take precedence; otherwise follow repository and app instructions. Follow Citadel's existing motion policy.

## Read the existing implementation first

- Find the affected route, `PageLayout` usage, shared components and current mobile styles. Reuse the existing interaction before introducing a new one. Use `ember-feature-scaffold` for routing and API wiring.
- Use `style.css` as the token source. Keep the orange accent, semantic colors, typography and radius scale. Give related fields smaller gaps than separate groups; preserve existing spacing conventions rather than imposing a new global scale.
- Use Notes for list/editor workspaces, Brains for scoped browser/reader flows, Memory for row editing, and Video Downloader for jobs/results. Adapt the task pattern rather than copying a screen's unrelated controls.

## Layout and navigation

- The existing shell switches below 768px (`max-width: 767px`). Keep 767 and 768 distinct when checking the transition. At narrow widths, give the active task the full content width. Use list-to-detail/editor navigation with a visible Back action, or a short labeled segmented selector.
- Preserve primary actions such as Save, Send, download and confirmation. Place secondary setup and management behind clear disclosure. Reflow header actions before shrinking text or targets; do not hide supported actions merely to fit a phone.
- Keep DOM reading order aligned with visual order. Retain meaningful labels and selected states; mobile actions must work without hover. Keep product navigation in its existing rail/account-menu locations.
- The view owns scrolling; preserve `min-width: 0` and `min-height: 0` through flex/grid ancestors. Wrap long titles, names, errors and URLs. Keep code or genuinely wide tables in a labeled local horizontal scroller instead of making the whole page scroll sideways.
- For dense admin content, choose task-specific rows, a detail view or a contained table. Retain the data and actions needed to complete the task. Do not create a separate mobile data contract.

## Touch and readability

- Give ordinary mobile controls an effective hit area of at least 44 by 44 CSS px. A 24px icon can sit inside that area; the icon itself need not grow. Keep adjacent hit areas separate. This is Ember's usability target, not a blanket claim about accessibility certification.
- Global coarse-pointer CSS supplies button minimum height; verify width, icon controls, links, segmented choices and modal close buttons individually. Do not assume a 44px-tall rule supplies a 44px-wide target.
- Keep visible labels, accessible names and focus indicators. Use a familiar icon plus text when the action is ambiguous. Status includes text or an icon alongside color. Touch, keyboard and pointer users should reach the same functions.
- Preserve the mobile input text floor already set in `style.css`. Keep text readable with longer labels and enlarged text; resolve overflow through layout rather than disabling zoom or making fonts smaller.

## Virtual keyboard, viewport and sheets

- Reuse the shell's viewport handling. `ember_web/src/App.vue` maintains `--app-viewport-height` and `--app-viewport-top` from `visualViewport`; the global stylesheet uses them with a `100dvh` fallback. The admin shell currently uses `100dvh` without that bridge. Inspect the affected app before assuming identical keyboard behavior.
- Keep the focused input, validation message and relevant Save/Send action reachable when the keyboard opens. Prefer scrolling the owning content pane; avoid fixed full-screen overlays and page-level scrolling that fight the shell. Do not add another independent viewport listener to each page.
- `--rail-height` already includes the bottom safe-area inset in both apps. Anchor ordinary mobile sheets above the rail with `bottom: var(--rail-height)`. Avoid charging the same inset twice. Reuse the shell's top/side safe-area padding.
- Size modal/sheet content to the available viewport and allow its body to scroll. Check the last field and final destructive action with the keyboard open. A document-level native dialog can have different positioning from the app shell; verify its actual behavior rather than assuming shell variables automatically fix it.
- Rotation, keyboard dismissal and browser chrome changes must leave the active pane usable. Preserve user zoom; follow the shell's existing treatment of viewport scale.

## Drafts, dialogs and async state

- Switching between list/editor or segmented modes preserves drafts, selection and the relevant list/reader scroll position. Keep draft-bearing components and job watchers mounted, as the frontend skill requires. Do not let a refresh reset the current document or result.
- Define Back and route-leave behavior for unsaved data. Preserve the draft or use the existing in-app confirmation pattern before discarding it. Label Save and Discard explicitly where offered; a Cancel/Stay action keeps the draft intact. Keep a completed server save distinct from a pending request.
- Keep dialogs outside ancestors hidden by mobile mode changes. Preserve a valid open dialog across a compatible transition, or close it deliberately and restore focus to a visible control. Reuse `BaseModal` and `ConfirmModal` for modal focus behavior. A nonmodal popover is not automatically a modal.
- Acknowledge actions immediately with a pending state, while reporting success only after confirmation. Use skeletons for predictable content or an appropriate loader for an unknown shape. Provide field-specific errors and a clear recovery action; retain entered values on failure.
- Remote search updates typed text immediately and may debounce requests when useful. Debounce alone does not prevent out-of-order results. Cancel superseded work where possible and reject responses that no longer match the current query, scope and request identity. Invalidate pending work on clear, scope change and unmount. Respect IME composition and support explicit submit.
- Scope changes clear private content before loading the next scope; late replies must not restore the old scope. Handle empty, pending, no-results, failed and succeeded states without losing the active task.

## Checks for the affected flow

Use the parent skill's existing type, unit and e2e commands in each touched app. For instruction-only changes, verify documentation references and `python sync_skills.py --check`; do not claim UI behavior was tested. Shared-component changes require checks in both apps.

For UI implementation, cover the relevant cases below in existing automated tests where practical and give the user concrete manual checks for device-only behavior. Follow the parent skill's manual browser-verification policy.

| Case | Expected result |
|---|---|
| Desktop, 768px, 767px, 375px; 320px for a narrow-phone change | Correct navigation transition; no horizontal page overflow; supported actions reachable. |
| Light and dark themes, long content, enlarged text | Readable hierarchy, contrast and wrapping; useful labels remain visible. |
| Touch and keyboard activation | Separate hit areas, accessible names, visible focus and no hover-only action. |
| Edit the last field with the keyboard open; rotate and dismiss keyboard | Field, error and Save/Send remain reachable; scroll ownership stays stable. |
| Back, mode switch and refresh with unsaved edits | Draft and context survive, or explicit discard is confirmed. |
| Open dialog, then change mobile mode | Dialog stays usable or closes deliberately; focus returns to visible content. |
| Slow, failed and out-of-order searches; clear input or switch scope | Latest valid query/scope owns results and status; old replies cannot leak content back. |
| Open a long sheet above the bottom rail | Last action and Danger zone remain reachable; safe-area padding is counted once. |

Report only checks actually performed. Record skipped device checks as pending. Review improvements against the requested task, not as proof that every existing screen already meets this guide.

## Brain provenance and future lessons

The source map is `Brain/Maps/UI UX Frontend Rulesets.md` from the Programming workspace root, with atomic rules under `Brain/Notes/`. The guide is self-contained so a Citadel checkout works without that local vault. Consult the map for detailed rationale when available; preserve the distinction between source advice, engineering guidance and verified project outcomes.

When asked to save a lesson to the Brain, update the matching rule with the project, date, observation and verification evidence. Keep project-specific choices in the project note. Merge repeated lessons and record a contextual exception when evidence conflicts. New Brain advice must be reconciled with Citadel instructions before importing it.
