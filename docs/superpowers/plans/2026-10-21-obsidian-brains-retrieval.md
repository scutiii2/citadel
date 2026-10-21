# Obsidian brains: Scoped retrieval Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for native execution in this session. Steps use checkbox syntax for tracking.

**Goal:** Deliver scoped retrieval from the approved Obsidian brains specification.

**Architecture:** Armory runtimes keyed by connection ID/generation/model reuse VaultIndex ranking with remote enumeration. API dedicated brain routes proxy authorized browse/read/search operations independent of tool opt-in.

**Tech Stack:** Existing FastAPI, db_gateway, SecretBox, FastMCP, SQLite hybrid index, Vue/TypeScript; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-obsidian-brains-promotion-design.md`

## Global constraints

Preserve Notes and Memory contracts. Every signed-in valid account reads the instance brain; only authorized publishers write it. Personal ownership uses immutable trusted UID. No stored key in browser reads, logs or prompts. HTTPS with checked connect-time DNS, no personal loopback/link-local/metadata, no redirects. No automatic publication, external writes, deployment, commits or model downloads during implementation. No motion preference settings. Existing approvals and capability gates still apply to agent use.

## Review focus

Concurrent saves must not lose revisions; stale workers cannot cross generations; unavailable personal destinations never fall back to shared; account deletion revokes access; model output never authorizes a publication.

## Task 1: Contract and regression tests

**Files:** Armory index runtime, remote source/index and brain HTTP routes; Ember API gateway; Web brain browser and navigation.

**Interfaces:** RemoteVaultIndex.refresh/search; ScopedRuntimes.get(snapshot)/retire; brain operations list/read/search/status; combine both sources using rank fusion and safe source metadata.

- [x] Add focused regression tests for: Partial scans never remove unseen docs; generation change never returns previous vault; isolated owners; bounded workers and model concurrency; disable/account deletion cancels refresh and retires derived state.
- [x] Run the focused tests using existing isolated test environments; record final verification below.

## Task 2: Implement and integrate

- [x] Implement the interfaces above using existing services and shared UI controls.
- [x] Exercise failure, retry, cancellation and owner/permission boundaries without external services.
- [x] Run owning regression suites, type checks and production builds for changed apps.

## Task 3: Verification and delivery

- [x] Add focused fake-API browser flows for changed UI.
- [x] Update README/API/generated-state documentation and account cleanup.
- [x] Review combined implementation against spec, record actual validation and limitations.

Execution is already requested by the user. Proceed natively through connections, retrieval, then promotion without repeated permission checkpoints. Preserve the original untracked spec in the primary checkout. Live integration needs a configured vault and is separate from mocked verification.

## Verification recorded 2026-10-21

Implemented in `codex/obsidian-brains` based on `d08062ff`. No commit, merge,
push, deployment or live vault publication was performed.

- Ember API: 189 affected tests passed, including migration, account deletion,
  Notes, promotions, suggestions, connection resolution and chat compatibility.
- Ember Web: full Vitest suite, 2,082 tests in 151 files passed; `vue-tsc -b`
  passed. New personal-connection and promotion Playwright flows: 2 passed.
  Existing Notes browser flows: 8 passed.
- Ember Admin: full Vitest suite, 483 tests in 51 files passed; `vue-tsc -b`
  passed. Instance connection Playwright flow: 1 passed.
- Both frontend production builds passed through their Playwright setup.
- Armory final affected suite: 146 passed (two existing framework warnings),
  including network restrictions, create-only version guard, owner/generation
  resolution, index retirement, partial remote scans and existing tool contracts.
- Garrison: 45 affected identity, delegation and router transport tests passed.
- CLI: 2 standalone destination tests passed with `--noconftest`; the full CLI
  suite was not run because this environment lacks rich and pytest-asyncio.
- Final Settings save-label encoding repair: 32 Settings tests passed.
- Tracked diff whitespace, new source whitespace and UTF-8 checks passed.

Independent review found two issues, both fixed and covered by regression tests:
retiring workers must retain their SQLite files until they stop, and confirmed
pre-write filename collisions must allow a corrected atomically reserved path.
Follow-up review reported no additional P1/P2 findings.

Verification used fake vaults, model responses and embeddings. Live TLS trust,
vault connectivity, configured interpretation and embedding services still need
an operator smoke test. Conditional publication requires Local REST API 5.2.0+.
See [operations](../../obsidian-brains.md) for rollout and generated-state details.
