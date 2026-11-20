# stronghold

Product logic for Citadel and Ember. Only `portcullis` calls it.

- Every route except `/health` requires a short-lived Ed25519 service assertion; keys are generated on first start.
- Account identity comes only from a Portcullis-signed requester token. Running turns renew it before expiry and stop if renewal fails.
- Private keys stay in the service's identity directory; only public keys are shared through the trust directory.
- No cookies, no sessions and no login here. Portcullis owns those.

## Run

    uv sync
    uv run python -m src.run

Default address `127.0.0.1:29650`. `STRONGHOLD_HOST` and `STRONGHOLD_PORT` override it.

| Variable | Default | Purpose |
|---|---|---|
| `AGENTS_REGISTRY_PATH` | `../legion/.data/agent_registry.json` | Legion's list of running agents (file) |
| `AGENTS_REGISTRY_URL` | none | The same list over HTTP; wins over the file when set |
| `STRONGHOLD_DATA_DIR` | `.data` | Holds `keys.json` |
| `STRONGHOLD_CONFIG` | `configs/config_app.json` | Host and port (tracked; see `configs/README.md`). A missing file means defaults. Usage limits and prices are in Stronghold Admin |

`keys.json` is made on first start: the key that encrypts saved secrets (personal brain keys, private-extension headers). Back it up with the data. Without it, saved secrets cannot be read. An older file may also hold a web push key pair; it is ignored.

## What Stronghold asks Portcullis

Jobs without a request call Portcullis's `/internal` routes with the internal token: an account's permissions, a line on the Logs page for an action, and writing to the Errors and chat-trace logs. See `src/platform.py`.

In Docker: `dev_deploy.bat` rebuilds and restarts the `stronghold` container from the root `docker-compose.yml`.

## Test

    uv run pytest -q

## Routes

| Route | Purpose |
|---|---|
| `GET /health` | Open. `{"status": "ok"}` |
| `GET /whoami` | Echoes the requester. Portcullis exposes it as `GET /api/stronghold/whoami` |
| `/notes/...` | Notes, tags, tag suggestions and generation. Portcullis exposes them as `/api/notes/...` after checking `chat.use` |
| `/memory/...` | Assistant memory. Portcullis exposes it as `/api/memory/...` after checking `chat.use` |
| `/tickets/...`, `/ticket-admin/...` | Tickets (Armory keeps them) and the account's read receipts (Treasury, collection `ticket_seen`). Portcullis exposes them as `/api/tickets/...` (`tickets.create`) and `/api/admin/tickets...`, `/api/admin/ticket-groups...` (`tickets.manage`) |
| `/triage/titles`, `/triage/ask` | Option titles from the `title-writer` agent and typed questions to the Triage Assistant (Laya); both count toward the token limits. Portcullis exposes them as `/api/triage/...` after checking `chat.use` |
| `/attachments/...` | Text extraction (`text`), PDFs and tables stored by Armory (`pdf`, `table`), plus Stronghold calls for Scribe audio (`audio`, `dictate`, `dictate/partial`) or Reader documents (`document`). Portcullis forwards the JSON endpoints and dictation to Stronghold. Attachment previews retain the Armory content stream |
| `/brains...` | Encrypted Personal Brain connections, browsing through Armory, Note publication and AI promotion suggestions. Portcullis exposes them as `/api/brains`. `POST /brains/resolve` authorizes shared access and resolves personal connections for Armory. Stronghold asks Portcullis for current account permissions and Armory for shared destination metadata |
| `/chats...`, `/chat-folders...` | Chat history (details and transcript in separate documents), folders and search. Portcullis exposes them as `/api/chats` and `/api/chat-folders` and Stronghold runs the answers (`/turns`). Deleting chats revokes their share links first, inside the same call |
| `/account-agents...` | The specialist agents an account switched off (Treasury, collection `account_agents`). Portcullis exposes it as `/api/account-agents` and reads the list when a chat turn starts |
| `/user-extensions...` | An account's own MCP servers: stored with encrypted headers (collection `user_extensions`), probed through Legion for status and tools. Portcullis exposes them as `/api/user-extensions` (`chat.use` to read, `extensions.personal.manage` to change) and reads `GET /user-extensions/for-turn` when a chat turn starts |
| `/schema` | The schema version the stored data is at, the steps applied and every Treasury collection Stronghold uses |
| `/tuning/...` | An account's own response limits (`GET\|PUT\|DELETE /tuning/limits`, `GET /tuning/limits/own`), capped by Legion's tuning, which Stronghold reads from the entry agent. Portcullis exposes them as `/api/account/tuning` and reads `/tuning/limits/own` when a chat turn starts |
| `/bard/...` | `POST /bard/speak` and `GET /bard/voices` call the configured Bard connection. Portcullis relays `/api/bard/audio/{id}` from Stronghold with Range |
| `/shares...` | Share links to frozen chat snapshots (Treasury, collection `shared_chats`) and the public read of one (`GET /shares/public/{token}`, no requester). Portcullis exposes them as `/api/chats/{id}/shares`, `/api/shares...` and `/api/shared/{token}`. Deleting a chat revokes its links in the same call |
| `/turns/...` | Chat turns, run here (one replica only: running turns live in memory). `POST /turns/{chat}` saves the question and starts the answer; `GET /turns/{chat}/events` is the SSE stream; `/approvals`, `/questions`, `/cancel`, `/summarize`, `/clear`, `/suggestion`; `GET /turns/running`; `DELETE /turns/{chat}` and `DELETE /turns` stop turns. The start body carries a `trusted` block (`forced_approval`, `tools_execute`, `extension_ids`, `second_brain_available`) that only Portcullis may fill. Error and chat-trace lines go to Portcullis's `POST /internal/logs`. Portcullis still runs its own copy until Plan 10.4 |
| `/usage/...` | Token usage and limits, kept in Treasury (collection `usage_records`). Portcullis exposes the reads as `/api/usage/...` and `/api/admin/usage/...`, and calls `POST /usage/check` and `POST /usage/records` around every agent call |
| `/templates/...` | Saved prompts, kept in Treasury (collection `prompt_templates`). Portcullis exposes them as `/api/templates/...` after checking `chat.use` |
| `/skills/...` | Learned skills, which Armory keeps. Portcullis exposes them as `/api/skills/...` after checking `chat.use` |
| `DELETE /<domain>/accounts/{uid}` | Removes everything a deleted account kept (`notes`, `memory`, `skills`, `templates`, `usage`, `tickets`, `shares`, `tuning`, `chats`, `brains`, `account-agents`, `user-extensions`, and `turns`, which stops its running turns). Called by Portcullis only |

## Tool services

Stronghold calls Bard for speech, Scribe for dictation and audio attachments, and Reader for document attachments. Configure these three services in **Stronghold Admin → Tool services**. Stronghold stores one record per service in its `settings.db` table `tool_services`. A record holds `enabled`, a Treasury `service_id`, an ordered list of `{origin_id, header_value?}` references, and a parent `token`. Treasury stores the addresses and lists Stronghold in `used_by`. Admin responses expose token-presence flags. Each request sends `X-Internal-Token` only to its selected origin, using that origin's override when present.

REST calls try the next origin on a connection refusal or connect timeout. A transport failure after a connection may have been made fails the call and puts that origin on a 30-second cooldown. An HTTP reply ends the attempt. File requests use the origin recorded when Stronghold received the file ID. The newest 2,000 mappings live in memory and include the account and service. A missing mapping returns 404, including pre-cutover clips, clips generated through MCP, and mappings lost to eviction or restart. Legion selects its MCP origin separately. If the backing stores are separate, an MCP tool can miss an attachment that Stronghold uploaded to a backup. If a Scribe connection cannot open, a new dictation stream can use the backup. The current stream is never replayed.

Uploads are capped at 20 MB, JSON at 1 MB (4 KB for Reader parse), and REST requests at 120 seconds. Bard audio supports Range and streams up to 64 MB within 120 seconds. Scribe allows one live stream per account with 150 seconds of PCM audio, frames up to 64,000 bytes, a 15-second idle limit, and a 120-second final-result limit.

| Route | Purpose |
|---|---|
| `GET /tool-services/status` | Configuration readiness for Bard, Scribe, and Reader |
| `GET /speech/audio/{file_id}` | Stream Bard audio from its origin with Range support |
| `WS /speech/dictate` | Relay PCM and stop frames to Scribe and return partial and final transcripts |
| `GET /admin/tool-services` | List saved connection metadata and token-presence flags |
| `POST /admin/tool-services/lookup` | Look up an address in Treasury |
| `PUT /admin/tool-services/{name}` | Register addresses and save connection settings. Treasury outages refuse the save with `[1002]` |
| `DELETE /admin/tool-services/{name}` | Clear the Stronghold record |
| `POST /admin/tool-services/{name}/test` | Check each saved origin's health and credentials without generating files |

Only Portcullis can call the admin routes. Armory's REST façade and Connections page remain until Plan 22.

## Schema

Treasury keeps any JSON, so `src/schema` is Stronghold's schema. `models.py` has the document shapes for chats, shares and usage; a store checks a document there before it writes it. `catalog.py` lists every collection (key shape, model, purge route); a test fails when code uses a collection that is not listed. `migrations.py` keeps a version in the `schema_state` document and runs the steps above it at start: add a step to `MIGRATIONS` (never edit a shipped one) and make it safe to run twice.

## Notes and memory

`/notes/...` are an account's private notes, kept in Treasury (collection `notes`). Armory's notes tools read the same collection for the notes an account shared with agents, so Armory must use the `stronghold` connection (`DB_GATEWAY_CONNECTION=stronghold`). Tag suggestions ask the Laya agent; tag generation asks the `tag-writer` agent. `/memory/...` is the assistant memory, which Armory keeps; Stronghold scopes every call to the requester.

`src/agents/` is a copy of Portcullis's agent client. Change both until chats move here.

`TREASURY_URL` overrides the `treasury_url` bootstrap address in `configs/config_app.json`. Internal peers resolve through Treasury’s catalog at request time.
