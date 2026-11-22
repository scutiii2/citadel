# Scope audit: what the code does versus the 2026-11-20 scope spec

Read-only audit of `main` at `4030fe6d` (2026-11-19), against [the scope spec](../specs/2026-11-20-service-scopes-design.md). Nothing was changed except this file and the spec's status line. The vault note `Brain/Projects/Citadel.md` was synced at `2a6af62a` (2026-11-18); 41 commits and 255 files have changed since, so several vault claims are stale (see "Vault gaps").

## Result in one line
Most of the plan's assumptions held, but five were wrong or collide with work done on 2026-11-18 and 19 (Plans 14 and 15 and the gateway stacks). Those five need your decision before any code moves.

## Findings against the spec

| # | Spec claim | What the code shows | Effect |
|---|---|---|---|
| 1 | Memory lives in Stronghold; Legion keeps its own persistent memory, which goes. | Legion has **no** memory store. `memory_recall.py` and `skill_recall.py` call Armory's `tool_mem_search`. The memory, skills and tickets data are SQLite files in **Armory** (`memory.db`, `skills.db`, `tickets.db`). Stronghold holds only routes and clients for them (`stronghold/src/memory/client.py`: "Account-scoped access to Armory's assistant memory"). | The Legion memory removal is not needed. The real work is a data move from Armory to Stronghold for memory, skills and tickets. |
| 2 | Armory tools that read Stronghold data are a hidden dependency. | Confirmed, in two ways. The notes tool reads Treasury directly (compose sets `DB_GATEWAY_INSTANCE: armory`, `DB_GATEWAY_CONNECTION: stronghold`). The Obsidian resolver calls Stronghold `/brains/resolve` on each request (`brain_resolver.py:41`), and the caller policy lets Armory call Stronghold for `/brains/resolve`, `/brains/instance-migration`, `/notes`, `/memory`, `/skills`, `/tickets`. | Armory does depend on Stronghold today. |
| 3 | Skills and Armory's own settings stay in Armory. | Skills are **per-user learned skills** (`skill_store.py`, owner-scoped). By the placement rule that is Stronghold data. | Spec needs correcting: skills move too. |
| 4 | Drop the extensions proxy; Legion holds outside MCP servers. | **Plan 14 (approved 2026-11-18, merged) did the opposite.** Armory is "the only service that holds the address, the credentials and the transports" of Bard, Scribe, Reader and any optional server, in `settings.db` table `connections`, with a REST façade that Stronghold and Portcullis call for speech and attachments. Stronghold and Portcullis no longer hold Bard, Scribe or Reader tokens. | Collision. Decision D1 below. |
| 5 | Notes, brains and usage tools move to Stronghold's MCP server. | Stronghold has **no** MCP server today (only `agents/mcp_session.py`, a client). **Plan 15 (merged 2026-11-19)** moved the shared Instance Brain connection *into* Armory (encrypted record in `settings.db`, revisions, migration from Stronghold). Personal brain connections stay in Stronghold. | Collision with the placement rule for brains. Decision D2 below. |
| 6 | Usage tools move to Stronghold. | Armory's usage report reads **Legion's** JSONL files (`.data/usage/YYYY-MM-DD.<agent>.jsonl`, `MCP_USAGE_DIR` defaults to Legion's data folder), not Stronghold's usage records. Legion writes those files itself, so Legion keeps durable data after all. | Two usage sources. Decision D5 below. |
| 7 | Armory stores per-account pdf and media files. | They are session-scoped files on disk with a sweeper and a **6 hour** limit (`file_ttl_seconds = 6 * 3600`), plus an in-memory download store with a **10 minute** limit and 5 MB per file. Already temporary. Armory also keeps an email delivery audit table (metadata only), Obsidian search indexes (derived, rebuildable) and server-manager watcher state (not read; verify). | Short-lived downloads are mostly built. Agreed limit of 1 hour for downloads still needs deciding against the existing 6 hours (files) and 10 minutes (downloads). |
| 8 | Stack-owned gateway instances inside Citadel's compose, internal only. | **Commit `983d0623` (2026-11-19) took both gateways out of Citadel's compose** so they run from their own repos (`AI/ModelProviders/<name>`) and join `citadel_core` as external members. Legion reaches them by name and keeps their address and token in Treasury. Every tool and model service also attaches to `citadel_core`, and `_TODO.md` plans a neutral `ai_net`. | Collision. Decision D4 below. |
| 9 | Services should start without dependencies. | Largely true already. `depends_on` in compose is a plain list (start order only, no health conditions). Registration in Treasury is a background loop that retries until accepted. There was a test for start order and Treasury outage (`5b084058`). Gaps: no `/ready` anywhere. `/health` is defined in Stronghold, Treasury and Portcullis (`/api/health`); not found in Armory or Legion by name (verify). | Rule needs only `/ready`, error codes and tool-level catching. |
| 10 | Tool error numbers 1000 to 1005. | None exist. Armory's `errors.py` returns a message with a reference id. The pdf and media capabilities have their own `ErrorCode` enums. | New work; keep the capability enums for their own codes. |
| 11 | Portcullis gets an allow/deny list and client records. | Portcullis already has an **IP filter** in `app_policy.py` (read once at start, edited on the Workspace settings page). No client records, keys, budgets or audit log for outside callers. | Build on the IP filter. |
| 12 | Treasury discovery. | Nothing exists (no probe or discover code). The catalog and pins exist (Plan 13). | New work, as planned. |
| 13 | Armory has no more dependency risk. | Armory mounts `/var/run/docker.sock` (`docker-compose.yml:43`) and Plan 14 routes user audio and documents through it. Plan 14 itself lists this risk. | Relevant to D1. |

## Decisions needed

**D1. Outside connections: Armory or Legion?**
Plan 14 put them in Armory a day before our talk. Moving them to Legion would undo it, and the speech and attachment REST façade has no natural home in Legion (an agent runtime).
Suggest: keep Armory as the holder of connection records. They are configuration of external systems, not user data, so "stateless" still holds. Drop only the idea of moving them. Then Stronghold and Portcullis stay free of tool tokens, which matches the earlier rule.

**D2. Brains and Obsidian: where do the tools live?**
Plan 15 put the shared vault connection in Armory, and Armory still asks Stronghold for personal connections on every call, which breaks "Armory never calls Stronghold".
Option A: move the whole vault tool and its indexes to Stronghold's MCP server (big: Stronghold gains sqlite-vec indexing).
Option B: Armory keeps the vault engine and the shared connection (an external system, like Plan 14 connections). Stronghold sends the personal connection with each call, as Legion already sends private extensions per turn. Armory stops calling Stronghold.
Suggest: B.

**D3. Memory, skills and tickets move from Armory to Stronghold.**
This is a data migration of three SQLite files, not a code-only change. Confirm that you want it, and confirm that per-user skills move too.

**D4. Gateways.**
Commit `983d0623` made them their own stacks one day ago. Your decision was stack instances inside the Citadel compose, internal only.
Option A: reverse `983d0623`, build the two instances into the Citadel compose on a private `llm_net`, and keep standalone copies for other projects.
Option B: keep own stacks, but add an access rule so only Legion's token works and no host port is published.
Suggest: A if you want Citadel to start alone, which was the goal.

**D5. Usage.**
Two sources exist (Legion JSONL files and Stronghold's records in Treasury). Suggest: the usage tool moves to Stronghold and reads its own records; Legion's JSONL stays as a local operational log or is dropped. Needs your call.

## Vault gaps (not synced with code)
The project note `Brain/Projects/Citadel.md` and the component notes do not mention:
- Plan 14 (tool connections in Armory, the Connections page, Armory's REST façade, Stronghold and Portcullis no longer holding Bard, Scribe, Reader tokens).
- Plan 15 (Instance Brain in Armory, the Brain page in Armory Admin, the Portcullis Admin Brain form retired).
- The gateways leaving Citadel's compose (`983d0623`), and Legion sending a tier while ConversationGateway owns model names (`b2c05872`).
- Ember changes (login after register, CORS for dev origins, server address field, read-aloud through blob URL).
- The ZimaOS layout and overlay changes, `tools/setup_env.py`, and the neutral `ai_net` plan.
- The decision note `Decision - JSON configs are tracked and secrets live in .env` still lists extensions and ticket settings as Armory runtime state; extensions are now connections.

Run the `project-sync` skill on Citadel to bring these in. I did not run it, because it rewrites the project note and your decisions D1 to D5 change what it should say.

## Not checked
- Whether Armory's server manager or watchers store durable state.
- How many tickets, memory notes and skills exist in a real deployment, and the real size of the downloads in use.
- Whether the Docker socket mount is really needed by Armory's server manager only.
- The live ZimaOS box (nothing was run).

## Resolutions (2026-11-20, same day)

All decisions were taken by the user after this audit. Details are in [the spec](../specs/2026-11-20-service-scopes-design.md).

| Decision | Outcome |
|---|---|
| D1 outside connections | MCP connections move to Legion, REST connections to Stronghold. Plan 14's Armory connection records and façade are removed. Addresses are registered once in Treasury's catalog (ids, origin rows, consumer-side backup lists). |
| D2 brains and Obsidian | Obsidian is removed for now. One personal Brain in Stronghold plus a global brain. Plan 15's Armory work is removed. |
| D3 memory, skills, tickets | All move to Stronghold. Notes, memory and skills merge into the Brain. No data migration: everything is pruned. |
| D4 gateways | Back into Citadel's compose on `llm_net`, Legion only. Reverses `983d0623`. |
| D5 usage | The usage tool is served by Stronghold from its own records. |
| Finding 1 | Corrected: Legion has no memory store; the data move is Armory to Stronghold. |
| Models | New rule: no service calls a model directly, only Legion does. Armory's Obsidian embeddings (direct Ollama) disappear with Obsidian. Ticket and triage calls already go through Legion agents (`LAYA_URL` points at a Legion agent; rename the label). |
