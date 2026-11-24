---
name: root-project-scaffold
description: Use when adding a new backend service under apps/ (a sibling of armory, legion, portcullis, stronghold, treasury) or auditing whether an apps/<name> folder matches the shared top-level shape, compose wiring and service identity setup. For what goes inside Armory capabilities, Legion agents or Ember pages use the matching scaffold skill.
---

# Citadel service scaffolding

Python services in `apps/`: `armory` (tools), `legion` (agents and model gateways), `portcullis` (auth and the browser's only door), `stronghold` (product logic), `treasury` (database gateway). Vue apps (`ember`, `*_admin`) have their own layout (`ember-feature-scaffold`). A new service must match this shape so `docker-compose.yml`, deploy scripts and docs work the same for all.

## Required shape of `apps/<name>/`

| Path | What |
|---|---|
| `README.md` | What it does, setup, run. Model on `apps/armory/README.md` |
| `pyproject.toml`, `uv.lock` | Own dependencies, own venv, never shared. Use `uv` (`use-uv`) |
| `Dockerfile`, `.dockerignore` | Image the root compose runs. Start from `apps/armory/Dockerfile` |
| `dev_deploy.bat` | Rebuilds and restarts only this container from the root compose. Copy `apps/portcullis/dev_deploy.bat`, change `SERVICE` |
| `shell.bat` | Terminal with the venv active. Copy `apps/portcullis/shell.bat` |
| `configs/` | Tracked JSON config plus a `README.md` documenting each key. No `.example` twins for JSON |
| `.env`, `.env.example` | Secrets only, in the project root. `.env` is gitignored, `.env.example` tracked |
| `src/`, `tests/` | Code and tests. Entry: `uv run python -m src.run` |
| `src/citadel_auth/` | Copy of `libs/citadel_auth/citadel_auth`; never edit it by hand |

Add only if needed: `docs/` (beyond the README), `migrations/` + `scripts/` (Alembic and CLIs, as Portcullis). Runtime state lives in `.data/<service>/` of the Citadel folder, not in the app. No other top-level folders: put code in `src/` or ask the user.

## Adding a service

1. Confirm it is a new deployable process, not a capability, agent or page.
2. Copy the files above from the nearest service and strip what does not apply.
3. Add the service name to `SERVICES` in `scripts/sync_citadel_auth.py`, then run `uv run scripts/sync_citadel_auth.py` (`--check` verifies).
4. Compose: add a service to `docker-compose.yml` with its `trust_<name>` and `identity_<name>` volumes, mount the peers' public trust folders read-only, publish a port only for a web UI, add `extra_hosts: ["host.docker.internal:host-gateway"]` for UI services, and run `python scripts/check_compose.py`.
5. Port: next free in the right block (workspace `AGENTS.md` "Ports"); an env override read by `src/config.py` set in compose. Armory 29600, Portcullis 29601, Treasury 29602, Legion agents 29603 up, Stronghold 29650, admin web apps 26500 up.
6. Every route reached by other services takes the signed service identity (`citadel_auth`); `/mcp` rejects calls without it. `GET /health` is public and `GET /ready` needs a signed assertion. Never import another service's code or expose the shared token to a browser.
7. A web UI also needs the ServiceHub checks in the workspace `AGENTS.md`.
8. Add the service to the table in `docs/deployment.md` and a `.env.example` entry in `tools/setup_env.py` if it needs a generated secret.

## Audit

Flag: a missing required item; a secret in a tracked file or an `.env` without `.env.example`; JSON config without a `configs/README.md`; `src/citadel_auth` differing from `libs/` (run the sync check); a top-level folder not listed; a conditional folder that is empty.

## Verify

- `ls` shows exactly the shape above, `git status` shows no real `.env` staged.
- `uv run python -m src.run` starts it standalone before it goes into compose.
- `python scripts/check_compose.py --self-test` passes (no Docker needed).
