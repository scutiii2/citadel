# db_gateway

Database gateway. Callers talk to named **instances** over HTTP. Each instance lists the
**connections** it may use. A connection is one configured database (SQLite today; SQL and
Firestore plug in the same way). Several instances can list the same connection: it is opened
once, shared, and wrapped in one cache, so a write through one instance is seen by the others.

```
instance "default" ──┐
                     ├──> connection "main" ──> cache ──> SQLite file
instance "reports" ──┘
instance "default" ───> connection "scratch" ─> SQLite file (cache off)
```

## Requirements
- Python 3.11+
- Runs standalone with its own `.venv_db_gateway`. It imports no other project.

## Setup and run
```
run.bat
```
First run creates the venv and installs dependencies, then seeds `.env`,
`configs/config_app.json` and `configs/config_connections.json` from their `.example` twins.
Default port is 8071 (`DB_GATEWAY_PORT` overrides it).

Tests: `.venv_db_gateway\Scripts\python.exe -m pytest`

## Configuration
- `configs/config_app.json`: host, port, `default_cache`.
- `configs/config_connections.json`: `connections` (name -> `type`, type options, optional `cache`,
  `allow_raw_sql`) and `instances` (name -> list of connection names). Strings may use `${NAME}`,
  resolved from the environment and `.env`, so DSNs and key paths stay out of the JSON.
- `.env`: `INTERNAL_API_TOKEN`. When set, every route but `/health` needs the `X-Internal-Token` header.

SQLite paths are relative to this folder. Files go under `data/` (gitignored).

## API
Records are JSON objects addressed by `(collection, key)`.

| Method | Path | Body |
|---|---|---|
| GET | `/health` | |
| GET | `/instances` | |
| GET / PUT / DELETE | `/instances/{i}/connections/{c}/collections/{col}/records/{key}` | PUT: `{"doc": {...}}` |
| POST | `/instances/{i}/connections/{c}/collections/{col}/query` | `{"filters": {"field": value}, "limit": 100, "offset": 0}` |
| POST | `/instances/{i}/connections/{c}/sql` | `{"sql": "...", "params": []}` |

A connection is reachable only through an instance that lists it. Filters match top-level fields
by equality. Raw SQL works only on SQL backends and only when the connection sets
`"allow_raw_sql": true`.

## Cache
Per connection, in process (L1): TTL + LRU, write-through. Writes go to the database first, then
drop that record and every cached query of that collection. Concurrent misses on one key share a
single database call. "Not found" is cached briefly. `ttl_seconds: 0` turns the cache off.

Limits: a change made outside the gateway shows up only after the TTL expires. A write racing an
in-flight read of the same key can leave that one entry stale until its TTL.

## Postgres
Install the driver once: `.venv_db_gateway\Scripts\pip install -e ".[postgres]"`. Put the DSN in
`.env` (`PG_DSN=postgresql://user:pass@host/db`) and add a connection:

```json
"warehouse": {"type": "postgres", "dsn": "${PG_DSN}", "max_pool_size": 5}
```

It uses the same `documents` table (created on first connect). Filters use jsonb containment, so an
array field matches when it contains the filter value. Raw SQL takes `$1, $2` parameters, not `?`.
Status: unit-tested against a fake pool only; not yet run against a real Postgres server.

## Adding a database type
Implement `DatabaseBackend` (`src/backends/base.py`) and add one entry to `BACKEND_TYPES` in
`src/backends/factory.py`. Firestore is not built yet.
