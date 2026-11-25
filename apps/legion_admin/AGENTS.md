# legion_admin

Project note: `Brain/Projects/legion_admin.md` in the Obsidian vault (`../../../../Brain/` from this folder).

Vue 3 + TypeScript admin app for Legion, for accounts holding `agents.manage` (Overview, Agents, Connections, MCP servers) or `tuning.manage` (Overview, Tuning: response-limit ceilings, `/api/admin/tuning`). Talks only to `portcullis` through the Vite `/api` proxy (no backend of its own).

## Rules
- Shared UI lives in `libs/citadel_ui` (`@citadel/ui`, a pnpm workspace package): PageLayout, ToggleSwitch, BaseModal, ConfirmModal, ThemeSelect, AdminSearch, RecordDrawer, StatusFilters, DraftActions, `useTheme`, base styles (`@citadel/ui/base.css`), `admin.css`. Fix it there once; every admin app picks it up on its next build. Keep app-specific code in the app. Run `pnpm install` at the Citadel root, not inside an app.
- Add a page: one entry in `src/router/pages.ts`, one route in `src/router/index.ts` with `meta.permission`, one view.
- Every panel header carries a `PanelHelp` icon first among its tools: a click opens a popover saying what the panel is for. Add it to each new panel.
- No checkboxes in admin panels, drawers or settings: an on/off or a choice from a list is a `ToggleSwitch` (a `small` one in dense lists). A checkbox is only for a form acknowledgement or checklist, such as agreeing to a policy or confirming something was read.
- Radius only through `--radius-*` tokens, colors only through `style.css` tokens (`radiusScale.test.ts` enforces it).
- A switch that calls the server stays pending until the server answers.
- Never add reduced-motion code.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`. Dev: `pnpm dev` (port 26500; `EMBER_API_PORT` sets the proxy target, default 29601).
