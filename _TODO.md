# _TODO.md

Deferred items — not scheduled, revisit when the trigger condition below is met.

## server_manager capability page (added 2026-10-06)

**Context**: Capability pages are built (spec: `docs/superpowers/specs/2026-10-06-capability-pages-design.md`); only `generator` has a `gui/page.json`. `server_manager` (start, stop, restart, list Docker apps on the host; fetch an app's log) is the other built-in capability. Skipped for now.

- **Simple page, no code change**: a `gui/page.json` with an app list `table` (`tool_srv_listApps`) and one form each for start, stop and restart (typed container name; a dropdown needs an `options_url` on the tool's `name` parameter).
- **Proper control panel, needs the page format extended**: row actions on a table (a Start/Stop/Restart button per app), download cards (so the log download works on the page), and several tools in one section (a list that refreshes after an action).
- Note: these tools are not approval-gated; anyone with `tools.use` could stop any app on the host (see the capability README).

**Revisit when**: user wants it built.

## Verify Firecrawl against the live API (added 2026-10-07)

The capability exists at `apps/armory/src/capabilities/firecrawl/`, but its tests mock HTTP calls. Live verification remains:

- Configure `FIRECRAWL_API_KEY` if needed, or use `FIRECRAWL_API_URL` for self-hosted Firecrawl.
- Try `/scrape page` on a real URL, then check map links and crawl `data` against the v2 response shapes.

## Verify the Docker deployment end to end (rewritten 2026-10-25)

**Done**: Dockerfiles for every service, one root `docker-compose.yml` (`core` network, service-name URLs, `0.0.0.0` binds), the Zima overlay, container-only configs in `docker/configs/`, volumes for the data folders, the Docker socket mounted into `armory`, Laya (`laya` replicas behind `laya_lb`, built from `../LayaModel`) in the stack, `dev_deploy.bat` per service and `tools/deploy.bat` (publish to `live`, push `.env` and `config_*.json`, set `COMPOSE_FILE` on the server). `server_launcher` and the per-app `run.bat` files are gone. See `docs/deployment.md`.

**Still to verify** (none of it has been run on the box):
- `tools/deploy.bat` against the real server: option 2 (one-session `tar` push as `lex`, `COMPOSE_FILE` line, the chown helper) and option 1 (publish to `origin/live`). Same for `LayaModel/tools/deploy.bat` and `Bard/tools/deploy.bat` (Bard: publish creates `origin/live`; first start downloads the Piper voice).
- Bard in the stack: start Citadel, then `Bard` (`docker compose up -d --build` there), restart armory, and check `bard__tool_bard_speak` plays in chat.
- A full `docker compose up -d --build` on ZimaOS with `LayaModel` next to `Citadel`, then `tool_srv_listApps` returning the `citadel-*` containers.
- `LAYA_URL=http://legion:9111/mcp` in `apps/armory/.env`: confirm legion listens on 9111 inside the container and tickets get grouped.
- Self-stop: `/server stop armory` kills the server running the tool; expected, but it cannot be restarted from the same chat.

**SMTP credential rotation (repository cleaned 2026-10-09)**: `zima_host.yaml` is deleted (2026-10-25), but its old inline password remains in Git history. Still required: revoke the exposed password at the mail provider, put a replacement `SMTP_PASSWORD` in the deployment `.env`, recreate the container and verify email delivery.

**Revisit when**: the next deploy to the box.

## Verify specialist agents and consider follow-up features (added 2026-10-07)

The agents are implemented. These manual checks remain unverified:

- **Email Assistant** (`email-assistant`, port 9112): paste an email and check its summary, triage and draft reply.
- **Data Analyst** (`data-analyst`, port 9113): attach a CSV, ask for a total and a top 5, and check the results.
- **App Monitor** (`scheduler`, port 9114): verify an explicitly requested app start shows `watched`, and a crash sends the original owner an email. URL/port checks and recurring schedules are unavailable.
- **Ember routing**: check delegation across the specialist roster with Laya routing enabled.

Optional follow-up features, not implemented:

- **Email**: read-only IMAP mailbox access, then saved drafts. Decide credentials in `.env` and treat mail content as untrusted. The existing email service provides SMTP sending for capability-owned JobWatchers, including ServerWatcher.
- **Data analysis**: sandboxed code execution, `.xls` support, charts and downloadable results.
- **Scheduling**: recurring monitoring, alerts on every change, log/file patterns, other recipients (requires an allowed-domains rule), SMS or push.

**Revisit when**: user wants the manual checks run or picks a follow-up feature.

## Sandboxed workspace for ai_agent (added 2026-10-09)

**Context**: Items 1 to 6 of the 2026-10-09 agentic-harness review (budget guard, delegated cancel, plan tool, tool-activity persistence, compaction, persistent memory) are done. One remains.

**Open**: a sandboxed workspace (files and shell): an isolated per-user directory and a limited command runner, fitted to the approval flow. Real security risk. Best as a new `mcp_server` capability, not inside `ai_agent`. Hardest. Also open from the memory work: retry or periodically sweep failed memory purges (a purge is best effort today: orphaned notes stay when mcp_server was unreachable or had no token).

**Revisit when**: user wants to tackle a sandboxed workspace; brainstorm that design first.

## Chess: standalone project (added 2026-10-09, backend built 2026-10-16, decoupled 2026-10-19)

**Context**: `Python/chess` is its own project, not part of Citadel or Ember. A conventional engine proposes and scores moves and its own local Laya picks among the top candidates, with the engine's best move as fallback. Laya is required, not optional. Port 8070, renamed from `mini_games` 2026-10-16. Spec 1 (backend, 144 tests, Laya eval in `docs/laya-eval.md`) merged as `8c4dc28e`.

**Dropped 2026-10-19**: the `ember_api` proxy with an `ember_web` page (old spec 2) and the mcp_server/armory chat tools (old spec 3). Chess does not use legion; it has its own Laya client.

**To do** (tracked in `Brain/Projects/chess.md`; chess has no git repo yet): (run.bat and 103 tests pass 2026-10-19; Tetris removed, chess only) `git init`; own UI; an autonomous brain; decide the auth headers and the folder name; session persistence.

**Optional phase 2**: stronger chess engine, `Python/chess/docs/phase-2-stronger-engine.md`. Stockfish, if added, is a separate picker; Laya stays.

**Revisit when**: user continues chess; start with the to-do list above.

## Context breakdown for delegated agents (added 2026-10-17)

**Context**: The context panel (opened from the header's context meter) breaks the answering agent's prompt into system prompt, delegable agents, built-in tools, MCP tools and messages, estimated or counted by the provider (`apps/legion/src/providers/context_breakdown.py`). When the orchestrator delegates, each specialist runs its own prompt, and none of that is broken down.

- Each agent would build its own breakdown; `ai_agent` already returns one usage row per agent in `agent_usage`.
- `ember_api` would pass each agent's breakdown along with its usage row (`AgentUsageIn` in `routes/chats.py`), and the panel would add a per-agent section.
- Open question: a specialist's prompt never fills the orchestrator's window, so this answers "what did each agent's prompt cost", not "how full is my context". Decide if that is worth a panel section before building.

**Revisit when**: user wants to see where a delegated answer's tokens went.

## Make chat Stop (cancel) near-instant (added 2026-10-18)

**Context**: Stop in the Ember chat page is cooperative. `ember_web` `chat.stop()` calls `POST /chats/{id}/cancel`, `TurnRegistry.cancel` (`apps/Ember/ember_api/src/services/turns.py`) sets `cancel_requested`, publishes `cancelling`, and forwards `cancel` to ai_agent. There the flag in `apps/legion/src/providers/cancellation.py` is checked only between provider rounds (`anthropic_provider.py`, `openai_provider.py`), so an LLM call or tool call already running finishes first. Approval and question waits already poll the flag.

**Plan**, by payoff:
1. **Abort the in-flight LLM call**: check the flag per streamed chunk and close the HTTP stream on cancel, then raise `ChatCancelled`. The partial text is already kept (`turns.py`). `bind_request` already carries a per-turn `threading.Event` into worker threads.
2. **Abort running tool calls**: `dispatch_with_progress` stops waiting and raises `ChatCancelled`. Python cannot kill a thread, so the tool runs on as an orphan. Safe for read-only tools; decide per tool for ones with side effects. Check that the delegation loop (`delegation.py`) polls fast enough.
3. **Instant UI in ember_api**: finish the turn at once on cancel (save the streamed text, publish `final` with `cancelled: true`, drop later agent events) while the agent cancel runs in the background. Risk: the next turn in that chat must not overlap the orphaned one.

**Also check**: a failed gateway cancel is only logged (`turns.py` `cancel`), so the user sees "stopping ..." while the turn keeps running; and cancel arriving between `turn.asking = True` and the request being sent may be missed.

**Revisit when**: user wants Stop to feel instant. Read the provider streaming code and `dispatch_with_progress` first, then propose the exact change for step 1.

## Frontend for db_gateway (added 2026-10-18)

**Context**: `apps/treasury` is backend only (`auth.py`, `config.py`, `registry.py`, `run.py`, `seed.py`, `backends/`); no UI exists. Only `ember_web` (`NotesView.vue`, `NotesClient.ts`) touches it, as a notes feature. Build a gateway frontend that uses the ember_web and ember_admin designs (shared tokens, components, radius scale, in-app confirms).

- Decide first which app hosts it (likely `ember_admin`, since it is an admin tool) and which gateway routes it needs; check `registry.py` and `run.py` for the API.
- Follow the `ember-frontend-design` and `ember-feature-scaffold` skills; any new `ember_api` route proxies to the gateway behind a permission.

**Revisit when**: user wants it built. Brainstorm the design first.

## Full cross-provider gateway fallback (added 2026-10-19)

**Context**: An agent's gateway list (primary plus `llm.fallback_gateways`) is limited to one provider. `AgentForm.vue` shows only the selected provider's gateways and resets the list when the provider changes. In legion, `fallback_gateways` entries accept only `gateway` and `model` (`apps/legion/src/agents/agent_spec.py`), and failover lives inside each provider module (`openai_provider.py`, `anthropic_provider.py`), which each read only their own gateway files. Anthropic and OpenAI use different message and tool-call formats, so a mid-turn switch needs the history converted.

**Plan**:
- **Spec**: add an optional `provider` to each fallback entry (default: the agent's provider). Validate it in `agent_spec.py`, `agent_config.py` and `agent_store.py`.
- **Failover above the providers**: move the retry loop out of the provider modules so a failed round can be retried on another provider. Keep completed tool results; strip gateway-bound thinking/reasoning.
- **History converter**: convert Anthropic and OpenAI message and tool-call history both ways, including tool results already collected in the turn.
- **ember_api**: pass the new field through the agent admin routes and validation.
- **ember_admin**: one gateway list across providers, each row labelled with its provider (`AgentForm.vue`, `AgentGatewayList.vue`); stop resetting rows on provider change.
- **Docs and tests**: README "Gateway failover" and the `aiagent-scaffold` skill; unit tests for the converter and failover order.

**Cheaper first step**: fail over to the other provider between turns only (the next turn starts fresh on the backup), which skips the converter.

**Revisit when**: user wants it built. Brainstorm the failover design first.

## Move Treasury out of Citadel into its own stack (added 2026-10-28)

**Context**: `apps/treasury` (the db_gateway) lives inside Citadel and ships in the root `docker-compose.yml`. It should deploy as its own stack, because other services will use it too, not just Citadel.

- Move it to its own project folder with its own repo, `docker-compose.yml`, `.env` and `tools/deploy.bat` (like `LayaModel` and `Bard`).
- Citadel services that call it (`ember_api` notes, `NotesClient.ts` path) reach it by URL on a shared Docker network, not by service name inside the `core` network.
- Remove it from Citadel's root compose, `docker/configs/`, `tools/deploy.bat`, `docs/deployment.md` and the Citadel docs and vault note.
- Check auth: other services need their own tokens or clients in `auth.py` and `registry.py`.
- Update the "Frontend for db_gateway" item above, since the gateway frontend then lives with Treasury.

**Revisit when**: user wants it built. Brainstorm the split first.
