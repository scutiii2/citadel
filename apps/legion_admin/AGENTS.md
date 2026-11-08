# legion_admin

Project note: `Brain/Projects/legion_admin.md` in the Obsidian vault (`../../../../Brain/` from this folder).

Vue 3 + TypeScript admin app for Legion, only for accounts holding `agents.manage`. Talks only to `ember_api` through the Vite `/api` proxy (no backend of its own). First page: Agents.

## Rules
- Code is copied from `ember_admin`, not shared. Nothing here imports from `ember_admin` or `ember_web`. Apply future fixes in both while both pages exist.
- Add a page: one entry in `src/router/pages.ts`, one route in `src/router/index.ts` with `meta.permission`, one view.
- Radius only through `--radius-*` tokens, colors only through `style.css` tokens (`radiusScale.test.ts` enforces it).
- A switch that calls the server stays pending until the server answers.
- Never add reduced-motion code.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`. Dev: `pnpm dev` (port 26500; `EMBER_API_PORT` sets the proxy target, default 29601).
