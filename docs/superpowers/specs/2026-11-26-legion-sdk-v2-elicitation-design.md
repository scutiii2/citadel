# Legion on MCP SDK v2, and elicitation

Date: 2026-11-26. Status: design, not built.

## Goal

An MCP server can ask the user something in the middle of a tool call, and the user answers in Ember. This works for tool calls made by the entry agent and by specialist sub-agents.

## Scope

In:

- Legion moves to the `mcp` Python SDK 2.x.
- Elicitation (form and URL mode) from servers that speak protocol `2026-07-28`: admin-added connections and users' private extensions.
- Relay through delegation, then Stronghold, Portcullis and Ember.

Out:

- Upgrading Armory, Stronghold or Portcullis. They stay on SDK 1.x, so Armory and Stronghold tools cannot ask yet.
- Elicitation from older servers (2025-11-25 and earlier). Legion shares their connections between users, and their requests carry no link to the call that caused them.
- The Tasks, Skills and file transfer extensions.
- Sampling and roots requests.
- Outside clients of Portcullis. They never receive questions.

## SDK facts

Read from the 2.3.0 source on 2026-11-26, not yet run. The table is in `docs/superpowers/plans/2026-11-26-legion-mcp-sdk-v2.md`. The ones that shape this design:

- `ClientSession.initialize()` stays on the old protocol; `discover()` selects the new one.
- `call_tool(..., allow_input_required=True)` returns `InputRequiredResult` to the caller.
- `MCPServer` has a public `middleware` hook; its context carries the request and `_meta`.
- A request timeout is error code -32001, not 408. A dead connection or an HTTP error reaches the caller as `MCPError`, not as an HTTP library exception, so failover and reconnect check the error code.
- `citadel_auth.ServiceAuth` is an `httpx` auth; Legion wraps it for `httpx2` without editing the shared library.

Still to prove by running, as the first implementation step: a 2.x client connects to a 1.30 server (probe with `discover()`, then connect the old way). Stop and reconsider if it does not.

## Part 1: SDK upgrade (Legion only)

About 15 files in `apps/legion/src` and `scripts`, and about 20 test files.

- Dependency: `mcp>=2.3,<3`.
- Server: `FastMCP` becomes `MCPServer`. `host` moves to `streamable_http_app(host=...)`, so DNS rebinding behaviour stays as it is today.
- Request size: v2 limits a request body to 4 MiB by default. `ask` carries the chat history, so set `max_request_body_size` to 32 MiB.
- Sync tools now run on a worker thread. Check that `cancel`, `status` and `interpret` are safe there; make `cancel` async if the cancellation registry is not thread-safe.
- Requester identity: one server middleware replaces `install_mcp` and the `request_ctx` read in `src/runtime/internal_auth.py`. On `tools/call` it reads the request and `_meta`, runs `mcp_requester`, and fails closed.
- Protocol choice:
  - Admin-added connections and private extensions probe with `discover()`. If the server does not support it, open a fresh session and use `initialize()`.
  - Built-in Armory and Stronghold connections, delegation and router calls use `initialize()`.
  - The private extension preflight sends a handshake-era protocol version.
- Renames: `isError`, `structuredContent`, `inputSchema`, `outputSchema`, `readOnlyHint` and `McpError` take their v2 names. Replace `getattr(result, "isError", False)` style reads with direct attribute reads, so a missed rename raises instead of reporting success.
- HTTP: MCP clients move to `httpx2`. `src/tools/private_extensions/guard.py` and the origin check in `transports.py` keep every address and redirect check. Set timeouts explicitly (the `httpx2` default is 5 seconds).
- Timeouts passed to the SDK become seconds as floats.

This part is committed with its tests passing before part 2 starts.

## Part 2: elicitation in Legion

### Turning it on

- New `ask` argument `elicit: bool = False`. Delegation passes it to specialists. `ask_user` stays top-level only.
- Elicitation is on for a turn only when `elicit` is true and the requester has a uid.

### Call loop

The registry and the private extension pool run the loop, because they hold the session across rounds. `mcp_upstream` gives them one async callback that asks the user. The callback waits on the server's event loop.

1. Call the tool with `allow_input_required=True`.
2. On `InputRequiredResult`, handle each elicitation request in turn, one card each.
3. Retry the call with `input_responses` and `request_state` on the same session. A private origin connection stays referenced until the loop ends. If the address drops, the call fails; it is never replayed on another address.
4. At most 5 rounds per tool call, counting rounds with no input request. A sampling or roots request fails the call.
5. Each round has the normal 120 second tool timeout. Waiting for the user does not count.

A 2026 session always declares the elicitation capability, by setting an `elicitation_callback` that only declines. Real answers go through the call loop. When the turn cannot show cards, the loop answers `decline`. A fallback session for an older server is built without the callback, so older servers are not offered elicitation and behave as they do today.

### Waiting

A new `src/runtime/elicitations.py` reuses `Broker`, like `questions.py`.

- Keepalive event every 20 seconds.
- Timeout 600 seconds, then Legion sends `cancel`.
- Stop ends the wait and the call is not retried.
- After `decline`, Legion adds "The user declined the server's question." to the tool result text.

### Events

`elicitation_request`:

| Field | Meaning |
|---|---|
| `id` | New random id |
| `server` | Label from Citadel's own configuration, never the server's claim |
| `tool` | Tool name |
| `mode` | `form` or `url` |
| `message` | Server text, plain, at most 2,000 characters |
| `fields` | Form mode only, see below |
| `url` | URL mode only |

Each field has `name`, `label`, `kind` (`text`, `number`, `integer`, `boolean`, `choice`, `multi_choice`), `required`, and optionally `description`, `options` (`value`, `label`), `min`, `max`, `max_length`.

`elicitation_resolved`: `id`, `outcome` (`accepted`, `declined`, `cancelled`, `timeout`).

Add `elicitation_request`, `elicitation_resolved` and `keepalive` to `_PASS_THROUGH` in `agent_events.py`.

### Answer tool

`answer_elicitation(request_id, id, action, content)` with `action` of `accept`, `decline` or `cancel`. It returns `{"answered": bool, "problem": str | null}`. A `problem` means the content failed validation and the card stays open. `answered: false` with no problem means nothing is waiting.

### Relay through delegation

```
specialist --progress event--> parent Legion --> Stronghold --> Ember
specialist <--answer_elicitation-- parent Legion <-- Stronghold <-- Ember
```

- When the parent forwards a specialist's `elicitation_request`, it records `(parent request_id, id)` to the specialist's address and child request id.
- `answer_elicitation` checks the local broker first, then that record, and forwards the call.
- The record is removed on `elicitation_resolved` or when the delegated call ends. This works at any delegation depth.

### Security

- Each waiting elicitation stores the requester uid. Only that uid can answer, at every level.
- Form schemas must be flat and use the field kinds above, with at most 10 fields, 20 options per choice, labels up to 80 characters, descriptions up to 200 and text values up to 2,000. Anything else is declined. Legion validates the answer against the schema before sending it.
- URLs must be `https`, with no embedded credentials, at most 2,048 characters. Legion never fetches them.
- The server's text never reaches the model. Answers are never logged, never saved in history or usage rows, and never given to the model by Legion.

## Part 3: Stronghold, Portcullis, Ember

### The client flag

Ember sends `can_elicit` with each turn, beside `can_ask`. Default false, so an older installed Ember never leaves a server waiting. Portcullis' turn body and Stronghold's turn route and options carry it.

### Stronghold

- The gateway sends `elicit` to Legion only when `can_elicit` is set, and gains `answer_elicitation`.
- The engine keeps `pending_elicitations` in the turn snapshot, so a reconnecting window sees the card. It is cleared on resolve and at turn end. Event strings and field counts are capped.
- Route `POST /turns/{chat_id}/elicitations` with `{id, action, content}`: 404 when no answer is being written, 409 when nothing waits, 422 on invalid content (including a `problem` returned by Legion, which keeps the card open), 502 when the agent call fails. Content is not logged. Saved steps keep the outcome only.

### Portcullis

One pass-through route `POST /chats/{chat_id}/elicitations` with the same permission as questions.

### Ember

Read `.agents/skills/ember-frontend-design/SKILL.md` first. New `ElicitationCard.vue` beside `QuestionCard.vue`, built from `@citadel/ui` parts and the shared chat styles; a reusable part that is missing is created in `libs/citadel_ui`. The client method and the store list mirror questions. A button that is busy keeps its size.

Form card: heading with server, agent and tool; the message as plain text; labelled fields with a required marker; the warning "Do not enter passwords or keys here."; buttons Send, Decline, Cancel. Errors sit beside their field and entered values are kept.

URL card: heading; the site name in punycode form; the full URL, wrapped and selectable; "Open link" as a real link with `rel="noopener noreferrer"`; "Copy link"; then Continue, Decline, Cancel. Continue sends `accept` and is enabled after the link was opened or copied. Opening the link alone sends nothing, because the server would ask again at once.

The desktop shell has no opener plugin, so "Open link" may do nothing there. Ship "Copy link" as the fallback and add the plugin only if the manual check fails.

## Errors

| Case | Result |
|---|---|
| `elicit` not set | `decline`, the tool goes on |
| Unsupported schema or URL | `decline`, the step shows the reason |
| User declines | `decline`, tool result carries the note |
| 600 seconds pass | `cancel` |
| Stop | Wait ends, no retry |
| Over 5 rounds, sampling or roots request | Tool call fails |
| Address drops between rounds | Tool call fails |
| Specialist ends while waiting | Record removed, card cleared |
| Late or duplicate answer | `answered: false`, HTTP 409 |

Pending elicitations live in memory. A restart loses them, as with `ask_user` today.

## Ship order

Legion, Stronghold, Portcullis, then Ember (installer rebuild and web publish). Every new argument and flag defaults to off, so each step is safe on its own.

## Tests

Run only the files that cover each change.

- Upgrade: the Legion tests that touch the SDK, updated. New cases: protocol fallback, a failed tool result detected after the rename, timeout triggers origin failover.
- Guard: the private extension address and redirect tests keep their intent on `httpx2`.
- Elicitation: a new `apps/legion/tests/test_elicitation.py` with a fake 2026 server: accept, decline, timeout, round cap, schema rejection, older server not offered elicitation, wrong uid refused, two-level relay.
- Stronghold: route and engine snapshot tests. Portcullis: pass-through test. Ember: `ElicitationCard.test.ts` and chat store tests.

Manual checks: 2.x client against a running 1.30 server, desktop "Open link", the card at 375 px in light and dark, and one real 2026 outside server if one is in use.
