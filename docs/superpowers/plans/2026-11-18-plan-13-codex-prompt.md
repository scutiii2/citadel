# Prompt for Codex: Plan 13 (service catalog in Treasury)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 13 in the Citadel repo (backends `portcullis`, `stronghold`, `legion`, `armory`, `treasury` under `apps/`; admin apps `legion_admin`, `treasury_admin`, `portcullis_admin`; shared library `libs/citadel_auth`).

Read these first, in order, fully:
1. `AGENTS.md` (repo root) and the `AGENTS.md` of each app you touch.
2. `docs/superpowers/plans/2026-11-18-plan-13-service-catalog-in-treasury.md`. It holds the goal, the design, the global constraints, the exact interfaces and code, and the tasks with their steps and tests. Follow it task by task.
3. For background only: `docs/superpowers/plans/2026-11-17-plan-12-dynamic-service-auth-design.md` and `apps/treasury/configs/README.md`.

Task: Treasury keeps a catalog of service addresses. Portcullis, Stronghold, Armory and Legion register their own address with it at start, and every call between them looks the peer up in the catalog at request time. `treasury_url` (config file, env `TREASURY_URL`) is the only bootstrap address left. Build exactly what the plan says.

How to work:
- Create branch `plan-13-service-catalog` from `main`. Do Tasks 1 to 9 in order, one commit per task (Tasks 5 and 6 get one commit per service, as the plan says). Write the failing test first in every task, run it, see it fail, then implement.
- Task 9 asks for vault notes in `D:\User\Documents\Programming\Brain`. That is a separate repo: do not touch it. Skip those lines, and list in your report which notes need an update.
- Use `uv` (not pip) and `pnpm` (not npm). Run tests from inside each app folder: `uv run pytest -q -p no:cacheprovider` (add `-m "not slow"` for Armory and Legion). Portcullis takes about 9 minutes: run it in the background. Admin apps: `pnpm exec vue-tsc -b` and `pnpm exec vitest run`.
- Never edit a copied `src/citadel_auth/` folder. Edit `libs/citadel_auth/` and run `uv run scripts/sync_citadel_auth.py` (then `--check`).
- Never read, print or write `.env*`, `secrets/` or key files. Edit `.env.example` files only.
- Never add a reduced-motion setting, media query or test.
- Keep each file's existing line endings (CRLF in most source files). Edit with your editor tools, not shell heredocs with escapes (unreliable on this Windows machine).
- Do not push. Do not weaken or delete a test that fails for a reason outside your change; stop and report instead.
- Line numbers in the plan are from a search on 2026-11-18 and may be off by a few lines. Read the surrounding code before you edit. If the plan and the code disagree (a call site the plan does not list, a class that stores a URL, a test that builds a removed setting), grep for the real users, follow the code, and add the finding to the plan file under a "Changes found during work" heading. Ask only if you would have to weaken a security rule of the plan (a service may register only its own name; only Portcullis may pin; addresses are checked base URLs).
- If a task needs a decision the plan does not make, choose the smaller change and note it in the plan file.

When done, report per task: commit hash, what changed, test commands with pass counts, anything not verified (a live Docker run, a real browser check and real Postgres are known gaps), the "Changes found during work" list, and the Brain notes that still need an update.
