# Plan 5.2b: Brains move to Stronghold

Branch: `refactor/stronghold-brains`.

## What moved

1. Stronghold `src/brains/`: encrypted, revisioned brain connections (`connections.py`), recoverable Note publication (`promotions.py`), AI promotion suggestions (`suggestions.py`), the private transport to Armory's `/brains/operation` (`gateway.py`) and the routes (`routes.py`): `/brains/connections/{scope}` (get, put, test), `/destinations`, `/browse`, `/promotions`, `/notes/{id}/review|promote`, `/promotions/{id}/reconcile`, `/suggestions` (list, review, dismiss), `/writable/{scope}`, `/resolve` and `DELETE /brains/accounts/{uid}`.
2. **Per-request permissions.** Stronghold has no sessions, so it asks Portcullis what an account may do on every request: new `GET /internal/accounts/{uid}/permissions` (404 for an unknown, inactive or unverified account), client call `PortcullisClient.permissions(uid)`. A permission taken away applies on the next request. Rules kept: instance connections need `settings.manage`, writing the instance brain needs `brain.instance.publish`, Notes, promotions and suggestions need `chat.use`.
3. Armory resolves connections through Stronghold: `POST /brains/resolve` (internal token and uid, the same permission check). `EMBER_API_URL` is gone; Armory reads `STRONGHOLD_URL` (default `http://127.0.0.1:29650`, Compose `http://stronghold:29650`).
4. Stronghold reads the Notes itself (`NotesService`) and runs the AI review through its own agent gateway and usage service, so `services/remote_notes.py` is gone.
5. Portcullis `/api/brains/*` are pass-throughs (login, plus `chat.use` where it applied). Auto-save asks `GET /brains/writable/{scope}` through `services/brain_client.py` (`RemoteBrains`). The chat page behaves as before.
6. Account delete purges brains through `DELETE /brains/accounts/{uid}` (also retires Armory's derived personal state); a failure logs `admin.brains_purge`.
7. Removed from Portcullis: `services/brain_connections.py`, `brain_gateway.py`, `brain_promotions.py`, `brain_suggestions.py`, `remote_notes.py`, `POST /api/brains/internal/resolve` and the brain error handlers. Their tests moved to Stronghold (`tests/test_brains_*.py`).

## What did not move

1. The turn engine's second-brain save request (`services/second_brain.py`, builds the agent's instruction) stays with the turn engine.
2. Armory's own brain index and operations (`/brains/operation`) are unchanged.

## Accepted behavior changes

1. **No data migration** (as decided for Plan 5): connections, promotions and suggestions start empty. Saved Obsidian API keys must be entered again; the old records stay in Portcullis's Treasury database, unreachable. Stronghold encrypts with its own `secrets` key (`keys.json` in `stronghold_data`): back it up with the data.
2. Armory down on a brain call now shows as `502 Stronghold is unavailable` (Stronghold answers 503, and Portcullis turns every 5xx into 502). Before, the browser saw 503 with a brain message.
3. Brain routes need Stronghold and Portcullis's internal routes reachable; with Portcullis down Stronghold answers 503 `Portcullis is unavailable`.
4. Request validation errors on a brain route are Stronghold's FastAPI 422 (field details), not the old fixed message; credentials are still never echoed back.

## Execution notes (2026-11-16)

- Stronghold suite: 521 passed. Armory and Portcullis full-suite results are in the commit message.
- Not run: Docker builds; Armory against a real Stronghold `/brains/resolve`; a real Obsidian vault; the Brain pages and auto-save in a browser.
