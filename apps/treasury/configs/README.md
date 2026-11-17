# configs

Every JSON file here is tracked; there is no `.example` twin. Secrets in a connection (a DSN, a password) are `${NAME}`
placeholders filled from `../.env` (see `../.env.example`). Restart Treasury after editing.

## config_app.json

| Key | Meaning |
|---|---|
| `host`, `port` | Where Treasury listens. `DB_GATEWAY_PORT` in the environment overrides `port`. |
| `default_cache` | Read cache used by every connection that sets none: `ttl_seconds`, `max_entries`, `negative_ttl_seconds`. |

## config_connections.json

- `connections`: each has a `type` (`sqlite`, and the Postgres and Firestore backends), the options of that type,
  `allow_raw_sql` (default false) and an optional `cache` block. A relative sqlite `path` is placed in
  `.data/treasury/` in the Citadel folder.

## Instances: not here

Treasury keeps no list of its callers. Each service registers its own instance when it starts
(`PUT /instances/{name}` with `{"connections": [...]}`): Portcullis registers `ember`, Stronghold `stronghold`,
Legion `legion`, Armory `armory` (or `mcp_server`), each with the connection it uses. A service may only register
the instance it owns, and only connections that exist in `config_connections.json`; anything else is refused.
Registration takes effect at once and is kept in the `instances` table of `.data/treasury/settings.db`, so a
Treasury restart keeps it. A service retries until Treasury answers, so start order does not matter.
