# Prompt for Codex: Plan 22b (remove the Obsidian chain)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 22b in the Citadel repo. It is a removal plan across Ember (`apps/ember`, Vue 3 + TypeScript), Portcullis, Stronghold, Armory (FastAPI, `uv`, pytest), Armory Admin (`apps/armory_admin`, Vue) and `libs/citadel_auth`. It deletes the Obsidian second brain: Ember's Brains page and "save to second brain" controls, Portcullis `/api/brains` and `/api/admin/brain` (one migration `0028`), Stronghold `/brains` and the legacy notes store, Armory `obsidian` and `vault` capabilities and the Armory Admin Brain page. The new Brain stays untouched.

Read these first, in order, fully:
1. `AGENTS.md` (repo root), and the `AGENTS.md` of each app you touch if it exists.
2. `docs/superpowers/plans/2026-11-22-plan-22b-remove-obsidian-chain.md`. It holds the goal, global constraints, assumptions (a) to (i), a file map and five tasks. Follow it step by step, in task order (Ember, Portcullis, Stronghold, Armory, policy), so no commit leaves a broken call.
3. Background only: `docs/superpowers/specs/2026-11-20-service-scopes-design.md` ("Obsidian is removed for now") and `docs/superpowers/plans/2026-11-20-scope-roadmap.md`.
4. Before you delete anything, `git grep` every name the task removes and read each live caller.

Task: build Tasks 1 to 5 of the plan.

How to work:
- Run `git status` and `git log --oneline -5` first. Plans 22, 23, 24 and 25 (`477a910f` or later) must be on `main`; if not, stop and report. Create branch `plan-22b-remove-obsidian-chain` from `main` (a worktree is fine; if the app `.venv` or `node_modules` folders are empty there, run Python suites with the main checkout's `.venv\Scripts\python.exe -u -m pytest -q -p no:cacheprovider` from the worktree app folder and say so). One commit per task, with the plan's messages, each ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Baselines once before editing, recorded in the plan file under "Baseline results": Armory, Stronghold, Legion, Portcullis (13 to 19 minutes, 2 known failures: `test_secret_box.py::test_an_invalid_key_in_env_stops_startup`, `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`; use a background run or long timeout), Ember and Armory Admin (`pnpm exec vue-tsc -b`, `pnpm test`). Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider` (`uv run pytest` fails here).
- Write each failing test first, see it fail for the stated reason, then change the code. If a snippet does not fit real code, fix it, keep the stated behaviour, and record it under "Changes found during work". Check assumptions (a) to (i) where the plan names them and record each result.
- Remove only what a task names. A grep hit on a live caller the plan did not name stops that item: keep the code and record it.
- Keep: the whole new Brain, Stronghold Admin Brain settings, Armory's other capabilities, Armory's Treasury registration, the extension proxy, `services/connections.py`, `connection_admin.py`, the Armory Admin Connections page.
- Library rule: edit only `libs/citadel_auth/`, then `python scripts/sync_citadel_auth.py`; `--check` must exit 0 at the end. Run it with a venv python that has PyYAML if `scripts/check_compose.py` is used (the Armory venv works). Never edit a copied `apps/*/src/citadel_auth/`.
- Task 2 and 3 order: Portcullis purge-list entries for notes and brains go in Task 2, the Stronghold routes in Task 3. Keep that order. Move the `need` and `permissions` helpers to `src/brain/access.py` before deleting `src/brains/` (assumption (a)).
- No data deleted by code. Only schema change: Portcullis migration `0028`. Verify it upgrades and, if the plan asks, downgrades, on a scratch database.
- Never read, print or write `.env*`, `secrets/` or key files. List `OBSIDIAN_*` and `MCP_VAULT_DIR` lines still in `.env.example` files in your report for the user. If you boot a service, do it from an empty scratch folder, scratch identity, port from `29900-29998`.
- Keep each file's line endings. Edit with editor tools, not shell heredocs.
- No reduced-motion settings anywhere (repo rule). No new dependency. Do not push, do not publish, no browser-verification agents. Copy the plan's manual checklist into the report as pending; report only checks you ran.
- Another session may hold an uncommitted edit of `docs/superpowers/plans/2026-11-20-scope-roadmap.md` on `main`. Do not resolve a conflict there; report it.

When done, report per task: commit hash, what changed, test commands with pass counts against baselines (per app), results of assumptions (a) to (i), tests removed, changed or added (counts), what you booted and saw, what was not verified, "Changes found during work", follow-ups, `.env.example` lines the user must remove, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
