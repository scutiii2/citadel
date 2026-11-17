# stronghold_admin

Admin web app for Stronghold, built with Vue 3, TypeScript and Vite. It runs on port 26504 (`STRONGHOLD_ADMIN_PORT`) and talks only to [portcullis](../portcullis) over the same origin: its Vite server (and its nginx in Docker) forwards `/api` to Portcullis, so the browser holds no server URL or token.

Pages: Usage, Analytics (logs, errors, chat activity, traffic), Tickets and Tool services. Calls: `/api/admin/usage`, `/api/logs`, `/api/traffic/analytics`, `/api/admin/tickets`, `/api/admin/ticket-groups`. Usage and Tickets data comes from `stronghold`; logs and traffic are Portcullis's own.

## Run

- `pnpm install` once, then `pnpm run dev` starts Vite on port 26504.
- In Docker it is the `stronghold_admin` service of the root `docker-compose.yml` (published on `127.0.0.1:26504`).
- Open <http://127.0.0.1:26504> and log in with an account that holds `usage.all.view`, `tickets.manage`, `settings.manage` or a logs/traffic permission. The session cookie belongs to the host, not the port, so a login in one admin app is a login in all of them. The rail links to the other admin apps by swapping the port.

## Check

`pnpm exec vue-tsc -b`, `pnpm test`, `pnpm run build`.
