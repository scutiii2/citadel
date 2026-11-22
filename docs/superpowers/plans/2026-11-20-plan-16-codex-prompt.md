# Prompt for Codex: Plan 16 (Treasury outside-service catalog)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 16 in the Citadel repo (backends `portcullis`, `stronghold`, `legion`, `armory`, `treasury` under `apps/`; shared library `libs/citadel_auth`).

Read these first, in order, fully:
1. `AGENTS.md` (repo root) and `apps/treasury/AGENTS.md` if it exists.
2. `docs/superpowers/plans/2026-11-20-plan-16-outside-service-catalog.md`. It holds the goal, global constraints, the file map and four tasks with the test code and implementation code. Follow it step by step; it is a script, not only a design.
3. For background only: `docs/superpowers/specs/2026-11-20-service-scopes-design.md` (section "Outside services and the catalog (Treasury)"), `docs/superpowers/plans/2026-11-20-scope-roadmap.md`, and `docs/superpowers/plans/2026-11-18-plan-13-service-catalog-in-treasury.md` (the existing Citadel-service catalog this plan sits beside; do not change its behaviour).
4. The code you will touch: `apps/treasury/src/service_catalog.py`, `apps/treasury/src/api.py`, `apps/treasury/tests/test_api.py`, `libs/citadel_auth/citadel_auth/catalog.py`, `libs/citadel_auth/tests/test_catalog.py`.

Task: Treasury keeps a catalog of outside services (groups with a hidden service id, origins with origin ids, `used_by`), exposes it through new routes, and the shared `ServiceCatalog` client reads, caches and resolves it. Addresses only, never tokens. Build Tasks 1 to 4 of the plan.

How to work:
- Run `git status` and `git log --oneline -5` first. Create branch `plan-16-outside-catalog` from `main`. One commit per task, with the commit messages the plan gives, each ending with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Before changing anything, run `apps/treasury` and `libs/citadel_auth` suites once and record the pass counts and any existing failure in the plan file under a "Baseline" heading. Do the same for `apps/legion`, `apps/stronghold`, `apps/armory` and `apps/portcullis` only in Task 4, to prove the vendored `citadel_auth` copies broke nothing. Portcullis has two known failures on `main`: `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown` (both fail because `checked_address` rejects `http://127.0.0.1:0`). Name them in the baseline; they are not yours.
- Write each failing test first, run it, see it fail for the stated reason, then implement. Use the test and implementation code in the plan. If a snippet does not fit the real code (a helper has another signature, a fixture name differs), fix the snippet, keep the behaviour the test states, and record the change in the plan file under a "Changes found during work" heading.
- Use `uv` (not pip). Run tests from inside each app or library folder: `uv run pytest -q -p no:cacheprovider` (add `-m "not slow"` for Armory and Legion; fall back to the folder's `.venv/Scripts/python.exe -m pytest` if `uv run` fails). Portcullis takes about 10 minutes: run it in the background and write its output to a file.
- Never edit a copied `apps/*/src/citadel_auth/` folder. Edit `libs/citadel_auth/` and run `uv run scripts/sync_citadel_auth.py` (then `--check`) from the repo root.
- Never read, print or write `.env*`, `secrets/` or key files.
- Keep each file's existing line endings (CRLF in most source files). Edit with your editor tools, not shell heredocs with escapes (unreliable on this Windows machine).
- Do not push and do not publish. Do not weaken or delete a test that fails for a reason outside your change; stop and report instead.
- Do not change the existing Citadel-service catalog (`NAMES`, `/services`, `/admin/services`, `register`, `pin`, `unpin`) or its tests. The outside catalog is a separate module with its own tables.
- Do not add routes, fields or behaviour beyond the plan (no admin UI, no Portcullis proxy, no consumer forms, no token storage, no ordering of origins in Treasury). Those belong to later plans. If you think something is missing, note it in your report instead of building it.
- If the plan and the code disagree, grep for the real users, follow the code, and record the finding as above. Ask only if you would have to weaken a rule in the plan's "Global Constraints" (Treasury stores no tokens, Citadel names refused, only Legion and Stronghold add origins, only Portcullis calls `/admin/*`).

When done, report per task: commit hash, what changed, test commands with pass counts compared with the baseline, anything not verified (a live Docker run, Treasury with a real Postgres, a real multi-service start are known gaps), the "Changes found during work" list, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
