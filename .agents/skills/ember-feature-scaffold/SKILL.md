---
name: ember-feature-scaffold
description: Use when adding an Ember (Vue 3 + TypeScript Windows app) page, tab, panel, store, router entry or API client call, or when reviewing whether Ember code follows the repo conventions. For the Portcullis backend use portcullis-feature-scaffold; for reaching Armory, Legion or Stronghold use portcullis-mcp-bridge; for a new Armory tool use armory-capability-scaffold.
---

# Ember feature scaffolding

Ember (`apps/ember`) is a Vue 3 + TS UI in a Tauri 2 shell. It talks only to Portcullis, at the address the user enters. Staff pages live in the admin apps (`portcullis_admin`, `legion_admin`, `armory_admin`, `stronghold_admin`, `treasury_admin`), not in Ember. `apps/ember/AGENTS.md` holds the hard rules; look and feel: `ember-frontend-design`.

## Working agreement

Propose each step first (files, packages, deletions), wait for approval, implement, verify, report. One step at a time. Do not commit unless asked.

## Where the feature lives

| Need | Touch |
|---|---|
| Presentation of data Ember already has | Ember only |
| New data, action, or anything to enforce | Portcullis route (`portcullis-feature-scaffold`) and the Ember client and view |
| Something Armory, Legion or Stronghold does | The Portcullis proxy or pass-through (`portcullis-mcp-bridge`); never a direct browser call |

The router guard and hidden tabs are cosmetic. Portcullis enforces permissions.

## Steps

Layout in `apps/ember/src/`: `features/<area>/` (view, `components/`, `api/`, `stores/`, tests together), `api/` (shared clients), `stores/`, `components/` (shared pieces, `ember-shared-components`), `composables/`, `router/`, `utils/`.

1. **Client**: never `fetch` or hand-built `/api` URLs. Use `apiRequest` from `api/http.ts`, or `apiUrl`, `authHeaders`, `credentialsMode`, `mediaUrl` from `utils/server.ts`. A 401 raises `UnauthorizedError` and the auth store drops the account. Export a plain object of functions with TypeScript response types. Armory tools go through `api/tools/McpServerClient.ts`.
2. **Store** only when state outlives one view (`defineStore` setup stores). Per-user state resets when `useAuthStore().account?.id` changes. Local storage is keyed per account and wrapped in try/catch (`readStored`/`writeStored`).
3. **View** `features/<area>/XxxView.vue` with a lazy route in `src/router/index.ts` (`meta: { permission: "..." }`, or `guestOnly: true`). A page the nav rail should show goes in `NAV_PAGES` in `src/router/pages.ts` (`to`, `label`, stroked 24x24 `icon` paths, one-line `description`, `permission`); others go in `AccountMenu.vue` (see `ember-page-layouts`). Do not duplicate a page: tool UI belongs on Capabilities. Keep state across tab switches by adding the view name to the `KeepAlive include` list in `App.vue`.
4. **Components and styling**: reuse the shared pieces and tokens (`ember-shared-components`, `ember-design-system`). Destructive actions use `ConfirmModal`; a setting that reaches other accounts saves explicitly, a local one applies instantly.
5. **TypeScript**: `erasableSyntaxOnly` is on, so no constructor parameter properties and no enums; declare fields explicitly.
6. **Markdown or HTML from the server or a model** only through `components/content/MarkdownContent.vue` (DOMPurify). Never raw `v-html`.
7. **Verify** from `apps/ember`: `pnpm exec vue-tsc -b`, then the nearest test (`*.test.ts`, Vitest + jsdom). If a page calls a new `/api` route, add it to `e2e/fakeApi.ts`, because the Playwright run (`pnpm run test:e2e`) fails on unknown calls. Use `use-pnpm`.

## Before reporting done

Type-check and the nearest tests pass; READMEs updated when the surface changed. Summarize what changed, what was verified, what the user should test by hand (they test manually; do not launch browser verification agents), and propose a commit message.
