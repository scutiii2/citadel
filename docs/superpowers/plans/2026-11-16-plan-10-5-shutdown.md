# Plan 10.5: shutdown and restart

Branch `refactor/turns-10-5`.

## State
- Stronghold `TurnRegistry.shutdown()` (called in the lifespan `finally`) cancels running turns; `_run` catches the cancel and saves the text so far as an interrupted answer. Test: `test_shutdown_saves_what_streamed_as_interrupted`, now also checks `GET /turns/running` is empty afterwards.
- Portcullis holds no turn state any more (lifespan has no `turns.shutdown()`), so a Portcullis restart cannot touch a running turn. The browser reconnects to `/events` with `Last-Event-ID`.

## Change
- `docker-compose.yml`: `stop_grace_period: 30s` on `stronghold`, so the partial text is saved before SIGKILL.

## Not verified
- No live run: a real Portcullis restart during a turn, and a real Stronghold stop with Treasury up.
