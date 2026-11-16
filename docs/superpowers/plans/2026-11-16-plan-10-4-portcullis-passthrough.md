# Plan 10.4: Portcullis turn routes become pass-throughs

Step 10.4 of [Plan 10](2026-11-16-plan-10-turn-engine.md). Executed 2026-11-16 on `refactor/turns-10-4`. The public `/api/chats/{id}/turns|events|approvals|questions|cancel|summarize|clear|suggestion` paths and bodies are unchanged.

## Done (Portcullis)

- `routes/chats.py`: start builds the `trusted` block (`forced_approval` from the admin switch, `tools_execute` from the account's permissions, `extension_ids` from Armory, `second_brain_available` for the one scope the turn would use, only when auto-save is wanted) and overwrites any `trusted` key from the browser. The 202 answer is rebuilt in the browser's shape (`id`, `running: true`). Approvals add `forced_approval`, and Portcullis writes the `tool.approval` log line from Stronghold's `tool` and `decision`; the browser still gets only `{"decided": true}`. Summarize and clear answer as `ChatOut`. Suggestion is skipped (`{text: null}`) when the account switched suggestions off.
- Events: `StrongholdForwarder.open_stream` plus a relay. A browser that leaves ends only the relay; the turn goes on in Stronghold. Stronghold's 4xx on the stream (404 no turn) comes back unchanged, 5xx is a 502. `Last-Event-ID` is turned into `after`.
- Running flags, put/append refusals, chat and folder deletes use `GET /turns/running`, `DELETE /turns/{chat}`, `DELETE /turns` (`services/stronghold_turns.py`). If Stronghold cannot say what runs, the write is refused (502) rather than guessed.
- Account delete also purges `/turns/accounts/{uid}`.
- `TurnRegistry`, `get_turns` and the lifespan shutdown call are gone from the app. `services/turns.py` and its helper modules are unused now and go in 10.6.

## Tests

- Portcullis: new `tests/test_turn_passthrough.py` (33 tests) on a new `tests/fake_turns.py` that `FakeUpstream` serves under `/turns`; `tests/turn_helpers.py` for the shared `start/events/chat`.
- Removed from Portcullis because the behaviour now lives in Stronghold and its tests: `test_turns`, `test_approvals`, `test_questions`, `test_suggestions`, `test_plan_events`, `test_agent_events`, `test_user_extension_turn`, `test_step_digest`, `test_summarization_steps`, the turn tests inside `test_account_agents`, `test_account_tuning`, `test_branch`, `test_chat_folders`, `test_usage_client`, `test_logs`, `test_second_brain`, and the turn half of `test_forced_approval` (the switch tests stay).
- Stronghold gained ports: `test_turn_approvals`, `test_turn_agent_events`, `test_turn_plan_events`, `test_turn_extensions`, `test_turn_extras` (storage failures, usage trouble, chat trace content and prompt clipping).

## Behaviour changes to know

- With suggestions switched off, `GET /suggestion` no longer 404s for an unknown chat; it answers `{text: null}`.
- An unknown `trusted` input is never trusted: Stronghold's defaults (every tool asks, no tools, no extensions, no auto-save) apply if Portcullis sent none.
- One extra Stronghold call per chat write and per list (the running ids).
- Not run against a live Stronghold, Legion or browser: an SSE stream through a real reverse proxy is untested here.

## Open

- 10.5: restart and shutdown behaviour in a real run.
- 10.6: delete `services/turns.py`, `summarization.py`, `question_answers.py` (Portcullis still imports `question_answers` for the request model limits), `step_digest.py`, `suggestions.py`, the unused part of `second_brain.py` (keep `available`), their tests, docs, vault.
