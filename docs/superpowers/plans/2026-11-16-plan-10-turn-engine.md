# Plan 10: Move the turn engine to Stronghold

Branch per sub-plan: `refactor/turns-<step>`. Written 2026-11-16 from the code as of `main` after Plan 9. Not executed.

## Why

Portcullis is meant to be a thin gateway: login, permission, pass-through. It still runs the chat turn itself: `services/turns.py` (844 lines, `TurnRegistry`) asks Legion over MCP, streams events to watchers, saves the answer, records usage and writes log lines. That is product logic, so it belongs in Stronghold, next to chats, usage and brains.

## What exists today (Portcullis)

| Piece | Where | Needs |
|---|---|---|
| Turn registry: running turns per account (max 3), event buffer, snapshot, subscribe, cancel, approvals, questions, discard, shutdown | `services/turns.py` | `AgentGateway` (Legion MCP), `AgentDirectory`, `ChatService` (already Stronghold-backed), `UsageClient` (Stronghold), `summarization`, `second_brain`, `question_answers`, `step_digest`, `LogWriter` (Portcullis DB), `Pricing` |
| Routes: start, events (SSE), approvals, questions, cancel; also `running` flags on chat list/get/delete/folder delete, suggestion, summarize | `routes/chats.py`, `routes/chat_folders.py` | everything above |
| Start-turn assembly: agent entry, usage block, brain permission, forced tool approval, disabled agents, extension ids (Armory), private extensions, own limits, `tools.execute` permission | `routes/chats.py::start_turn` | Portcullis settings DB, Stronghold, Armory, Legion |
| Legion MCP client and registry reader | `services/agent_gateway.py` (261), `agent_directory.py` (333), `mcp_session.py` | `LEGION` registry file or URL, internal token |
| Helpers also used elsewhere | `suggestions.py`, `summarization.py`, `extension_probe.py` (Portcullis admin) | `AgentGateway` |

## Target

Stronghold owns `/turns`: it holds the registry, calls Legion, saves the answer, records usage. Portcullis only checks login and permission, adds what only it knows, and passes through, including the SSE stream.

```
browser/Ember --Portcullis (login, permission, force-approval flag, tools.execute, extension ids)--> Stronghold /turns --> Legion (MCP)
                                                          <-- SSE pass-through of /turns/{chat}/events
```

## Decisions to settle first (answered below)

1. **Running state is in memory.** Two Stronghold replicas would each see only their own turns. Either Stronghold stays one replica for turns (document it, say so in compose), or running state moves to Treasury. Recommend: one replica, same as Portcullis today.
2. **Who builds the turn options.** Recommend Portcullis sends a small trusted block with the request (`forced_approval`, `tools_execute`, `extension_ids`), and Stronghold fills the rest itself (disabled agents, private extensions, limits, usage check, brain scope). That keeps Stronghold off Portcullis's settings DB. Private extensions and account agents are Treasury documents Portcullis reads today (`UserExtensionService`, `AccountAgentService`): move them to Stronghold first (10.1) or Stronghold cannot fill them.
3. **Logs.** `LogWriter` writes Portcullis's DB (error log, chat-trace log, shown in `stronghold_admin` Analytics). Options: Stronghold calls a new internal `POST /internal/logs` on Portcullis (recommended: admin pages keep working, one log store), or Stronghold keeps its own log. The Portcullis `PortcullisClient` already exists in Stronghold (used for permissions).
4. **Legion access from Stronghold.** Stronghold needs the Legion registry (file or URL) and the internal token; today only Portcullis has them. Add `LEGION_REGISTRY` / URL settings to Stronghold and compose.
5. **SSE pass-through.** `pass_on` buffers; the events route needs a streaming pass-through that survives long idle gaps and client disconnects (cancels the upstream read, never the turn).

## Decided (owner, 2026-11-16)

1. One Stronghold replica runs turns. Say so in `docker-compose.yml`. State stays in memory.
2. Stronghold fills most turn options. Portcullis sends only `forced_approval`, `tools_execute` and `extension_ids`. So 10.1 (account agents and private extensions to Stronghold) comes first.
3. Turn error and chat-trace logs go to a new Portcullis `POST /internal/logs` (internal token, same as the permissions route).
4. `extension_probe` and the admin Agents pages stay in Portcullis for now, with their own copy of the Legion gateway. Duplicate code until a later plan.
5. Not asked, taken as recommended: Stronghold gets Legion's registry and the internal token through its own settings and compose; the events route gets a streaming pass-through.

## Steps

| Step | Result | Notes |
|---|---|---|
| 10.1 | **Done 2026-11-16** (`2026-11-16-plan-10-1-agents-extensions.md`): account agents and private extensions (domains) move to Stronghold, with purge routes | Same method as Plan 5 sub-plans. Needed so Stronghold can build turn options. |
| 10.2 | Legion client in Stronghold: `AgentGateway`, `AgentDirectory`, `mcp_session`, `Caller` copied and adapted; config, compose, tests with a fake gateway | **Done 2026-11-16.** The gateway, directory and `mcp_session` were already in Stronghold; its gateway test file was missing and is ported (31 tests). Compose says one replica. Portcullis keeps its copy while `extension_probe` still uses it. |
| 10.3 | Stronghold `/turns`: registry, publish, subscribe, cancel, approvals, questions, discard, summarization, suggestions, second-brain request, usage record, log client. Tests ported from `tests/test_turns*.py` and `test_chat_turns*.py` | **Done 2026-11-16** (`2026-11-16-plan-10-3-stronghold-turns.md`). The bulk. `TurnRegistry` is copied nearly as is; its DB handle goes away (it only keeps it). |
| 10.4 | Portcullis routes become pass-throughs; `get_turns` and `TurnRegistry` removed; `running` flags come from Stronghold (`GET /turns/running`, folder delete and chat list ask it); streaming pass-through for events; FakeUpstream gains turn fakes | **Done 2026-11-16** (`2026-11-16-plan-10-4-portcullis-passthrough.md`). Public `/api/chats/{id}/turns|events|approvals|questions|cancel` unchanged. |
| 10.5 | Shutdown and restart: Stronghold marks running turns interrupted on stop (as `shutdown()` does now); Portcullis lifespan drops `turns.shutdown()` | Check two things in a real run: a turn survives a Portcullis restart, and a Stronghold restart saves partial text. |
| 10.6 | Cleanup: delete Portcullis `turns.py`, `summarization.py`, `question_answers.py`, `step_digest.py`, `second_brain.py`, `suggestions.py` and their tests; docs, vault, roadmap | Keep `agent_gateway`/`agent_directory` in Portcullis only if `extension_probe` and admin agent pages still need them. |

## Risks

- Streaming and cancellation are where bugs hide: a dropped SSE client must not cancel the turn; a cancel must reach Legion's `request_id`. Test both with real timing, not only fakes.
- Event order and the replay `after` counter must stay exactly as now, or the browser shows duplicated or missing text.
- Moving 10.1 first changes two more domains' purge lists in `admin.py`.
- Portcullis's suite is about 17 to 27 minutes; each sub-plan runs it once at the end.

## Not decided here

- Whether `extension_probe` and the admin Agents pages should also move (they use the same gateway).
- A task queue or a persisted running state (only if replicas are wanted).
