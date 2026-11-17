# Prompt for Codex: Plan 12 (dynamic service-to-service auth)

<!-- history-note -->
> **History (noted 2026-11-18).** This document names files and settings that no longer exist: `specifics/`, seed files,
> `config_*.json` toggle, tuning and connection files, and tokens or addresses kept in `.env`. Those settings are now saved
> in each service's database and edited in its admin app; see `apps/armory/docs/settings.md` and each service's
> `configs/README.md`. Kept as it was written; do not follow its file paths.

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 12 in the Citadel repo (backends `portcullis`, `stronghold`, `legion`, `armory`, `treasury` under `apps/`).

Read these first, in order, fully:
1. `AGENTS.md` (repo root) and the `AGENTS.md` of each app you touch.
2. `docs/superpowers/plans/2026-11-17-plan-12-dynamic-service-auth-design.md` (why and the design).
3. `docs/superpowers/plans/2026-11-17-plan-12-implementation.md` (exact decisions, steps, files, tests, done criteria).

Task: replace the shared `INTERNAL_API_TOKEN` between the five backends with per-service Ed25519-signed short-lived assertions, and a Portcullis-signed requester token for user identity, exactly as the implementation plan says.

How to work:
- Create branch `plan-12-service-auth` from `main`. Do steps 12.1 to 12.6 in order, one commit per step. Do not do 12.7 (live run); stop after 12.6 and report.
- Hard cut-over: no legacy mode, no switch to turn auth off, no fallback to the old token. Delete each service's old token code, tests and docs in the step that migrates it.
- Start 12.1 with the MCP spike in decision 9. If the MCP streamable-HTTP client cannot take a per-request `httpx.Auth`, stop and report; do not invent a workaround.
- Use `uv` (not pip) and `pnpm` (not npm). Run tests from inside each app folder: `uv run pytest -q -p no:cacheprovider` (add `-m ""` for Armory and Legion before the last commit of their step; Portcullis takes about 10 minutes, run it in the background).
- Never edit a copied `src/citadel_auth/`; edit `libs/citadel_auth/` and run `scripts/sync_citadel_auth.py`.
- Do not touch `D:\User\Documents\Programming\Brain` (separate repo). Do not push. Do not weaken or delete a test that fails for a reason outside your change; stop and report instead.
- Edit files with your editor tools, not shell heredocs with escapes (unreliable on this Windows machine).
- If the plan and the code disagree (a file or call the plan does not list, a route a service calls that the policy table lacks), grep for the real callers, follow the code, add the row or file to the plan file under a "Changes found during work" heading, and carry on. Ask only if the design's security rules (Goals 1 and 2) would have to be weakened.

When done, report per step: commit hash, what changed, test commands with pass counts, anything not verified, and the "Changes found during work" list.
