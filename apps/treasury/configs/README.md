# configs

Both files are tracked; there is no `.example` twin. Secrets in a connection (a DSN, a password) are `${NAME}`
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
- `instances`: which connections each caller may use. The caller is the name a service sends as
  `DB_GATEWAY_INSTANCE` (Armory) or its own name. A name that lists an unknown connection stops Treasury at start.
