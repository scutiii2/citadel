# Plan 7: Admin app split

Branch: `refactor/admin-split`.

## Result

One admin web app per backend, each on its own port, each talking only to Portcullis through its own `/api` proxy:

| App | Port | Pages | Permission |
|---|---|---|---|
| `legion_admin` | 26500 | Agents, Connections (unchanged) | `agents.manage` |
| `portcullis_admin` (was `ember_admin`) | 26501 | Overview, Accounts, Roles, Invites, Workspace settings, Config issues, Profile, Settings, Login | the existing account, role, invite and settings permissions |
| `armory_admin` | 26503 | Capabilities, Extensions | `capabilities.manage`, `extensions.manage` |
| `stronghold_admin` | 26504 | Usage, Analytics, Tickets, Tuning | `usage.all.view`, a logs or traffic permission, `tickets.manage`, `tuning.manage` |
| `treasury_admin` | 26505 | Instances (read-only) | `settings.manage` |

## How

1. The new apps are built from the `legion_admin` skeleton (login, auth store, theme, layout, nav rail, route guard) by a one-off generator; their pages and everything those pages import are copied from `ember_admin`. Code is copied, never shared, as in `legion_admin` before.
2. `ember_admin` was renamed with `git mv` (history kept) and trimmed: the moved pages, their api clients, components, utils and tests were removed, and the Overview lost its ticket tiles (they live in `stronghold_admin` now). `legion_admin` already had the Agents page, so the duplicate Agents page in `ember_admin` was dropped, not moved.
3. Each rail links to the other admin apps (letters L P A S T): the same host with the other port. The session cookie is host-wide, so one login works in all of them. Ports are fixed; a per-app URL setting waits until an app is hosted elsewhere.
4. New Portcullis route `GET /api/admin/treasury` (`settings.manage`): Treasury's instances and connections, whether Treasury answers, and which one Portcullis uses. Treasury has no admin API to change anything (its instances are in config files), so `treasury_admin` is read-only.
5. `docker-compose.yml`: `ember_admin` is now `portcullis_admin`; `armory_admin`, `stronghold_admin` and `treasury_admin` are new services. `docker-compose.zima.yml`, `docs/deployment.md` and `tools/publish_live.py` follow.

## Decisions to know

1. **Tuning is in `stronghold_admin`**, as the roadmap listed. The page edits Legion's response-limit ceilings through `/api/admin/tuning` (which Portcullis forwards to Legion), and the ceilings are what Stronghold's account tuning reads. Moving it into `legion_admin` later is one page copy.
2. **Analytics is in `stronghold_admin`** as listed, though its logs and traffic data are Portcullis's own. It still calls Portcullis only.
3. `@vitejs/plugin-vue` is pinned to 6.0.9 in the new apps: 6.0.11 resolves `<style scoped src="./x.css">` against the project root in vitest and breaks the chart tests. `ember_admin` already had 6.0.9 in its lockfile.
4. Browser storage keys stay `ember_admin.*` (theme, sidebar preferences) so saved choices survive the rename.

## Not done

1. Playwright e2e: the specs for the moved pages (tickets, tuning, usage, agent gateways, router agent) were removed with the pages; the specs left in `portcullis_admin/e2e` were not run and may still name moved pages.
2. `legion_admin` has a TypeScript error in `ConnectionsView.vue` (`.value` on a plain client object) that was there before this plan; the unit tests pass and the build was not part of this plan.
3. No vault notes for the new apps yet beyond the Citadel and Portcullis ones.

## Execution notes (2026-11-16)

- `armory_admin` 95 tests, `stronghold_admin` 260, `treasury_admin` 32, `portcullis_admin` 201, `legion_admin` 78 (vue-tsc clean for the first four; `vite build` passes for armory, stronghold, treasury and portcullis). Portcullis: see the commit message.
- Not run: Docker builds of the new images, the apps in a browser (rail links, login across ports, the pages against a live Portcullis), Playwright.
