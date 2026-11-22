# Prompt for Codex: Plan 22d (remove the inert extension plumbing)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 22d in the Citadel repo. It is a removal plan across Portcullis, Stronghold, `apps/ember_cli`, Ember (`apps/ember`) and Legion. No new behaviour, route, setting, dependency or screen.

Read these first, in order, fully:
1. `AGENTS.md` (repo root), the workspace `D:\User\Documents\Programming\AGENTS.md` ("Work pace and testing budget" applies), and the `AGENTS.md` of each app you touch if it exists.
2. `docs/superpowers/plans/2026-11-22-plan-22d-remove-extension-plumbing.md`. It holds the goal, global constraints, a table of what the checks found, and two tasks with test code. Follow it step by step.
3. Background only: `docs/superpowers/plans/2026-11-22-plan-22c-remove-extension-proxy.md` (its open question 3 is this plan's input).

Task: build Tasks 1 and 2 of the plan. (1) Portcullis, Stronghold, `ember_cli` and Ember's `slashCommands.ts` stop sending or accepting `extension_ids` / `enabled_extensions`. (2) Legion drops the `enabled_extensions` parameter from `ask`, `agent_config`, `delegation`, the three providers and `mcp_upstream.list_tools`, plus the dead `_tool_is_enabled` gate.

How to work:
- Run `git status` and `git log --oneline -3` first. Plan 22c must be on `main` (`ef90cd9e` or later); if not, stop and report. Work in the current checkout and branch. Do not create a branch or worktree. Do not commit unless I ask. Do not push.
- No baseline run. Read the code, then edit. After each task run only the test files the task names, once, with `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` from the app folder (`uv run pytest` fails on this machine; if `uv run --no-sync` also fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). Ember: `pnpm exec vitest run <files>` and `pnpm exec vue-tsc -b` from `apps/ember`. No full suite, no Docker or compose check. If a run takes over about 2 minutes, stop it, say so and ask.
- Write each failing test first and see it fail for the stated reason. If a snippet in the plan does not fit the real code (fixture, import or variable names), fix the snippet, keep the behaviour the test states, and record the change in your report.
- Hard rules: remove only what a task names. A `git grep` hit on a live reader the plan did not name means keep that code and list it under "Findings". `enabled_extensions` is a positional argument in several Legion functions and many test fakes: remove it from every signature, call and fake together, and read each changed call afterwards to check that no later positional argument shifted. Callers go before callees (Task 1 before Task 2).
- Keep `private_extensions` everywhere, Stronghold's `/extensions` routes for private extensions, the permissions `extensions.manage` and `extensions.personal.manage`, the Armory `settings.db` tables, and never edit `apps/ember_web` or any plan or spec file. In Stronghold's turn request model check for `extra="forbid"` before removing `extension_ids`.
- Never read, print or write `.env*`, `secrets/` or key files.
- Keep each file's line endings. Edit with editor tools, not shell heredocs with escapes. No dependency. No reduced-motion code (repo rule). No subagents, no browser checks.
- Another session may hold an uncommitted edit of `docs/superpowers/plans/2026-11-20-scope-roadmap.md`. Do not touch it.

When done, report once: per task what changed (files), the test commands you ran with pass counts, which commands you did not run, "Findings" (live readers kept and why), the final grep result with the reason for each remaining hit, anything not verified, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
