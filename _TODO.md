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

**Done**: Dockerfiles for every service, one root `docker-compose.yml` (`core` network, service-name URLs, `0.0.0.0` binds), the Zima overlay, container-only configs in `docker/configs/`, volumes for the data folders, the Docker socket mounted into `armory`, Laya (`laya` replicas behind `laya_lb`, built from `../LayaAgent`) in the stack, `dev_deploy.bat` per service and `tools/deploy.bat` (publish to `live`, push `.env` and `config_*.json`, set `COMPOSE_FILE` on the server). `server_launcher` and the per-app `run.bat` files are gone. See `docs/deployment.md`.

**Still to verify** (none of it has been run on the box):
- `tools/deploy.bat` options 1 to 3 against the real server: the `scp` copies, the `COMPOSE_FILE` line written over `ssh`, and the publish to `origin/live`.
- A full `docker compose up -d --build` on ZimaOS with `LayaAgent` next to `Citadel`, then `tool_srv_listApps` returning the `citadel-*` containers.
- `LAYA_URL=http://garrison:9111/mcp` in `apps/armory/.env`: confirm garrison listens on 9111 inside the container and tickets get grouped.
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

## Close the agentic-harness gaps in ai_agent (added 2026-10-09)

**Context**: Review on 2026-10-09 found `apps/garrison` is a tool-calling agent runtime with delegation and approvals (tool loop in `src/llm/anthropic_provider.py` and `openai_provider.py`, `delegate_to_agent`, `approvals.review`, `ask_user`), not yet a full agentic harness. Missing pieces, easiest first. Do them together as one batch.

1. **Budget and stuck-loop guard — done** (`160df65`): shared guard in both provider loops; per-agent `llm.max_turn_tokens` and `llm.max_turn_seconds` beside `max_tool_rounds` (defaults 100,000 tokens / 300 seconds). Stops before a third consecutive identical tool call; intervening work resets the repetition count. Tokens are checked at response boundaries, so one response can exceed the cap.
2. **Cancel through delegation — done** (`1d8f203`): unique child request IDs linked to the parent; forwards Stop to each peer's MCP `cancel` tool. Deadline cancellation survives parent cleanup and late delegate startup; late worker events are dropped. Cancellation remains cooperative for tools already running.
3. **Plan/todo tool — done** (`5069200`): local `update_plan` tool with per-turn pending / in_progress / done checklists, offered by both providers. Live `plan_update` snapshots retain delegated-agent identity; small Ember API pass-through, reconnect snapshots, and Ember web panel make them visible.
4. **Tool-activity persistence across turns — done** (`55f1a1f`, `705340f`, `a92e059`): an answer's stored `steps` now reach the model as a text digest (`apps/Ember/ember_api/src/services/step_digest.py`). The last 3 tool-using answers carry full lines (args cut to 200, results to 300, block to 1,500 characters); older ones carry tool names only, also capped at 1,500 characters. `update_plan` and `ask_user` are skipped. The block is labelled as a record, not instructions; built at send time and never stored. Spec: `docs/superpowers/specs/2026-10-09-tool-activity-digest-design.md`.
5. **Compaction/summarizing — mostly existed, remainder done**: summarizing already lived in `ember_api` (`services/summarization.py`: auto at `auto_summarize_ratio` 0.6, manual button, 2,000-token cap, raw `log_attachment`), and `ai_agent`'s `trim_history_to_fit` is only a fallback. What was missing, the summarizer seeing tool results, is covered by item 4 (`render_messages(include_steps=True)` in the summary prompt only).
6. **Persistent memory — done** (`9cf776f`, `6950a67`): a `memory` capability in `apps/armory/src/capabilities/memory/` (tools `tool_mem_save`, `tool_mem_search`, `tool_mem_forget`; slash commands `/memory save|search|forget`); per-user notes in SQLite with FTS5 at `specifics/memory/.data/memory.db`, 500 characters per note and 200 notes per user; the model saves only user-stated facts (a tool-description rule, not enforced by code); recall is on demand. Known weakness: the model must remember to search. Next step if that proves unreliable: automatic recall injected each turn. Spec: `docs/superpowers/specs/2026-10-10-persistent-memory-design.md`.
   Follow-ups:
   1. **Done** (`cc675cd`, `118a4b2`, `1e2a0d6`, `0c90aba`, `61c495f`): notes are keyed on a stable account uid and purged when an account is deleted (spec docs/superpowers/specs/2026-10-10-memory-owner-uid-design.md).
   2. **Done**: `apps/garrison/agents/reviewer.json` now has `"tools": { "deny": ["tool_mem_*"] }`, so the reviewer agent (the only specialist without a tool scope) cannot save notes from other agents' output; a test pins it against the real memory tool names.
   3. **Done**: every memory tool refuses when `MCP_HOST` is not loopback and `INTERNAL_API_TOKEN` is empty (`is_exposed_without_token` in `apps/armory/src/services/internal_token.py`, also used by the startup banner); it cannot tell a container port published only to localhost, so such a setup needs the token too.
   4. **Done** (`a84ebbe`, `6bf32ae`): the entry agent loads the newest notes at the start of each turn (agent-file key `memory_recall`, `apps/garrison/src/agents/memory_recall.py`; spec docs/superpowers/specs/2026-10-10-memory-auto-recall-design.md). Relevance-ranked recall and recall for specialist agents are not built.
   5. Retry or periodically sweep failed memory purges (a purge is best effort today: orphaned notes stay when mcp_server was unreachable or had no token).
7. **Sandboxed workspace (files and shell)**: isolated per-user directory and a limited command runner, fitted to the approval flow. Real security risk. Best as a new `mcp_server` capability, not inside `ai_agent`. Hardest.

Items 1 to 6 are complete; item 7 remains open.

**Revisit when**: user wants to tackle a sandboxed workspace; brainstorm that design first.

## Chess: standalone project (added 2026-10-09, backend built 2026-10-16, decoupled 2026-10-19)

**Context**: `Python/chess` is its own project, not part of Citadel or Ember. A conventional engine proposes and scores moves and its own local Laya picks among the top candidates, with the engine's best move as fallback. Laya is required, not optional. Port 8070, renamed from `mini_games` 2026-10-16. Spec 1 (backend, 144 tests, Laya eval in `docs/laya-eval.md`) merged as `8c4dc28e`.

**Dropped 2026-10-19**: the `ember_api` proxy with an `ember_web` page (old spec 2) and the mcp_server/armory chat tools (old spec 3). Chess does not use garrison; it has its own Laya client.

**To do** (tracked in `Brain/Projects/chess.md`; chess has no git repo yet): (run.bat and 103 tests pass 2026-10-19; Tetris removed, chess only) `git init`; own UI; an autonomous brain; decide the auth headers and the folder name; session persistence.

**Optional phase 2**: stronger chess engine, `Python/chess/docs/phase-2-stronger-engine.md`. Stockfish, if added, is a separate picker; Laya stays.

**Revisit when**: user continues chess; start with the to-do list above.

## Ascension (dropped from this repo, 2026-10-25)

`apps/ascension` is no longer in Citadel: its design docs, plans, specs and `docker/configs/ascension` were deleted, and only the `0013_ascension_permission.py` migration remains. The old items (card images in the UI, splitting Ascension out of `mini_games`, the game host at `/games`) are closed here. If the game returns as its own project, track its card-image work there.

## Context breakdown for delegated agents (added 2026-10-17)

**Context**: The context panel (opened from the header's context meter) breaks the answering agent's prompt into system prompt, delegable agents, built-in tools, MCP tools and messages, estimated or counted by the provider (`apps/garrison/src/llm/context_breakdown.py`). When the orchestrator delegates, each specialist runs its own prompt, and none of that is broken down.

- Each agent would build its own breakdown; `ai_agent` already returns one usage row per agent in `agent_usage`.
- `ember_api` would pass each agent's breakdown along with its usage row (`AgentUsageIn` in `routes/chats.py`), and the panel would add a per-agent section.
- Open question: a specialist's prompt never fills the orchestrator's window, so this answers "what did each agent's prompt cost", not "how full is my context". Decide if that is worth a panel section before building.

**Revisit when**: user wants to see where a delegated answer's tokens went.

## Make chat Stop (cancel) near-instant (added 2026-10-18)

**Context**: Stop in the Ember chat page is cooperative. `ember_web` `chat.stop()` calls `POST /chats/{id}/cancel`, `TurnRegistry.cancel` (`apps/Ember/ember_api/src/services/turns.py`) sets `cancel_requested`, publishes `cancelling`, and forwards `cancel` to ai_agent. There the flag in `apps/garrison/src/llm/cancellation.py` is checked only between provider rounds (`anthropic_provider.py`, `openai_provider.py`), so an LLM call or tool call already running finishes first. Approval and question waits already poll the flag.

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

**Context**: An agent's gateway list (primary plus `llm.fallback_gateways`) is limited to one provider. `AgentForm.vue` shows only the selected provider's gateways and resets the list when the provider changes. In garrison, `fallback_gateways` entries accept only `gateway` and `model` (`apps/garrison/src/agents/agent_spec.py`), and failover lives inside each provider module (`openai_provider.py`, `anthropic_provider.py`), which each read only their own gateway files. Anthropic and OpenAI use different message and tool-call formats, so a mid-turn switch needs the history converted.

**Plan**:
- **Spec**: add an optional `provider` to each fallback entry (default: the agent's provider). Validate it in `agent_spec.py`, `agent_config.py` and `agent_store.py`.
- **Failover above the providers**: move the retry loop out of the provider modules so a failed round can be retried on another provider. Keep completed tool results; strip gateway-bound thinking/reasoning.
- **History converter**: convert Anthropic and OpenAI message and tool-call history both ways, including tool results already collected in the turn.
- **ember_api**: pass the new field through the agent admin routes and validation.
- **ember_admin**: one gateway list across providers, each row labelled with its provider (`AgentForm.vue`, `AgentGatewayList.vue`); stop resetting rows on provider change.
- **Docs and tests**: README "Gateway failover" and the `aiagent-scaffold` skill; unit tests for the converter and failover order.

**Cheaper first step**: fail over to the other provider between turns only (the next turn starts fresh on the backup), which skips the converter.

**Revisit when**: user wants it built. Brainstorm the failover design first.
