# portcullis_admin

Project note: `Brain/Projects/portcullis_admin.md` in the Obsidian vault (`../../../../Brain/` from this folder). Renamed from `ember_admin` in Plan 7.

Vue 3 + TypeScript admin app for Portcullis: Overview, Accounts, Roles, Invites, Workspace settings, Config issues, Profile and Login. It talks only to `portcullis` through the Vite `/api` proxy. The other backends have their own admin apps (`legion_admin`, `armory_admin`, `stronghold_admin`, `treasury_admin`); the sidebar shortcuts link to them. Follow the `ember-frontend-design`, `ember-design-system`, `ember-admin-ui` and `ember-feature-scaffold` skills for UI and API conventions.

## Rules
- Code is copied between the admin apps, not shared. Apply a fix to a shared component (PageLayout, ToggleSwitch, BaseModal, ThemeSelect, AdminSearch, RecordDrawer, StatusFilters, DraftActions...) in every admin app that has a copy.
- Anything opened from a panel opens in a `RecordDrawer`; only `ConfirmModal` stays modal.
- Every panel header carries a `PanelHelp` icon first among its tools: a click opens a popover saying what the panel is for. Add it to each new panel.
- No checkboxes in admin panels, drawers or settings: an on/off or a choice from a list is a `ToggleSwitch` (a `small` one in dense lists). A checkbox is only for a form acknowledgement or checklist, such as agreeing to a policy or confirming something was read.
- Radius only through the `--radius-*` tokens, colors only through `style.css` tokens. `radiusScale.test.ts` enforces it.
- A switch that calls the server stays pending until the server answers; never show a state it did not confirm.
- Never add reduced-motion code.
- Browser storage keys still start with `ember_admin.` (theme, sidebar preferences) so saved preferences survive the rename.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`, `pnpm run test:e2e` (the e2e specs for the moved pages were removed with them).
