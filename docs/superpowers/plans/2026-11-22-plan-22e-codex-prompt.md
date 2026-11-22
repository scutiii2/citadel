# Prompt for Codex: Plan 22e (rename the permission `extensions.manage` to `tool_services.manage`)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 22e in the Citadel repo. It renames one permission across Portcullis (with a reversible migration) and four front ends (Portcullis Admin, Stronghold Admin, Armory Admin, Ember). No new behaviour, route, screen or dependency.

Read these first, in order, fully:
1. `AGENTS.md` (repo root), the workspace `D:\User\Documents\Programming\AGENTS.md` ("Work pace and testing budget" applies), and the `AGENTS.md` of each app you touch if it exists.
2. `docs/superpowers/plans/2026-11-22-plan-22e-rename-extensions-manage.md`. It holds the goal, global constraints, a table of what the checks found, and two tasks with test code and the migration. Follow it step by step.
3. Background only: `docs/superpowers/plans/2026-11-22-plan-22c-remove-extension-proxy.md`.

Task: build Tasks 1 and 2 of the plan. (1) Portcullis: migration `0029` renames the `permissions` row `extensions.manage` to `tool_services.manage` (grants follow the row), `permissions.py` and `routes/connections.py` use the new constant, tests updated. (2) Portcullis Admin, Stronghold Admin, Ember and Armory Admin check the new name.

How to work:
- Run `git status` and `git log --oneline -3` first. Plans 22c and 22d must be on `main` (`c46541a6` or later); if not, stop and report. Work in the current checkout and branch. Do not create a branch or worktree. Do not commit unless I ask. Do not push.
- No baseline run. Read the code, then edit. After each task run only the test files the task names, once. Python, from the app folder: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` (`uv run pytest` fails on this machine; if `uv run --no-sync` also fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). Front ends, from the app folder: `pnpm exec vitest run <files>`. No full suite, no Playwright e2e, no Docker or compose check. If a run takes over about 2 minutes, stop it, say so and ask.
- Write each failing test first and see it fail for the stated reason. If a snippet in the plan does not fit the real code (helper names, table or column names, export names), fix the snippet, keep the behaviour the test states, and record the change in your report. The migration test body is deliberately left for you to write with the helpers already in `test_migrations.py`; its contract is stated in the plan.
- Hard rules: rename only `extensions.manage`. Never touch `extensions.personal.manage`, `private_extensions`, `/api/user-extensions` or Stronghold's `/extensions` routes. Do not edit old migrations `0010` or `0019`. Check the table and column names in the migration SQL against `src/models/role.py` and migration `0028` before running it; the migration must also upgrade cleanly on a database that has no `extensions.manage` row. After editing, `git grep -n "extensions\.manage" -- apps ':!apps/ember_web' ':!apps/portcullis/migrations'` and `git grep -n "EXTENSIONS_MANAGE" -- apps` must return only tests that assert the old name is gone (if any); list each remaining hit with its reason.
- Never edit `apps/ember_web` or any plan or spec file. Never read, print or write `.env*`, `secrets/` or key files.
- Keep each file's line endings. Edit with editor tools, not shell heredocs with escapes. No dependency. No reduced-motion code (repo rule). No subagents, no browser checks.
- Another session may hold an uncommitted edit of `docs/superpowers/plans/2026-11-20-scope-roadmap.md`. Do not touch it.

When done, report once: per task what changed (files), the test commands you ran with pass counts, which commands you did not run, "Findings" (anything the plan did not name that you kept or changed, and why), the final grep results, anything not verified, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
