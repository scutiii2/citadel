# Plan 6: Stronghold schema

Branch: `feat/stronghold-schema`.

## Decision

The roadmap asked for SQLAlchemy models and migrations. Plan 5 had already put every Stronghold domain in Treasury as documents, so the owner chose to formalize that, not add a SQL database (2026-11-16). Treasury stays the only store; Stronghold gets a schema layer on top of it.

## What was built

1. `apps/stronghold/src/schema/models.py`: pydantic models for the documents of chats, shares and usage: `ChatDoc`, `ChatMessagesDoc`, `ChatFolderDoc`, `ShareDoc`, `UsageRecordDoc`, all keyed on the account uid (`owner`) and repeating their own `key`. Unknown fields are allowed, so older documents still read. `checked(model, doc)` runs before every write in `chats/store.py`, `shares/store.py` and `usage/service.py`: a document that does not fit raises `ValidationError` at the write, not later on a page.
2. `schema/catalog.py`: the one list of the 21 collections Stronghold uses (name, domain, key shape, model if any, purge route). Collections of the other domains have no model yet (`model=None`); a later plan can add one.
3. `schema/migrations.py`: a version in the `schema_state` document and an ordered list of steps. At start Stronghold runs the steps above the stored version and records each. Version 1 is the baseline (nothing to change). A step must be safe to run twice. Data at a newer version than the code (a rollback) is refused and left alone. Storage down or too-new data does not stop Stronghold from starting: it logs the error and `app.state.schema_version` stays `None`.
4. `GET /schema`: version, latest, steps applied and the catalog, for the Stronghold admin app (Plan 7). Internal token only; Portcullis does not expose it yet.
5. Tests: `tests/test_schema.py` (12). The test database refuses any collection missing from the catalog, so new storage cannot skip it; the catalog's purge routes are called to prove they exist; a source scan checks collection constants against the catalog.

## What did not change

1. Documents already written by Plans 5 and 5.2b are valid as they are: no data migration. Fresh install, as decided.
2. Treasury has no indexes or constraints, so uniqueness and limits stay in the stores (`create` if absent, counts before writes).
3. `services/chat_app_import.py` and `scripts/import_chat_app.py` in Portcullis are still there. They write the old SQL tables nothing reads. Delete them in a cleanup the owner approves (a deletion outside this plan).

## Accepted behavior changes

1. A store bug that builds a wrong document now fails the request (500) at the write instead of saving it.
2. Stronghold's start does one more Treasury call (read `schema_state`; one write on a fresh database).

## Execution notes (2026-11-16)

- Stronghold suite: see the commit message. Portcullis and Armory are untouched.
- Not run: Docker build, a real Treasury (the schema state document on a live database), two replicas starting together.
