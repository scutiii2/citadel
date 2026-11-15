# Plan 5.3: Templates and skills move to Stronghold

Branch: `refactor/stronghold-templates-skills`.

## Tasks

1. Stronghold `src/templates/`: store and `/templates` routes (collection `prompt_templates`), `DELETE /templates/accounts/{uid}`.
2. Stronghold `src/skills/`: Armory client and `/skills` routes, `DELETE /skills/accounts/{uid}`. The client shares Armory's HTTP client with memory.
3. Portcullis: `/api/templates` and `/api/skills` pass the request on after the `chat.use` check. Account delete purges skills and templates through Stronghold. `services/template_service.py` and `services/skills.py` removed.
4. Tests: the behavior tests moved to Stronghold; Portcullis keeps login, permission, pass-through and purge tests.

## Accepted behavior changes

1. Templates start empty: they are stored in Stronghold's own database. No migration, as decided. Skills are unchanged; Armory still keeps them.
2. Skill action log lines ("Edited a skill") are sent to Portcullis after the action. If that call fails the action still succeeds and the line is lost.
3. When Stronghold is down, `/api/templates` and `/api/skills` answer 502 `Stronghold is unavailable`. When only Armory is down, skills still answer 503.
4. A failed template purge on account delete is logged as `admin.templates_purge` (before: `admin.settings_purge`). A failed skills purge keeps the source `admin.skills_purge`; its message now says Stronghold did not confirm.
5. Portcullis no longer validates template and skill bodies; Stronghold does, with the same rules and the same 422 answers. Portcullis still refuses a malformed id with 422.

## Execution notes (2026-11-15)

- Executed in full. Stronghold suite: 236 passed. Portcullis: full-suite result is in the commit message.
- Not run: Docker builds; Stronghold calling a real Armory for skills; the Templates and Skills pages in a browser.
