# portcullis

> **Chats (Plan 5.9).** Stronghold keeps chat history, folders and search (`apps/stronghold/src/chats`). Since Plan 10 Stronghold also runs the answers (the turn engine); Portcullis only passes the turn routes on. Every chat route needs Stronghold running (502 otherwise), and chats made before the move are not copied. The old `chats` and `chat_folders` SQL tables stay here, unused.

## Speech HTTP routes

| Route | Permission | Behavior |
| --- | --- | --- |
| `POST /api/attachments/document` | `files.upload` | Passed to Stronghold (Plan 5.7), which does the work and keeps the contract below. `DocumentIn` base64 JSON, pdf/png/jpg/jpeg/webp, 20 MB cap; asks Reader for its text and returns `{filename, text, char_count, truncated, read}`; `read` is `pages`, with empty text, when Reader cannot read it. 150 second timeout. Logs `attachments.document`. |
| `POST /api/attachments/dictate` | `files.upload` | `AudioIn` base64 JSON, supported audio suffix, 20 MB cap; returns `{text, duration_s}` from Scribe. Logs `attachments.dictate` without transcript text. |
| `POST /api/attachments/dictate/partial` | `files.upload` | Same audio validation; transient cumulative preview through Scribe `/api/transcribe-partial`, returning `{text, duration_s}` without retaining audio or logging transcript text. |
| `WS /api/attachments/dictate/stream` | session cookie + `files.upload` | Same-origin binary mono 16 kHz PCM16 and JSON `{"type":"stop"}`; returns `{type:"partial"|"final", text}` events. Scribe capacity closes with 1013 so the browser can use HTTP previews. |
| `POST /api/bard/speak` | `tools.execute` + `files.download` | JSON `{text, voice?}`; returns `{file_id, duration_s, voice}`. Logs `bard.speak` without spoken text. |
| `GET /api/bard/voices` | `tools.execute` + `files.download` | Returns `{voices: string[]}` for installed voices only. |
| `GET /api/bard/audio/{id}` | `tools.execute` + `files.download` | Streams owned Bard audio from Stronghold and forwards Range. |
| `GET /api/connection-status` | signed-in account | Returns readiness and a safe configuration reason for Bard, Scribe, and Reader. |

Portcullis checks login and permissions and forwards the JSON features to Stronghold. It opens Bard audio and live dictation against Stronghold with signed service and requester assertions. Stronghold holds the tool-service origin references and per-caller tokens. Attachment previews continue through Armory. Rejected audio or text returns 400, quota and size errors return 413, and unavailable services or refused credentials return 502.

Stronghold allows one live dictation stream per account, with at most
64,000 bytes per PCM frame, 150 seconds of audio, 15 seconds idle while recording,
120 seconds awaiting the final result and 270 seconds total connection lifetime.
Completed streams log `attachments.dictate` with the byte count, before delivering
the final transcript. Upstream error details, close reasons and credentials stay
private. Scribe applies its own shared stream capacity and account quota.

Reverse proxies must preserve the original `Host` and browser `Origin`, forward
WebSocket `Upgrade` and `Connection` headers, and allow at least 270 seconds for
the connection. The security middleware reads `X-Forwarded-Proto` only from a
`trusted_proxies` peer (as for HTTP) and applies the IP allow/deny lists to
WebSocket handshakes, so an HTTPS browser origin behind the proxy is accepted. Ember compares both origin scheme and authority; rewriting
the host or losing the HTTPS scheme causes the handshake to be refused. Keep the
Scribe address and token in Armory Admin. The browser connects to Portcullis.

## Triage strategy

Triage and ticket questions go to Legion's `triage-assistant` agent, which asks its own model list in order
(edited in Legion Admin). Their text can therefore reach any model on that list, cloud ones included; text the
secret check marks confidential goes only to trusted models. The retired database preference and migration `0026`
remain for schema/data history; the application no longer reads that preference.

## Conversation compaction

Manual `/compact` (the existing `POST /api/chats/{id}/summarize`) and automatic
compaction discover the dedicated `context-summarizer` agent. They use its
tool-free `interpret` operation with a `compact` prompt, independently of the
entry agent answering the chat. Legion uses the same helper with a shorter
`routing` prompt before Router decisions. The helper uses the existing light
model tier, and usage is attributed to `context-summarizer`.

Compaction still folds a prior summary into the new transcript, includes tool
digests in its prompt, preserves exact identifiers and paths, and retains the
cumulative original transcript as a log attachment. The transcript changes only
after a usable summary returns. Each compaction call has a 60-second timeout.
Missing/offline helper or failed summarization leaves manual compaction unchanged;
automatic compaction keeps the available history and continues answering. An
existing compacted summary is also available to subsequent routing briefs.


## Chat short-term memory

These routes require login and `chat.use`. Portcullis forwards them to Stronghold,
which checks that the signed requester owns the chat.

| Route | Purpose |
|---|---|
| `GET /api/chats/{id}/stack` | Read stack items and capacity |
| `POST /api/chats/{id}/stack/items` | Add `{"text": "...", "pinned": false}` |
| `PUT /api/chats/{id}/stack/items/{item_id}` | Set `{"pinned": true}` or unpin with `false` |
| `DELETE /api/chats/{id}/stack/items/{item_id}` | Remove an item |
| `POST /api/chats/{id}/stack/compact` | Compact unpinned items |

Send `Content-Type: application/json` on POST requests, including compaction.

## Long-term memory (Brain)

Accounts with `chat.use` can list and create files at `/api/brain/files`, read, update and delete an individual file at `/api/brain/files/{id}`, and revert an edit with `POST /api/brain/files/{id}/revert`. `GET /api/brain/search` accepts `q` and optional `limit`. `GET /api/brain/summary` shows disk usage and limits.

Staff with `settings.manage` can read and update limits at `/api/admin/stronghold-brain-settings`. On account deletion, Portcullis asks Stronghold to purge the account’s long-term memory and logs any unconfirmed purge.

## Internal Router metadata and access

`GET /api/agents` adds derived `internal_role` status metadata (not an agent-file field)
and a sanitized `decision` summary
for Router; ordinary agent response fields remain compatible. Running definitions
and disabled/offline definitions retain the internal role. Discovery of the Laya
triage agent explicitly excludes internal roles. Router configuration passes
through existing `/api/admin/agents` routes and `agents.manage` checks.

The browser agent MCP proxy continues allowing only `status`; internal `route`,
`ask` and `interpret` calls are refused. Routing backend/model usage uses existing
usage accounting and permissions. Chat traces retain up to 64 attempt diagnostics
without increasing the established 20-row chat-message breakdown limit; prompt
text and credentials are excluded from routing metadata.


## Native capability workspace API

Media groups use fixed `/api/media-downloader/packages` GET/POST routes, GET
`/packages/{id}`, POST `/packages/{id}/items` (`{url,preset}`), DELETE
`/packages/{id}/items/{item_id}` and POST `/packages/{id}/start`. The same
`tools.execute` and added `video` capability checks apply. Armory owns groups,
validates URLs and permanently locks membership when queue admission succeeds.
Nested ZIP links are rewritten to authenticated same-origin file downloads.
Restart Armory and portcullis after deployment; no database migration is needed.

PDF/video workspaces proxy only fixed Armory routes (`/pdf/ui`, `/media/ui`,
and the existing `/upload/pdf`). Armory must be restarted after installing
the HTTP adapters, with service identity and public trust mounts configured and `pdf` / `video`
online. The authenticated account must add the native capability from the
Supermarket. Legacy standalone extension subscriptions do not grant native access.
Every route requires `tools.execute`; file uploads additionally require
`files.upload`, and preview/download routes additionally require `files.download`.
No new permissions or role grants are introduced.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/pdf-merger/files` | List this account's unexpired source/output files. |
| POST | `/api/pdf-merger/files` | JSON `{filename, data}` (base64), 15 MiB per file; return original file metadata. |
| DELETE | `/api/pdf-merger/files/{id}` | Delete an owned file (204). |
| GET | `/api/pdf-merger/files/{id}/content` | Owned source bytes for PDF/image thumbnails; no-store, sandboxed. |
| POST | `/api/pdf-merger/merge` | Ordered `{segments, output}` plan; return `{job_id}` immediately. Ranges and individual page ordering are expressed by segments. |
| GET | `/api/pdf-merger/jobs/{id}` | `{job_id,state,done,total,result,error}`; queued/progress/done/error. |
| POST | `/api/pdf-merger/jobs/{id}/cancel` | Cooperatively cancel an owned merge. |
| GET | `/api/pdf-merger/files/{id}/download` | Check ownership, then stream a fresh signed Armory download. |
| POST | `/api/media-downloader/probe` | `{url}` through Armory UrlPolicy; metadata and presets. |
| POST | `/api/media-downloader/downloads` | `{url,preset}`; return `{job_id}` immediately. |
| GET | `/api/media-downloader/jobs/{id}` | Owned JobStatus with progress, file or structured error. |
| POST | `/api/media-downloader/jobs/{id}/cancel` | Cooperatively cancel an owned download. |
| GET | `/api/media-downloader/files` | Owned unexpired media files. |
| DELETE | `/api/media-downloader/files/{id}` | Delete an owned media file (204). |
| GET | `/api/media-downloader/files/{id}/download` | Check ownership, then stream a fresh signed Armory download (Range supported). |

Identity always comes from the session's stable UID, never browser headers or
request bodies. Armory enforces file/job ownership, quotas, expiry, merge limits,
and video URL/extractor policy. Errors retain readable messages and stable codes;
missing and other-account objects have the same unavailable response.
Download origins are fixed server-side; redirects and malformed upstream links
are refused. Upstream signatures/origins are rewritten to local authenticated
links. Preview/download responses are not cached. Mutations audit IDs only.
Default file TTL is six hours; expired files must be uploaded/downloaded again.
Jobs remain owned by Armory after browser polling stops and do not survive its
process restart. Cancellation is cooperative and may finish after the response.

## Usage cost estimates

Prices live only in Stronghold (Stronghold Admin > Usage settings); Portcullis reads them from `GET /usage/pricing` for the cost on chat messages and the Usage page. Fill it with your model names and separate
`input` / `output` prices in **USD per 1,000,000 tokens** (`currency: "USD"`).
The shipped
`example-model` entry is a placeholder. Fill in real names and prices yourself,
then restart Stronghold. Unknown models and calls missing both token counts show
no cost; a single missing side counts as zero when the other is known.

Chat GET, branch, summarize/clear responses and live `final` events include
optional `cost` on messages and each `agent_usage` row. `GET /api/usage` returns
`report.total_cost`, `currency`, `unpriced_tokens` and nullable group/agent costs;
`GET /api/usage/records` includes nullable per-call `cost`. The corresponding
admin detail endpoints receive the same fields. Aggregate costs sum priced
calls, with null when none can be priced. All-account totals remain tokens-only.
Costs are computed on read without storing them or migrating the database, so
new prices also apply to old answers. Ember Web shows costs in answer chips,
usage details, the Usage page and its Markdown export, with a note for partial
totals. Public share links still expose only plain questions and answers.

## Ticket read receipts

The ticket and triage routes are answered by Stronghold (`apps/stronghold/src/tickets`, `src/triage`); portcullis checks the login and the permission and passes the request on (`502` when Stronghold is down). Stronghold keeps the read receipts in Treasury; the old `ticket_staff_activity` and `account_ticket_seen` tables stay in this database, unused. Deleting an account purges its receipts through Stronghold (best effort, `admin.tickets_purge`).

Reporter routes require `tickets.create` and return only reporter-safe fields.
`GET /api/tickets` includes `has_unread` per ticket;
`GET /api/tickets/unread-count` returns `{count}` for the navigation badge.
`GET /api/tickets/{id}` checks upstream ownership before marking the ticket seen.
Staff activity is recorded atomically by mcp_server and read from it on every list and detail,
including changes made outside Ember. Reporter lists include all owned tickets
so old tickets contribute to unread counts. Migration `0018` once added cached staff
activity timestamps and per-account ticket read receipts; Stronghold replaced both.

`POST /api/tickets/{id}/reopen` requires `tickets.create` and upstream ownership.
Only resolved or closed tickets may reopen. The core sets status to open, clears
`closed_at` and adds a system comment in one transaction; other statuses return
400, and foreign or unknown tickets return 404. The action is logged by id only.


## Skills page API

Skills are how-tos the assistant proposed after solving a task (armory's `skills`
capability). Only an `active` skill is ever returned to the assistant, and these routes
are the only way to activate one: no agent tool can. They require a verified account
with `chat.use`; the owner is always the authenticated account's internal uid.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/skills` | All the account's skills, newest first; `[{id, title, when_to_use, steps, tools, status, successes, failures, created_at, failing}]`. `status` is `proposed`, `active` or `retired`; `failing` is true once the skill failed 3 or more times and more often than it worked, and the assistant is no longer offered it. |
| PUT | `/api/skills/{id}` | `{title, when_to_use, steps, tools}` rewrites the text (80/300/1200/200 characters; tools optional). The status stays and the worked and failed counts reset. 409 with the reason for a duplicate title, 404 when missing. |
| PUT | `/api/skills/{id}/status` | `{status}` approves (`active`), rejects or retires (`retired`) or sends back for review (`proposed`); 409 at the 50-active-skills cap, 404 when missing. |
| DELETE | `/api/skills/{id}` | Deletes an owned skill (204); 404 when missing. |

portcullis checks the login and `chat.use`, then passes each request to Stronghold
(`/skills/...`), which calls Armory's token-protected `/skills/owners/{uid}/skills`
routes. Stronghold down returns 502 `Stronghold is unavailable`, Armory down returns
503, a disabled capability returns 404, and redirects are refused. Changes are logged
by action only, never skill text. Deleting an account purges its skills through
Stronghold (`DELETE /skills/accounts/{uid}`, best effort, logged as
`admin.skills_purge` when it fails).

Backend for [ember_web](../ember_web). It owns ember_web's user accounts and
login sessions (its own database, separate from chat_app's) and will proxy
all of ember_web's MCP traffic to `ai_agent` and `mcp_server`, so the
browser never talks to those servers or holds their credentials.

Built with FastAPI + async SQLAlchemy (SQLite via aiosqlite). The auth logic
mirrors chat_app's `services/auth_service.py`: same werkzeug password
hashes, same bootstrap-admin rules, same role/permission tables.

Chat turn streams relay bounded `plan_update` checklist snapshots by agent.
Reconnect snapshots include the latest plans for that turn; plans are not
stored in the chat transcript.

Delegated answers retain bounded `context_breakdown` parts and
`context_breakdown_exact` on each `agent_usage` row, including chat resaves
and imports. Each row also keeps its own `context_tokens` and `context_window`.
The answer's top-level context fields describe the answering agent's window; they
are absent when the router sent the question straight to a specialist, and Ember
then shows the fullest agent row's window. Such answers, and any with several
agents, carry `turn_tokens`: what every agent of the answer used together.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Accounts, bootstrap admin, login/logout/me, sessions | done |
| 2 | Registration with invite codes, email verification (MCP Email capability) | done |
| 3 | MCP proxy to ai_agent / mcp_server with permission checks | done |
| 4 | ember_web switches to portcullis (login pages, `/api` via Vite proxy) | done |
| 5 | Cleanup: drop the old direct CORS on ai_agent / mcp_server | done |

## Requirements

- Python 3.11+ (developed on 3.14)

## Setup and running

The server listens on `EMBER_API_PORT` (default `29601`).

In Docker: `dev_deploy.bat` in this folder rebuilds and restarts the `portcullis` container from the root `docker-compose.yml` (see [docs/deployment.md](../../../docs/deployment.md)).

Manually:

```bash
uv sync
uv run python -m src.run
```

On first start a missing `.env` is built from an old
`secrets/secret_*.env` set if there is one, else from `.env.example`,
`.data/portcullis/ember_api.db` is created, and the bootstrap admin account is made. If
`BOOTSTRAP_ADMIN_PASSWORD` is empty, a random password is printed to the
console once - save it.

Tests:

```bash
uv run pytest
```

## Tool services

Portcullis sends Bard speech and voices, Scribe dictation and audio attachments, and Reader document attachments to Stronghold. It streams browser audio from Stronghold's `/speech/audio/{file_id}` and relays live dictation to `/speech/dictate`. The browser URLs and permission checks stay the same. PDF and table uploads and owned attachment previews retain their Armory routes.

`GET /api/connection-status` returns configuration readiness from Stronghold. `GET /api/config-issues` lists unavailable configurations under **Stronghold Tool services**.

Each admin route requires `tool_services.manage` and forwards to the same path on Stronghold without the `/api` prefix.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/admin/tool-services` | List the three connections and their status |
| `POST` | `/api/admin/tool-services/lookup` | Look up a typed address in Treasury |
| `PUT` | `/api/admin/tool-services/{name}` | Save addresses, availability, and write-only tokens |
| `DELETE` | `/api/admin/tool-services/{name}` | Remove a connection from Stronghold |
| `POST` | `/api/admin/tool-services/{name}/test` | Test each saved origin |

Armory no longer proxies outside MCP servers (Plan 22c): add one as a Legion connection.

## API

Every `POST` must send `Content-Type: application/json` (anything else gets
`415`) - with the `SameSite=Strict` cookie this blocks cross-site request
forgery. (Other methods need a CORS preflight cross-site, which portcullis
never grants; the MCP client's session `DELETE` has no body at all.)

| Method | Path | Auth | Returns |
|---|---|---|---|
| `POST` | `/api/auth/login` | - | `{username, password}` -> the account; sets the session cookie. `401` with one generic message on any failure; `429` + `Retry-After` after too many failures (`security.rate_limit`). |
| `POST` | `/api/auth/logout` | cookie | `204`; deletes the session server-side and clears the cookie. |
| `GET` | `/api/auth/me` | cookie | `{id, username, email, email_verified, prompt_suggestions, roles, permissions}` or `401`. |
| `POST` | `/api/auth/register` | - | `{username, email, password, invite_code}` -> `201 {account}`; signs in the verified account. `400` bad/expired/used invite, `409` email mismatch or taken username/email, `422` invalid fields. |
| `POST` | `/api/auth/verify-email` | cookie | `{code}` -> the account, now verified. `400` wrong/expired code. |
| `POST` | `/api/auth/verify-email/resend` | cookie | `{sent: true}`; `503` if SMTP failed, `409` if already verified. |
| `POST` | `/api/account/email` | cookie | `{current_password, email}` -> `{account, verification_email_sent, email_error}`. The new email is unverified (permissions off) until its emailed code is entered. `400` wrong password, `409` email taken or bootstrap admin. |
| `POST` | `/api/account/password` | cookie | `{current_password, new_password}` (8+ chars) -> the account. Logs out every other session. `400` wrong password, `409` bootstrap admin (change it in `.env`). |
| `PATCH` | `/api/account/preferences` | logged in | `{prompt_suggestions: bool}`: whether chat suggests the next prompt. Returns the account. |
| `GET` | `/api/account/devices` | cookie | Devices this account logged in from, most recent first: `[{id, label, user_agent, ip_subnet, first_seen_at, last_seen_at, current}]`. |
| `DELETE` | `/api/account/devices/{id}` | cookie | `204`; its next login counts as a new device again. `404` unknown or another account's. |
| `POST` | `/api/admin/invites` | `invites.manage` | `{invitee_email}` -> `201 {id, invitee_email, delivery_method, created_at, expires_at}`. The code is delivered by email. `503` if email is unavailable or delivery fails. |
| `GET`, `PUT` | `/api/armory-tool-approval` | `settings.manage` | Armory's switch for requiring approval before every tool run: `GET` -> `{force_tool_approval}`, `PUT {value: true\|false}` -> `{force_tool_approval}` (`422` for a non-boolean, `502` if Armory cannot answer). Armory stores it; the change is logged as `admin.setting` with the old and new value. |
| `GET` | `/api/settings` | any logged-in account | `{force_tool_approval}`: what the administrator requires of everyone, read from Armory. If Armory does not answer it says `true`. A switch left in `app_settings` from before Armory owned it is sent to Armory once, then dropped. |
| `GET` | `/api/settings/pages` | any logged-in account | `{hidden: ["/usage", ...]}`: pages the administrator hid from every sidebar. |
| `PUT` | `/api/admin/settings/pages` | `settings.manage` | `{hidden: [...]}` -> `{hidden: [...]}`. Hides pages from every account's sidebar (nav only: they still open by URL). Ids look like `/usage`, at most 20, repeats dropped; `/` and `/settings` cannot be hidden. `400` for a bad id or a list too long to store, `422` for a bad body. Logged as `admin.setting`. |
| `POST` | `/api/admin/servers/lookup` | `agents.manage` | Sends `{address}` to Legion for a read-only Treasury catalog lookup. |
| `GET` | `/api/admin/servers` | `agents.manage` | Lists connections and resolved origins. `has_value` and `has_override` indicate saved tokens. |
| `GET` | `/api/admin/treasury/outside` | `settings.manage` | Outside service groups, their origins, and `used_by`. |
| `PATCH` | `/api/admin/treasury/outside/{service_id}` | `settings.manage` | `{name}` renames a group and returns it with the same ID. |
| `DELETE` | `/api/admin/treasury/outside/origins/{origin_id}` | `settings.manage` | Removes one origin and returns the catalog. An origin in use requires `?confirm=true`. |
| `DELETE` | `/api/admin/treasury/outside/{service_id}` | `settings.manage` | Removes a group and its origins and returns the catalog. A group in use requires `?confirm=true`. |
| `GET` | `/api/admin/invites/email-status` | `invites.manage` | `{ready, reason}` from the Armory SMTP readiness check. `reason` is null when ready. |
| `GET` | `/api/admin/invites` | `invites.manage` | Open (unused, unexpired) invites, without codes. |
| `DELETE` | `/api/admin/invites/{id}` | `invites.manage` | `204`; the code stops working. `409` if already used. |
| `GET` | `/api/admin/summary` | `any administrative permission; unrelated counts are null` | `{accounts, unverified, disabled, open_invites, roles}`: counts for the Admin overview tiles. |
| `GET` | `/api/admin/accounts` | `accounts.view (also accounts.manage/accounts.delete/roles.assign)` | `[{id, username, email, email_verified, is_active, is_protected, created_at, roles: [{id, name}]}]`. Optional `?q=` (username/email substring, case-insensitive) and `?status=all\|unverified\|disabled`; `422` for any other status. |
| `PATCH` | `/api/admin/accounts/{id}` | `accounts.manage` | Any of `{username, email, is_active}` -> the account. Disabling ends its sessions. `409` taken name/email, protected account, or disabling yourself. |
| `DELETE` | `/api/admin/accounts/{id}` | `accounts.delete` | `204`. `409` for the protected account or yourself. |
| `PUT` `DELETE` | `/api/admin/accounts/{id}/roles/{role_id}` | `roles.assign` | Assign / remove a role -> the account. `409` removing from the protected account, or removing your own last role management/assignment access. |
| `POST` | `/api/admin/accounts/{id}/send-verification` | `accounts.manage` | `{sent: true}`; `409` already verified, `503` SMTP failed. |
| `GET` | `/api/admin/roles` | `roles.view (also roles.manage/roles.assign)` | `[{id, name, description, is_protected, permissions, account_count}]` |
| `POST` | `/api/admin/roles` | `roles.manage` | `{name, description?}` -> `201` role. `409` name taken (case-insensitive). |
| `PATCH` | `/api/admin/roles/{id}` | `roles.manage` | Any of `{name, description, permissions}` (`""` clears the description) -> the role. `permissions` replaces the full permission set; omitted leaves it unchanged. Details and permissions save atomically. Administrator can't be renamed or lose permissions; delegated authority and own admin access remain enforced. |
| `DELETE` | `/api/admin/roles/{id}` | `roles.manage` | `204`. `409` for Administrator, or if it's your only source of role management/assignment access. |
| `PUT` `DELETE` | `/api/admin/roles/{id}/permissions/{name}` | `roles.manage` | Grant / revoke -> the role. `404` unknown permission; `409` changing Administrator or revoking your own last role management/assignment access. |
| `GET` | `/api/admin/permissions` | `roles.view (also roles.manage/roles.assign)` | `[{name, description}]` - defined in code (`services/permissions.py`), not editable. |
| `POST` | `/api/tickets` | `tickets.create` | `{type: "bug"\|"feature"\|"other", title, description}` -> `201 {ticket, duplicate, group_size}` (`200` for a duplicate). No reporter, tags, source or staff fields accepted. |
| `GET` | `/api/tickets` | `tickets.create` | `{tickets: [...]}` for the signed-in reporter; optional `?status=open\|in_progress\|resolved\|closed`. |
| `GET` | `/api/tickets/{id}` | `tickets.create` | `{ticket}` with comments; `404` for a missing or another reporter's ticket. |
| `POST` | `/api/tickets/{id}/comments` | `tickets.create` | `{body}` -> `{ticket}`; adds a reporter comment. |
| `POST` | `/api/tickets/{id}/close` | `tickets.create` | Send JSON `{}` -> `{ticket}`; closes an own ticket. |
| `GET` | `/api/admin/tickets` | `tickets.manage` | `{tickets: [...]}`; filters `status`, `type`, `tag`, `priority` (effective priority), `assignee`, `group_id`, `possible` (boolean), `limit` (1-500, default 100). |
| `GET` | `/api/admin/tickets/stats` | `tickets.manage` | `{open, urgent, groups}`: open tickets, urgent tickets and open groups. |
| `GET` | `/api/admin/tickets/{id}` | `tickets.manage` | `{ticket}` with comments for any reporter. |
| `PATCH` | `/api/admin/tickets/{id}` | `tickets.manage` | Any of `{status, priority, assignee, tags}` -> `{ticket}`; empty assignee clears it, at most five tags. Logged as `tickets.update`. |
| `POST` | `/api/admin/tickets/{id}/comments` | `tickets.manage` | `{body}` -> `{ticket}`; staff comment, logged as `tickets.comment`. |
| `POST` | `/api/admin/tickets/{id}/move` | `tickets.manage` | `{group_id}` -> `{ticket}`; positive id joins a group, `null` splits into a new one. Logged as `tickets.move`. |
| `GET` | `/api/admin/ticket-groups` | `tickets.manage` | `{groups: [...]}`; filters `status`, `tag`, `priority` (group priority), `limit` (1-500, default 100). |
| `PATCH` | `/api/admin/ticket-groups/{id}` | `tickets.manage` | `{priority?, pinned?}` -> `{group}`; setting priority pins it unless `pinned: false`; unpinning returns to automatic elevation. Logged as `tickets.group_priority`. |
| `GET` | `/api/chats` | `chat.use` | This account's chats, newest first: `[{id, title, agent_id, message_count, folder_id, pinned, created_at, updated_at}]` (no messages; `folder_id` is null for a chat in no folder). |
| `GET` | `/api/chats/search?q=` | `chat.use` | `q` 2-100 characters. Chats whose title or message text contains `q` (case-insensitive, literal; attached files' text is not searched), newest first, at most 50: `[{id, title, folder_id, updated_at, title_match: {start, length}\|null, snippet: {text, start, length}\|null, message_index, message_matches}]`. The snippet is one line around the first matching message. |
| `GET` | `/api/chats/{id}` | `chat.use` | One chat with `messages`. `404` if missing or another account's. |
| `PUT` | `/api/chats/{id}` | `chat.use` | `{title, agent_id, messages: [{role, content}]}` creates or replaces the chat. `413` over 2 MB or 1000 chats. |
| `PATCH` | `/api/chats/{id}` | `chat.use` | `{title?, folder_id?, pinned?}` (at least one) -> the chat row. `folder_id: null` takes the chat out of its folder. `404` unknown chat or a folder that is not this account's. Allowed while an answer is being written; filing and pinning do not change `updated_at`. |
| `DELETE` | `/api/chats/{id}`, `/api/chats` | `chat.use` | `204`; one chat, or all of this account's. |
| `POST` | `/api/chats/{id}/turns` | `chat.use` | `{question, agent_id?, caveman?, title?, truncate_to?, ask_before_tools?, allowed_tools?, allow_read_only?, can_ask?, plan?, plan_lean?}` -> `202 {chat, sequence}`. Extensions and tools are not chosen per request: portcullis turns on every extension mcp_server lists, and each agent's `tools.allow` decides what it may call. The agents the account switched off (`/api/account-agents`) are sent to the agent as `agent:<id>` filter entries; the turn fails with an error if the agent is too old to leave them out. `truncate_to` (regenerate / edit): index of the typed question this one replaces; it and everything after it are dropped first (`422` unless that message is a question the user typed, `404` for an unknown chat). `ask_before_tools`: the agent asks before each tool runs, except `allowed_tools` (names, at most 200; the tools the user allowed for this chat); see `/approvals` below. `can_ask: true` lets the agent ask clickable questions; clients that cannot show them, such as `chat_cli`, leave it out. Older agents that do not report `user_questions: true` simply never get the question tool. `plan` and `plan_lean` (both default `true`) are the chat's task-checklist toggles: `plan: false` withholds the `update_plan` tool for the turn, `plan_lean: false` drops the "update only when an item changes status" instruction; an agent that does not report `plan_toggle: true` ignores them. `agent_id` is accepted but ignored: every turn goes to the entry agent (`GET /api/agent`). Saves the question (creating the chat) and starts the answer **in portcullis**: it finishes, is saved and counts toward the usage limits even if the browser leaves. `503` no entry agent is registered, `409` already answering, `429` usage limit or 3 answers already running. |
| `GET` | `/api/chats/{id}/events?after=N` | `chat.use` | Server-Sent Events of the chat's running (or just finished) answer: a `snapshot` of the text and tool steps so far when joining late, then `token` / `step_*` / `summarizing` / `question_request` / `question_resolved` events and, when the entry agent delegates, `agent_start` / `agent_end` (a specialist begins or finishes; keys `agent_id`, `agent_label`, `delegated_by`, `question` cut to 500 characters, `step_id`, `ok`, `at`) and `agent_token` (the specialist's streamed `text`, chunks cut to 4,000 characters; never saved with the answer). The `snapshot` carries pending `questions: [{id, questions}]` so a reload restores them; `question_request` carries `{id, questions}` and `question_resolved` carries `{id, outcome}` (answered, skipped, timeout or cancelled). ai_agent-only `keepalive` events are dropped. It also carries `active_agents: [{agent_id, label, since, step_id}]`, the delegated agents working now, outermost first (the entry agent itself is not listed; the browser adds it); it is cleared when the turn ends. Its `steps` carry their `id` (live viewers only; the id is not saved) and `agent_id` / `agent_label`. Then last `final` `{message, cancelled}` or `error`. `404` when there's nothing to watch. The saved answer carries `model`, `total_tokens`, `input_tokens`, `output_tokens`, `duration_s` (the whole turn, seconds), `context_tokens` / `context_window` when ai_agent reported them, and `steps: [{tool, label, arguments, ok, result, agent_id?, agent_label?}]` (`agent_id` / `agent_label` only on steps a delegated agent ran; results cut to 4,000 characters, at most 50 steps), and, when the answer ran more than one agent (its own plus delegated ones), `agent_usage: [{agent, agent_label?, provider_id?, gateway?, model?, input_tokens?, output_tokens?, total_tokens, started_at?, finished_at?}]` (times ISO-8601 UTC with `Z`) (at most 20; an answer from one agent has none). Every answer also carries `agent`, the id of the ember agent that wrote it (older answers lack it). |
| `POST` | `/api/chats/{id}/approvals` | `chat.use` | `{step_id, decision: allow \| always \| deny}` answers a tool the running answer waits to run (the `id` of an `approval_request` event) -> `{decided: true}`. `404` no answer running, `409` nothing waiting for that step (unknown or already answered), `502` agent unreachable. Only the chat's own account can; logged as `tool.approval`. |
| `POST` | `/api/chats/{id}/questions` | `chat.use` | Answers or skips the clickable questions the running answer waits on (`question_request` event): `{step_id, skipped?, answers?: [{selected, other}]}` -> `{answered: true}`. `404` no answer running, `409` nothing waiting, `422` invalid answer, `502` agent unreachable. |
| `POST` | `/api/chats/{id}/cancel` | `chat.use` | `{cancelled}`; ai_agent stops at its next round, keeping what streamed. |
| `POST` | `/api/chats/{id}/summarize` | `chat.use` | `{agent_id?}` (accepted but ignored; the entry agent summarizes) -> the chat, its history replaced by a `summary` message plus a `log_attachment` (raw messages, never sent to the agent again). `503` no entry agent is registered, `502` if the agent couldn't; nothing changes then. |
| `GET` | `/api/chats/{id}/suggestion` | `chat.use` | The message the user will probably type next, `{text}` (null for none). One small model call per answer, cached, counted in usage as kind `suggestion`; off when the account's `prompt_suggestions` is off. |
| `POST` | `/api/chats/{id}/clear` | `chat.use` | -> the chat, restarted: everything kept as one `log_attachment`. |
| `POST` | `/api/chats/{id}/branch` | `chat.use` | `{upto}` -> `201` a new chat (server-made id, title `Branch of <title>`, same agent) holding the messages up to and including message `upto`, which must be one of the assistant's answers (`422` for a question, summary, raw log or command result, or an index past the end). The original is untouched and may still be answering. `404` unknown chat, `413` at the chat limit. |
| `POST` | `/api/chats/{id}/messages` | `chat.use` | `{title, messages}` appends (slash-command calls and results), creating the chat if needed. |
| `GET` | `/api/chat-folders` | `chat.use` | `[{id, name, position, chat_count}]` in display order. |
| `POST` | `/api/chat-folders` | `chat.use` | `{name}` (1 to 60 characters, trimmed) -> `201` folder. `409` duplicate name (ignoring case) or 30 folders already. Logged as `chat_folder.create`. |
| `PATCH` | `/api/chat-folders/{id}` | `chat.use` | `{name?, position?}` (at least one), or `{direction: "up"|"down"}` on its own. Direction moves one place and saves all affected positions in one transaction; moving past an end is a no-op. `404` unknown, `409` duplicate name. Logged as `chat_folder.rename` for renames and `chat_folder.move` for moves. |
| `DELETE` | `/api/chat-folders/{id}` | `chat.use` | Deletes the folder **and every chat in it**, with their share links. `404` unknown, `409` while a chat in it is writing an answer. Logged as `chat_folder.delete`. |
| `GET` | `/api/templates` | `chat.use` | This account's saved prompts, most recently edited first: `[{id, name, body, created_at, updated_at}]`; `id` is a 32-character hex string. Kept in db_gateway (`503` while it is down). |
| `POST` | `/api/templates` | `chat.use` | `{name, body}` -> `201` the template. Name up to 60 characters (trimmed), body up to 10,000, at most 100 per account. `409` for a name the account already has (ignoring case) or the limit, `422` for a blank or too-long field. |
| `PUT` | `/api/templates/{id}` | `chat.use` | `{name, body}` replaces one. `404` if missing or another account's, `409` name taken, `422` for an id that is not 32 hex characters. |
| `DELETE` | `/api/templates/{id}` | `chat.use` | `204`; `404` if missing or another account's. The template routes are answered by Stronghold (`apps/stronghold/src/templates`), which keeps them in its own database; `502` when Stronghold is down. Deleting an account purges them there (best effort, `admin.templates_purge` on failure). |
| `GET` | `/api/nav-preferences` | any logged-in account | How this account arranges its nav rail: `{order, pinned, hidden}`, lists of page ids (route paths such as `/agents`). All empty means the default arrangement. |
| `PUT` | `/api/nav-preferences` | any logged-in account | Replaces it with the same shape. At most 50 ids per list, each 1-64 characters (`422` otherwise). Repeats are dropped; `pinned` and `hidden` keep only ids in `order`, and a hidden page is never pinned. portcullis does not know the page list, so unknown ids are kept. Returns what was stored. |
| `DELETE` | `/api/nav-preferences` | any logged-in account | Back to the default arrangement. `204`, also when nothing was saved. | Nav preferences and the account's switched-off agents are kept in db_gateway (one document per account, keyed by uid). While it is down, `GET` answers the default arrangement and saving gives `503`; account agents answer `503` for every call (an empty list would switch every agent back on). Migration `0023` drops the old tables, and refuses to run while any still holds rows: copy them to the gateway or empty them first. |
| `POST` | `/api/triage/titles` | `chat.use` | `{descriptions}` (2-10 strings, 1-300 characters each): a one-word lowercase title for each, in order, written by the `title-writer` agent (one plain model call that sees only the descriptions). An unusable reply falls back to `option1`, `option2`...; a repeat gets a number. `503` when `title-writer` is not running or does not answer, `429` at the usage limit. Counted in usage as kind `triage_titles`; logged as the action `triage.titles` (the count of options only) and, on a `503`, as an error. |
| `POST` | `/api/triage/ask` | `chat.use` | `{kind: "choice"\|"yes_no", text, question, options?, trace?}`: asks the Triage Assistant one typed question about `text` (1-4000 characters) directly, without the orchestrator. `choice` needs 2-10 `options` `{title, description}` (title: one word, unique ignoring case); `yes_no` takes none. Answer: `{kind: "yes_no", answer, yes, confidence, uncertain}` or `{kind: "choice", choice, probabilities, confidence, uncertain, also_check?, candidates?, unknown?, answered_by?, rounds?}` (`rounds` only with `trace: true`). `422` when the Triage Assistant refuses the question (for example the text is too long), `503` when the Triage Assistant is not running or gives no usable answer, `429` at the usage limit. Counted in usage as kind `triage`; logged as the action `triage.ask` (the kind, the number of options and the pick, never the text or the question) and, on a `503`, as an error. |
| `GET` | `/api/account-agents` | any logged-in account | The specialist agents this account switched off: `{disabled: [agent ids]}`. A new account has every agent on. `503` while db_gateway is down (an empty list would switch them all back on). |
| `PUT` | `/api/account-agents/{agent_id}` | any logged-in account | `{enabled: bool}` switches one agent on or off for this account's chats (`agent_id` 1-64 characters of `A-Za-z0-9_.-`, else `422`). Same reply as `GET`. Repeating a change is a no-op; at most 200 agents per account (`409`). Logged as `account.agent_enable` / `account.agent_disable`. The entry agent leaves a switched-off specialist out of its roster and refuses to delegate to it. |
| `GET` | `/api/user-extensions` | `chat.use` | This account's own MCP servers ("private extensions"): `[{id, label, description, url, header_names, enabled, status, error, tools}]`. `id` is a slug of the label, unique per account. `status` is `connected`, `error` or `unknown`, from `ai_agent`'s `probe_extension`, cached for 60 seconds; a disabled extension is not probed and reports `unknown`. Header **values** are never returned, only their names. |
| `POST` | `/api/user-extensions` | `chat.use` | `{label, url, description?, headers?}` -> `201` the extension, probed once. Saved even if it cannot be reached right now. `422` with a message for a bad address (http or https only, no username or password) or header (up to 20; name `A-Za-z0-9-`; value 1-2000 characters, no control characters; `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Upgrade`, `TE`, `Trailer`, `Proxy-Authorization` and `Cookie` are refused); `409` at 20 extensions. |
| `PATCH` | `/api/user-extensions/{id}` | `chat.use` | Any of `{label, description, url, headers, enabled}` -> the extension. `headers`, when present, replaces all of them (send it only when the user retyped them). A URL with a new host and no `headers` clears the saved headers, so a token is never sent to another host unasked. `404` for another account's id, `422` for an empty body. |
| `DELETE` | `/api/user-extensions/{id}` | `chat.use` | `204`; `404` for another account's id. |
| `POST` | `/api/chats/{id}/shares` | `chat.use + chat.share` | `{expires_in_days: 1 \| 7 \| 30 \| null}` (default 7; null: never) -> `201 {id, chat_id, title, message_count, created_at, expires_at, token}`. Freezes a sanitized copy of the chat behind a new link; **`token` is in this response only** (portcullis stores its SHA-256). `404` unknown chat, `409` at 50 active links, `422` bad expiry or nothing shareable. Logged as `share.create`. |
| `GET` | `/api/shares?chat_id=` | `chat.use` | This account's active links, newest first: `[{id, chat_id, title, message_count, created_at, expires_at}]`. Never a token. |
| `DELETE` | `/api/shares/{id}` | `chat.use` | `204`, the link stops working at once; `404` if missing or another account's. Logged as `share.revoke`. |
| `GET` | `/api/shared/{token}` | **none** | `{title, messages: [{role, content}], created_at, expires_at}` - the read-only snapshot. Unknown, malformed, revoked and expired tokens all get the same `404`. `429` past 60 requests a minute from one address. `Cache-Control: no-store`, `X-Robots-Tag: noindex`. |
| `GET` | `/shared/{token}` | **none** | The page a share link opens: the same frozen chat as read-only HTML (escaped text, no script, own CSP, `no-store`, `noindex`). `404` and `429` as above. |
| `POST` | `/api/shared-folders` | `folders.use` | `{name, minutes}` (1-60) opens a temporary folder: `{id, name, token, created_at, expires_at, files}`. `409` past 3 open folders. Never extended. |
| `GET` | `/api/shared-folders` | `folders.use` | The account's open folders with their files and tokens, newest first. |
| `DELETE` | `/api/shared-folders/{id}` | `folders.use` | Ends the folder now: link dead, files wiped. `204`; `404` for a folder that is not yours or has expired. |
| `DELETE` | `/api/shared-folders/{id}/files/{file_id}` | `folders.use` | Owner removes one file. Guests have no way to remove. |
| `GET` | `/api/folder-links/{token}` | **none** | `{name, expires_at, max_file_bytes, files}`. Unknown, malformed, deleted and expired links give the same `404`. `429` past 60 requests a minute from one address. `no-store`, `noindex`. |
| `GET` | `/api/folder-links/{token}/files/{file_id}` | **none** | The file as an attachment (`application/octet-stream`, `nosniff`). |
| `PUT` | `/api/folder-links/{token}/files?name=` | **none** | The body is the raw file, streamed to disk (no multipart). `413` over 100 MB; `409` when the folder (500 MB, 50 files) or the owner (1 GB) is full, or the file is empty. The Ember page is `/folder/{token}`. Files live in `<data>/shared_folders/<folder id>/`; a sweeper deletes expired folders every 30 s and at start. |
| `GET` | `/api/usage?days=30&since=YYYY-MM-DD&group_by=agent&agent=&provider=` | `chat.use` | `{six_hour, weekly: {used, limit, reset_at}, report: {days, since, total_tokens, input_tokens, output_tokens, summary_tokens, turns, chats, by_agent, group_by, groups: [{key, tokens, input_tokens, output_tokens, turns}], daily, hourly}}`. `group_by`: `agent` (default), `provider`, `gateway` or `model`; `groups` is the report grouped that way, biggest first (a missing value is `unknown`). `agent` and `provider` (optional) keep only that agent's / provider's rows. `hourly`: 24 token counts by UTC hour of day. `since` (optional, a UTC day) replaces `days` and starts the report at that day's midnight ("this month" is the 1st); `days` in the report is then the span covered. `422` for a future `since`, one older than 366 days, or a malformed one. |
| `GET` | `/api/usage/records?days=30&since=YYYY-MM-DD&agent=&provider=&limit=100` | `chat.use` | This account's usage rows in the period, newest first: `[{id, turn_id, kind, chat_id, agent, agent_id, provider_id, gateway, model, input_tokens, output_tokens, total_tokens, started_at, finished_at, delegated_by, created_at}]` (UTC times; same `days` / `since` rules and filters). `limit` 1-500, default 100. |
| `GET` | `/api/admin/usage?days=30&since=YYYY-MM-DD` | `usage.all.view` | Every account's tokens and answers in the period, including zero usage and disabled accounts (same `days` / `since` rules). |
| `GET` | `/api/admin/usage/{account_id}` | `usage.all.view` | Selected account limits and report; same period, grouping and filters as personal usage. |
| `GET` | `/api/admin/usage/{account_id}/records` | `usage.all.view` | Selected account recent calls; same period, filters and limit as personal records. |
| `GET` | `/api/commands` | `tools.use` | mcp_server's slash commands: `[{capability, name, description, tool_name}]`. |
| `GET` | `/api/commands/help`, `/api/commands/help/{capability}?target=&command=` | `tools.use` | mcp_server's capability help (what `/help` shows). |
| `GET` | `/api/commands/options?template=...&arg.<name>=...` | `tools.use` | A command-form select's options: `[{value, label, extra}]` from the mcp_server path `template`, which must be an `options_url` some tool's schema declares (its `{name}` placeholders filled from `arg.<name>`). `400` undeclared template or missing arg, `502` mcp_server down. |
| `POST` | `/api/uploads` | `files.upload` | `{filename, data}` (base64, up to 15 MB) -> `201 {path}`: stored by mcp_server's `/upload` (which picks the allowed file types) for a command's file-path parameter. `400` refused type. |
| `GET` | `/api/server/download?path=` | `tools.use` | A file a tool offered with a `[[DOWNLOAD ...]]` marker, streamed from mcp_server's `/download?path=` (identity and internal token added). Always sent as an attachment of type `application/octet-stream`, named by mcp_server's `Content-Disposition` filename (cleaned to a bare name) or else the last part of `path`, so a file never runs as a page on ember's origin. `path` is 1 to 1000 characters without control characters (`422`). `404` unknown file, `400` refused, `502` mcp_server unreachable or failing. mcp_server's `/download` takes an opaque id (see "Downloads" under Security). |
| `GET` | `/api/capabilities` | `tools.view (also capabilities.manage)` | mcp_server's built-in capabilities: `[{name, label, enabled, tools, resources, has_gui}]`. |
| `GET` | `/api/capabilities/{name}/gui` | `tools.view (also capabilities.manage)` | The capability's page layout (`{version, title, description, sections}`) as mcp_server validated it; `404` when it has no page. |
| `PATCH` | `/api/capabilities/{name}` | `capabilities.manage` | `{enabled}` turns a capability on/off for every mcp_server client. |
| `GET` | `/api/logs` | any `logs.*` | `{kinds, accounts}`: the log kinds this account may read and every account to filter by. |
| `GET` | `/api/logs/analytics?range=24h\|7d\|30d\|90d` | any `logs.*` | Counts for the Analytics page, only for the kinds this account may read (default `7d`): `{period, bucket (hour\|day), kinds, totals {kind: {current, previous}}, series [{bucket, counts}] (zero-filled), top_sources {kind: [{source, count}]}, accounts {kind: [{account_id, username, count}]}, heatmap [{weekday, hour, count}]}`. Top lists hold 10; `account_id` null is the server, `username` null a deleted account; heatmap is UTC, weekday 0 = Sunday. `422` bad range. |
| `GET` | `/api/logs/{kind}?actor=server\|<account id>` | `logs.view` (action), `logs.errors.view` (error), `logs.chat.view` (chat_trace) | The 200 newest entries: `[{id, kind, account_id, source, message, details, prompts, created_at}]`. A chat turn's `details` lists each agent that ran (`agents[]`); `prompts` (JSON, one `{messages, truncated}` per agent, same order, system prompts never stored) is `null` unless the account holds `logs.chat.prompts.view`. |
| `POST` | `/api/attachments/file` | `files.upload` | `{filename, data}` (base64, up to 15 MB, audio 20 MB) -> `{filename, file_id, kind, size, pages, expires_at, text, char_count, truncated, table, read}`. The one upload route for every file: Armory keeps the original and Stronghold sends back a text preview. `read` is `reader` or `pages` for a PDF with no text of its own, else null. A CSV or Excel file is also registered as a table. `file_id` is null when only the text could be attached. The routes below stay for older clients. |
| `POST` | `/api/attachments/text` | `files.upload` | `{filename, data}` (base64, up to 15 MB) -> `{filename, text, char_count, truncated}`: text from a text/code, `.pdf`, `.docx` or `.xlsx` file, at most 20,000 characters. The file isn't kept. `400` with a readable reason when it can't be read. |
| `POST` | `/api/attachments/pdf` | `files.upload` | `{filename, data}` (base64, up to 15 MB) -> `{filename, file_id, pages, kind, expires_at, text, char_count, truncated}`. Stores PDF/image originals via mcp_server in PDFMerger for the signed-in account. Text preview is optional, including for scanned PDFs. Requires the configured `pdf_merger` HTTP extension with requester forwarding and its internal token. |
| `GET` | `/api/attachments/files/{file_id}/content` | `files.download` | Streams owned chat attachment bytes for inline image previews, with no-store, nosniff and sandbox CSP. Uses Armory ownership checks without requiring a PDF workspace subscription. Expired or foreign files return 404. |
| `GET` | `/api/traffic/analytics?range=24h\|7d\|30d\|90d` | `traffic.view` | Network traffic for the Analytics Traffic tab (default `7d`): `{period, bucket (hour\|day), latency_cap_ms, totals {requests, error_rate, p95_ms, upstream_failures: {current, previous}}, series [{bucket, requests {2xx,3xx,4xx,5xx}, p50_ms, p95_ms}] (zero-filled), routes {busiest, slowest: [{name, count, error_rate, p95_ms}]}, upstream [{target, calls, failures, failure_rate, p95_ms, tools [{name, calls, failures, p95_ms}]}]}`. Counts come from `traffic_buckets` (written by `TrafficMiddleware` and the upstream timing, flushed every 30 s); names are route templates, never raw paths. Latency is kept as bands (50/100/250/500/1000/2500/5000 ms), so a percentile is its band's upper bound, and one in the slowest band shows as `latency_cap_ms` (meaning "at least"). `error_rate` is 5xx over all requests (`null` with no requests); `slowest` needs 5 requests per route; top lists hold 10. `422` bad range. |
| `GET` | `/api/config-issues` | `config.issues.view` | `[{file, key, message}]`: problems in `config_app.json`, the agent registry and the secret files. Never includes secret values. |
| `GET` | `/api/agent` | `chat.use` | The agent every question goes to, as `{id, label}` - no URL. `503` "No agent is running" when none is registered. |
| `GET` | `/api/agents` | `chat.use` | Every agent, for the Agents page: `[{id, label, entry, orchestrator, focus, status, provider, gateway, model}]` - no URL. `provider`, `gateway` and `model` come from the agent's `llm` block in the definitions and are `null` when not set. `status` is `running` (in ai_agent's registry), `offline` (defined in `agents/` but not running) or `disabled` (`enabled: false`); running first, the entry agent leading its group. Definitions come from `agent_definitions.json` beside the registry file, or `defined` in `GET /registry`; without them only running agents are listed. `[]` when none. |
| `GET` | `/api/admin/agents/gateways` | `agents.manage` | `{providers: {<provider>: [{id, label, model, tiers}]}}`: the providers and gateways from ai_agent's `gateways/<provider>/<gateway>.json` files (no keys), for the agent form's pickers. |
| `GET` `POST` | `/api/admin/agents` | `agents.manage` | `GET` -> `{agents: [{id, ...agent file}]}` (a broken file carries `error`). `POST {id, config}` creates `agents/<id>.json` -> `201`. `config` is the agent file (`label`, `port`, `url` (the address the agent registers under; empty = the host and port it listens on), `enabled`, `entry`, `llm`, `persona`, `instructions`, `focus`, `tools`, `orchestrator`); ai_agent validates it: `400` invalid or unknown gateway, `409` id or enabled port already used or a second entry agent. `502` when no agent is running or ai_agent does not answer (the call goes to the entry agent). Logged as `agents.create`. |
| `POST` | `/api/admin/agents/{id}/reset` | `agents.manage` | Drops this machine's edits (ai_agent's untracked `.data/agent_overrides.json` entry) so the tracked `agents/<id>.json` applies again -> the agent's file. `409` when it has no override or no tracked default. `GET /api/admin/agents` rows carry `overridden: true` when a reset is possible. Logged as `agents.reset`. |
| `PUT` `DELETE` | `/api/admin/agents/{id}` | `agents.manage` | `PUT {config}` replaces the agent in the untracked overrides file, never the tracked `agents/<id>.json` (`404` unknown, same `400`/`409` rules); `DELETE` removes it (`409` for the entry agent, `404` unknown) -> `204`. ai_agent's supervisor starts, restarts or stops the agent within a few seconds. Logged as `agents.update` / `agents.delete`. |
| `GET` `PUT` | `/api/admin/agent-prompts` | `agents.manage` | The prompt texts every agent shares (`app_name`, `app_description`, `identity_template`, `default_instructions`, `roster_intro`, `caveman_instructions`). `GET` -> `{values, defaults, overridden}`. `PUT {name: text \| null}` changes some; `null` or blank resets one to its default; `400` for an unknown name, a text over 8,000 characters or an `identity_template` with a placeholder other than `{app_name}`, `{app_description}`, `{role}`. ai_agent restarts every agent to apply it. Logged as `agents.prompts`. |
| `POST` | `/api/admin/agent-prompt-preview` | `agents.manage` | `{id, config, caveman?}` -> `{prompt}`: the system prompt the draft agent file would get (an orchestrator's includes its roster). Only the draft itself is validated (`400`). |
| `GET` `POST` `DELETE` | `/api/mcp/agents/{agent_id}` | `chat.use` | MCP Streamable HTTP proxy to that agent. `404` if the id isn't in ai_agent's registry. |
| `GET` `POST` `DELETE` | `/api/mcp/server` | `tools.use` | MCP Streamable HTTP proxy to mcp_server. |
| `GET` | `/api/health` | - | `{status: "ok"}` |

## Private extensions

A user can add an MCP server of their own (`/api/user-extensions`; kept in db_gateway, so a chat answer still runs without them while it is down, with a notice). Only that
account sees it and only its chats use it. `portcullis` stores it; `ai_agent`
makes every connection (it holds the address guard: public and private-LAN
addresses only, never loopback, link-local or cloud-metadata ones).

- **Headers are secrets.** They are stored as one Fernet token per extension,
  made with `EMBER_SECRETS_KEY` in `.env`. The key is generated and appended to
  `.env` on first start (a warning line, without the key, is logged once).
  Keep it with any backup of `.env`. If it is lost or replaced, the affected
  extensions show "Its headers can't be read" and are left out of turns until
  their headers are entered again; the others keep working. A value that is
  not a valid key stops startup with a one-line message. Needs the
  `cryptography` package.
- **Nothing leaks.** The API returns header names only. The activity log
  (`account.user_extension_add`, `_edit`, `_remove`) names the label and the
  URL's host, never the full URL (it may carry a token) or a header value.
- **On a turn**, the account's enabled extensions are read from the database
  and sent to `ai_agent` as `private_extensions` (the browser cannot name one).
  An `ai_agent` that does not report `private_extensions` in `status` is
  refused: the turn fails with a message rather than quietly running without
  them. Their tools are named `u_<id>__<tool>` and always ask for approval
  (the agent raises the usual `approval_request`).
- **Notices.** An extension the agent could not use, or whose headers could not
  be read, is reported to the watcher as a live turn event
  `{type: "notice", notices: [{id, label, error}]}`. It is not saved in the chat.

Stronghold stores tickets and groups in Treasury. Portcullis forwards authenticated requests to Stronghold.
Stronghold records the account’s stable uid as the ticket owner, so ownership survives a username change.

Titles are 1-120 characters, descriptions 1-4000, comments 1-2000 and
assignees at most 64. Invalid request fields and ids return `422`.
Armory's `404` is preserved; other upstream `4xx` responses become `400`
with the upstream message. Unreachable, malformed or `5xx` upstream responses
become `502` (Stronghold says `"armory is unreachable"`, portcullis `"Stronghold is unavailable"`). Staff actions log ids and changed
field names only, after upstream success, never titles, descriptions or comments.
Manual ticket creation has no additional rate limiter; mcp_server limits
automatic reports. Add manual limits later if abuse appears.

## Outside clients

A program outside the Citadel can call Legion's entry agent with its own key through one door. It has no account, cookie or
chat; the key opens nothing else (not `/api/chats`, not any admin route), and a signed-in session cannot use the door.

### The door: `POST /api/outside/legion/ask`

```
curl -H "Authorization: Bearer ock_..." -H "Content-Type: application/json" \
     -d '{"question":"Say hello","history":[{"role":"user","content":"earlier"}]}' \
     http://<host>:29601/api/outside/legion/ask
```

Body: `question` (1 to 8000 characters), optional `history` (up to 20 turns of `{role: user|assistant, content}`); other fields
are refused. Answer: `{answer, usage: {total_tokens, budget_remaining}, request_id}`.

| Status | Meaning |
|---|---|
| `200` | The answer; its tokens were recorded. |
| `401` | Wrong, missing, disabled or deleted key: one identical text for all of them. |
| `403` | The client may not use this service, or its address is outside the client's `ip_allow`, or the address is refused by the main deny list or the outside IP lists. |
| `413` | Body over 1 MiB (answered before the key is checked; not audited). |
| `415` | Content type is not `application/json` (answered before the key is checked; not audited). |
| `422` | Malformed body. The error lists `loc`, `msg` and `type` only, never the submitted text. It is answered before the key is checked, so it is not audited. |
| `429` + `Retry-After` | Client rate limit, or the token budget is used up. |
| `503` | Legion or the entry agent is down, the budget cannot be read, or the tokens could not be recorded (the answer is then withheld). Nothing is counted. |

Every check that cannot decide refuses (fail closed).

### The Stronghold level: `POST /api/outside/stronghold/ask`

Same body, answers, statuses, key, rate limit, budget and audit log as the Legion door; the client record must list the
service `stronghold` (a client allowed `legion` only gets `403`). The agent may use five Stronghold Brain tools and
nothing else: `tool_brain_search`, `tool_brain_read`, `tool_brain_list`, `tool_brain_write`, `tool_brain_update`, on the
client's own Brain folder (its uid, `oc_<12 hex>`, created at the first write). Legion gets
`disabled_tools = ["*", "!stronghold__tool_brain_search", ...]` (the `"!name"` exception form), and Stronghold refuses every
other tool for an `oc_` uid on its own. The global brain, tickets, usage, skills, short-term memory, sharing and every
Armory tool stay out of reach. Deleting the client also asks Stronghold to purge `/brain`, `/stack`, `/brain/proposals`
and `/brain/shares` for its uid (best effort, one error log per failure; the delete still answers `204`). The path
through a live Legion and Stronghold has not been run.

### Key and client record

The key is `ock_` plus 43 URL-safe characters. It is shown once, on create and on rotate; Portcullis keeps only its
SHA-256 and the 8-character prefix (`key_prefix`). It never appears in logs, errors or the audit log.

A client is `{id, uid, name, key_prefix, services, ip_allow, rate_per_minute, enabled, created_at, last_used_at, budget}`:
`name` 1 to 60 of letters, digits, space, `-_.`, unique ignoring case; `services` is `["legion"]` by default (`legion` and `stronghold` are the two services); `ip_allow` a list of addresses or networks (empty = any address the IP lists let in); `rate_per_minute`
1 to 600 (default 10); `budget_tokens` 1 to 100000000 (required on create); `budget_days` 1 to 366 (default 30).

### Budget

Tokens are summed over a rolling window of `budget_days` from the client's audit events. The budget is checked before a
call and the call's tokens are added after it, so the overshoot is bounded by the calls in flight at once (up to
`rate_per_minute` within the 120 s ask window), not by one call. If the record cannot be
written, the answer is withheld. `budget` in a client view is `{tokens, days, used, remaining, resets_at}`
(`resets_at`: when the oldest counted call leaves the window, `null` if none).

### Audit log

Each call or refusal is one event: `at, service, action (call|refused), reason, status, tokens, ip`. Reasons:
`invalid_key`, `disabled`, `service_not_allowed`, `ip_not_allowed`, `rate_limited`, `budget_exhausted`,
`budget_unavailable`, `upstream`. It holds no question or answer text and no key. Refusals of unknown keys are not
audited (no client to attach them to).

### IP lists

Two lists, `security.outside_ip_filter.allow_list` and `deny_list`, apply only to `/api/outside/*` (set them in the
Portcullis settings; like other policy values they apply from the next start). On that path the main deny list applies
too, but the main allow list does not (it is for people); an empty outside allow list admits any address. A client's own
`ip_allow` narrows this further.

### Admin routes (`settings.manage`)

All under `/api/admin/outside-clients`; each change is logged in the activity log as `outside_client.create|update|rotate|delete`
with the client's id, name and changed field names, never a key.

| Method | Path | Returns |
|---|---|---|
| `POST` | `/` `{name, budget_tokens, services?, rate_per_minute?, budget_days?, ip_allow?}` | `201 {client, key}`; the only time the key is shown. |
| `GET` | `/` | `{clients: [...]}`, never a key or hash. |
| `GET` | `/{id}` | The client plus `events` (newest 50; `limit` 1 to 200, `before_id` pages back). |
| `PATCH` | `/{id}` any of `name, services, ip_allow, rate_per_minute, budget_tokens, budget_days, enabled` | The client. |
| `POST` | `/{id}/rotate-key` | `{client, key}`; the old key stops working. |
| `DELETE` | `/{id}` | `204`; its events go too. |

Errors: `404` unknown id, `400` with the reason in words, `422` malformed body (unknown fields such as `key` are refused).

```
curl -b cookies -H "Content-Type: application/json" -d '{"name":"Docs bot","budget_tokens":50000}' \
     http://<host>:29601/api/admin/outside-clients
```

### No tools, no memory

Each call is stateless and reaches no tool. Portcullis asks Legion with no extensions, `approval_mode=deny`,
`allowed_tools=[]`, no plan and no questions back, and with `disabled_tools=["*"]`. The last one matters most: deny
and the empty allow list only gate the model's own tool loop, while Legion's memory recall, skill recall and skill
learning call the upstream directly; `"*"` is Legion's filter wildcard, checked first, and delegates inherit it. This was
proven by a probe against Legion's real filter (`tests/legion_filter_probe.py`, run by `tests/test_legion_ask.py`), not
against a live Legion ask. Legion sees the client as requester uid `oc_<12 hex>` with username `outside:<uid>` (`:` is not
allowed in account usernames, so it can never equal an account) and an empty email. The only context is the `history` the client sends.

### Known gaps

- Not built: a Stronghold level (a client with its own memory namespace), a Portcullis Admin screen for clients, per-client
  tool access, a per-call token ceiling.
- The client IP comes from `X-Forwarded-For` only when the peer is loopback (a `trusted_proxies` entry), so every loopback
  proxy in front of Portcullis must append to that header, not pass it through, or a client can pick its own address
  (which defeats the IP lists and a client's `ip_allow`).
- Refusals of unknown keys are not audited or counted; a flood of bad keys is limited only by the IP lists and traffic counters.
- IPv4-mapped IPv6 addresses (`::ffff:a.b.c.d`) do not match IPv4 entries in either IP filter (pre-existing).
- A call refused for budget still uses a rate slot.
- A missing token count from Legion is counted as 0 (and a warning is logged).
- If the entry agent were ever switched to plan or architect mode, delegation would run: delegates still get
  `disabled_tools ["*"]` and deny, but model calls happen. Keep the entry agent out of those modes.

## Security model

- **Sessions:** a random 256-bit token in an `HttpOnly`, `SameSite=Strict`
  cookie (`Secure` when `cookie_secure` is on, or when a `trusted_proxies` peer
  sends `X-Forwarded-Proto: https`, as Tailscale Funnel does). The database stores only its
  SHA-256, with an expiry (`session_hours`); logout deletes the row.
- **Passwords:** werkzeug hashes, checked on a worker thread so hashing
  never blocks the event loop. Unknown usernames are checked against a dummy
  hash so they take as long as a wrong password.
- **Audit:** every login attempt is stored in `login_attempts` (IP, matched
  account if any, success). The activity log (`log_entries`, Logs page)
  records logins, logouts, registration, email verification, account
  changes, every admin action and capability/extension changes; errors and
  one line per answered chat turn go there too. Entries older than 90 days
  are deleted on startup; a deleted account's entries stay.
- **Permissions:** `chat.use`, `chat.share`, `tools.view`, `tools.execute`, `files.upload`, `files.download`,
  `accounts.view`, `accounts.manage`, `accounts.delete`, `roles.view`, `roles.manage`, `roles.assign`,
  `invites.manage`, `settings.manage`, `capabilities.manage`, `usage.all.view`,
  `extensions.personal.manage`, `tool_services.manage`,
  `logs.view`, `logs.errors.view`, `logs.chat.view`, `logs.chat.prompts.view`, `config.issues.view`,
  `traffic.view`, `tickets.create`, `tickets.manage` (`src/services/permissions.py`). The Administrator role always holds all
  of them (new ones are added to it on startup). New registrations get `default_role` (config, default `Member`:
  `chat.use`, `chat.share`, `tools.view`, `tools.execute`,
  `extensions.personal.manage`, `files.upload`, `files.download`, `tickets.create`) - unlike chat_app, where new accounts get no
  role. An unverified account cannot use permission-gated routes. A role holding
  any of the `STAFF_PERMISSIONS` in `permissions.py` cannot be assigned to it (`409`).
- **Starter roles:** migration `0019` creates `Viewer`, `Support`, `Moderator`, `Auditor`, `Tool Services Manager` (renamed from `Power User` by `0030`) and `Operator` once,
  with preset permissions (none holds `roles.manage`, `roles.assign`, `accounts.delete` or any `logs.chat.*`). An existing
  role of the same name is left alone, and edits or deletions later stick.
- **Ticket permissions:** `tickets.create`: "Report bugs, suggest features and follow your own tickets";
  `tickets.manage`: "See every ticket, triage them and set status, priority and assignee".
  Migration `0012` grants `tickets.create` once to existing roles holding `chat.use`;
  later revocations stick. Staff access does not grant reporter access.
- **Invites and verification codes:** 10 random characters, stored as
  SHA-256, single use. Invites expire after 7 days and are delivered only to the
  invited address. Registration checks the invite and email before revealing
  whether a username is taken. Successful registration verifies the address
  automatically. A failed registration leaves the invite unused. Users who
  need to verify can request a 15-minute code from the verify screen.
- **Email:** Armory's Email capability sends invite and verification templates.
  Configure SMTP on the Email page of Armory Admin and enable **Email** in
  capability controls. Portcullis checks SMTP readiness before creating an
  invite and discards the invite if delivery fails. A lost response can follow
  SMTP acceptance. Check delivery status before manually retrying.

- **MCP proxy:** the browser only ever talks to portcullis. Upstream URLs come
  from server-side config (`mcp_server_url`) and ai_agent's own registry file
  (`agents_registry_path`), never from the request. Only
  `content-type`, `accept`, `mcp-session-id`, `mcp-protocol-version` and
  `last-event-id` are forwarded; the browser's cookie and any
  claimed identity headers and metadata are dropped. Portcullis adds a signed
  requester token from the authenticated account and a fresh Ed25519 service
  assertion to each backend request. `/internal/*` admits only Stronghold.
  Responses, including SSE, are relayed chunk by chunk; the upstream request
  closes when the browser disconnects.
- **What may pass** (`src/services/mcp_policy.py`, bodies up to 1 MB): the
  MCP handshake (`initialize`, `ping`, a few notifications) for everyone;
  on agents only `tools/call` of `status` - chat turns run inside portcullis
  (`/api/chats/{id}/turns`), so the browser can't bypass the usage limits or
  skip saving an answer; on mcp_server `tools/list`, any `tools/call` and
  `resources/list` / `resources/templates/list` / `resources/read`.
  Anything else gets a JSON-RPC error (`403`) and never reaches the server.

Legion and Armory require signed service assertions. Each downstream user
operation verifies Portcullis's requester token, including per-tool MCP metadata.

- **Chat turns** (`routes/chats.py`, `services/stronghold_forwarder.py`): Stronghold runs the
  answers (`apps/stronghold/src/turns`: Legion calls, the event buffer, approvals, questions,
  summaries, suggestions, usage and the chat trace). Portcullis checks login and permission, then
  passes the request on and relays the event stream. The browser leaving closes only the relay.
  At most 3 running answers per account, kept in Stronghold's memory (run one replica); a
  Stronghold stop saves a running answer as interrupted.
- **What only Portcullis decides** (the `trusted` block of `POST /api/chats/{id}/turns`, filled here
  and overwriting anything the browser sends): `forced_approval` (Armory's `force_tool_approval`, read for each
  start and approval and switched by an admin with `PUT /api/armory-tool-approval`; `true` when Armory does not answer),
  `tools_execute` (the account's `tools.execute` permission), and no extension list (the turn body carries none). Stronghold's defaults
  are the safe side: approval forced, no tool execution, no extensions, no auto-save.
  Typed commands (`/tool`) call Armory directly with no agent and are not affected.
- **Regenerate / edit** (`truncate_to` on `POST /api/chats/{id}/turns`): the
  server cuts the history before a typed question and asks again, so the
  browser never rewrites saved history itself.
- **Branching** (`ChatService.branch`, `POST /api/chats/{id}/branch`): a copy
  of the saved messages up to one answer becomes a new chat with a
  server-made id. Only saved messages are read, so a chat that is still
  answering can be branched.
- **Chat folders and pins** (`services/folder_service.py`, `routes/chat_folders.py`): folders are one level deep per account. A branch stays in its source's folder and is not pinned. The schema change is migration `0005`.
- **Share links** (`services/share_service.py`, `routes/shares.py`; Stronghold keeps the links in `apps/stronghold/src/shares`): the one
  feature that lets someone read a chat without logging in, so its rules live
  on the server. A link's token is 256 random bits and only its SHA-256 is
  stored (shown once, at creation). What is shared is a frozen copy taken
  then, cut to the questions the user typed and the assistant's plain
  answers: tool steps and results, usage data, summaries, raw logs,
  slash-command results, error texts, download markers and the text of
  attached files are left out. Links expire (1, 7 or 30 days, or never; an expired one is removed when read or when its owner makes a new link), can be revoked, and die with their chat
  (deleting one chat, all of them or a folder revokes the links first, and nothing is deleted if Stronghold cannot) or account. Unknown, revoked and expired
  links answer alike, and `GET /api/shared/{token}` is limited per address
  (`PublicReadLimiter`, in memory). portcullis cuts the chat down to what may be shared and passes the snapshot on; Stronghold answers `502` when it is down. Links made before Plan 5.5 are gone, and the old `shared_chats` table stays here, unused.
- **Chat search** (`services/chat_search.py`, `GET /api/chats/search`): a
  literal, case-insensitive scan of the account's titles and messages,
  streamed and stopped at 50 hits; ASCII queries are pre-filtered in SQL.
- **Usage limits** (`services/usage_client.py`; the caps are in Stronghold's config `usage`): tokens of
  every answer and summary are recorded per agent by Stronghold; a question over the
  6-hour or weekly cap is refused with `429` before anything is saved, and with `503`
  when Stronghold cannot say (a failed record is only logged).
- **Extensions:** portcullis turns on every extension mcp_server lists; the
  browser cannot name one. Which agent may call an extension's tools is that
  agent's `tools.allow`. Adding an extension makes mcp_server connect to any
  URL, so that is admin-only.
- **Agents switched off by the user:** the browser cannot send tool switches
  any more. portcullis reads the account's switched-off agents from db_gateway
  and passes them to the agent as `agent:<id>` entries in `disabled_tools`.
- **Errors:** an unhandled exception answers a generic `500` and is written
  to the error log with its traceback (under the account, when logged in).
- **Summaries:** done by Stronghold (`POST /api/chats/{id}/summarize` passes through); automatic
  before a question once the chat's context is 60% full (Stronghold's `usage` config).
- **Chat history:** every query is filtered by the logged-in account, and
  chat ids are unique per account, so another user's chat looks exactly like
  a missing one (`404`). Limits: 2 MB per chat, 1000 chats per account.
- **Body size:** requests over 32 MB are refused with `413` before they are
  read (`src/body_limit.py`).
- **Login rate limiting** (`services/rate_limiter.py`, config
  `security.rate_limit`): after 5 failed logins in 15 minutes from one IP or
  for one account, login answers `429` with `Retry-After` until 15 minutes
  after the last failure - checked before the password, so no hashing work
  and no password answer during a lockout. Refused tries aren't recorded.
- **Client IP** (`src/security.py`): the socket address, or the last
  `X-Forwarded-For` hop when the peer is a `trusted_proxies` entry (Vite's
  loopback proxy, which sets it). Used for the audit, rate limit and IP filter.
  `X-Forwarded-Proto` is honoured under the same rule and sets the cookie's
  `Secure` flag. Behind a proxy that hides client addresses (the Docker
  deployment behind Funnel), set `security.rate_limit.scope` to `"account"` so
  one shared address cannot lock every user out.
- **IP filter:** optional allow/deny lists, `403` on every route.
- **Headers:** nosniff, `X-Frame-Options: DENY`, `Referrer-Policy:
  no-referrer`, `default-src 'none'` CSP on every response; HSTS when
  `hsts_max_age` is set. ember_web's `vite preview` sets its own CSP.

- **Devices** (`services/device_service.py`, config `security.fingerprint`,
  port of chat_app's fingerprinting): a hash of User-Agent, Accept-Language
  and the /24 (IPv4) or /64 (IPv6) network. A login from one the account
  never used is allowed and written to the activity log
  (`auth.new_device`); users see and forget theirs on the Account page.
- **Command form:** option lists come only from `options_url`s a tool
  declares, as plain paths on mcp_server (never a host); uploads go through
  mcp_server's own `/upload` checks.

- **Hardening (security review of 2026-10-03):**
  - *Verification codes* are voided when the email changes (a code sent to the
    old address cannot verify the new one) and verification emails are limited
    to one per 30 seconds and five per hour per account (`429` with
    `Retry-After`), on resend and on email change.
  - *Wrong passwords* typed into "change password" or "change email" count
    towards the login lockout, so a stolen session cannot guess the password
    there.
  - *Request bodies* are capped at 1 MB everywhere except `/api/chats`,
    `/api/attachments` and `/api/uploads` (32 MB), so the pre-login routes
    cannot be fed huge bodies.
  - *Attachments* are refused when an office file claims to unpack to more than
    100 MB or 5,000 entries, and reading stops at 500 PDF pages, 200,000 sheet
    rows, or as soon as 20,000 characters are read.
  - *Usernames and emails* are unique ignoring case at registration.
  - A command-form option value of `.` or `..` is refused. Old `login_attempts`
    rows (over 30 days) are deleted at startup.
  - *Downloads:* `GET /api/server/download?path=` forwards `path` to mcp_server
    as it is. It must therefore be an **opaque id that mcp_server checks against
    the requesting account**, never a file path mcp_server would serve to anyone
    who names it. mcp_server's `/download` does exactly that: ids are random,
    held in memory for 10 minutes, bound to the verified requester username, and an unknown, expired or someone else's id are
    the same `404`. Today `/server logs` is the one tool that offers a file.
  - Known and left as is: five wrong logins lock that account (and address)
    out for the lockout time, so someone can lock a known username out on
    purpose; and any member with `tools.use` can run any tool (that is what the
    permission means; "ask before each tool" is opt-in per chat).
- **Backups:** the backup settings (Portcullis Admin > Workspace settings) copy the database
  every 24 hours (default) into `.data/portcullis/backups` and keeps 14. See the config
  README. `python -m scripts.backup_db` makes one now. The Config issues page
  warns when backups are off, when `cookie_secure` is off on a host other
  machines can reach, when HSTS is off while cookies are secure.

## Changing the schema

The database schema is versioned with Alembic. At startup portcullis brings
the database to the newest revision (`migrations/versions/`):

- a new database gets every migration;
- a database made before migrations existed is marked as the baseline
  (`0001`) without being rebuilt;
- `usage_records` keeps `agent_id`, `provider_id`, `gateway`, `started_at`, `finished_at` and `delegated_by` for each agent's share of an answer (migration `0003`; older rows have them empty);
- a database that is behind gets the missing migrations, after a backup
  (`.data/portcullis/backups/`). SQLite cannot undo a half-finished migration, so the
  backup is the way back; if the backup fails, nothing is changed.

To change a table or add a column:

1. Edit the model in `src/models/`.
2. Stop portcullis, then run `python -m scripts.migrate_db revision "what changed"`.
   It writes a new file in `migrations/versions/`.
3. Read that file. Check it does what you meant (a new `NOT NULL` column on a
   table with rows needs a `server_default`). SQLite edits go through
   `op.batch_alter_table`, which the generator already uses.
4. Start portcullis, or run `python -m scripts.migrate_db upgrade`.
   `python -m scripts.migrate_db status` shows where the database is.

`tests/test_migrations.py` fails when a model differs from what the
migrations build, so a model edit without its migration is caught.

## Layout

```
configs/   config_app.json                    host, port, cookie, URLs, trusted proxies (the rest is in Admin)
.env       BOOTSTRAP_ADMIN_* (+ .env.example); secrets/ is the old layout, read once to build it
           (runtime data - ember_api.db, backups - is in .data/portcullis/ of the Citadel folder)
src/
  run.py, app.py, config.py, db.py, deps.py, json_only.py, security.py, body_limit.py
  models/     Account, AppSetting, Role, Permission, LoginAttempt, AuthSession, InviteCode, EmailVerificationCode, Chat,
              UsageRecord, LogEntry, KnownDevice, PromptTemplate, SharedChat
  services/   DatabaseBackup / BackupScheduler (backup_service), MigrationRunner (migrations), SettingsService (settings_service), AuthService, SessionService, OtpService, RegistrationService, EmailSender (MCP Email capability),
              AccountService, AdminService, AgentDirectory, ChatService, ChatSearch, TemplateService, ShareService, PublicReadLimiter,
              UsageService, McpServerInfo, McpServerTools, mcp_session, LogWriter,
              text_extraction, config_validation, DeviceService, LoginRateLimiter, McpPolicy, McpProxy,
              permissions, DbGatewayClient (db_gateway)
  routes/     auth, account, admin, settings, chats, templates, shares, usage, mcp, server_info, logs,
              attachments, config_issues
  utils/      config_loader
scripts/   backup_db.py                         back up the database now
           migrate_db.py                        schema status / upgrade / new migration (see "Changing the schema")
migrations/  Alembic environment and versions/ (0001_baseline.py)
tests/
```

### Permission split (migration 0010)

Startup backs up existing databases, then grants the equivalents of the old
`admin.manage`, `tools.use`, and `chat.use` permissions to each existing role.
This runs once: subsequent restarts preserve revoked grants. Legacy broad
permission rows remain only for rollback and are neither listed nor authorized.
The Administrator role receives all currently known permissions on startup.

Read-only permissions do not grant mutation access. Account and role management
permissions include the corresponding discovery routes needed to perform their
actions. Role assignment, role changes, and account edits/deletions cannot affect
permissions beyond the actor's own authority. Invitations currently have no role
picker; the inviter must hold every permission in the configured default role.

`chat.share` controls creating public links; owners can still list and revoke
existing links with `chat.use`. Personal extension listing and use remain under
`chat.use`; creating, editing, switching, or removing one also requires
`extensions.personal.manage`. File attachment extraction requires `files.upload`.

`tools.execute` applies to both direct MCP calls and agent calls, including shared
and private extensions and delegated agents. Without it, chat sends a server-owned
block-all filter; an older agent lacking `tool_filter_all` is refused before it
answers. Update/restart ai_agent together with portcullis. `tools.view` still allows
tool discovery and resource reads. File download permission gates Ember's server
file-transfer route; it does not prohibit copying chat text or tool results.

To roll back, deploy the previous code with the pre-migration backup. Alembic
downgrade to 0009 retains original broad grants and removes the new permission
rows, but does not undo role edits made after upgrading.

The usage routes (`/api/usage...`, `/api/admin/usage...`) are answered by Stronghold (`apps/stronghold/src/usage`), which keeps the rows in Treasury; portcullis checks the login and the permission and passes the request on (`502` when Stronghold is down; the browser's own `account_id`/`uid` fields are never sent on). The caps (`usage.six_hour_token_limit`, `usage.weekly_token_limit`) and the `pricing` block are Stronghold's config. Usage recorded before the move stays in the old `usage_records` table and is not shown; the old table is not dropped. The administrators' list asks Stronghold for totals per uid and adds every account itself.

Admin usage includes every existing account, including disabled accounts and accounts with no usage in the selected period. Tokens include summaries; answers count distinct chat turns (delegated agents count once, summaries count zero). Personal usage remains scoped to the session account. Admin detail routes require usage.all.view, independently of chat.use and accounts.view.



## Document storage (db_gateway)

Accounts, chats, usage and the rest stay in this project's SQLAlchemy database. New data that
needs no joins or foreign keys can be kept as documents in the `db_gateway` project instead, so
it can sit on SQLite, Postgres or Firestore and be shared with other apps.

`config_app.json` has a `db_gateway` block: `url` (default `http://127.0.0.1:29602`), `instance`
(`ember`) and `connection` (`data`). Portcullis registers that instance with Treasury at start, and the
connection must exist there (`data` is built in; see `apps/treasury/configs/README.md`). Calls require a short-lived Portcullis service assertion for Treasury.

`src/services/db_gateway.py` has `DbGatewayClient` with `get`, `put`, `delete` and `query`
(equality filters). A missing record is `None` or `False`. An unreachable gateway raises
`DbGatewayUnavailable`, so only a feature that uses it fails; portcullis starts without the
gateway. Routes get it from `get_db_gateway` in `src/deps.py`; tests use `FakeDbGateway`
(the `db_gateway` fixture).


## Internal API

`/internal/...` is for Stronghold only. Every route requires a signed Stronghold service assertion. `POST /internal/requester-token` renews identity only for an active account with a running Stronghold turn. `GET /internal/accounts/{uid}/permissions`, `POST /internal/accounts/{uid}/actions`, `POST /internal/errors` and `POST /internal/logs`. The web apps' nginx proxies only `/api/`, so these routes are not reachable from a browser.

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

`/api/health` remains available. `GET /api/admin/ready` aggregates all five service reports for accounts with `settings.manage`. The admin screen is pending.
