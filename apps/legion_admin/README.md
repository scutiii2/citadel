# legion_admin

Admin-only web UI for Legion (first page: Agents). It has no backend: it calls `portcullis`.

Run: `pnpm install && pnpm dev` (http://127.0.0.1:26500).

Needs `portcullis` running (default port 29601, override with `EMBER_API_PORT`) and an account with the `agents.manage` permission.


## Outside MCP connections

Open **MCP servers** and enter the primary MCP address. A known address fills in
its Treasury service name. Give a new address a service name. Add backup addresses
for the same service and path in the order Legion should try them.

A backup can use its own token value with the connection's token header.
Leave a saved token field blank to keep its value. Changes apply at Legion's next
start. For Armory, choose **One address**.
