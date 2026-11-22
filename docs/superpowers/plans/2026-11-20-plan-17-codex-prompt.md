# Prompt for Codex: Plan 17 (Treasury Admin page for outside services)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 17 in the Citadel repo (backends `portcullis`, `stronghold`, `legion`, `armory`, `treasury` under `apps/`; admin apps such as `treasury_admin`; shared library `libs/citadel_auth`).

Read these first, in order, fully:
1. `AGENTS.md` (repo root) and the `AGENTS.md` of each app you touch (`apps/portcullis`, `apps/treasury_admin`). For the Treasury Admin UI also read `.agents/skills/ember-frontend-design/SKILL.md` and `ember-design-system`. For narrow-screen layout also read `.agents/skills/ember-frontend-design/mobile-ui.md`.
2. `docs/superpowers/plans/2026-11-20-plan-17-outside-admin-page.md`. It holds the goal, global constraints, file map and three tasks with the test code and implementation code. Follow it step by step; it is a script, not only a design.
3. For background only: `docs/superpowers/plans/2026-11-20-plan-16-outside-service-catalog.md` (the Treasury routes this plan calls; already merged to `main`), `docs/superpowers/specs/2026-11-20-service-scopes-design.md` (section "Outside services and the catalog (Treasury)") and `docs/superpowers/plans/2026-11-20-scope-roadmap.md`.
4. The code you will touch: `apps/portcullis/src/routes/admin_treasury.py`, `apps/portcullis/tests/conftest.py` (`FakeDbGateway.admin`), `apps/portcullis/tests/test_admin_treasury.py`, `apps/treasury_admin/src/api/TreasuryAdminClient.ts`, `apps/treasury_admin/src/views/ServicesView.vue` and its test (the pattern to follow), `apps/treasury_admin/src/router/index.ts`, `apps/treasury_admin/src/router/pages.ts`, `apps/treasury_admin/src/components/admin/ConfirmModal.vue`.

Task: Portcullis gets four routes under `/api/admin/treasury/outside` that pass through to Treasury's `/admin/outside` routes; Treasury Admin gets an "Outside services" page where an administrator renames a group and removes an origin or a whole group after a confirmation that names the services using it. Build Tasks 1 to 3 of the plan.

How to work:
- Run `git status` and `git log --oneline -5` first. Plan 16 (`8d432e3d` or later) must be on `main`; if it is not, stop and report. Create branch `plan-17-outside-admin` from `main`. One commit per task, with the commit messages the plan gives, each ending with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Before changing anything, run the Portcullis and Treasury Admin suites once and record the pass counts and any existing failure in the plan file under a "Baseline" heading. Portcullis has two known failures on `main`: `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown` (both reject `http://127.0.0.1:0`). Name them in the baseline; they are not yours.
- Write each failing test first, run it, see it fail for the stated reason, then implement. Use the test and implementation code in the plan. If a snippet does not fit the real code (a fixture or helper has another name, a selector differs, the nav or router test counts pages), fix the snippet, keep the behaviour the test states, and record the change in the plan file under a "Changes found during work" heading.
- Use `uv` (not pip) and `pnpm` (not npm). Python tests run from inside `apps/portcullis`: `uv run pytest -q -p no:cacheprovider` (fall back to `.venv/Scripts/python.exe -m pytest` if `uv run` fails). The full Portcullis run takes about 10 minutes: run it in the background and write its output to a file. Treasury Admin: `pnpm exec vue-tsc -b` and `pnpm exec vitest run` from `apps/treasury_admin`.
- Never edit a copied `src/citadel_auth/` folder; this plan should not touch `libs/citadel_auth` at all.
- Never read, print or write `.env*`, `secrets/` or key files.
- Never add a reduced-motion setting, media query or test. Add no new border-radius values: `src/radiusScale.test.ts` must keep passing.
- The audit log must never contain an address: log the service id or origin id only. Add no token field, display or storage anywhere.
- Keep each file's existing line endings (CRLF in most source files). Edit with your editor tools, not shell heredocs with escapes (unreliable on this Windows machine).
- Do not push and do not publish. Do not weaken or delete a test that fails for a reason outside your change; stop and report instead.
- Do not add routes, pages, fields or behaviour beyond the plan: no add form, no change to Treasury's own routes, no permission other than `settings.manage`. If you think something is missing, note it in your report instead of building it.
- If the plan and the code disagree, grep for the real users, follow the code, and record the finding as above. Ask only if you would have to weaken a rule in the plan's "Global Constraints".

When done, report per task: commit hash, what changed, test commands with pass counts compared with the baseline, anything not verified (a real browser view of the page at desktop and phone width, a real Treasury round trip with a registered group, a live Docker run are known gaps), the "Changes found during work" list, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
