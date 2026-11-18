# Prompt for Codex: Plan 14 (tool connections live in Armory)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 14 in the Citadel repo (backends `portcullis`, `stronghold`, `legion`, `armory`, `treasury` under `apps/`; admin apps `armory_admin`, `portcullis_admin`, `stronghold_admin`, `legion_admin`, `treasury_admin`; shared library `libs/citadel_auth`; the desktop app `apps/ember`).

Read these first, in order, fully:
1. `AGENTS.md` (repo root) and the `AGENTS.md` of each app you touch. For any admin app UI, also read `.agents/skills/ember-frontend-design/SKILL.md` and `ember-design-system`.
2. `docs/superpowers/plans/2026-11-18-plan-14-tool-connections-in-armory.md`. It holds the goal, the three connection classes, the architecture, the six approved decisions and the tasks. This plan is a design, not a script: it names the routes, files and behaviours but not every line of code.
3. For background only: `docs/superpowers/plans/2026-11-17-plan-12-dynamic-service-auth-design.md` (signed service calls) and `docs/superpowers/plans/2026-11-18-plan-13-service-catalog-in-treasury.md` (the service catalog; Bard, Scribe and Reader stay out of it).
4. The tool services' REST contracts, to build the Armory clients against: `D:\User\Documents\Programming\AI\ToolServices\Bard\src\app.py` (`/api/speak`, `/api/voices`, `/api/files/{id}`), `Scribe\src\app.py` (`/api/transcribe`, `/api/transcribe-partial`, `/api/files`, the `/api/stream` WebSocket) and `Reader\src\app.py` (`/api/files`, `/api/parse`). Read only; do not edit those repos.

Task: Armory becomes the only service that holds the address, credentials and transports of Bard, Scribe and Reader (the "required" connections), and of any optional server-side connection. Stronghold and Portcullis stop keeping Bard, Scribe and Reader tokens and addresses; they call an Armory REST façade instead. Build what the plan says, with its six approved decisions:
1. Portcullis opens the audio, attachment-content and dictation streams straight to Armory.
2. The dictation WebSocket relay moves into Armory, with its bounds.
3. A missing required connection leaves the control visible with the reason.
4. Keep the per-caller `X-Internal-Token` for the tool services.
5. Client-sided (per-account) connections are out of scope.
6. The admin page is called "Connections" and replaces "Extensions" and "Tool services".

Starting state: the interim fix "Bard audio streams through Stronghold" (Task 0 of the plan) is being committed on `main` by the person who wrote the plan. Run `git log --oneline -8` and `git status` first. If that commit is not there yet, stop and report; do not recreate it. Task 3 removes its Stronghold route.

How to work:
- Create branch `plan-14-armory-connections` from `main`. Do Tasks 1 to 5 in order, one commit per task (per service where the task spans several). Because the plan is a design, begin each task by adding a short "Interfaces" subsection for that task to the plan file (route paths, record fields, function signatures, error mapping) and commit it with the task. Write the failing test first, run it, see it fail, then implement.
- Before changing anything, run each touched app's suite once and record the pass count and any failure that already exists, in the plan file under "Baseline". One Portcullis test and one other already fail on `main` as of 2026-11-18 evening; find them and name them in the baseline so they are not blamed on this work.
- Use `uv` (not pip) and `pnpm` (not npm). Run tests from inside each app folder: `uv run pytest -q -p no:cacheprovider` (add `-m "not slow"` for Armory and Legion; fall back to the app's `.venv/Scripts/python.exe -m pytest` if `uv run` fails). Portcullis takes about 9 minutes: run it in the background and write its output to a file. Admin apps and Ember: `pnpm exec vue-tsc -b` and `pnpm exec vitest run`.
- Never edit a copied `src/citadel_auth/` folder. Edit `libs/citadel_auth/` and run `uv run scripts/sync_citadel_auth.py` (then `--check`). The caller allow-list for the new Armory routes (`stronghold`, `portcullis` only) belongs in `citadel_auth.policy`.
- Never read, print or write `.env*`, `secrets/` or key files. Edit `.env.example` files only.
- Never add a reduced-motion setting, media query or test.
- Secrets are write-only everywhere: no route, log line, status view or test snapshot may contain a stored token. Add a test for each new view.
- Keep each file's existing line endings (CRLF in most source files). Edit with your editor tools, not shell heredocs with escapes (unreliable on this Windows machine).
- Do not push and do not publish. Do not weaken or delete a test that fails for a reason outside your change; stop and report instead.
- Keep Armory's new routes thin and bounded: no command execution, no file path from a caller, size and time limits on every body and stream, one dictation stream per account. Armory has the Docker socket mounted, so treat these routes as exposed to user content.
- If the plan and the code disagree (a call site the plan does not list, a setting still read somewhere), grep for the real users, follow the code, and add the finding to the plan file under a "Changes found during work" heading. Ask only if you would have to weaken a security rule (the caller allow-list, write-only secrets, or the base-URL check on addresses).
- If a task needs a decision the plan does not make, choose the smaller change and note it in the plan file.

Deployment is not part of your work, but Task 5 must leave the server steps written in `docs/deployment.md` in the order the plan gives: publish Armory, enter the three connections in Armory Admin, then publish Stronghold and Portcullis, then remove the old tokens.

When done, report per task: commit hash, what changed, test commands with pass counts (compared with the baseline), anything not verified (a live Docker run, a real Bard, Scribe or Reader, a real microphone and dictation stream, and a real browser or Tauri window check are known gaps), the "Changes found during work" list, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
