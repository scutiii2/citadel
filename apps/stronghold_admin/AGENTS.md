# stronghold_admin

Project note: `Brain/Projects/stronghold_admin.md` in the Obsidian vault (`../../../../Brain/` from this folder), once it exists.

Vue 3 + TypeScript admin app for Stronghold. All API calls go through Portcullis. Pages: Overview (counts and shortcuts), Usage, Analytics, Tickets, Usage settings (token limits and pricing, `/api/admin/stronghold-usage-settings`), Brain settings (memory and sharing limits, `/api/admin/stronghold-brain-settings`) and Tool services.

## Rules
- Code is copied between the admin apps, not shared. Nothing here imports from another app. Apply a fix to a shared component (PageLayout, ToggleSwitch, BaseModal, ThemeSelect, AdminSearch, RecordDrawer, StatusFilters, DraftActions, PanelHelp, StatTile, SettingsPanel...) in every admin app that has a copy.
- Add a page: one entry in `src/router/pages.ts`, one route in `src/router/index.ts` with `meta.permission`, one view. A page whose permission is a list (Analytics) must use the exported constant, not its name as a string.
- Anything opened from a panel opens in a `RecordDrawer` (the ticket drawer is a side `BaseModal`); only `ConfirmModal` stays modal.
- Every panel header carries a `PanelHelp` icon first among its tools: a click opens a popover saying what the panel is for. Actions in a panel header are icon buttons (`admin-icon`, `accent` for the primary one) with an accessible name.
- A settings page is one `SettingsPanel`: help, `DraftActions` and a search in the header, sections in the body hidden with `v-show` so a search never drops a draft.
- No checkboxes in admin panels, drawers or settings: an on/off or a choice from a list is a `ToggleSwitch`. A checkbox is only for a form acknowledgement or checklist.
- Radius only through `--radius-*` tokens, colors only through `style.css` tokens (`radiusScale.test.ts` enforces it).
- A switch that calls the server stays pending until the server answers.
- Never add reduced-motion code.
- `@vitejs/plugin-vue` is pinned to 6.0.9: 6.0.11 breaks `<style scoped src>` in vitest. Keep the pin until it is fixed.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`, `pnpm run test:e2e` (built app on port 5197, fake `/api`; `STRONGHOLD_E2E_PORT` overrides it). Dev: `pnpm dev` (port 26504; `STRONGHOLD_ADMIN_PORT` overrides it, `EMBER_API_PORT` sets the proxy target, default 29601).
