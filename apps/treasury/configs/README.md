# configs

`config_app.json` is tracked; there is no `.example` twin. It holds only where Treasury listens:

| Key | Meaning |
|---|---|
| `host` | Address to bind. `127.0.0.1` keeps Treasury on this machine. |
| `port` | Port to listen on. `DB_GATEWAY_PORT` in the environment overrides it. |

Restart Treasury after editing.

## The connections are not here

Four local SQLite connections are built in, so a new install works before anyone has opened the admin page:
`main` (`main.db`), `data` (`ember.db`, Portcullis's data), `stronghold` (`stronghold.db`) and `scratch`
(`scratch.db`, raw SQL allowed, no cache). A relative sqlite `path` is placed in `.data/treasury/` in the Citadel folder.

An administrator changes them on the Connections page of Treasury Admin; what is saved there lives in
`.data/treasury/settings.db` (table `connections`, see `src/connection_admin.py`) and replaces the built-in connection of
the same name or adds a new one. "Use the built-in" removes the saved one. Each connection has a `type` (`sqlite`,
`postgres` or `firestore`), the options of that type, `allow_raw_sql` (default false) and an optional `cache`.

- A new connection is offered to the instances at once. A changed or removed one is used from the next start.
- A Postgres `dsn` must be a `${NAME}` placeholder: the value stays in `../.env` (see `../.env.example`), so no secret
  is saved in the database. Saving a placeholder whose name is not set is refused.
- A connection an instance uses cannot be removed.

The cache defaults (`ttl_seconds`, `max_entries`, `negative_ttl_seconds`) for a connection that sets none are on the
same page (table `settings`, key `default_cache`) and are used from the next start.

## Instances: not here

Treasury keeps no list of its callers. Each service registers its own instance when it starts
(`PUT /instances/{name}` with `{"connections": [...]}`): Portcullis registers `ember`, Stronghold `stronghold`,
Legion `legion`, Armory `armory` (or `mcp_server`), each with the connection it uses. A service may only register
the instance it owns, and only connections that exist (built in or saved); anything else is refused.
Registration takes effect at once and is kept in the `instances` table of `.data/treasury/settings.db`, so a
Treasury restart keeps it. A service retries until Treasury answers, so start order does not matter.

## Service addresses

Treasury keeps the four peer addresses (Portcullis, Stronghold, Armory, Legion) in `.data/treasury/settings.db`:
`service_addresses` holds registrations and `service_pins` holds administrator pins. Each service may register only
its own name through `PUT /services/{name}`. All four read `GET /services`; only Portcullis may change pins through
`/admin/services`, after checking `settings.manage` for Treasury Admin, Services.

A pin wins over registration; registration wins over the caller’s built-in local default. Removing a pin uses
registration again, or the default when nothing registered. Addresses are HTTP(S) bases without credentials,
paths, queries or fragments. Callers add `/mcp` when needed. Treasury is the bootstrap address, never a catalog entry.

Services start without Treasury: they use a last-good disk cache, then local defaults, and retry registration and
refresh in the background. Set `treasury_url` in each service’s tracked `configs/config_app.json`, or override it with
`TREASURY_URL`. Set `advertise_url` or `CITADEL_ADVERTISE_URL` when the listener’s local address is not reachable by peers.
