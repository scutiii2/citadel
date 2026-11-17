# Plan 12: dynamic service-to-service auth (design)

<!-- history-note -->
> **History (noted 2026-11-18).** This document names files and settings that no longer exist: `specifics/`, seed files,
> `config_*.json` toggle, tuning and connection files, and tokens or addresses kept in `.env`. Those settings are now saved
> in each service's database and edited in its admin app; see `apps/armory/docs/settings.md` and each service's
> `configs/README.md`. Kept as it was written; do not follow its file paths.

Status: design approved 2026-11-17 (decisions below). Replaces the shared `INTERNAL_API_TOKEN` between `portcullis`, `stronghold`, `legion`, `armory` and `treasury`. Implementation can be handed to Codex after this is approved.

## Problem

One secret is shared by every backend and checked by string compare.
- Any holder can call any backend and claim any identity. Stronghold believes `X-Requester-Uid` from whoever has the token.
- Armory runs tools (SSH, Docker, files) and Treasury holds all data. Both are open to anyone with the token.
- The secret never changes, and the same file is copied into five projects (`shared_token.py`, five auth modules, about 125 files touch it).

## Goals

1. Each service has its own identity. Receivers know who is calling.
2. Only Portcullis can say which user a request is for. A compromised Stronghold or Legion cannot invent a requester.
3. Credentials are short-lived and nothing is set by hand.
4. Start order does not matter, and one service being down does not stop the others from talking.
5. One small shared library replaces five copies.

Out of scope: the tool services outside Citadel (Bard, Scribe, Reader, Lens, Mimic) and the gateways (ConversationGateway, DecisionGateway). They keep their per-caller tokens, which Legion and Stronghold already hold. Browser sessions and login stay as they are.

## Decision: services sign for themselves, no central issuer

My earlier sketch had Portcullis issue tokens. That fails on start order and on outage: Treasury and Armory start first, Stronghold calls Portcullis, and if Portcullis is down nothing could renew. So:

- **Every service has its own Ed25519 key pair**, made on first start. No new dependency: `cryptography` is already in all five `uv.lock` files.
- **Every call carries a short assertion signed by the caller**: `{iss, aud, iat, exp (60 s), jti}`. Receivers verify the signature with the caller's public key.
- **Public keys are distributed through a trust directory**, one folder per service.
  - Docker: a volume per service, mounted **read-write only in its owner** and **read-only in the others**. Mount rules, not a secret, decide who may publish a key, so a service cannot replace another's key.
  - Without Docker: `~/.citadel/trust/<service>/` on a dev machine; the same rule, relaxed to the user account.
- **Private keys stay out of the trust folders** (others can read those). Each service keeps its private key in its own identity folder and publishes only the public key.
- **Receivers re-read the directory on an unknown key id**, so a service that restarts with a new key is picked up without a restart.

Rejected alternatives:
- Central issuer (Portcullis): circular start, single point of failure.
- Per-service static tokens (about two plans of work): fixes impersonation but nothing rotates and the tokens are set by hand.
- mTLS: needs certificates, and Windows without Docker makes it fragile.

## Who may be a user

Service assertions say *who is calling*. They do not say *which user*. For that:

- Portcullis, after it checks the login and permission, **signs a requester token**: `{sub: uid, username, email, permissions version, aud: [stronghold, legion, armory], exp}`. Only the `portcullis` key may sign it.
- Stronghold, Legion and Armory pass it on unchanged. They verify it against Portcullis's public key and read the requester from the token, never from `X-Requester-*` headers or MCP `_meta`.
- **Long turns:** a turn runs for minutes. The requester token lives 15 minutes; Stronghold's turn engine asks Portcullis for a fresh one (`POST /internal/requester-token`, allowed only for `stronghold`, only for an account with a running turn) before it runs out. Open question 1.

## Authorisation table

One table in the shared library, same in all services: `caller → audience → allowed route prefixes`. Examples:

| Caller | May call |
|---|---|
| portcullis | stronghold (`/`), armory (`/mcp`, `/upload`, `/admin`), treasury (admin routes), legion (`/registry`, `/agents`) |
| stronghold | treasury (data), armory (`/mcp`, notes), legion (`/mcp`), portcullis (`/internal/*`) |
| legion | armory (`/mcp`), treasury (its own connections) |
| armory | stronghold (`/brains/resolve`, notes), treasury |
| treasury | nothing outbound |

Anything not in the table is 403. `/health` stays open.

## Shared library

New package `citadel_auth` (kept in this repo, vendored or path-installed into each app), replacing `shared_token.py`, five auth middlewares and the client header code:

- `Keyring`: make, load and publish this service's key; read the trust directory; cache public keys.
- `sign(aud) -> assertion`; `verify(assertion, expected_aud) -> Caller`.
- `AuthMiddleware` (ASGI) and a FastAPI dependency; MCP server hook for Armory and Legion.
- `ServiceClient`: an `httpx` auth hook that adds a fresh assertion (cached for about 30 s per audience).
- `requester`: `mint` (Portcullis only), `verify`, `current()` context variable.
- Policy table and its loader.

## Rollout: hard cut-over, no legacy

Decided: no dual-accept, no `AUTH_LEGACY`, no migration of the old token. Each service deletes the shared token as it moves, so there is never old code to keep in step. No stack has run live yet, so nothing running is broken by this.

All steps land on one branch (`plan-12-service-auth`) and merge to `main` once, after 12.7. Between steps the services cannot call each other for real (their unit tests use fakes and stay green), so the first honest test across services is 12.7.

| Step | Work |
|---|---|
| 12.1 | `citadel_auth` library, unit tests, trust-directory mounts in `docker-compose.yml`. |
| 12.2 | Treasury: inbound checks. Smallest; delete its `shared_token.py` and token tests. |
| 12.3 | Armory: `/mcp`, `/upload`, media routes, outbound to Stronghold and Treasury; requester read from the token. |
| 12.4 | Stronghold: inbound, outbound (armory, legion, treasury, portcullis `/internal`), requester-token refresh. |
| 12.5 | Legion: `/mcp`, `/registry`, `/agents`; outbound to Armory and Treasury. |
| 12.6 | Portcullis: mint requester tokens, sign every outgoing call, `/internal/*` checks callers. Remove `INTERNAL_API_TOKEN`, `INTERNAL_TOKEN_FILE`, the `internal_token` volume, `.env.example` lines and docs for them. |
| 12.7 | Live run of the whole stack (nobody has run it live yet). Fix what it shows, then merge. |

Each service's step removes that service's old token code and tests in the same step.

## Tests

- Library: sign/verify, expiry, wrong audience, wrong key, replayed `jti` inside the window (small in-memory set per receiver), tampered claims, unknown `kid` reload.
- Per service: one test per rule in the policy table that matters (allowed, denied, unknown caller), one that a forged `X-Requester-Uid` is ignored.
- Compose: a check that the trust mounts are `rw` for the owner only.
- These are the only new test families; each service's old token tests are deleted in its own step.
- The slow tests are tagged `slow` per the test audit (`2026-11-17-test-audit.md`).

## Failure behaviour

- Receiver cannot read the trust directory: refuse requests (fail closed), `/health` stays open, log once.
- Caller key missing at start: make a new one. Receivers pick it up on the next unknown `kid`.
- Clock skew over 30 s between containers: assertion rejected with a clear error naming the skew. Docker hosts share a clock, so this is mainly a Windows-direct concern.
- Dev mode without Docker: same code, trust directory in the home folder, no extra setup.

## Risks

- Replay inside the 60 s window needs the `jti` check; without it a sniffed assertion works for 60 s. Traffic stays on the private Docker network, so the exposure is small.
- Private keys on disk: volume per service, mode 0600. A host admin can read them; the same was true of the shared token.
- A bug in the shared library breaks all five services at once; the library tests and the live run in 12.7 are the guard.
- Not testable without a live run: real container start order, volume mount modes, Windows file permissions.

## Decisions on the open questions

1. **Turn length:** requester tokens last 15 minutes. Stronghold refreshes them from Portcullis while a turn runs, only for an account with a running turn. A leaked token is useful for 15 minutes at most, not for the whole turn.
2. **Admin apps:** unchanged. They call only Portcullis with a user session and never hold service keys.
3. **Dev without Docker:** trust directory is `~/.citadel/trust/<service>/`, overridable with `CITADEL_TRUST_DIR`. Same code path as Docker.
4. **Legacy:** hard cut-over (see Rollout). The old shared token is not read anywhere after its service moves.

## Size

Seven steps on one branch. The library (12.1) and Portcullis (12.6) are the largest; Treasury (12.2) is the smallest.
