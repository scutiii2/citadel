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
| `/stack/...` | Short-term memory for a single chat. Portcullis exposes this under `/api/chats/{id}/stack`. |
| `/tickets/...`, `/ticket-admin/...` | Support tickets, staff triage and the account's read receipts. Portcullis exposes them as `/api/tickets/...` (`tickets.create`) and `/api/admin/tickets...`, `/api/admin/ticket-groups...` (`tickets.manage`) |
| `/triage/titles`, `/triage/ask` | Option titles from the `title-writer` agent and typed questions to the Triage Assistant (agent `triage-assistant`, which asks its own model list); both count toward the token limits. Portcullis exposes them as `/api/triage/...` after checking `chat.use` |
| `/attachments/...` | Text extraction (`text`), PDFs and tables stored by Armory (`pdf`, `table`), plus Stronghold calls for Scribe audio (`audio`, `dictate`, `dictate/partial`) or Reader documents (`document`). Portcullis forwards the JSON endpoints and dictation to Stronghold. Attachment previews retain the Armory content stream |
| `/chats...`, `/chat-folders...` | Chat history (details and transcript in separate documents), folders and search. Portcullis exposes them as `/api/chats` and `/api/chat-folders` and Stronghold runs the answers (`/turns`). Deleting chats revokes their share links first, inside the same call |
| `/account-agents...` | The specialist agents an account switched off (Treasury, collection `account_agents`). Portcullis exposes it as `/api/account-agents` and reads the list when a chat turn starts |
| `/user-extensions...` | An account's own MCP servers: stored with encrypted headers (collection `user_extensions`), probed through Legion for status and tools. Portcullis exposes them as `/api/user-extensions` (`chat.use` to read, `extensions.personal.manage` to change) and reads `GET /user-extensions/for-turn` when a chat turn starts |
| `/schema` | The schema version the stored data is at, the steps applied and every Treasury collection Stronghold uses |
| `/tuning/...` | An account's own response limits (`GET\|PUT\|DELETE /tuning/limits`, `GET /tuning/limits/own`), capped by Legion's tuning, which Stronghold reads from the entry agent. Portcullis exposes them as `/api/account/tuning` and reads `/tuning/limits/own` when a chat turn starts |
| `/bard/...` | `POST /bard/speak` and `GET /bard/voices` call the configured Bard connection. Portcullis relays `/api/bard/audio/{id}` from Stronghold with Range |
| `/shares...` | Share links to frozen chat snapshots (Treasury, collection `shared_chats`) and the public read of one (`GET /shares/public/{token}`, no requester). Portcullis exposes them as `/api/chats/{id}/shares`, `/api/shares...` and `/api/shared/{token}`. Deleting a chat revokes its links in the same call |
| `/turns/...` | Chat turns, run here (one replica only: running turns live in memory). `POST /turns/{chat}` saves the question and starts the answer; `GET /turns/{chat}/events` is the SSE stream; `/approvals`, `/questions`, `/cancel`, `/summarize`, `/clear`, `/suggestion`; `GET /turns/running`; `DELETE /turns/{chat}` and `DELETE /turns` stop turns. The start body carries a `trusted` block (`forced_approval`, `tools_execute`) that only Portcullis may fill. Error and chat-trace lines go to Portcullis's `POST /internal/logs`. Portcullis still runs its own copy until Plan 10.4 |
| `/usage/...` | Token usage and limits, kept in Treasury (collection `usage_records`). Portcullis exposes the reads as `/api/usage/...` and `/api/admin/usage/...`, and calls `POST /usage/check` and `POST /usage/records` around every agent call |
| `/templates/...` | Saved prompts, kept in Treasury (collection `prompt_templates`). Portcullis exposes them as `/api/templates/...` after checking `chat.use` |
| `/skills/...` | Learned skills kept in Stronghold’s Brain. Portcullis exposes them as `/api/skills/...` after checking `chat.use` |
| `DELETE /<domain>/accounts/{uid}` | Removes everything a deleted account kept (`skills`, `templates`, `usage`, `tickets`, `shares`, `tuning`, `chats`, `stack`, `account-agents`, `user-extensions`, and `turns`, which stops its running turns). Called by Portcullis only |

Free resets, limit boosts and cached-token weighting: `src/usage/allowance.py` holds the rules and one
`usage_allowances` document per account holds the state. Administrators use `/admin/usage-allowances` through
Portcullis (`settings.manage`). A chat turn and a Triage Assistant question spend a reset when the account asked for it.

## Support tickets

Stronghold records tickets, groups, and counters in Treasury collections `tickets`, `ticket_groups`, and `ticket_counters`. It serves reporter and staff routes at `/tickets` and `/ticket-admin`. Deleting an account removes its tickets and read receipts.

Stronghold asks Legion’s Triage Assistant for a tag and possible group. These calls count toward the reporter’s usage as kind `ticket`. Reports still file when Triage is unavailable. Ticket settings live in `settings.db`, table `ticket_settings`, and are served at `/ticket-admin/settings`.

Legion can call `tool_ticket_createTicket`, `tool_ticket_listMyTickets`, `tool_ticket_getTicket`, `tool_ticket_addComment`, and `tool_usage_summary` through Stronghold’s MCP server. The usage tool reports the requesting account’s Treasury usage records. Ember’s Tickets and Usage pages replace the retired `/ticket` and `/usage` slash commands.

## MCP server

Legion connects to `/mcp` over Streamable HTTP with a signed service assertion. The tools are
`tool_stack_add`, `tool_stack_list`, `tool_stack_remove`, and `tool_stack_pin`.
A call carries a signed requester and a `chat_id` hint. Stronghold verifies the requester
and checks chat ownership before reading or changing the stack. Listed notes are untrusted data.

## Short-term memory

Each chat has a stack in Treasury. Defaults are 40 items, 500 characters per normal item,
1,500 per compaction item, and a warning at 80% capacity. Overrides use the `brain` table
and `stack` key in Stronghold's `settings.db`. When full, an add drops the oldest
unpinned item. If every item is pinned, it refuses the add.

The `context-summarizer` agent in Legion combines unpinned items when the next turn starts
after a warning or when the user requests compaction. Pinned items stay in the stack.
Deleting a chat removes its stack. Portcullis purges an account's stacks on account deletion.

| Route | Purpose |
|---|---|
| `GET /stack/{chat_id}` | Read items, capacity, and warning status |
| `POST /stack/{chat_id}/items` | Add text with optional pinning |
| `PUT /stack/{chat_id}/items/{item_id}` | Set the item's pinned state |
| `DELETE /stack/{chat_id}/items/{item_id}` | Remove an item |
| `POST /stack/{chat_id}/compact` | Compact unpinned items |
| `DELETE /stack/accounts/{uid}` | Purge a deleted account's stacks |

## Long-term memory (Brain)

Stronghold stores one account’s notes under `<root>/accounts/<uid>/[folder/]<slug>-<id8>.md`. Folders can be up to three levels deep. Each file has a header between `---` lines with one JSON value per `key: value` line, followed by a blank line and the Markdown body. The account folder identifies the owner. Records carry an id, title, tags, source, last editor, edit permission, edited flag, revision, and creation and update timestamps. A headerless Markdown file dropped into an account folder is adopted as a manual note.

For automatic notes, the first user edit to the title, body or tags saves a revert copy in `.originals/<id>.md`. Automatic notes return an editing warning. Agents can read every note in their account. They can edit automatic notes and manual notes the user marks `agent_editable`. Only users can move or delete notes or change that flag.

Legion calls `tool_brain_search`, `tool_brain_read`, `tool_brain_list`, `tool_brain_write`, `tool_brain_update`, and `tool_brain_propose` through signed `/mcp` requests. Each call needs a verified requester. Search uses BM25 over titles, tags and Markdown bodies. Stronghold creates the folder on first write.

`tool_brain_propose` queues a draft for review on Ember’s Notes page. Stronghold serves review routes at `/brain/proposals`, which Portcullis forwards from `/api/brain/proposals`. Keep creates an agent-authored file. Decline clears the draft text.

| Method and path | Input | Result |
|---|---|---|
| `GET /brain/files` | Optional `folder` | File summaries and folders |
| `POST /brain/files` | `title` with optional `body`, `tags`, `folder` | Created file |
| `GET /brain/files/{id}` | File id | File and Markdown body |
| `PUT /brain/files/{id}` | Changed fields and optional `expected_revision` | Updated file |
| `DELETE /brain/files/{id}` | File id | 204 |
| `POST /brain/files/{id}/revert` | File id and optional `expected_revision` in the request body | Restored file |
| `GET /brain/search` | `q` and optional `limit` | Ranked summaries and snippets |
| `GET /brain/summary` | | File count, bytes including revert copies, skipped files, and current quota |
| `DELETE /brain/accounts/{uid}` | Deleted account uid from Portcullis | 204 |

`GET /admin/brain-settings` returns active limits, ranges and the root. `PUT /admin/brain-settings` applies limit changes live. The `brain` table in `settings.db` stores `long_term`, `stack`, and `root`. Stronghold chooses the root at startup from `STRONGHOLD_BRAIN_ROOT`, then the saved `root`, then `<data dir>/brain`.

| Section | Setting | Default | Accepted range |
|---|---|---:|---:|
| `long_term` | `max_record_chars` | 20,000 | 200–100,000 |
| `long_term` | `max_files` | 500 | 1–5,000 |
| `long_term` | `max_total_bytes` | 5,000,000 | 10,000–100,000,000 |
| `long_term` | `search_limit` | 8 | 1–30 |
| `stack` | `max_items` | 40 | 2–200 |
| `stack` | `max_item_chars` | 500 | 20–2,000 |
| `stack` | `compact_item_chars` | 1,500 | 100–6,000 |
| `stack` | `warn_ratio` | 0.8 | 0.3–0.95 |

## Skills

Stronghold stores one Markdown file per skill under `<brain root>/accounts/<uid>/.skills/`. Back up this folder with the rest of the Brain. The long-term notes quota excludes skill files.

Legion can propose skills with `tool_skill_propose`, search approved skills with `tool_skill_search`, and record outcomes with `tool_skill_mark`. Only signed-in users can approve, edit, retire or delete skills through the `/skills` routes that Portcullis exposes as `/api/skills`. Account deletion also purges the files.

Titles, when-to-use text, steps and tool lists allow up to 80, 300, 1,200 and 200 characters respectively. Agents can have at most 20 proposals awaiting approval per account. Each account can have 50 active skills and 200 skill files. Search returns up to three approved skills using whole-word BM25. Armory's prefix matching and existing skill data do not carry over.

A skill stops appearing in search after at least three failures when failures outnumber successes. Editing resets both counts.

## Global brain and sharing

The global brain stores Markdown files and skills under `<brain root>/_global/`, beside `accounts/`. Back up both directories. Signed-in chat users can read global files and active skills. `brain.global.write` controls file changes, skill management and share review. Administrators receive it at startup.

The `oc_` uid prefix is reserved for Portcullis outside clients. An `oc_` uid may call only `tool_brain_search`, `tool_brain_read`, `tool_brain_list`, `tool_brain_write` and `tool_brain_update`, on its own folder; every other tool refuses it ("Not available to outside clients.") and it never reads or lists the global brain.

Portcullis serves the session routes under `/api/brain`. Use `/global/files`, `/global/search`, `/global/summary` and `/global/skills` to read global content. Use `/shares` to send a file, section, skill or short-term item, `/shares/sent` and `/shares/inbox` to list shares, and `/blocks` to manage blocked accounts. Reviewers use `/global/shares`.

A share freezes the selected content. It drops file tags and converts private Markdown links, images and wiki links to plain labels. Public HTTP, HTTPS and mailto text links remain. HTML links and bare paths stay as written. Unknown, inactive, self and blocking recipients return the same response.

The recipient can accept or decline a pending share. The sender can revoke it before a decision. A reviewer approves or rejects shares sent to the global brain. Acceptance creates a file marked `shared` or a proposed skill with fresh counts. Both show the sender. Decline, revoke and rejection clear the snapshot text. Blocking also declines pending shares from that sender. Accepted copies stay after account purge.

`/admin/brain-settings` exposes live `sharing` limits for snapshot characters, pending sends per account, inbox size and review queue size. Agents read global results alongside personal results. Global results are labelled and read-only, and global skills have no markable ID. Agents have no sharing or import tool.

The personal and global BM25 scores come from separate corpora. Personal files come first on ties. Pending inboxes respect the configured limits. Sent history displays up to 200 rows. A crash after creating an accepted copy and before saving the decision can leave a pending share with an imported copy.

## Tool services

Stronghold calls Bard for speech, Scribe for dictation and audio attachments, and Reader for document attachments. Configure these three services in **Stronghold Admin → Tool services**. Stronghold stores one record per service in its `settings.db` table `tool_services`. A record holds `enabled`, a Treasury `service_id`, an ordered list of `{origin_id, header_value?}` references, and a parent `token`. Treasury stores the addresses and lists Stronghold in `used_by`. Admin responses expose token-presence flags. Each request sends `X-Internal-Token` only to its selected origin, using that origin's override when present.

REST calls try the next origin on a connection refusal or connect timeout. A transport failure after a connection may have been made fails the call and puts that origin on a 30-second cooldown. An HTTP reply ends the attempt. File requests use the origin recorded when Stronghold received the file ID. The newest 2,000 mappings live in memory and include the account and service. A missing mapping returns 404, including pre-cutover clips, clips generated through MCP, and mappings lost to eviction or restart. Legion selects its MCP origin separately. If the backing stores are separate, an MCP tool can miss an attachment that Stronghold uploaded to a backup. If a Scribe connection cannot open, a new dictation stream can use the backup. The current stream is never replayed.

A PDF with no readable text is sent to Reader at upload (110 seconds for upload and parse). The reply's `read` field is
`reader` with the text, or `pages` when Reader is not configured or cannot read it; the model is then shown the pages.
`/attachments/document` does the same when the user asks, and replies `{filename, text, char_count, truncated, read}`.
Stored audio is sent to Scribe the same way: `read` is `scribe` with the transcript, or `listen` when Legion has to
transcribe it. `/attachments/audio` remains for older clients.

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

The Brain replaces the private-notes and assistant-memory user routes. Existing notes stay in Treasury's `notes` collection. The legacy note store is retired. Armory no longer has notes, memory or skills tools (Plan 22); its old `memory.db` and `skills.db` stay on disk, unused.

`src/agents/` is a copy of Portcullis's agent client. Change both until chats move here.

`TREASURY_URL` overrides the `treasury_url` bootstrap address in `configs/config_app.json`. Internal peers resolve through Treasury’s catalog at request time.

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

Treasury failures in storage-backed MCP calls return numbered messages. Usage and permission checks still fail closed.
