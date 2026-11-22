# mcp_server

A general-purpose MCP (Model Context Protocol) tool server of built-in capabilities, among them `server_manager` for
starting/stopping/restarting/listing managed apps. Built to be called by
`chat_app` or any other MCP client speaking streamable HTTP.

## Requirements

- Python >= 3.11
- An SMTP account for outbound mail (Email capability, ServerWatcher notifications, Ember invites and verification)


## Setup

1. Copy `.env.example` to `.env` (created automatically on first run). Everything else is set in Armory Admin - see [Configuration](#configuration).

2. Run the server:

   ```
   cd apps/armory
   uv sync
   uv run python -m src.run
   ```

   (Needs [uv](https://docs.astral.sh/uv/). Sync once; afterwards only the last line.)

## Configuration

Both loaded once at boot by `src/run.py`:

- **`.env`** - credentials and deployment settings, gitignored. Copy
  `.env.example` to `.env`. See [`docs/secrets.md`](docs/secrets.md).
- **Armory Admin pages** - capabilities, deployment values, email and limits, saved in
  `.data/armory/settings.db`. See [`docs/settings.md`](docs/settings.md).


## Security

Every internal route requires a short-lived Ed25519 service assertion; keys are generated on first start.
User identity comes only from a Portcullis-signed requester token, verified per tool call on shared MCP sessions.
Private identity keys stay separate from public keys in `CITADEL_TRUST_DIR`; there is no auth-off mode.

## Code layout

See [`src/README.md`](src/README.md) for the full map - what lives
where, and where new code goes.

## Capabilities

Each tool this server offers lives under its own folder in
`src/capabilities/`, with its own README - see
[`src/capabilities/README.md`](src/capabilities/README.md) for the
shape every capability follows and how to add a new one:

- [`capabilities/server_manager`](src/capabilities/server_manager) - start/stop/restart/list managed apps (`/server ...`)
Stronghold serves support tickets and account usage tools. Ember’s Tickets and Usage pages replace the retired Armory `/ticket` and `/usage` slash commands. Armory Admin’s Ticket settings page still reaches Stronghold through Portcullis. Existing Armory ticket databases stay on disk without migration.

Every capability can be turned off without touching code, live - no
restart needed. `GET /capabilities` lists each one's current state
(`name`, `enabled`, `label`, `tools`, `resources`, `has_gui`, and
`loaded`, `missing`, `load_error`: `loaded` is false for a folder that was
found but never brought online, `missing` means its folder is gone from
disk, `load_error` is the text of the last failed import);
`PATCH /capabilities/{name}` (body `{"enabled": bool}`) toggles it,
saves the change in `settings.db`, and adds/removes its
tools and resources from the running server, all in one request. Going
online re-imports the capability from disk, and answers `409` with
`{"error": ...}` if that fails. `POST /capabilities/refresh` rescans
`src/capabilities/` so a folder added while the server runs shows up
(offline) and returns the same list. A new folder is never loaded until it
is switched online. See `src/capability_routes.py`,
`src/services/capability_loader.py` and `src/infra/README.md`'s
`capability_registry.py` entry. armory_admin's Capabilities page calls these.

Client-readable URI resources follow the same pattern one level over -
see [`src/resources/README.md`](src/resources/README.md).

## Runtime state

Runtime state is not kept in this folder. It lives in the Citadel root, one folder per service:

- **`.data/armory/`** - databases (`email/`; old `memory/` and `skills/` files stay on disk, unused), `uploads/`, `watchers/`, `pdf_merger/store/` and `logs/` (`server.log` plus one file per error reference id).
- **`.cache/armory/`** - files Armory can make again: `media_downloader/store/`.

`CITADEL_DATA_DIR` and `CITADEL_CACHE_DIR` in the root `.env` move the two roots; each `MCP_*_DIR` / `MCP_*_PATH` setting still overrides one path. Configuration stays in the tracked `configs/` folders.

## Maintenance

One-off: `python -m src.prune_unused_tables <path to settings.db>` reports the unused `extensions` and `connections` tables in `settings.db`; add `--apply` to drop them. It is a dry run by default. Stop Armory and copy the file first. Only those two tables are removed; Armory never does this itself.

## Tests

```
pytest            # fast run: skips the `slow` tests (tests/math, real worker processes)
pytest -m ""      # everything; run before a merge
```

## Docker

Armory runs as the `armory` service of the root `docker-compose.yml`, with `treasury` started as its dependency. Rebuild
it on this machine with `dev_deploy.bat` in this folder, or `docker compose up -d --build armory` from the repo root.
Deploying to the ZimaOS box is covered in [docs/deployment.md](../../docs/deployment.md).

Container-only configs are mounted from `docker/configs/armory/`, and the host Docker socket is mounted for the
Server Manager capability. The SMTP account is set on the Email page of Armory Admin.
The SMTP password the old `zima_host.yaml` recipe once held must still be revoked at the mail provider, because
removing the file does not remove it from Git history.

### PDF chat attachments

`POST /upload/pdf` accepts a multipart `file` (PDF, PNG, JPEG, WebP, TIFF,
GIF or HEIC; at most 15 MB). It requires a service assertion and a signed requester token.
Original bytes remain in Armory's native PDF store under the verified account UID.
The response contains an opaque file ID, metadata and expiry; ownership checks apply to every operation.

## Liveness, readiness, and tool failures

`GET /health` is public and answers `{"status":"ok"}` while the process runs.
`GET /ready` requires a signed Citadel service assertion. Authorized calls return
HTTP 200 with dependency addresses and states (`configured`, `reachable`,
`unreachable`, `not_configured`) even during an outage.

| Code | Failure | Retryable |
|---|---|---|
| 1000 | `TOOL_INTERNAL` | No |
| 1001 | `DEP_NOT_CONFIGURED` | No |
| 1002 | `DEP_UNAVAILABLE` | Yes |
| 1003 | `DEP_TIMEOUT` | Yes |
| 1004 | `DEP_AUTH_REJECTED` | No |
| 1005 | `DEP_ERROR` | Maybe |

PDF and media tools keep their existing capability codes.
