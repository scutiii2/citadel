# Forge: group chats with your own Claude and Codex workers

Date: 2026-10-18
Status: approved; implementation split into three plans (api, worker, web)

## Goal

Let an Ember user talk to their own Claude Code and Codex CLI sessions from a page in `ember_web`, and have those sessions do work on the user's own computer. Each user has group chats. A group chat has one human (the owner) and the owner's own workers. A worker is a Claude or Codex instance running under the owner's own subscription.

## Why workers run on the user's computer

A server-side process that spawns `claude` or `codex` uses whatever account is logged in on the server. Doing that for several Ember users would put all of them on one subscription, which breaks the providers' terms. So each user runs a small daemon, `ember-worker`, on their own machine, logged in to their own CLIs. The daemon connects out to `ember_api`. Ember never sees or stores a CLI login or a subscription token.

## Scope

In version 1:

- One human per group (the owner). Every query is filtered by `account_id`.
- Providers: Claude (Agent SDK) and Codex (`codex exec --json`), behind one `Provider` interface.
- A user may invite only their own workers, and only workers whose reported plan passes the provider's plan allowlist.
- Addressed routing (`@claude`, `@codex`) with an opt-in per-group relay.
- One folder per group member, shared by the workers on that member's machine.
- Permission requests relayed to the Forge page as Allow/Deny cards.

Out of scope, recorded in `_TODO.md` ("Forge: deferred features"): several humans per group, git worktree per worker, file browser, sharing groups, usage charts.

## Decisions

| Topic | Decision |
|---|---|
| Worker behaviour | Addressed routing; opt-in relay between workers, off by default, depth cap 3 |
| Workspace | One folder per group member, shared; no worktrees |
| Permissions | Relay each request to the page. Modes: Ask (default), Accept edits, Plan, Full auto (type-to-confirm) |
| Transport | Worker opens an outbound WebSocket to `ember_api`; the browser uses HTTP streaming like Chat |
| Placement | AccountMenu entry at `/forge`, gated by a new `forge.use` permission |
| Name | Forge |

## Architecture

```
browser (ember_web /forge)
   |  HTTP + streaming (events?after=seq)
ember_api  -- forge services, MessageStore, GroupEventBus
   |  WebSocket (worker connects out, bearer pairing token)
ember-worker (user's PC)  -- ClaudeProvider / CodexProvider
   |  subprocess / Agent SDK, uses the user's own CLI login
claude / codex CLI
```

`ember_api` is the hub. It keeps the registry of live worker sockets, stores the transcript, and fans events out to the browser. It assumes one `ember_api` process, which is how Ember runs today. A second process would need a shared registry; that is not built.

## Data model

New migration `0021` in `apps/Ember/ember_api/migrations/versions/` (`0020` is taken), models in `src/models/forge.py`. Owners are `accounts.id` foreign keys with `ON DELETE CASCADE`, like `chat_folders`; there is no `owner_uid`.

- `forge_worker`: `id`, `account_id`, `provider` (`claude` or `codex`), `label`, `token_hash`, `reported_plan`, `last_seen`, `created_at`. The pairing token is shown once; only its hash is stored. Revoking a worker deletes its row: its group memberships go with it and its token stops working. Every stored worker message carries the worker's label and provider in its body, so a transcript stays readable after the worker is gone. `label` is the worker's `@mention` handle: 1 to 24 letters, digits, `-` or `_`, unique per account ignoring case, pre-filled with the provider name.
- `forge_group`: `id`, `account_id`, `title`, `mode` (`ask`, `accept_edits`, `plan`, `full_auto`), `relay` (bool, default false), `last_worker_id` (the worker addressed last, for messages with no @mention), `created_at`.
- `forge_group_worker`: `group_id`, `worker_id`, `folder`, `last_seq` (the newest message this worker has already been shown, so the next turn sends only what it missed). The folder is per member because a user's Claude and Codex workers may run on different computers, where the same project has different paths. The UI pre-fills the same path for both.
- `forge_message`: `id`, `group_id`, `seq`, `sender` (`user` or a worker id), `kind` (`text`, `tool`, `permission_request`, `permission_result`, `system`), `body` (JSON), `created_at`. `seq` is unique and increasing per group, so the browser resumes from the last `seq` after a reconnect.

The plan allowlists are stored in `app_settings` (names `forge_plans_claude` and `forge_plans_codex`, each a JSON list of lower-case plan strings), editable by accounts with `settings.manage`, not in a table.

An invite is rejected when `worker.account_id != group.account_id`, when `reported_plan` fails the provider's allowlist, when the worker is already in the group, or when the group already has 8 workers.

## Worker protocol

Frames are JSON, one per WebSocket message.

Pairing: on the Forge page the user picks a provider and label and gets a one-time token and the command `run.bat pair <ember_url> <token> --provider <claude|codex>`, run from the `ember_worker` folder (`apps/Ember/ember_worker`; the same command also exists as the `ember-worker` console script). The worker stores the token in its own config file, reads its CLI auth, reports its plan, and refuses to pair when the CLI is not logged in.

Connection: the worker connects to `/api/forge/worker` with `Authorization: Bearer <token>`. `ember_api` checks the hash, rejects revoked tokens, and registers the socket under the worker id. The worker sends a heartbeat every 20 seconds (updates `last_seen`) and reconnects with backoff. A dropped socket marks the worker offline; a running turn gets a `system` message "worker disconnected". Revoking a worker closes its socket.

Server to worker:

- `turn`: `group_id`, `folder`, `mode`, `prompt`, and the group history since this worker's last turn (size-capped).
- `permission_reply`: `request_id`, `allow` or `deny`.
- `cancel`: `group_id`.

Worker to server:

- `delta`: streamed text.
- `tool`: tool name and a short summary.
- `permission_request`: `request_id`, tool, summary.
- `turn_done`, `turn_error`.
- `usage`: tokens, when the CLI reports them (stored; no charts in version 1).

## Routing

- `@<label>` in the user's message selects the target worker (the default labels are `claude` and `codex`). Only one turn runs per group at a time; a message sent while one runs is refused with 409. With no mention, the last-addressed worker gets the message. With no worker addressed yet and exactly one invited, that worker gets it.
- With `relay` on, a worker reply whose last line starts with `@<other label>` is forwarded to that worker as a new turn. A depth cap (default 3) stops loops.
- With `relay` off, mentions inside worker replies are plain text.

## Permissions

The worker maps the group `mode` onto the CLI's own permission settings through a per-provider `PermissionMapper`. Claude Code maps Ask, Accept edits, Plan and Full auto to its `default`, `acceptEdits`, `plan` and `bypassPermissions` modes and relays what it would ask. `codex exec` is non-interactive, so Codex cannot ask: Ask and Plan run in its read-only sandbox, Accept edits in `workspace-write`, Full auto in `danger-full-access`, and the page says so. Requests it cannot resolve itself become `permission_request` frames, shown as Allow/Deny cards; the worker waits. A request unanswered for 10 minutes is denied. `full_auto` needs type-to-confirm in the UI and posts a `system` message. The mode that skips all prompts without that confirmation is not offered.

## Plan gating

`PlanPolicy.is_allowed(reported_plan)` per provider, with allowlists in `app_setting`. The allowlist starts empty, so unknown plans are refused (fail closed). Nobody guesses plan strings: the Forge page shows each worker's reported string as the CLI gave it, and an account with `settings.manage` types the eligible ones into the allowlist. Comparison ignores case and surrounding spaces. The check runs on invite and again when a turn starts; a downgrade in between fails the turn with a `system` message. This is a UI and API guard only, since the provider enforces the real limit. A worker also reports its own plan, so the value is not verified by Ember.

## API (ember_api)

All routes require a session with `forge.use` and filter by `account_id`.

- Plan allowlists: `GET /api/forge/plans` (any `forge.use` account sees the eligible strings), `PUT /api/forge/plans/{provider}` (needs `settings.manage`).
- Workers: `GET /api/forge/workers`, `POST /api/forge/workers` (returns the token once), `DELETE /api/forge/workers/{id}` (revoke).
- Groups: `GET/POST /api/forge/groups`, `PATCH /api/forge/groups/{id}` (title, mode, relay), `DELETE /api/forge/groups/{id}`.
- Members: `POST /api/forge/groups/{id}/workers` (invite, with folder), `DELETE /api/forge/groups/{id}/workers/{worker_id}`.
- Chat: `GET /api/forge/groups/{id}/events?after=<seq>` (streaming), `POST /api/forge/groups/{id}/messages`, `POST /api/forge/groups/{id}/permissions/{request_id}`, `POST /api/forge/groups/{id}/cancel`.
- Worker socket: `WS /api/forge/worker`.

## Classes

Everything is async. Routes stay thin; services take their dependencies by injection.

`ember_api`, `src/services/forge/`:

- `WorkerConnection`: wraps one WebSocket; `send(frame)`, receive loop, heartbeat tracking.
- `WorkerRegistry`: live `worker_id` to `WorkerConnection`; `register`, `get`, `drop`.
- `WorkerPairingService`: create a worker, hash and verify tokens, revoke.
- `PlanPolicy` (ABC) with `ClaudePlanPolicy` and `CodexPlanPolicy`, plus `PlanPolicyRegistry`. A new provider is one new subclass.
- `GroupService`: create groups, change mode and relay, invite workers. Enforces ownership and plan gating.
- `MessageStore`: `append`, `list_after(seq)`.
- `TurnRouter`: mention parsing, target choice, relay depth.
- `PermissionBroker`: pending requests, replies, timeout.
- `GroupEventBus`: per-group async fan-out to open browser streams.
- `TurnCoordinator`: runs one turn end to end (router, registry, frames into `MessageStore` and `GroupEventBus`). The only class that knows the whole flow.

`ember_worker`, new app `apps/Ember/ember_worker/` (layout per the root-project-scaffold skill):

- `Provider` (ABC): `detect_plan()`, `run_turn(turn) -> AsyncIterator[Event]`, `cancel()`. Subclasses `ClaudeProvider` (Agent SDK) and `CodexProvider` (async subprocess, `codex exec --json`).
- `PermissionMapper` per provider.
- `WorkerClient`: socket, reconnect with backoff, heartbeat; hands frames to `TurnRunner`.
- `TurnRunner`: one active turn per group, cancel.
- `WorkerConfig`: URL and token in a config file.

## Frontend (ember_web)

Route `/forge` in the AccountMenu, gated by `forge.use`. Follows the `ember-frontend-design` skill: shared tokens and the radius scale, in-app confirms, type-to-confirm for risky actions.

- Left: group list and "New group" (title, mode, invite workers with a folder each).
- Center: transcript and composer. Sender badges (you, Claude, Codex); tool calls as collapsed one-line rows; permission cards inline; `@` autocomplete over invited workers; Stop button visible while a turn runs.
- Right panel: members (online dot, plan, folder), mode pills, relay toggle with the depth cap, Invite.
- Workers dialog: list with provider, label, plan, online state and an eligible badge. "Add worker" shows the token and pairing command once, with a copy button. Revoke uses type-to-confirm. The invite list shows only the user's workers; ineligible ones are disabled with the reason.
- Mode changes between Ask, Accept edits and Plan apply at once. Full auto needs type-to-confirm.
- Pinia `forgeStore` resumes the event stream from the last `seq`.
- Empty state with no workers: a short pairing guide.

## Error handling

- Worker offline when addressed: a `system` message, no silent drop.
- Folder missing on the worker: the worker returns `turn_error`, shown in the transcript.
- Permission timeout: auto-deny, with a `permission_result` message.
- Provider failure or CLI not logged in: `turn_error` with the CLI's own message.
- Plan no longer eligible at turn start: the turn fails with a `system` message.

## Security

- Pairing tokens are random, shown once, stored as hashes, and revocable. A revoked token cannot connect.
- The worker runs code on the user's own machine under that user's account; the Ember host runs none of it.
- Ownership is enforced in services, not only in routes: every read and write takes `account_id`.
- `full_auto` is the only unattended mode and needs type-to-confirm.
- The socket only carries work for the worker's own owner; group history sent to a worker contains only that owner's group.

## Testing

- `ember_api` (pytest): ownership and invite rules, plan gating with a fake policy, `TurnRouter` mentions and relay depth, `PermissionBroker` timeout, `MessageStore` ordering and resume, all with a fake `WorkerConnection`.
- `ember_worker`: unit tests with a fake `Provider`; `PermissionMapper` mappings; reconnect and cancel behaviour.
- `ember_web`: checked against the fake-API approach already used for other pages.
- No live provider call runs in automated tests.

## Subscription terms and limits (checked 2026-10-18)

- Anthropic's Agent SDK documentation says third-party developers may not offer claude.ai login or route requests through Free, Pro or Max credentials on behalf of their users. Forge keeps to this by running each user's own CLI on their own computer with their own login; Ember never handles a login. It must not be offered as a service that runs one account's subscription for other people.
- Since 2026-06-15 Anthropic gives paid plans a separate monthly Agent SDK credit that covers Agent SDK use in your own projects and `claude -p`. It is not the interactive Claude Code allowance, so Forge's Claude worker may draw on that credit instead of the normal plan limit. Check the credit size on the current Anthropic help page before relying on Forge for heavy work.
- Neither CLI's plan field names are confirmed here; the first worker run shows what they report.

## Wire protocol (exact)

One JSON object per WebSocket text frame, with a `type` field. Both the `ember_api` and `ember_worker` plans implement exactly this.

Worker to server:

| type | fields |
|---|---|
| `hello` | `plan` (string or null), `version` (string). Always the first frame. |
| `heartbeat` | none |
| `delta` | `turn_id`, `text` |
| `tool` | `turn_id`, `name`, `summary` |
| `permission_request` | `turn_id`, `request_id`, `tool`, `summary` |
| `usage` | `turn_id`, `input_tokens`, `output_tokens` |
| `turn_done` | `turn_id`, `text` (the full final reply) |
| `turn_error` | `turn_id`, `message` |

Server to worker:

| type | fields |
|---|---|
| `ready` | `worker_id`. Sent once after `hello` is accepted. |
| `turn` | `turn_id`, `group_id`, `folder`, `mode`, `prompt`, `history` (list of `{sender, text}`) |
| `permission_reply` | `request_id`, `allow` (bool) |
| `cancel` | `turn_id` |

`turn_id` is a UUID string made by `ember_api`. `request_id` is a UUID string made by the worker. Unknown frame types are ignored by both sides. A `hello` rejected for a revoked token closes the socket with code 4401.

Browser events (`GET /api/forge/groups/{id}/events`, server-sent events): a stored message is `{"type":"message","seq":int,"sender":str,"kind":str,"body":object,"created_at":str}` and has an SSE `id:` equal to `seq`; `{"type":"delta","turn_id":str,"sender":str,"label":str,"text":str}` and `{"type":"turn","running":bool}` are live only and carry no id. After a reconnect the stream replays stored messages with `seq` above `after`; a partly streamed reply is shown again in full when its `turn_done` message arrives.

## Plans

Three plans, built in this order, each testable alone: `docs/superpowers/plans/2026-10-18-forge-api.md`, `…-forge-worker.md`, `…-forge-web.md`.

## Open items

- `ember_api` has no WebSocket route today. Its middleware is pure ASGI and ignores non-HTTP scopes, so a route works; serving one needs the `websockets` package, added to `pyproject.toml` by the api plan.
- Confirm how the Claude Agent SDK and `codex exec --json` expose permission requests, so `PermissionMapper` can be specified exactly. If a CLI cannot relay prompts, that provider falls back to the mode-only behaviour and the page says so.
