# Plan 8: Disable ember_web

Branch: `chore/disable-ember-web`.

## Result

- `ember_web` removed from `docker-compose.yml` and the ZimaOS overlay. Port 26502 is free.
- `apps/ember_web` stays as reference for Plan 9; its README opens with a "Reference only" note.
- `docs/deployment.md`: service table marks it disabled, quick-start and ZimaOS link steps no longer open it, the Funnel section says it applies again when a user web app returns.
- `tools/publish_live.py` no longer publishes `apps/ember_web`.
- `AGENTS.md` still names `apps/ember_web` for UI work (the skills use it as the design reference).

## Not done

- Docker not run. `docker compose config` stops on the missing gateway admin passwords in the root `.env`, so the compose edit was checked by reading only.
- Users have no web chat until Plan 9 ships the Windows app.
