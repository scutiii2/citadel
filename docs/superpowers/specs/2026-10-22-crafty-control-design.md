# Crafty control: per-user Minecraft server control

Date: 2026-10-22. Status: design approved in chat, awaiting spec review.

## Goal

Let a signed-in user control the Minecraft servers hosted in their own Crafty Controller (v2 API) from Ember chat and
slash commands: list servers, read status, start, stop, restart. Each user enters their own Crafty URL and API token at
runtime. There is no global Crafty config and no shared token. The behaviour is ported from TwinksDCBot
(`core/crafty/client.py`, `cogs/minecraft/service.py`).

## Non-goals (v1)

- Raw console command (`stdin`) and `kill_server`.
- Shared or admin-owned connections, role gates beyond Ember's normal tool approval.
- Plain `http://` endpoints. Crafty's default is HTTPS (self-signed), which the TLS toggle covers.
- Discord UI. TwinksDCBot stays as it is.

## Architecture

Same split as Obsidian brains: ember_api owns the encrypted per-user connection; armory resolves it on every call and
talks to Crafty. Secrets never reach the browser.

```
ember_web  --PUT/test-->  ember_api  /api/crafty/...           (stores encrypted connection)
chat tool  ---------->    armory tool_crafty_*  --resolve-->  ember_api /api/crafty/internal/resolve
                          armory client  --HTTPS, pinned-->   user's Crafty
```

### 1. ember_api: storage and routes

- `src/services/crafty_connections.py`, modeled on `brain_connections.py`:
  - Collections `crafty_connections` and `crafty_connection_revisions`; immutable revisions give atomic concurrent saves.
  - One connection per user. Id is `crafty-` + first 32 hex chars of sha256(uid). No scopes.
  - `ConnectionInput`: `label` (1-80), `endpoint` (HTTPS, no credentials, query or fragment), `api_token`
    (write-only, optional on update, control characters rejected), `verify_tls` (default `true`), `enabled`,
    `servers` (list of `{name, server_id}`), `expected_revision`.
  - Server `name`: `^[a-z0-9][a-z0-9_-]{0,31}$`, unique within the connection. `server_id` is Crafty's UUID.
  - The token is stored with `SecretBox.encrypt_map({"api_token": ...})`. Reads return `credential_configured: bool`
    only.
  - `resolve(uid)` returns `{endpoint, api_token, verify_tls, servers, revision, generation}`. Errors: not configured
    (404), disabled (409), unreadable credential (503, "enter it again").
  - `purge_owner(store, uid)`: deletes both collections' rows for the user. Wired into the account-deletion path in
    `routes/admin.py` next to `purge_brains`.
- `src/routes/crafty.py`, prefix `/api/crafty`, tag `crafty`:

  | Method | Path | Auth | Purpose |
  |---|---|---|---|
  | GET | `/connection` | signed-in, email verified | Public view (no token). |
  | PUT | `/connection` | same | Save a revision; audit-log `crafty.connection_save`. |
  | DELETE | `/connection` | same | Disable and clear the credential; audit-log. |
  | POST | `/connection/test` | same | Build a candidate snapshot, ask armory to call Crafty, return the live server list. |
  | POST | `/internal/resolve` | `X-Internal-Token` + `X-Requester-Uid` | Snapshot for armory. Never reaches browsers. |

  Internal auth and requester validation copy `brains.resolve_connection` (constant-time token compare, active and
  verified account).
- Register the router in `app.py`; map the service error type to JSON like `BrainError`.

### 2. armory: gateway route for the test

- `src/crafty_routes.py` installs `POST /crafty/operation` (same internal-token checks and size cap as
  `brain_routes.py`), operations: `test` only. ember_api sends the candidate snapshot; armory calls Crafty's server list
  and returns `{status, servers:[{server_id, server_name}], message}`. This keeps every outbound request to a
  user-supplied URL inside armory's address guard.

### 3. armory: `capabilities/crafty/`

- Files: `__init__.py` (`META` id `crafty`, label "Crafty"), `contract.py`, `domain.py`, `tool.py`, `help.json`,
  `README.md`, `utils/` (client, resolver). `STATIC-GUIDELINES.md` is only needed if the capability creates a dot-folder or `static/` folder; it creates neither.
- Tools (alias `crafty`, camelCase tasks), all `@offload`, all take the caller from `identity_context`:

  | Tool | Command | Read-only hint |
  |---|---|---|
  | `tool_crafty_listServers` | `/crafty list` | yes |
  | `tool_crafty_getStatus(server)` | `/crafty status` | yes |
  | `tool_crafty_startServer(server)` | `/crafty start` | no |
  | `tool_crafty_stopServer(server)` | `/crafty stop` | no |
  | `tool_crafty_restartServer(server)` | `/crafty restart` | no |

  `server` is the short name. An unknown name raises an error listing the names the user has.
  `tests/test_read_only_declarations.py` pins the read-only list and must be updated to add exactly the two read tools.
- `contract.py`: `ServerInfo` (name, running, online, max, version), `ServerListResult`, `ServerStatusResult` (adds
  players, cpu, mem, world_name), `ServerActionResult`. Every result ends with a `message` safe to relay verbatim.
- `utils/client.py` `CraftyClient(endpoint, api_token, verify_tls)`: methods `list_servers()`, `stats(server_id)`,
  `action(server_id, action)`. Endpoints, ported from TwinksDCBot, plus the list call:
  `GET /api/v2/servers`, `GET /api/v2/servers/{id}/stats`, `POST /api/v2/servers/{id}/action/{start_server|stop_server|restart_server}`.
  Bearer auth, 10 s timeout, response `status != "ok"` becomes a `CraftyError` with Crafty's message.
- `utils/resolver.py`: calls `/api/crafty/internal/resolve` the way `services/brain_resolver.py` does (same headers, 5 s timeout, 32 KB cap, no redirects).
- Status normalization is ported from `MinecraftService.get_status` (players may arrive as a JSON string).
- Client transport: the existing pinned-HTTPS urllib handler (sync, run through `@offload`), not a new `aiohttp` path.
  `checked_addresses`, `PinnedHTTPSConnection`, `PinnedHTTPSHandler` move from `obsidian/utils/network.py` to
  `src/services/net_guard.py` (behaviour unchanged, `@catalog` kept) and Obsidian imports them from there. Capabilities
  import `services/`, never another capability.
- Network policy: `personal=True` mode. Private LAN allowed; loopback, link-local, multicast, reserved, cloud metadata
  and redirects rejected. TLS verification follows the stored `verify_tls`.
- Audit: follow the `getAuditLog` convention used by `email/tool.py`; control actions record user, server name, action.

### 4. ember_web: settings page

- A "Crafty" section beside the existing personal Brain connection settings: label, URL, token (masked, "token set"
  indicator), verify-TLS switch with a warning when off, enabled switch.
- "Test connection" runs `/connection/test` and shows the servers Crafty returned. The user ticks the ones to keep and
  names each; Save sends the list with `expected_revision`.
- Follows `ember-frontend-design` and the design system skills. Reuse existing form components and the settings
  layout; no new tokens.

## Permissions

- Every user reaches only their own Crafty: resolution is keyed by the requester uid taken from trusted internal
  headers, never from tool arguments.
- Start, stop and restart do not declare `readOnlyHint`, so Ember's Auto mode still asks before running them.
- No new Ember permission in v1. If a gate is wanted later, add `crafty.use` to ember_api's permission table and check
  it in `/internal/resolve`.

## Security notes

- User-supplied URL means SSRF risk: all outbound calls go through the pinned, address-checked handler. DNS answers are
  checked at connect time, so rebinding cannot swap in a blocked address.
- The token is write-only: encrypted at rest with `EMBER_SECRETS_KEY`, never returned, never logged, redacted from
  error text.
- Crafty on a different network is reachable only if Zima can route to it (VPN, tunnel, public address). `localhost`
  entered by a user means the armory container and is rejected.

## Error handling

- No connection: "Set up your Crafty connection in Settings first."
- Disabled connection, unknown server name, Crafty unreachable, bad token (Crafty rejects), TLS failure: each a distinct
  message; none echoes the token or the raw response body.
- Revision conflict on save: "The connection changed. Reload before saving." (409).

## Testing

- ember_api: revision conflict, owner isolation (user B cannot resolve user A), token never in public view, purge on
  account delete, internal-token rejection, name validation.
- armory: client against a fake Crafty (ok, error status, players as string); address guard (loopback rejected, LAN
  allowed, redirect rejected); tool behaviour with a stubbed resolver (no connection, unknown name); read-only
  declaration test; help.json and tool-keyword and display-label tests that already cover every tool.
- ember_web: Vitest component test for the settings form (token masked, test lists servers, save sends revision).
- Verified live once against the real Crafty on Zima before calling it done: the `GET /api/v2/servers` response shape is
  taken from Crafty's API docs, not from TwinksDCBot, which never calls it.

## Open items to settle in the plan

- Exact response fields of `GET /api/v2/servers` on the installed Crafty version.
- Whether `@offload` accepts the sync client as is (assumed yes, as in `server_manager`).
- Where the ember_web brain settings live, to place the Crafty section next to them.
