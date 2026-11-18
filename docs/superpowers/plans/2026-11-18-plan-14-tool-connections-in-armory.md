# Plan 14: every tool connection lives in Armory

> Status: decisions approved 2026-11-18 (the recommendations below). Nothing here is built. Written from the discussion about the Bard speaker failing on a missing Portcullis token.

**Goal:** Armory is the only service that holds the address, the credentials and the transports of the services Citadel talks to besides its own five. Stronghold and Portcullis stop keeping Bard, Scribe and Reader tokens and addresses.

**Why now:** Bard is configured in three places today: Armory's extension entry (MCP, for agents), Stronghold's Tool services page (REST, for speak and attachments) and, until the 2026-11-18 interim fix, Portcullis (REST, for the audio stream). Each has its own token. One missing token breaks a feature and the error names a different service ("Stronghold is unavailable") than the one at fault.

## The three connection classes

| Class | What it is | Who adds it | Transports | Used by | Lives in |
|---|---|---|---|---|---|
| **Required** | Bard, Scribe, Reader. Citadel features call them directly: read aloud, dictation, attached audio and documents. | Fixed names. An admin supplies address and token. | REST for Citadel's own features, MCP for agents, or both | Stronghold and Portcullis (through Armory), Legion (MCP) | Armory settings database |
| **Server-sided optional** | Anything else an admin connects for everyone (Lens, Mimic, a vendor MCP server). | Admin, in Armory Admin | MCP, REST, or both | Armory capabilities and agents, gated by permission | Armory settings database |
| **Client-sided optional** | A user's own MCP server, used only for that user's turns. | The account, in the Ember app | MCP today, REST later | Only that account | Stronghold's db_gateway (`user_extensions`), unchanged |

"Required" means Citadel reports it as a configuration problem when missing (the Config issues page), and the feature that needs it says so instead of failing late. Optional ones never raise an issue.

Any class can be reached over MCP, REST or both. A connection record says which transports it has; nothing assumes one.

## Architecture

**One record per connection**, in Armory's `settings.db` (table `connections`):

```
name, class (required | server), label, description, enabled,
mcp:  { url, auth }              # optional block
rest: { base_url, auth }         # optional block
web_url
auth: token (X-Internal-Token, write-only)  |  internal (signed service assertions)  |  headers (write-only map)
```

Required names (`bard`, `scribe`, `reader`) are reserved and always listed, even when empty. Secrets are write-only everywhere: views say only whether one is set.

**MCP side.** Armory builds the agent tools from the `mcp` block, exactly as it does for extensions today. Tool names keep their prefix (`bard__tool_bard_speak`). The existing extension entries for these three are migrated into connection records. Server-sided optional connections are today's extensions, moved onto the same record.

**REST side.** Armory exposes a small façade, reachable only by signed service calls (Plan 12) from Stronghold and Portcullis:

| Armory route | Calls | Used for |
|---|---|---|
| `POST /connections/bard/speak`, `GET /voices`, `GET /audio/{id}` (Range) | Bard `/api/speak`, `/api/voices`, `/api/files/{id}` | read aloud |
| `POST /connections/scribe/transcribe`, `/transcribe-partial`, `/files`, WebSocket `/dictate` | Scribe `/api/transcribe`, `/api/transcribe-partial`, `/api/files`, `/api/stream` | attached audio, dictation |
| `POST /connections/reader/files`, `/parse` | Reader `/api/files`, `/api/parse` | attached documents |

Armory forwards the requester identity and the stored token, and keeps the error mapping that Stronghold has now (400 and 413 pass through, other refusals become 502 with a message that names the connection and the reason, for example "Bard refused the token").

**Callers.** Stronghold's JSON features call Armory (it already does for uploads, memory, skills and tickets, with the same keyring pattern). Portcullis keeps only the streams it owns today (attachment content, audio, the dictation socket) and opens them against Armory instead of the tool service.

**What disappears:** Stronghold `ToolService`, its `tool_tokens` and the Tool services page in Stronghold Admin; Portcullis `services/scribe.py`, `tool_tokens`, `scribe_url` and the Tool services page in Portcullis Admin; `BARD_URL`, `SCRIBE_URL`, `READER_URL` and the three `*_TOKEN` variables in Compose, `.env.example` and the docs.

**Plan 13.** Bard, Scribe and Reader stay out of the Treasury catalog. Their address now lives in Armory's records, so "set on an admin page" in Plan 13's list becomes "set in Armory Admin, Connections".

## Armory Admin: Connections page

Replaces the Extensions page. Three sections:

1. **Required**: three fixed cards. Each shows address, token set or not, which transports are on, and a **Test** button per transport (MCP lists tools, REST calls `/health`). A missing one shows a clear "Not connected" state and which Citadel features it disables.
2. **Server-sided optional**: today's extension list with Add, Edit, Remove and the same form, with an MCP block and an optional REST block.
3. **Client-sided**: a read-only note and a count, linking to the Ember page where accounts add their own. Armory cannot read their secrets and does not store them.

## Tasks

Each task ends green on its own suite and is committed separately. Python through `uv` / the project `.venv`, JS through `pnpm`. After any change to `libs/citadel_auth` run `scripts/sync_citadel_auth.py` and check with `--check`.

### Task 0: finish the interim fix (already built, uncommitted)
Bard audio streams through Stronghold and Portcullis drops its Bard token. Stronghold's 738 tests and the targeted Portcullis tests pass; the full Portcullis suite is running. Commit it: it removes one of the three Bard configurations immediately and Task 3 replaces it. Not optional if the speaker must work before the rest lands.

### Task 1: Armory connection store and REST façade
- `apps/armory/src/services/connections.py`: record model, validation (address is a base URL with no credentials, path, query or fragment; names reserved; secrets write-only), store in `settings.db`.
- Migrate the `extensions` table onto `connections` (same data, new shape); keep `/extensions` routes answering the old status shape for Ember until the UI moves.
- `apps/armory/src/connection_routes.py`: the REST façade above, behind the service-assertion middleware, allowed callers `stronghold` and `portcullis` only (extend `citadel_auth.policy`).
- REST clients for Bard, Scribe, Reader with the error mapping, Range streaming and the dictation WebSocket relay moved from Portcullis `ScribeGateway`, keeping its bounds (frame size, 150 s of audio, idle and final timeouts, one stream per account).
- Tests: record validation, secret never returned, each route with a fake upstream, caller allow-list, error mapping, Range, WebSocket limits.

### Task 2: Armory Admin Connections page
- New view and API client, replacing `ExtensionsAdminView`. Cards for the three required connections, the optional list with the existing add and edit form, Test buttons.
- Config issues: report a missing required connection (`/config-issues` in Portcullis reads Armory's status).
- Tests: view tests for the three sections, secret fields, Test results; radius and layout checks as in `ember-frontend-design`.

### Task 3: Stronghold uses Armory
- New `ArmoryConnections` client beside `ArmoryUploads`. `bard`, `attachments` (audio, document, dictate) call it. Remove `ToolService`, `tool_tokens`, `tool_token_routes`, `BARD_URL`, `SCRIBE_URL`, `READER_URL`, `service_token` use for them, and the Tool services page in Stronghold Admin.
- Keep the interim `GET /bard/audio/{id}`, now backed by Armory, or drop it if Portcullis streams from Armory directly (see Question 1).
- Tests: the existing `test_bard`, `test_attachments`, `test_tool_tokens` become tests against a fake Armory.

### Task 4: Portcullis streams from Armory
- Audio, attachment content and the dictation WebSocket open against Armory. Remove `services/scribe.py`, `tool_tokens`, `tool_token_routes`, `scribe_url`, the Tool services page and the related admin client.
- Tests: audio and dictation route tests against a fake Armory; remove the token tests.

### Task 5: Deployment, docs, cleanup
- Compose: remove `BARD_URL`, `SCRIBE_URL`, `READER_URL` from Stronghold, the token variables from `.env.example` files.
- Docs: `docs/deployment.md` (a "Tool connections" section), the three service READMEs, `_TODO.md`, Plan 13's left-alone list.
- Server steps in this order: publish Armory, open Armory Admin, Connections, enter address and token for Bard, Scribe and Reader (the same tokens as today), then publish Stronghold and Portcullis, then remove the old tokens from their admin pages.

## Decisions (approved 2026-11-18)

1. **Streams.** Portcullis opens the audio, attachment-content and dictation streams straight to Armory, not through Stronghold. Task 3 therefore drops the interim `GET /bard/audio/{id}` in Stronghold.
2. **Dictation relay.** The WebSocket relay moves into Armory, with its bounds (frame size, 150 s of audio, idle and final timeouts, one stream per account). Portcullis only authenticates the browser and relays to Armory.
3. **Missing required connection.** The control stays visible and says why it is off. A hidden control looks like a bug.
4. **Tokens.** Keep the per-caller `X-Internal-Token` that Bard, Scribe and Reader use now. Signed service assertions for them is a later step, listed in `_TODO.md`.
5. **Client-sided REST.** Out of this plan. It means server-side requests to user-chosen addresses and needs its own security review.
6. **Name.** "Connections" in Armory Admin, replacing both "Extensions" and "Tool services".

## Risks

- **Armory becomes a dependency of speech, dictation and attachments.** An Armory restart cuts a running dictation stream. Armory is already required for chat tools, so the new dependency is mostly one more thing that breaks together, not a new failure.
- **Privilege.** Armory has the Docker socket mounted. Moving user audio and documents through it enlarges what a bug in the façade could reach. Keep the façade routes thin, bounded and covered by the caller allow-list, and do not let it run any command.
- **Extra hop for uploads.** Stronghold sends a file to Armory, Armory to the tool service. Files are capped at 20 MB, so the cost is one more copy in memory.
- **Migration.** The three tokens must be entered in Armory Admin before Stronghold and Portcullis are updated, or the features fail until they are. The order above avoids that.
- **Scope.** Tasks 1 to 4 touch four apps and an admin app. Run them as separate commits, Armory first, so each can be tested and deployed alone.

## Not in this plan

- Moving ConversationGateway, DecisionGateway or the model services (Laya, Paradee and so on): they stay as their own stacks.
- Changing Plan 12's signed service calls or Plan 13's catalog.
- Moving client-sided connections out of Stronghold.
