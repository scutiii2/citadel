# ember

Project note: `Brain/Projects/ember.md` in the Obsidian vault (`../../../../Brain/` from this folder), once it exists.

Ember Windows app: Vue 3 + TypeScript UI inside a Tauri 2 shell (`src-tauri/`). It talks only to Portcullis, at the address the user enters. Follow the `ember-frontend-design` skill (it routes to `ember-design-system`, `ember-shared-components`, `ember-page-layouts` and the others).

## Rules
- Never call `fetch` or build an `/api` URL by hand: use `apiRequest`, or `apiUrl`, `authHeaders` and `credentialsMode` from `src/utils/server.ts`. Use `mediaUrl` for `<img>` and `<audio>` sources. The browser build and the Windows app differ only there.
- Radius only through `--radius-*` tokens. Never add reduced-motion code.
- Panels follow the admin apps. Copies live in `src/components/ui/panel/` (`PanelHelp`, `RecordDrawer`, `DraftActions`, `StatTile`, `StatusFilters`, `SettingsPanel`, `AdminSearch`, `admin.css`) and `src/composables/useDraftPanel.ts`: apply a fix to a copy in every admin app and here.
- Anything opened from a page or panel opens in a `RecordDrawer`. `BaseModal` is only for chat, the attachment preview and the dialog and drawer bases (`architecture.test.ts` enforces it); `ConfirmModal` stays modal.
- Every page header carries a `PanelHelp` first among its actions; the page description lives in it. Header actions are icon buttons (`admin-icon`, `accent` for the primary one) with an accessible name.
- An on/off or a choice from a list is a `ToggleSwitch`. A checkbox is only for selecting list rows or a form acknowledgement.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`, `pnpm run test:e2e` (built app, fake `/api`; port 26507, `EMBER_E2E_PORT` overrides it). The Tauri shell needs Rust.

- Shared UI lives in `libs/citadel_ui` (`@citadel/ui`) and is the real source for every frontend, Ember included. Use an existing component, composable or style from there; if none applies, create it there and export it from `src/index.ts`, not in the app. Ember is in the pnpm workspace; move any remaining local copy of a library file to the library when you touch it.
