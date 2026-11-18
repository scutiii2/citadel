# treasury_admin

Admin web app for Treasury, built with Vue 3, TypeScript and Vite. It runs on port 26505 (`TREASURY_ADMIN_PORT`) and talks only to [portcullis](../portcullis) over the same origin: its Vite server (and its nginx in Docker) forwards `/api` to Portcullis, so the browser holds no server URL or token.

Pages: Instances (Treasury's instances and the connections each may use, read-only) and Connections (the databases Treasury keeps data in, plus the cache defaults). Calls: `/api/admin/treasury` and `/api/admin/treasury/connections`. Each service registers its own instance; the connections are built in or saved here.

## Run

- `pnpm install` once, then `pnpm run dev` starts Vite on port 26505.
- In Docker it is the `treasury_admin` service of the root `docker-compose.yml` (published on `127.0.0.1:26505`).
- Open <http://127.0.0.1:26505> and log in with an account that holds `settings.manage`. The session cookie belongs to the host, not the port, so a login in one admin app is a login in all of them. The rail links to the other admin apps by swapping the port.

## Check

`pnpm exec vue-tsc -b`, `pnpm test`, `pnpm run build`.
