# treasury_admin

Project note: `Brain/Projects/treasury_admin.md` in the Obsidian vault (`../../../../Brain/` from this folder), once it exists.

Vue 3 + TypeScript admin app for Treasury, for accounts holding `settings.manage`. Talks only to `portcullis` through the Vite `/api` proxy (no backend of its own). Pages: Instances (Treasury's instances and the connections each may use, read-only) and Connections (the databases Treasury keeps data in, and the cache defaults, saved in Treasury's database).

## Rules
- Code is copied between the admin apps, not shared. Nothing here imports from another app. Apply a fix to a shared component (PageLayout, ToggleSwitch, BaseModal...) in every admin app that has a copy.
- Add a page: one entry in `src/router/pages.ts`, one route in `src/router/index.ts` with `meta.permission`, one view.
- Radius only through `--radius-*` tokens, colors only through `style.css` tokens (`radiusScale.test.ts` enforces it).
- A switch that calls the server stays pending until the server answers.
- Never add reduced-motion code.
- `@vitejs/plugin-vue` is pinned to 6.0.9: 6.0.11 breaks `<style scoped src>` in vitest. Keep the pin until it is fixed.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`. Dev: `pnpm dev` (port 26505; `TREASURY_ADMIN_PORT` overrides it, `EMBER_API_PORT` sets the proxy target, default 29601).
