# legion_admin: admin-only frontend for Legion

Date: 2026-11-08. Status: approved design, first page only (Agents).

## Goal
A dedicated admin frontend for Legion at `apps/legion_admin`, separate from `ember_admin`
because Legion-related features will be removed from `ember_admin` later. First page: Agents.

## Decisions
- Stack matches `ember_admin`: Vue 3 + TypeScript + Vite + Pinia + vue-router, pnpm, vitest.
- Backend path: via `ember_api`. No new backend routes. The app uses `/api/auth/*` and
  `/api/admin/agents*` (`ember_api/src/routes/agent_admin.py`, permission `agents.manage`).
- Vite dev server proxies `/api` to `ember_api` (`EMBER_API_PORT`, default 29601) with `xfwd`,
  so the browser sees one origin. Session cookie is `SameSite=Strict`, so no cross-origin calls.
- Admin-only: router guard allows only accounts holding `agents.manage`; others get a
  no-access view. `ember_api` enforces the same permission server-side; the guard is UX only.
- Code is copied from `ember_admin`, not shared, so `ember_admin` can drop its agents page
  later without breaking this app. Two copies exist until then (accepted cost).
- No PWA. No reduced-motion code (repo rule). Colors and radius only through tokens.

## Structure
```
apps/legion_admin/
  AGENTS.md, CLAUDE.md (@AGENTS.md), README.md
  package.json, vite.config.ts, tsconfig*.json, index.html
  Dockerfile, nginx.conf
  src/
    main.ts, App.vue, style.css (tokens copied from ember_admin)
    api/        http.ts, AuthClient.ts, AgentsAdminClient.ts
    stores/     auth.ts
    router/     index.ts, pages.ts (one nav list: Agents), guard
    views/      LoginView.vue, NoAccessView.vue, AgentsAdminView.vue
    components/ PageLayout, AgentAdminCard, AgentForm, AgentGatewayList,
                RouterPolicyForm, SharedPromptsModal, ConfirmModal
```
Shell: sidebar with nav from `pages.ts`; later Legion pages add one entry each.

## Agents page (`/agents`)
Same behavior as `ember_admin` `/agents`: list agents as cards; create, edit, delete,
enable/disable; router policy form; shared prompts modal. A switch that calls the server
stays pending until the server answers.

## Ports and deploy
- Dev + host port: `26500` (first of `26500-26999`; nothing in the repo uses it yet).
  Recheck at implementation time.
- Add `legion_admin` to `docker-compose.yml` (`127.0.0.1:26500:80`, `depends_on: [ember_api]`,
  network `core`). Note: git shows `apps/Ember/*` moved to `apps/*`; compose still has
  `apps/Ember` paths. Use the new flat paths for `legion_admin`; do not fix the old entries.
- Dockerfile builds standalone (no ember_web imports; copy `PwaStatus`-free layout CSS).

## Tests
vitest: router guard (no session, wrong permission, `agents.manage`), `AgentsAdminClient`
requests, `radiusScale`-style token test copied, smoke render of `AgentsAdminView`.
Checks: `pnpm exec vue-tsc -b`, `pnpm test`.

## Out of scope
New backend routes, moving routes out of `ember_api`, other Legion pages, removing the
agents page from `ember_admin`, PWA.

## Docs
`Brain/Projects/legion_admin.md` project note (vault rules in `Brain/AGENTS.md`).
