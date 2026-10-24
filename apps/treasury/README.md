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
- Runs standalone with its own `.venv_treasury`. It imports no other project.

## Setup and run
```
py -m venv .venv_treasury
.venv_treasury\Scripts\pip install -e ".[dev]"
.venv_treasury\Scripts\python -m src.run
```
Create the venv and install once. The first start seeds `.env`,
`configs/config_app.json` and `configs/config_connections.json` from their `.example` twins.
Default port is 8071 (`DB_GATEWAY_PORT` overrides it).

In Docker: `dev_deploy.bat` in this folder rebuilds and restarts the `treasury` container from the root `docker-compose.yml` (see [docs/deployment.md](../../docs/deployment.md)).

Tests: `.venv_treasury\Scripts\python.exe -m pytest`

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
| PUT | `.../records/{key}?if_absent=true` | `{"doc": {...}}`: stores only when the key is free, else `409` |
| POST | `/instances/{i}/connections/{c}/collections/{col}/query` | `{"filters": {"field": value}, "limit": 100, "offset": 0}` |
| POST | `/instances/{i}/connections/{c}/sql` | `{"sql": "...", "params": []}` |

`if_absent` is atomic on every backend, so of two racing creates exactly one wins; use it for unique names.
A connection is reachable only through an instance that lists it. Filters match top-level fields
by equality. Raw SQL works only on SQL backends and only when the connection sets
`"allow_raw_sql": true`.

## Cache
Per connection, in process (L1): TTL + LRU, write-through. Writes go to the database first, then
drop that record and every cached query of that collection. Concurrent misses on one key share a
single database call. "Not found" is cached briefly. `ttl_seconds: 0` turns the cache off.

A read that was already in flight when a write to its collection (or a raw SQL statement) landed
is returned to its caller but not cached, so it cannot overwrite fresher data.

Limit: a change made outside the gateway shows up only after the TTL expires.

## Postgres
Install the driver once: `.venv_treasury\Scripts\pip install -e ".[postgres]"`. Put the DSN in
`.env` (`PG_DSN=postgresql://user:pass@host/db`) and add a connection:

```json
"warehouse": {"type": "postgres", "dsn": "${PG_DSN}", "max_pool_size": 5}
```

It uses the same `documents` table (created on first connect). Filters use jsonb containment, so an
array field matches when it contains the filter value. Raw SQL takes `$1, $2` parameters, not `?`.
Status: unit-tested against a fake pool, and the backend contract test passes against a real
Postgres 16 server.

## Firestore
Install the driver once: `.venv_treasury\Scripts\pip install -e ".[firestore]"`. Add a connection:

```json
"cloud": {"type": "firestore", "project": "my-project", "credentials_file": "${FIRESTORE_KEY_FILE}"}
```

`project`, `credentials_file` and `database` are all optional; without a key file it uses Google
application default credentials. Keep the key file path in `.env`, never the key itself in git.
Collections and documents map one to one (key = document id, no `/`). Filters are equality on
document fields, results are ordered by document id, and raw SQL is unsupported. Set
`FIRESTORE_EMULATOR_HOST` to use the local emulator. Each read is billed, so keep the cache on.
Status: unit-tested against a fake client, and the backend contract test passes against the local
emulator (needs Java 21+; `npx firebase-tools emulators:exec --only firestore --project demo-test "<pytest command>"`
starts it, sets `FIRESTORE_EMULATOR_HOST` and stops it). Not yet run against a real Firebase project.

## Testing against real databases
`tests/test_backend_contract.py` runs one behaviour contract (put, get, replace, delete, filters,
order, limit, offset) against every backend that is available. SQLite always runs. Point it at your
own server to run the others; each run uses a collection of its own and cleans up after itself:

```
set DB_GATEWAY_TEST_POSTGRES_DSN=postgresql://user:pass@localhost/testdb
set FIRESTORE_EMULATOR_HOST=localhost:8080
set GOOGLE_CLOUD_PROJECT=demo-test
.venv_treasury\Scripts\python.exe -m pytest tests/test_backend_contract.py -rs
```

Use a throwaway Postgres database and the Firestore emulator, never a real project.

## Adding a database type
Implement `DatabaseBackend` (`src/backends/base.py`) and add one entry to `BACKEND_TYPES` in
`src/backends/factory.py`.
