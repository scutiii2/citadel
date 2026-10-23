# Codex handoff prompt: calendar schedule and alerts

Paste everything below the line into Codex, started in `D:\User\Documents\Programming\Python\Citadel`.

---

You are implementing a finished design in the Citadel repo (`D:\User\Documents\Programming\Python\Citadel`, its own git repo, branch `main`). Read these first, in order:

1. `AGENTS.md` (repo rules) and `apps/Ember/ember_admin/AGENTS.md`.
2. `docs/superpowers/specs/2026-10-24-calendar-schedule-design.md` (what and why).
3. `docs/superpowers/plans/2026-10-24-calendar-schedule.md` (how: 14 tasks with exact files, code, tests and commands).

**Job:** execute the plan task by task, in order, Task 1 to Task 14. Each task is test-first: write the failing test, run it and see it fail, implement, run it and see it pass, then commit. Do not skip, merge or reorder tasks. Do not add features the plan does not list.

**Ignore the plan's tooling header.** It names Claude skills (`superpowers:*`); you do not have them. Just follow the steps in the plan.

**Rules that matter**
- Run git only inside the Citadel repo, never at `D:\User\Documents\Programming`. One commit per task, using the commit message the task gives (Conventional Commits style, as in `git log`). Do not push. Do not amend earlier commits.
- Never read or print `.env*`, `secrets/`, key files, or the real feed URLs in `D:\User\Documents\Programming\Python\CalendarViewer\feeds.json`. The CalendarViewer folder is reference only; do not edit it.
- Never add a reduced-motion setting, `prefers-reduced-motion` query or test. Animations always play.
- Data goes in db_gateway documents, not SQLAlchemy tables. There is no Alembic migration in this work.
- Skills live in `.agents/skills/` (do not touch them). Before any ember_web or ember_admin UI work, read `.agents/skills/ember-frontend-design/SKILL.md` and `.agents/skills/ember-design-system/SKILL.md`; radius only via `--radius-*`, colors only via tokens, shared code must not import from `features/`.
- Environment is Windows with Git Bash. ember_api tests: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest <path> -q` (sync tests with `asyncio.run`; no pytest-asyncio). Web and admin: `npx vitest run`, `npx vue-tsc -b`, Playwright via `npx playwright test`.
- Where the plan says to read an existing file and adapt (`ToggleSwitch` binding, `BaseModal` close button, `make_member` helper, auth store permission check), do that, keep the assertion's intent, and do not loosen it.
- If an existing test breaks because of a new setting, permission or route (exact-list assertions), update that test minimally and say so in the commit body.

**Stop and ask me instead of guessing** if: a plan step cannot work as written, a library API differs from the plan, a test you did not write fails for a reason unrelated to this work, or you would need to change a file the plan does not list (other than the minimal test fixes above).

**Report back after each task** in 3 lines: what passed (exact command and result), the commit hash, anything you changed from the plan. At the end, run the full suites for ember_api, ember_web (vitest, vue-tsc, Playwright) and ember_admin (vitest, vue-tsc) and report the real results. State plainly anything you could not run or verify. The manual smoke check in Task 14 Step 4 needs a person: list what to check and do not claim it passed.
