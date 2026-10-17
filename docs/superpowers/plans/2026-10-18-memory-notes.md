# Memory and Notes Implementation Plan

**Goal:** Implement the approved separate Memory and Notes pages on `codex/ember-memory-notes`, using Ember Web's existing design.

**Architecture:** Keep Notes on its existing API. Add an account-scoped Memory API in ember_api backed by internal HTTP routes in mcp_server and its existing SQLite memory store. No new database, dependencies, or model calls. The browser never supplies an owner or receives an internal token.

**Design:** The two mockups approved in this chat. Preserve the rail, theme tokens, compact page headings, list/form Notes layout, explicit Save and agent-access toggle. Memory uses searchable cards, Add and Edit dialogs, confirmed deletion, and Load more. Show real text and creation dates; the store has no category, provenance or last-edited fields, so do not fabricate them.

**Constraints:** Keep memory separate from private notes. All memory endpoints require `chat.use`, and internal endpoints require the shared token and an enabled memory capability. Preserve the existing memory tool contracts. Never add a reduced-motion setting or query. Do not commit or push without instruction.

## Tasks

- [x] Add failing store and internal-route tests for owner isolation, atomic edits, duplicate text, stale edits, validation and disabled memory.
- [x] Implement internal list/create/edit/delete using existing storage; update FTS atomically with text and preserve creation dates.
- [x] Add failing ember_api tests for authentication, permission, owner identity, upstream failure and validation. Implement a typed service and routes; add audit privacy coverage.
- [x] Add Memory view tests, typed client, route and navigation entry. Implement search, pagination, add/edit/delete, busy/error states and accessible dialogs.
- [x] Refine Notes spacing and focus styling without changing its save/conflict/access behavior.
- [x] Update READMEs and e2e fake API, run focused tests, frontend type-check/build and relevant regression suites; review the diff.

## Review focus

Cross-account IDs must remain inaccessible; stale edits must not overwrite newer text; upstream failure must retain drafts; search and pagination must stay in step; narrow layouts must wrap without horizontal overflow.

## Verification record

- All 1,911 frontend unit tests passed across 132 files.
- All 9 Memory/Notes Playwright browser flows passed.
- TypeScript and production Vite/PWA build passed.
- All 64 focused mcp_server memory store, internal route and existing tool tests passed.
- All 66 relevant ember_api tests passed: 51 existing Notes/account-purge regression tests and 15 Memory API tests, including permission enforcement, audit privacy and malformed upstream responses.
- Independent code review found no actionable issues; `git diff --check` passed.
- Fixed a pre-existing ChatHeader TypeScript overload error by choosing event registration methods explicitly; its regression tests passed.
- No dependency manifests, database schemas or existing memory tool result contracts changed. Local commit and merge into main authorized by the user; no push requested.
