# armory_admin

Admin web app for Armory, built with Vue 3, TypeScript and Vite. It runs on port 26503 (`ARMORY_ADMIN_PORT`) and talks only to [portcullis](../portcullis) over the same origin: its Vite server (and its nginx in Docker) forwards `/api` to Portcullis, so the browser holds no server URL or token.

Capabilities manages tool availability.

## Run

- `pnpm install` once, then `pnpm run dev` starts Vite on port 26503.
- In Docker it is the `armory_admin` service of the root `docker-compose.yml` (published on `127.0.0.1:26503`).
- Open <http://127.0.0.1:26503> and log in with an account that holds `capabilities.manage`. The session cookie belongs to the host, not the port, so a login in one admin app is a login in all of them. The rail links to the other admin apps by swapping the port.

## Check

`pnpm exec vue-tsc -b`, `pnpm test`, `pnpm run build`.
