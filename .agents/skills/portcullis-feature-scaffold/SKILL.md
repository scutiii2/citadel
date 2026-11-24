---
name: portcullis-feature-scaffold
description: Use when adding or changing a portcullis (FastAPI) backend feature - a route, permission, model, Alembic migration, service, audit log entry or a pass-through to Stronghold - and its tests. For reaching Armory, Legion or Stronghold use portcullis-mcp-bridge; for the Vue side use ember-feature-scaffold.
---

# Portcullis backend scaffolding

Portcullis owns accounts, sessions, roles and permissions, invites, settings and logs, and is the only door from the browser to the other services. FastAPI + async SQLAlchemy (SQLite). `apps/portcullis/README.md` ("Layout", "Changing the schema", "Security model") is the source of truth; this is the checklist.

## Where the feature lives

| Data or work | Home |
|---|---|
| Accounts, sessions, roles, settings, logs, devices | Portcullis database (model + migration) |
| Chats, turns, brain, skills, tickets, usage, attachments, tool services | Stronghold owns it. The Portcullis route checks login and permission, then passes the request on (`portcullis-mcp-bridge`) |
| Record data with no joins or foreign keys | Treasury through `DbGatewayClient` (`services/db_gateway.py`, `get_db_gateway`, `FakeDbGateway` in tests); answer `503` when unreachable |
| Running a tool | An Armory capability (`armory-capability-scaffold`) |

Security is enforced here, never only in the UI.

## Steps

1. **Permission.** Reuse one when it fits. A new one goes in `src/services/permissions.py` (constant + `ALL_PERMISSIONS`; add it to `STAFF_PERMISSIONS` if staff-only). Administrator gets it on next start. Existing roles do not: grant it once inside the migration that adds the feature (see `migrations/versions/0012_ticket_permissions.py`), so a later revocation sticks. A read-only permission never grants mutation. Tell the user which roles get it.
2. **Model** (new data): file in `src/models/`, export from `src/models/__init__.py`. Relationships use `lazy="selectin"`. Times are naive UTC via `src.db.utcnow`. Per-account data keys on `account.uid`, never the username.
3. **Migration** for any table or column change: stop Portcullis, run `python -m scripts.migrate_db revision "what changed"` in `apps/portcullis`, read the file (a new `NOT NULL` column needs `server_default`). In `tests/test_migrations.py` bump `HEAD`/`NEXT`; for a new column on an existing table add a `drop_<column>` helper beside `drop_log_prompts` and call it wherever a test rewinds a model-built database.
4. **Service**: class taking `AsyncSession`; logic lives here, not in routes. Blocking work (hashing, file I/O) goes through `asyncio.to_thread`. Secrets and codes are stored hashed. Mail goes through the Armory email capability (`services/email_service.py`).
5. **Route** in `src/routes/` (one `APIRouter` per area, prefix `/api/...`): gate with `Depends(require_permission(NAME))` (also rejects unverified accounts) or `Depends(current_account)`. Bodies are pydantic models; response models get `@classmethod of(cls, row)`. Register in `src/app.py` (`include_router`). New app-wide clients are made in the lifespan, stored on `app.state`, read through a `deps.py` getter and injectable through `create_app(...)` so tests pass fakes.
6. **POST bodies are JSON only**: `JsonOnlyMiddleware` answers 415 otherwise (CSRF guard with the `SameSite=Strict` cookie). No form endpoints.
7. **Audit**: a route that changes something calls `logs.action(account, "<area>.<verb>", "<what changed>")` (`LogWriter` via `Depends(get_log_writer)`) after it succeeds. Log ids and field names, never user text.
8. **Tests** in `apps/portcullis/tests/`: `conftest.py` gives `client`, `client_factory(**settings)`, `email`, `upstream`, `server_tools`, `db_gateway`, `traffic`; `tests/test_registration.py` has `as_admin`, `new_invite`, `register`. Cover happy path, 401 logged out, 403 without the permission or unverified, and validation errors. Run the nearest file only: `uv run pytest -q tests/test_x.py` from `apps/portcullis`.
9. Update the API table in `apps/portcullis/README.md`.
