# stronghold

Product logic for Citadel and Ember. Only `portcullis` calls it.

- Every route but `/health` needs `X-Internal-Token` (the shared internal token).
- The asking account arrives in `X-Requester-Uid`, `X-Requester-Username` and `X-Requester-Email`. Data is keyed on the uid.
- No cookies, no sessions and no login here. Portcullis owns those.

## Run

    uv sync
    uv run python -m src.run

Default address `127.0.0.1:29650`. `STRONGHOLD_HOST` and `STRONGHOLD_PORT` override it.

In Docker: `dev_deploy.bat` rebuilds and restarts the `stronghold` container from the root `docker-compose.yml`.

## Test

    uv run pytest -q

## Routes

| Route | Purpose |
|---|---|
| `GET /health` | Open. `{"status": "ok"}` |
| `GET /whoami` | Echoes the requester. Portcullis exposes it as `GET /api/stronghold/whoami` |
