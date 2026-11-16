# Plan 10.3: Stronghold `/turns`

Step 10.3 of [Plan 10](2026-11-16-plan-10-turn-engine.md). Executed 2026-11-16 on `refactor/turns-10-3`. Stronghold only gains the turn engine; Portcullis still runs its own copy until 10.4, so nothing a browser sees has changed.

## Done

- `apps/stronghold/src/turns/`: `engine.py` (`TurnRegistry`, `Turn`, `TurnOptions`: the Portcullis engine with the account id replaced by the uid, chats read and written through `ChatStore`, usage through `UsageService`), `routes.py`, `logs.py`, and the helpers moved over unchanged: `summarization`, `suggestions`, `question_answers`, `step_digest`, `second_brain.save_request`.
- Routes under `/turns`: `POST /{chat}` (start), `GET /{chat}/events` (SSE), `/approvals`, `/questions`, `/cancel`, `/summarize`, `/clear`, `GET /{chat}/suggestion`, `GET /running`, `DELETE /{chat}`, `DELETE /`, `DELETE /accounts/{uid}`.
- Stronghold now builds the rest of the turn options itself: entry agent, usage check (429), saved auto-save preference, switched-off agents (503 when unreadable), private extensions (a notice when unreadable), the account's own limits.
- `usage` settings gain `max_context_tokens_per_chat` and `auto_summarize_ratio` (they were Portcullis's); `with_cost` moved next to `Pricing`. `docker/configs/stronghold/app.json` carries both.
- Logs: `PortcullisClient.write_log` posts to the new Portcullis `POST /internal/logs` (`error` and `chat_trace`, source names `chat.answer` and `chat.turn` kept, so the admin Logs pages show them as before). The route and its test are in Portcullis.
- The registry is created at start and `shutdown()` runs on stop, so a running turn saves what it has, marked interrupted.
- Tests: 41 new turn route tests (`tests/test_turns.py`, with `tests/turn_agent.py` as the Legion stand-in), plus the pure tests ported (digest, summarization, question answers, suggestion helpers).

## Deviations from Plan 10

- The `trusted` block has a fourth field, `second_brain_available`. Whether auto-save may use a brain needs the account's permissions, Armory's capability list and the brain connection check; Portcullis already does that for the chat PATCH route, so it sends the answer per scope. `second_brain.available` therefore stays in Portcullis (10.6 must not delete it).
- `POST /turns/{chat}/approvals` returns `tool` and `decision` besides `decided`, so Portcullis can write the `tool.approval` log line after the pass-through. 10.4 must strip them from what the browser gets.
- Portcullis must overwrite `trusted` in every request body it passes on (10.4). Stronghold's defaults are the safe side (every tool asks, no tools, no extensions, no auto-save).

## Open for 10.4 and later

- Portcullis routes, the streaming pass-through, `running` flags, `FakeUpstream` turn fakes.
- Owner action: copy `max_context_tokens_per_chat` and `auto_summarize_ratio` into Stronghold's `config_app.json` if the values differ from the defaults (150000 and 0.6).
- Not run against a live Legion, Treasury or Portcullis.
