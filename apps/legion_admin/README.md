# legion_admin

Admin-only web UI for Legion (first page: Agents). It has no backend: it calls `ember_api`.

Run: `pnpm install && pnpm dev` (http://127.0.0.1:26500).

Needs `ember_api` running (default port 29601, override with `EMBER_API_PORT`) and an account with the `agents.manage` permission.
