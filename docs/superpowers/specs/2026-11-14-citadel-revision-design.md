# Citadel revision: Portcullis, Armory, Legion, Stronghold, Treasury

Status: DRAFT for review. Nothing implemented. Date: 2026-11-14.

## Goal
Split Citadel into five backend services, one admin web app per backend, and a Windows desktop app (Ember) that replaces `ember_web`.

## Decisions (from user)
- Portcullis is a thin gateway. Stronghold takes the product logic.
- Treasury stays a backend (databases).
- Ember (Windows) wraps the existing Vue code.
- `ember_web` stays for now, disabled, as code reference only. Deleted soon after.
- One admin app per backend service.
- Order: renames and splits first, Windows app last.

## Target

| Backend | From | Role |
|---|---|---|
| `portcullis` | `ember_api` | Entry point. Login, sessions, accounts, roles, permissions, rate limits, security, logs, traffic. Authenticates, then forwards to the other backends. |
| `armory` | `armory` | Tools: capabilities, extensions, server manager. Unchanged. |
| `legion` | `legion` | AI agents. Unchanged. |
| `stronghold` | most of `ember_api` | Product logic (see below). |
| `treasury` | `treasury` | Database gateway. Unchanged. |

| Admin app | From | Port |
|---|---|---|
| `legion_admin` | exists | 26500 |
| `portcullis_admin` | `ember_admin`, renamed and trimmed | 26501 |
| `armory_admin` | split out of `ember_admin` | 26503 |
| `stronghold_admin` | new | 26504 |
| `treasury_admin` | new | 26505 |

Ember (Windows app): `apps/ember`, Tauri wrapper around a copy of `ember_web` code. `ember_web` itself is removed from `docker-compose.yml` (port 26502 freed) and its README marked "reference only".

## Route ownership (from `apps/ember_api/src/routes`)

Stays in Portcullis: `auth`, `account`, `admin` (accounts, roles, invites), `settings`, `logs`, `traffic`, `server_info`, `config_issues`, `nav_preferences`, `mcp` (proxy), `agent_admin` and `account_agents` (forward to Legion).

Moves to Stronghold: `chats`, `chat_folders`, `shares`, `notes`, `brains`, `memory`, `calendar`, `tickets`, `triage`, `templates`, `skills`, `usage`, `attachments`, `bard`, `account_tuning`, `admin_tuning`, `capability_files`, `user_extensions`.

Services follow their routes (`services/calendar_*`, `brain_*`, `turns.py`, `chat_service.py`, `alert_*`, `vapid.py`, and so on). Shared helpers (`permissions`, `secret_box`, `rate_limiter`) are decided per task: copy if tiny, else extract into a shared package.

## Legion on the model gateways
Legion stops calling providers itself and calls two shared services in `AI/ModelProviders`. Neither holds a model or runs tools.

| Gateway | Port | Replaces in Legion | Kinds behind it |
|---|---|---|---|
| `ConversationGateway` | 29407 | `src/providers/language/` (`anthropic_provider.py`, `openai_provider.py`) and its failover | `anthropic`, `openai` (incl. Gemini), `scuti` (CNV model services) |
| `DecisionGateway` | 29406 | `src/providers/decision/` (`jev.py`, `laya.py`, `provider.py`) | `typesafe` (Jev), `ollama`, `scuti` (Laya at `/v1/ask`) |

Fit:
- ConversationGateway returns tool calls to the caller, so Legion's tool loop, `update_plan`, delegation, budgets and approvals stay in Legion. Only the provider call changes.
- Agent files keep `llm.provider` and `llm.gateway`. `gateway` now names a saved gateway id in ConversationGateway. Anthropic and OpenAI keys move out of `apps/legion/.env` into that service's `gateways.json` (write-only).
- Legion authenticates with a caller token (`cg_...`, `dg_...`) in `X-Internal-Token` and sends `X-Requester-Username` so usage is labelled per account.
- Legion's `laya-only`, `jev-only` and `both` strategies become choices between two DecisionGateway gateway ids, with the `both` fallthrough kept in Legion.
- Both gateways are services of the Citadel stack: two more containers in the root `docker-compose.yml`, built from their own repos (`../../AI/ModelProviders/ConversationGateway`, `.../DecisionGateway`, the way LayaModel is built from `../LayaModel`). Source, git history and docs stay in `AI/ModelProviders`. They are separate containers, not part of Stronghold. They are not owned by Citadel: Legion is one client among others.
- Inside the stack Legion calls them by service name on the `core` network (`http://conversation_gateway:29407`, `http://decision_gateway:29406`). Both need `SERVICE_ADMIN_PASSWORD` in their `.env`, a volume for their state folder (`gateways.json`, `tokens.json`, `settings.json`), and `depends_on` from `legion`.
- Unlike the web apps (published on `127.0.0.1` only), the two gateways publish their port on `0.0.0.0` so outside services can connect. Their own `docker-compose.yml` is for standalone use; run only one of the two, never both, or the ports clash.
- Outside services connect the same way Legion does: HTTP to the gateway's published port with their own caller token in `X-Internal-Token` (made on the gateway's `/admin/` page, one per caller) and an optional `X-Requester-Username` for usage labels. Both already bind `0.0.0.0` by default (`SERVICE_BIND`, `SERVICE_PORT`) and need `SERVICE_ADMIN_PASSWORD`, so no code change is needed for this.
- Rules for staying independent: no Citadel imports or Citadel-specific fields in the gateway contract; Legion-only needs (agent roles, approvals) stay on Legion's side; each caller gets its own revocable token, never the shared `INTERNAL_TOKEN`.

Things that need care:
- Legion keeps `cooldown.py`, `gateway_failover.py`, `model_limits.py`, `token_limits.py`, `reasoning_effort.py`. Each is either deleted (the gateway does it) or kept (Legion policy). Decided per file at execution.
- Echo the opaque `reasoning_state` on assistant messages so Anthropic thinking survives tool rounds.
- Usage is counted twice: in the gateway and in Legion's `usage_log.py`. Legion's copy stays the source for Ember's usage pages.
- Scuti tool calls: `tool_choice` other than `auto` is rejected. Scuti image input is unverified.
- Decision answers are cached 300 s in the gateway. Router calls repeat often, so this is a gain, but cache-key behavior needs a test.

## Request flow
Frontends call only Portcullis. Portcullis authenticates, then forwards `/api/<product path>` to Stronghold with the internal token and `X-Requester-*` headers (the pattern Armory and Legion already use). Stronghold never sees cookies. One origin for every client, including the Windows app.

## Data
`ember_api` has one SQLAlchemy database, with chat tables that reference accounts. Moving chats, shares and usage to Stronghold means a second database and no cross-database foreign keys. Stronghold keys on the account `uid`, which is already immutable and already sent to Legion and Armory. Migrating existing rows is its own task and needs a verified backup.

## Phases
0. Baseline: new branch, all current tests green, backup of `ember_api` data.
1. Rename `ember_api` → `portcullis` (dir, compose, env, docs, vault notes, deploy tools). Mechanical, no behavior change.
2. Stronghold skeleton: FastAPI app, health, internal-token auth, compose service, port, Portcullis forwarder with a test.
2b. Legion on gateways (independent of the Stronghold work, can run beside it): conversation provider swap first, then decision provider swap. Migrate gateway entries and keys, then remove the old provider code.
3. Move product logic into Stronghold one domain per task, each task keeping Portcullis tests green. Order, least coupled first: calendar, notes/brains/memory, templates/skills, tickets/triage, shares, usage, attachments/bard, tuning, chats/folders/turns last.
4. Stronghold database: own schema for chats, shares and usage. No data migration (fresh install on the deployment device).
5. Admin split: `armory_admin` (Capabilities, Extensions), rename `ember_admin` → `portcullis_admin`, `stronghold_admin` (Tickets, Usage, Analytics, Tuning), `treasury_admin` (connections, instances; new, minimal).
6. Disable `ember_web` (remove from compose, README note).
7. Ember Windows app: copy `ember_web` code to `apps/ember`, Tauri shell, configurable Portcullis URL, auth and origin changes in Portcullis, installer.

## Risks
- Chat turns are the heaviest and most coupled part. Done last in phase 3.
- Browser-only features need decisions in phase 7: web push, shared-chat links, games iframe, FullCalendar.
- `ember_api` checks `Origin` strictly. The Tauri origin needs allowing, or the app needs token auth.
- Rename sweep covers the vault (`Brain/Projects/Citadel.md`, component notes), `AGENTS.md`, `_TODO.md`, `publish_live`, `tools/deploy.bat`.
- Port for Stronghold in the 29600–29899 block collides with Legion's one-port-per-agent range from 29603. Pick the next free port at phase 2.

## Open questions
Resolved:
1. Chats and turns go to Stronghold.
2. Stronghold gets its own database. No data migration: the user reinstalls on the deployment device. Phase 4 becomes "create the Stronghold schema", with no row copying.
3. Frontends call only Portcullis.
5. Both gateways are containers in the Citadel stack, built from `AI/ModelProviders`, with ports open to outside callers by token.
6. A published port plus per-caller tokens is enough. No TLS or reverse proxy.

4. Legion keeps its failover and cooldown logic and rewires it. `GatewayRoute`, `cooldown.py`, the fallback lists, the per-kind cooldown tuning and the public `SwitchInfo` stay. Only `classify()` changes: it stops reading Anthropic and OpenAI SDK exceptions and reads the ConversationGateway error `kind` (`rate_limit`, `quota`, `auth`, `unavailable`) and `Retry-After` instead. The JSON-parse special case for the Anthropic stream goes away with the SDK. A gateway error without a `kind` stays non-retryable. Tests keep their expected switch and cooldown outcomes; only the fake errors change.

Confirmed proposals (2026-11-14): the admin page split in phase 5, the minimal `treasury_admin`, admin ports 26503 to 26505, and Tauri for the Windows app.

Open: none. Plans are in `docs/superpowers/plans/`; the roadmap lists them in order.

## Rules for every phase
- Behavior-preserving steps (rename, route moves, provider swap) get a baseline first: the existing tests pass before the edit, and the same tests pass after it, with only imports and fakes changed.
- Move one ownership boundary per task. Keep each intermediate state buildable and testable. No feature changes inside a move.
- Preserve public routes, error shapes and ordering unless the spec says otherwise.
