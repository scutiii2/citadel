# Plan 5: Move product logic to Stronghold, domain by domain

One sub-plan and one branch (`refactor/stronghold-<domain>`) per domain. Each is merged before the next starts.

## How every domain moves

1. **Code**: the domain's services and routes move from `apps/portcullis/src` to `apps/stronghold/src/<domain>/`. Its tests move with it.
2. **Public routes stay**: Portcullis keeps `/api/<domain>/...`. It checks the login and the permission, then passes the request to Stronghold `/<domain>/...` with the requester headers. No route the browser uses changes.
3. **Identity**: Stronghold reads `X-Requester-Uid`. It checks no login and no permission.
4. **Data**: Stronghold stores in Treasury, instance `stronghold`, connection `stronghold` (`data/stronghold.db`). No data migration.
5. **Account delete**: Portcullis calls Stronghold's purge route for the domain. A failure is logged and does not stop the delete.
6. **Proof**: both suites pass; the domain's public behavior is covered by tests on both sides.

## Back-channel (decided 2026-11-15)

Stronghold's background jobs have no request, yet need things Portcullis owns. Stronghold calls a small internal Portcullis API (`/internal/...`), guarded by the shared internal token and refused when no token is configured:

| Route | Use |
|---|---|
| `GET /internal/accounts/{uid}/recipient?permission=` | `{uid, email}` when the account is active, verified and holds the permission; 404 otherwise |
| `GET /internal/switches` | The administrator's on/off settings |
| `POST /internal/accounts/{uid}/notify` | Email the account. Stronghold names an account, never an address |
| `POST /internal/accounts/{uid}/actions` | A line on the Logs page for something the account did |
| `POST /internal/errors` | A line in the Errors log, source `stronghold.<name>` |

Accounts, SMTP, settings and logs stay in Portcullis. Later domains add routes here only when a job needs them.

## Sub-plans

| # | Domain | Status |
|---|---|---|
| 5.1 | calendar | Executed 2026-11-15: `2026-11-15-plan-5-1-calendar.md` |
| 5.2 | memory, notes (with a copy of the agent client) | Executed 2026-11-15: `2026-11-15-plan-5-2-memory-and-notes.md` |
| 5.2b | brains (usage accounting is in Stronghold now; needs per-request permissions) | To write |
| 5.3 | templates, skills | Executed 2026-11-15: `2026-11-15-plan-5-3-templates-and-skills.md` |
| 5.4 | tickets, triage | Executed 2026-11-15: `2026-11-15-plan-5-4-tickets-and-triage.md` |
| 5.5 | shares | Executed 2026-11-15: `2026-11-15-plan-5-5-shares.md` |
| 5.6 | usage | Executed 2026-11-15: `2026-11-15-plan-5-6-usage.md` |
| 5.7 | attachments, bard | Executed 2026-11-15: `2026-11-15-plan-5-7-attachments-bard.md` |
| 5.8 | tuning (account; the admin side stays with Legion admin, Plan 7) | Executed 2026-11-15: `2026-11-15-plan-5-8-tuning.md` |
| 5.9 | chats, folders, turns (with Plan 6, the schema) | To write |
