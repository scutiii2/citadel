# @citadel/ui

Components, composables and base styles shared by the five admin apps (armory, legion, portcullis, stronghold, treasury). Ember is not in the workspace yet.

- **Consumed as source.** There is no build step: each app's Vite build compiles it. Apps import from `@citadel/ui` only (never a deep path), plus `@citadel/ui/base.css` (tokens, shell, global busy-button rule) and `@citadel/ui/admin.css`, `@citadel/ui/infoPage.css`.
- **Workspace.** `pnpm-workspace.yaml` at the Citadel root lists this package and `apps/*_admin`. One `pnpm-lock.yaml` at the root. Run `pnpm install` there.
- **Per-app values are arguments.** `initTheme("<app>_admin.theme")` sets the app's storage key. A `PasswordInput` shows the label row only when you fill its `help` slot.
- **Tests.** `pnpm test` here runs the shared components' tests. `pnpm run build` type-checks.
- **Docker.** `docker/admin.Dockerfile` builds any admin app from the Citadel root (`--build-arg APP=<folder>`); `tools/publish_live.py` ships this folder.
- **Not shared yet** (differs between apps): headers and navs.
