# Plan 12: dynamic service-to-service auth (design)

Status: design only, for review. Replaces the shared `INTERNAL_API_TOKEN` between `portcullis`, `stronghold`, `legion`, `armory` and `treasury`. Implementation can be handed to Codex after this is approved.

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

## Rollout (each step ships and passes tests on its own)

Both schemes are accepted during the move: a receiver takes a valid assertion **or** the old token while `AUTH_LEGACY=1`.

| Step | Work |
|---|---|
| 12.1 | `citadel_auth` library, unit tests, trust-directory mounts in compose. No behaviour change. |
| 12.2 | Treasury accepts assertions (smallest, 5 files), then Stronghold and Armory call it with assertions. |
| 12.3 | Armory: `/mcp`, `/upload`, media routes; requester from the token. |
| 12.4 | Stronghold: inbound routes, outbound clients (armory, legion, treasury, portcullis `/internal`), requester token refresh. |
| 12.5 | Legion: `/mcp`, `/registry`, `/agents`; outbound to Armory and gateways. |
| 12.6 | Portcullis: mint requester tokens, sign every outgoing call, `/internal/*` checks callers. |
| 12.7 | Remove `AUTH_LEGACY`, `INTERNAL_API_TOKEN`, `INTERNAL_TOKEN_FILE`, `shared_token.py` (five copies), the `internal_token` volume, docs, `.env.example` lines, and tests of the old scheme. |
| 12.8 | Live run of the whole stack (nobody has run it live yet). |

Order matters: receivers change before senders, so no step breaks a running stack.

## Tests

- Library: sign/verify, expiry, wrong audience, wrong key, replayed `jti` inside the window (small in-memory set per receiver), tampered claims, unknown `kid` reload.
- Per service: one test per rule in the policy table that matters (allowed, denied, unknown caller), one that a forged `X-Requester-Uid` is ignored.
- Compose: a check that the trust mounts are `rw` for the owner only.
- These are the only new test families; the old token tests are deleted in 12.7.
- The slow tests are tagged `slow` per the test audit (`2026-11-17-test-audit.md`).

## Failure behaviour

- Receiver cannot read the trust directory: refuse requests (fail closed), `/health` stays open, log once.
- Caller key missing at start: make a new one. Receivers pick it up on the next unknown `kid`.
- Clock skew over 30 s between containers: assertion rejected with a clear error naming the skew. Docker hosts share a clock, so this is mainly a Windows-direct concern.
- Dev mode without Docker: same code, trust directory in the home folder, no extra setup.

## Risks

- Replay inside the 60 s window needs the `jti` check; without it a sniffed assertion works for 60 s. Traffic stays on the private Docker network, so the exposure is small.
- Private keys on disk: volume per service, mode 0600. A host admin can read them; the same was true of the shared token.
- A bug in the shared library breaks all five services at once; the dual-accept rollout and the library tests are the guard.
- Not testable without a live run: real container start order, volume mount modes, Windows file permissions.

## Open questions for you

1. **Turn length:** requester tokens last 15 minutes and Stronghold refreshes them. Is that acceptable, or should a turn carry one token for its whole life (simpler, but a longer window if it leaks)?
2. **Admin apps:** they call only Portcullis with a user session today. Keep that, or let them call Treasury and others directly? Recommendation: keep.
3. **Dev without Docker:** is `~/.citadel/trust` acceptable, or should local runs use one shared folder inside the repo?
4. **Legacy period:** is dual-accept until 12.7 fine, or do you want a hard cut-over after 12.6?

## Size

About 8 steps, one pull request each. The library (12.1) and Portcullis (12.6) are the largest; Treasury (12.2) is the smallest.
