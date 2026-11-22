# Prompt for Codex: Plan 24b (outside clients at the Stronghold level)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 24b in the Citadel repo, in Legion, Stronghold and Portcullis (FastAPI, FastMCP, `uv`, pytest). It adds `POST /api/outside/stronghold/ask`: an outside client allowed the service `stronghold` talks to Legion's entry agent, which may use only five Stronghold Brain tools (search, read, list, write, update) on the client's own `oc_` folder. Legion's tool filter gets an exception form `"!name"`; Stronghold adds its own wall for `oc_` uids; deleting a client purges its Brain data. No front end, no migration, no dependency.

Read these first, in order, fully:
1. `AGENTS.md` (repo root), and the `AGENTS.md` of each app you touch if it exists.
2. `docs/superpowers/plans/2026-11-22-plan-24b-outside-clients-stronghold-level.md`. It holds the goal, global constraints, assumptions (a) to (g), a file map and four tasks with test code. Follow it step by step.
3. Background only: `docs/superpowers/plans/2026-11-22-plan-24-outside-clients.md`, `docs/superpowers/specs/2026-11-20-service-scopes-design.md` (section "Outside clients and access levels") and `docs/superpowers/plans/2026-11-20-scope-roadmap.md`.
4. The code you will touch, before you edit: Legion `src/runtime/tool_filter.py`, `delegation.py`, `mcp_upstream.py`, `memory_recall.py`; Stronghold `src/mcp_tools/scope.py`, `server.py`, `brain_tools.py` and the brain search code; Portcullis `src/routes/outside.py`, `outside_clients_admin.py`, `services/outside_clients.py`, `legion_ask.py` and their tests.

Task: build Tasks 1 to 4 of the plan.

How to work:
- Run `git status` and `git log --oneline -5` first. Plan 24 (`ba29fde1` or later) and Plan 25 (`477a910f`) must be on `main`; if not, stop and report. Create branch `plan-24b-outside-stronghold` from `main` (a worktree is fine; if app `.venv` folders are empty there, run each suite with the main checkout's `.venv\Scripts\python.exe -u -m pytest -q -p no:cacheprovider` from the worktree app folder and say so). One commit per task, with the plan's messages, each ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Baselines once before editing, recorded in the plan file under "Baseline results": Legion, Stronghold, Portcullis (13 to 19 minutes, 2 known failures: `test_secret_box.py::test_an_invalid_key_in_env_stops_startup`, `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`; use a background run or long timeout). Use `uv run --no-sync python -u -m pytest -q -p no:cacheprovider` (`uv run pytest` fails here).
- Write each failing test first, see it fail for the stated reason, then change the code. If a snippet does not fit real code (fixture names, FastMCP decorators, how Portcullis tests sign a request), fix it, keep the stated behaviour, and record it under "Changes found during work". Check assumptions (a) to (g) where the plan names them and record each result.
- Hard rules: an outside client never reads the global brain, never gets Armory tools, tickets, usage, skills, short-term memory, sharing or questions back. Both walls must hold: Legion filter AND Stronghold `oc_` check, each with its own test. Guards fail closed: if Stronghold cannot tell whether a uid is outside, refuse. No model call outside Legion. Question and answer text never in a log or error. A client allowed `legion` only must get a refusal on the new route. Do not touch `libs/citadel_auth` or `src/brain/access.py`.
- Test the exception form through Legion's real filter, not a mock, as Plan 24 did for `disabled_tools`. Check that delegation passes exceptions on unchanged and that skill recall and skill learning stay blocked.
- Never read, print or write `.env*`, `secrets/` or key files. If you boot a service, do it from an empty scratch folder, scratch identity, port from `29900-29998`, never against real data.
- Keep each file's line endings. Edit with editor tools, not shell heredocs. No dependency. No reduced-motion settings anywhere (repo rule). Do not push, do not publish, no browser-verification agents. Copy the plan's manual checklist into the report as pending; report only checks you ran.
- Another session may hold an uncommitted edit of `docs/superpowers/plans/2026-11-20-scope-roadmap.md` on `main`. Do not resolve a conflict there; report it.
- Do not add behaviour beyond the plan. Answer the plan's open questions in the report only if you hit them; do not decide them.

When done, report per task: commit hash, what changed, test commands with pass counts against baselines (per app), results of assumptions (a) to (g), tests added or changed (counts), what you booted and saw, what was not verified (a live stack, a real outside call), "Changes found during work", follow-ups, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
