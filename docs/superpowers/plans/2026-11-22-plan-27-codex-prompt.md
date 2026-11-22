# Prompt for Codex: Plan 27 (final leftovers)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 27 in the Citadel repo. It has three small tasks: an Armory maintenance script that drops two unused tables, a Portcullis migration that renames a starter role, and roadmap text. No new runtime behaviour, route, screen or dependency.

Read these first, in order, fully:
1. `AGENTS.md` (repo root), the workspace `D:\User\Documents\Programming\AGENTS.md` ("Work pace and testing budget" applies), and the `AGENTS.md` of each app you touch if it exists.
2. `docs/superpowers/plans/2026-11-22-plan-27-final-leftovers.md`. It holds the goal, global constraints, a table of what the checks found, and three tasks with test code, the script and the migration. Follow it step by step.
3. Background only: `docs/superpowers/plans/2026-11-22-plan-22e-rename-extensions-manage.md` (the `0029` migration and its test are the pattern for Task 2).

Task: build Tasks 1 to 3 of the plan. (1) `apps/armory/src/prune_unused_tables.py` with its test and a README paragraph. (2) Portcullis migration `0030` (`Power User` to `Tool Services Manager`, `Operator` text) with its tests. (3) Clear the "Plan 14" cells on roadmap rows 19 and 22c and relabel row 27 as Built.

How to work:
- Run `git status` and `git log --oneline -3` first. Plans 22c to 22e must be on `main` (`84a46790` or later); if not, stop and report. Work in the current checkout and branch. Do not create a branch or worktree. Do not commit unless I ask. Do not push.
- No baseline run. Read the code, then edit. After each task run only the test file the task names, once. Python, from the app folder: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` (`uv run pytest` fails on this machine; if `uv run --no-sync` also fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). No full suite, no Docker or compose check. If a run takes over about 2 minutes, stop it, say so and ask.
- Write each failing test first and see it fail for the stated reason. The `0030` migration tests are left for you to write with the helpers already in `test_migrations.py`; their contract is stated in the plan (exact seeded name and text and a free target name to rename; role id, permissions and holders never change; downgrade reverses; an edited or already-renamed role is left alone with no error). If a snippet in the plan does not fit the real code (table or column names, helper names), fix the snippet, keep the behaviour, and record the change in your report.
- Hard rules: the script drops only `extensions` and `connections`, only with `--apply`, and never creates a missing file. Never open, read or run anything against a real `settings.db`; tests use a temporary database only. Armory gets no startup code. Do not edit old migrations `0010`, `0019` or `0029`. Check the role and column names in the migration SQL against `0019` and `src/models/role.py` before running it. Run `git grep -n "Power User" -- apps` and confirm no application code (outside migrations and tests) looks a role up by that name; if one does, update it and list it under Findings.
- Keep `apps/ember_web` untouched and edit no plan or spec file except the roadmap row text named in Task 3. Never read, print or write `.env*`, `secrets/` or key files.
- Keep each file's line endings. Edit with editor tools, not shell heredocs with escapes. No dependency. No reduced-motion code (repo rule). No subagents, no browser checks.

When done, report once: per task what changed (files), the test commands you ran with pass counts, which commands you did not run, "Findings" (role lookups by name, starter role texts that differed from the plan, anything else not named), anything not verified (say plainly that the script was never run against a real `settings.db`), and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
