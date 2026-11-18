# legion_admin

Admin-only web UI for Legion (first page: Agents). It has no backend: it calls `portcullis`.

Run: `pnpm install && pnpm dev` (http://127.0.0.1:26500).

Needs `portcullis` running (default port 29601, override with `EMBER_API_PORT`) and an account with the `agents.manage` permission.
