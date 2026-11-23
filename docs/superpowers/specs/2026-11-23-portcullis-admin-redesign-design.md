# Portcullis Admin redesign specification

Bring the [Portcullis mockup](../../../apps/portcullis_admin/mockups/portcullis-redesign.html) into the live-data Vue app. Follow the [Citadel frontend skill](../../../.agents/skills/ember-frontend-design/SKILL.md). Include the agreed profile theme, settings Cancel icon, and search focus fixes in the existing Legion Admin UI.

## Shell and navigation

- Use Ember orange and a compact full-width header. Place the sidebar toggle, Portcullis Admin identity, divider, and current page title on the left. Place Notifications, Help, and Profile on the right. Profile contains identity, existing Profile, Settings, and Ember links, theme, and Log out. Use a labeled Dark, Light, and System selector with a token-rounded border, chevron, and one inset keyboard focus outline. Keep existing theme persistence and default.
- Keep Overview, Accounts, Roles & permissions, Invites, Workspace settings, and authorized Config issues in navigation. Preserve existing permission filters and saved sidebar ordering, pinning, and visibility. Place Legion, Armory, Stronghold, and Treasury shortcuts at the bottom. Expanded desktop shows labels, collapsed desktop shows named icons, and mobile discloses navigation above content.
- Use `PageLayout` for geometry and scrolling. The header owns the visible page title. Keep section headings, action slots, and task-specific notices. Keep production home, deep links, verification, session-expiry, no-access behavior, and PWA notices.
- Notifications link to real config issues when authorized and available. Distinguish an empty result from a failed check. Help explains the current workflow using real app behavior.

## Panels and drawers

- Give record lists and editable settings panels labeled search in their headers. Draw one inset focus outline around the search icon and input. Search is panel-local and preserves drafts and selection. Keep pending, error, empty, no-match, and retry states distinguishable. Clip row hover, selection, and focus inside rounded borders.
- Make the full row open details when it has one details action. Keep native keyboard activation and table semantics. Restore focus to the row after closing, or to panel search when the row is gone.
- Open record details and editors in a full-height right drawer with a dimmed backdrop. Put Edit, Expand, and Close together in the header. Expand to about 90% of viewport width, capped at full viewport on phones. Preserve record, draft, and scroll when resizing. Put Cancel and Save in a persistent footer. Validate before save confirmation and confirm discard on Cancel, Close, Escape, or backdrop dismissal while editing. Closing confirmation keeps the draft. Failed saves retain retryable input. Keep stronger confirmations for destructive actions.
- For inline settings, reserve slots immediately left of search for Cancel × and Save, in that order. Both appear only while dirty. Cancel confirms discard. When an action disappears, return focus to search if it had focus before confirmation. Keep layout stable and move the controls and search together on narrow screens.

## Accounts and roles

- Use the real account roster with username, email, assigned role names, and status. Search username, email, and any assigned role. Preserve `q` and the All, Unverified, and Disabled `status` deep links. Roles are optional and an account may hold multiple. Show all assigned roles in details, and show **No roles** for an empty set. Keep protected and current-account indicators and existing visibility rules.
- In the account drawer, stage role choices independently by role ID. Use labeled checkboxes and preserve existing role delegation and protected-account restrictions. Save only changed account fields and role assignments via the existing endpoints after confirmation. Keep the existing separate enable/disable, resend verification, and typed account deletion actions. Handle partial saves explicitly, updating the list from server-confirmed responses and retrying only outstanding changes. Refresh the signed-in account and re-evaluate access if its roles or details change.
- Roles & permissions keeps name, description, grouped permission editor, role creation, affected-account lookup, and deletion confirmation. Open the existing editor in the record drawer. Preserve protected role rules, permission delegation, route-leave and unload guards, and the full draft when permission search hides fields.

## Overview, invites, settings, and config issues

- Overview uses real permission-scoped counts and links for pending work, including the bookmarked account filters. Show unavailable counts distinctly from zero.
- Invites keeps email and manual delivery, expiration, copy-link, and revoke confirmation. Search open invites locally. Open creation in a drawer and preserve `?create=1`. New accounts receive the configured default role through the existing backend behavior.
- Workspace settings keeps Tool approval, Sidebar pages, and the full app configuration form including reset behavior, validation, and restart guidance. Each panel owns search, draft, and save. Validate hidden app configuration fields before submitting and reveal the first hidden invalid field. Preserve independent save and apply timing.
- Config issues keeps authorized access, severity filters, grouping by file, and Check again. Search file, key, and displayed diagnostic text. Keep restart guidance and redaction. A failed check preserves the error state. A successful check with zero issues keeps the existing return to home.

## Legion follow-up

Apply the same Theme selector styling to the production Legion Profile menu and the same single inset outline to its shared panel search. Replace the Tuning text Cancel with a labeled × icon, keep both dirty-action slots reserved, and retain existing draft validation, discard confirmation, and save behavior.

## Acceptance

- Portcullis routes render real data with one page title. Keyboard, mouse, and touch can navigate, use search, open records, resize drawers, confirm or discard changes, and return focus.
- Preview parity at desktop, 768px, 767px, and 375px in Light and Dark for shell, last-row hover and focus, search, and drawers. Profile theme switching works with persisted preference and System.
- Accounts with zero, one, or multiple roles stay correct after editing, role rename, failure, and retry. Existing permissions, redirects, action protections, and API contracts remain in force.
- Production scope is Portcullis Admin and the named Legion Admin controls. This work uses existing APIs and storage keys and adds no schema migration, dependency, or deployment step.
