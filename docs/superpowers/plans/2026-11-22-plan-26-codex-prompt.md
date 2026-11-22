# Prompt for Codex: Plan 26 (remove what Plan 22b left behind)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 26 in the Citadel repo. It is a small removal plan across Legion, Armory, Portcullis, `apps/ember_cli`, `libs/citadel_auth` and one Armory Admin test file. No new behaviour, route, setting, dependency or screen.

Read these first, in order, fully:
1. `AGENTS.md` (repo root), the workspace `D:\User\Documents\Programming\AGENTS.md` ("Work pace and testing budget" applies), and the `AGENTS.md` of each app you touch if it exists.
2. `docs/superpowers/plans/2026-11-22-plan-26-obsidian-leftovers-cleanup.md`. It holds the goal, global constraints, a table of what the checks found, and four tasks with test code. Follow it step by step.
3. Background only: `docs/superpowers/plans/2026-11-22-plan-22b-remove-obsidian-chain.md` (its follow-ups are this plan's input).

Task: build Tasks 1 to 4 of the plan. (1) Delete Legion's `vault-librarian` agent and add the "no agent allows a removed tool" test. (2) Remove `brain_scope` and `X-Brain-Destination` from Legion `internal_auth.py`, Armory `identity_context.py` and Portcullis `caller.py`. (3) Remove the second-brain fields from `ember_cli`. (4) Remove only the Stronghold-to-Armory auth paths that are proven dead, rename the `vault` fixture in `CapabilitiesAdminView.test.ts`, then run the final sweep.

How to work:
- Run `git status` and `git log --oneline -3` first. Plans 22b and 24b must be on `main` (`4cf3ad79` or later); if not, stop and report. Work in the current checkout and branch. Do not create a branch or worktree. Do not commit unless I ask. Do not push.
- No baseline run. Read the code, then edit. After each task run only the test files the task names, once, with `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` from the app folder (`uv run pytest` fails on this machine; if `uv run --no-sync` also fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). Armory Admin: `pnpm exec vitest run <file>`. No full suite, no Docker or compose check. If a run takes over about 2 minutes, stop it, say so and ask.
- Write each failing test first and see it fail for the stated reason. If a snippet in the plan does not fit the real code (fixture or class names), fix the snippet, keep the behaviour the test states, and record the change in your report.
- Hard rules: remove only what a task names. A `git grep` hit on a live caller the plan did not name means keep that code and list it under "Findings". Task 2: `Requester` is a positional dataclass; check every `Requester(...)` call before and after, and switch positional token arguments to `requester_token=`. Task 4: prove each auth path dead (no Armory route, no Stronghold call) before removing it; keep `/mcp`, `/upload`, and `/connections` if it is still served and called. Edit `libs/citadel_auth/` only, then `python scripts/sync_citadel_auth.py`, then `python scripts/sync_citadel_auth.py --check` must exit 0; run these with a venv python that has PyYAML if a script needs it (the Armory `.venv` works). Never edit a copied `apps/*/src/citadel_auth/`.
- Keep `.obsidian` in Armory's `confined_paths.py`, the extension proxy, `services/connections.py`, the Connections page, and never edit `apps/ember_web` or any plan or spec file.
- Never read, print or write `.env*`, `secrets/` or key files. Do not open `apps/armory/.env.example`; list its needed edit in your report for me.
- Keep each file's line endings. Edit with editor tools, not shell heredocs with escapes. No dependency. No reduced-motion code (repo rule). No subagents, no browser checks.
- Another session may hold an uncommitted edit of `docs/superpowers/plans/2026-11-20-scope-roadmap.md`. Do not touch it.

When done, report once: per task what changed (files), the test commands you ran with pass counts, which commands you did not run, "Findings" (live callers kept, paths kept and why), the final sweep result with the reason for each remaining hit, anything not verified, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
