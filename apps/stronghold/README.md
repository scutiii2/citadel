# stronghold

Product logic for Citadel and Ember. Only `portcullis` calls it.

- Every route but `/health` needs `X-Internal-Token` (the shared internal token).
- The asking account arrives in `X-Requester-Uid`, `X-Requester-Username` and `X-Requester-Email`. Data is keyed on the uid.
- No cookies, no sessions and no login here. Portcullis owns those.

## Run

    uv sync
    uv run python -m src.run

Default address `127.0.0.1:29650`. `STRONGHOLD_HOST` and `STRONGHOLD_PORT` override it.

| Variable | Default | Purpose |
|---|---|---|
| `DB_GATEWAY_URL` | `http://127.0.0.1:29602` | Treasury. Stronghold uses instance `stronghold`, connection `stronghold` |
| `PORTCULLIS_URL` | `http://127.0.0.1:29601` | Portcullis's `/internal` API (see below) |
| `ARMORY_URL` | `http://127.0.0.1:29600` | Armory, which keeps the assistant memory and the learned skills |
| `AGENTS_REGISTRY_PATH` | `../legion/.data/agent_registry.json` | Legion's list of running agents (file) |
| `AGENTS_REGISTRY_URL` | none | The same list over HTTP; wins over the file when set |
| `STRONGHOLD_DATA_DIR` | `.data` | Holds `keys.json` |
| `STRONGHOLD_CONFIG` | `configs/config_app.json` | Feature settings; copy `config_app.json.example`. A missing file means defaults |

`keys.json` is made on first start: the key that encrypts saved secrets (calendar links) and the web push key pair. Back it up with the data. Without it, saved links cannot be read and browsers must subscribe to push again.

## What Stronghold asks Portcullis

Background jobs have no request to take an account from. They call Portcullis's `/internal` routes with the internal token: an account's address and standing (`recipient`), the administrator's switches, sending an email to an account, a line on the Logs page for an action, and writing to the Errors log. See `src/platform.py`.

In Docker: `dev_deploy.bat` rebuilds and restarts the `stronghold` container from the root `docker-compose.yml`.

## Test

    uv run pytest -q

## Routes

| Route | Purpose |
|---|---|
| `GET /health` | Open. `{"status": "ok"}` |
| `GET /whoami` | Echoes the requester. Portcullis exposes it as `GET /api/stronghold/whoami` |
| `/calendar/...` | Feeds, events, alarms, prefs, push, alerts. Portcullis exposes them as `/api/calendar/...` after checking `calendar.use` |
| `/notes/...` | Notes, tags, tag suggestions and generation. Portcullis exposes them as `/api/notes/...` after checking `chat.use` |
| `/memory/...` | Assistant memory. Portcullis exposes it as `/api/memory/...` after checking `chat.use` |
| `/tickets/...`, `/ticket-admin/...` | Tickets (Armory keeps them) and the account's read receipts (Treasury, collection `ticket_seen`). Portcullis exposes them as `/api/tickets/...` (`tickets.create`) and `/api/admin/tickets...`, `/api/admin/ticket-groups...` (`tickets.manage`) |
| `/triage/titles`, `/triage/ask` | Option titles from the `title-writer` agent and typed questions to the Triage Assistant (Laya); both count toward the token limits. Portcullis exposes them as `/api/triage/...` after checking `chat.use` |
| `/attachments/...` | Text from a file attached to a question (`text`), PDFs and tables kept in Armory (`pdf`, `table`), audio for Scribe (`audio`, `dictate`, `dictate/partial`) and documents for Reader (`document`). Portcullis exposes them as `/api/attachments/...` and still streams file content and the dictation socket |
| `/brains...` | Encrypted Obsidian brain connections, browsing through Armory, Note publication and AI promotion suggestions. Portcullis exposes them as `/api/brains`; Armory resolves a connection with `POST /brains/resolve`. Stronghold asks Portcullis for the account's permissions on every request |
| `/chats...`, `/chat-folders...` | Chat history (details and transcript in separate documents), folders and search. Portcullis exposes them as `/api/chats` and `/api/chat-folders` and runs the answers itself, saving the question and the answer here. Deleting chats revokes their share links first, inside the same call |
| `/tuning/...` | An account's own response limits (`GET\|PUT\|DELETE /tuning/limits`, `GET /tuning/limits/own`), capped by Legion's tuning, which Stronghold reads from the entry agent. Portcullis exposes them as `/api/account/tuning` and reads `/tuning/limits/own` when a chat turn starts |
| `/bard/...` | `POST /bard/speak` and `GET /bard/voices`, asked from Bard. Portcullis exposes them as `/api/bard/speak|voices` and still streams `/api/bard/audio/{id}` |
| `/shares...` | Share links to frozen chat snapshots (Treasury, collection `shared_chats`) and the public read of one (`GET /shares/public/{token}`, no requester). Portcullis exposes them as `/api/chats/{id}/shares`, `/api/shares...` and `/api/shared/{token}`, and calls `POST /shares/revoke` before it deletes chats |
| `/usage/...` | Token usage and limits, kept in Treasury (collection `usage_records`). Portcullis exposes the reads as `/api/usage/...` and `/api/admin/usage/...`, and calls `POST /usage/check` and `POST /usage/records` around every agent call |
| `/templates/...` | Saved prompts, kept in Treasury (collection `prompt_templates`). Portcullis exposes them as `/api/templates/...` after checking `chat.use` |
| `/skills/...` | Learned skills, which Armory keeps. Portcullis exposes them as `/api/skills/...` after checking `chat.use` |
| `DELETE /<domain>/accounts/{uid}` | Removes everything a deleted account kept (`calendar`, `notes`, `memory`, `skills`, `templates`, `usage`, `tickets`, `shares`, `tuning`, `chats`, `brains`). Called by Portcullis only |

## Notes and memory

`/notes/...` are an account's private notes, kept in Treasury (collection `notes`). Armory's notes tools read the same collection for the notes an account shared with agents, so Armory must use the `stronghold` connection (`DB_GATEWAY_CONNECTION=stronghold`). Tag suggestions ask the Laya agent; tag generation asks the `tag-writer` agent. `/memory/...` is the assistant memory, which Armory keeps; Stronghold scopes every call to the requester.

`src/agents/` is a copy of Portcullis's agent client. Change both until chats move here.

## Calendar

Private read-only schedules from ICS links, with alerts before events (in-app, email, web push). The `calendar` block of the config file sets `enabled`, `tick_seconds`, `feed_refresh_minutes`, `lookahead_hours`, `late_grace_minutes`, `max_feeds_per_account`, `max_alarm_rules`, `max_ics_bytes`, `fetch_timeout_s`, `allow_private_urls` and `push_contact`. With `enabled` false the routes answer 404 and no scheduler runs. The channel switches (`calendar_inapp`, `calendar_email`, `calendar_push`) stay on Portcullis's admin Settings page.
