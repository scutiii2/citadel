# Citadel revision roadmap

Spec: `docs/superpowers/specs/2026-11-14-citadel-revision-design.md`. This file lists the plans in order. Only Plan 1 is written in full. Each later plan is written when the one before it is done, because its file lists, names and test commands depend on what the earlier plan left behind (for example, the Stronghold layout comes from Plan 3). Writing them now would mean placeholders.

| # | Plan | Spec phase | Depends on | Branch | Status |
|---|---|---|---|---|---|
| 1 | Baseline and Portcullis rename | 0, 1 | none | `refactor/portcullis-rename` | Written: `2026-11-14-plan-1-baseline-and-portcullis-rename.md` |
| 2 | Stronghold skeleton and Portcullis forwarder | 2 | 1 | `feat/stronghold-skeleton` | Written: `2026-11-14-plan-2-stronghold-skeleton.md` |
| 3 | Legion on ConversationGateway, Anthropic-protocol agents | 2b | 1 | `refactor/legion-conversation-gateway` | Written: `2026-11-14-plan-3-legion-conversation-gateway.md` |
| 3b | Legion on ConversationGateway, OpenAI-protocol agents | 2b | 3 | `refactor/legion-openai-gateway` | Written and executed 2026-11-15: `2026-11-15-plan-3b-legion-openai-gateway.md` |
| 4 | Legion on DecisionGateway | 2b | 3b | `refactor/legion-decision-gateway` | Written and executed 2026-11-15: `2026-11-15-plan-4-legion-decision-gateway.md` |
| 5 | Move product logic to Stronghold, domain by domain | 3 | 2 | `refactor/stronghold-<domain>` per domain | All sub-plans 5.1 to 5.9 executed 2026-11-15/16 (the calendar of 5.1 was removed by Plan 11): `2026-11-15-plan-5-stronghold-domains.md` |
| 6 | Stronghold database schema | 4 | 5 (chats domain) | `feat/stronghold-schema` | Executed 2026-11-16 as a schema layer over Treasury: `2026-11-16-plan-6-stronghold-schema.md` |
| 7 | Admin app split | 5 | 5 | `refactor/admin-split` | Executed 2026-11-16: `2026-11-16-plan-7-admin-split.md` |
| 8 | Disable `ember_web` | 6 | 7 | `chore/disable-ember-web` | Executed 2026-11-16: `2026-11-16-plan-8-disable-ember-web.md` |
| 9 | Ember Windows app | 7 | 8 | `feat/ember-windows` | Executed 2026-11-16 (shell not built): `2026-11-16-plan-9-ember-windows.md` |
| 11 | Remove the calendar from Citadel | - | 10 | `refactor/remove-calendar` | Executed 2026-11-16: `2026-11-16-plan-11-remove-calendar.md` |
| 10 | Move the turn engine to Stronghold | 5 | 9 | `refactor/turns-<step>` | Planned 2026-11-16; all steps 10.1 to 10.6 done: `2026-11-16-plan-10-turn-engine.md` |

## Order and parallel work
- Plans 2 and 3 can run in parallel after Plan 1. They touch different services (`stronghold` is new; Legion's provider code).
- Plan 4 follows Plan 3 because both edit Legion's `src/providers/` and its tuning config.
- Plan 5 starts only after Plan 2. Its sub-plans run one at a time. Order, least coupled first: calendar, notes/brains/memory, templates/skills, tickets/triage, shares, usage, attachments/bard, tuning, chats/folders/turns.
- Plan 7 splits in this order: `armory_admin`, rename `ember_admin` to `portcullis_admin`, `stronghold_admin`, `treasury_admin`.

## What each later plan must contain (from the spec)

**Plan 2.** FastAPI app in `apps/stronghold`, `/health`, internal-token auth, `X-Requester-*` header handling, compose service on the next free port in 29600-29899 that does not collide with Legion's per-agent ports from 29603, and a Portcullis forwarder route with a test that proves cookies never reach Stronghold.

**Plan 3.** Replace `apps/legion/src/providers/language/` (`anthropic_provider.py`, `openai_provider.py`) with a ConversationGateway client. Rewire `gateway_failover.py` so `classify()` reads the gateway error `kind` and `Retry-After`; keep `GatewayRoute`, `cooldown.py`, fallback lists, cooldown tuning and `SwitchInfo`. Echo `reasoning_state`. Add the gateway to `docker-compose.yml` (built from `../../AI/ModelProviders/ConversationGateway`, ports on `0.0.0.0`, state volume, `SERVICE_ADMIN_PASSWORD`). Move gateway entries and keys out of `apps/legion/.env`. Decide keep-or-delete per file for `model_limits.py`, `token_limits.py`, `reasoning_effort.py`.

**Plan 4.** Replace `apps/legion/src/providers/decision/` (`jev.py`, `laya.py`, `provider.py`) with a DecisionGateway client. Keep the `laya-only`, `jev-only` and `both` strategies in Legion as a choice between two gateway ids. Add the gateway to compose (same shape as Plan 3).

**Plan 5.** Per domain: move routes and services from `apps/portcullis` to `apps/stronghold`, keep the public `/api/...` path through the Portcullis forwarder, move the domain's tests, prove the same tests pass.

**Plan 6.** Stronghold's own SQLAlchemy models and migrations for chats, shares and usage, keyed on the account `uid`. No data migration (fresh install).

**Plan 7.** Admin page assignment (confirmed):
- `armory_admin` (port 26503): Capabilities, Extensions.
- `stronghold_admin` (port 26504): Tickets, Usage, Analytics, Tuning.
- `portcullis_admin` (port 26501, renamed `ember_admin`): Accounts, Roles, Invites, Settings, Workspace settings, Config issues, Overview, Profile, Login.
- `treasury_admin` (port 26505): connections and instances, minimal.
- `legion_admin` (26500): unchanged.
Each app follows the `legion_admin` pattern: no backend, calls Portcullis only, one permission gate.

**Plan 8.** Remove `ember_web` from `docker-compose.yml`, mark its README "reference only", keep the folder.

**Plan 9.** Copy `ember_web` code into `apps/ember`, Tauri shell, configurable Portcullis URL, allow the desktop origin in Portcullis (or token auth), decide web push, shared-chat links, games iframe and calendar view, installer.
