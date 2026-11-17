# Plan 12 implementation: dynamic service-to-service auth

Design (read first, it is the source of truth for the why): `docs/superpowers/plans/2026-11-17-plan-12-dynamic-service-auth-design.md`.
This file is the how: exact decisions, steps, files, tests and done criteria. Where the two disagree, the design wins, then raise it.

Branch: `plan-12-service-auth`, cut from `main`. One commit per step. Merge once, after 12.7. Never push, never touch `Brain/` (the vault is a separate repo; Claude updates it afterwards).

## Rules for the work

- Follow `AGENTS.md` in the repo root and in each app. Python: `uv`, never `pip`. Node: `pnpm`, never `npm`.
- Hard cut-over. No legacy mode, no `AUTH_LEGACY`, no switch that turns auth off, no fallback to `INTERNAL_API_TOKEN`. Each step deletes that service's old token code, its old tests and its doc lines in the same step.
- Python code is async and non-blocking (`asyncio.to_thread` for file reads in request paths, or read once and cache).
- Bash heredocs with escapes are unreliable on this Windows machine: edit files with the editor tools, not shell one-liners.
- Test commands (run inside the app folder): `uv run pytest -q -p no:cacheprovider`. Armory and Legion skip `slow` tests by default; before the last commit of a step run `uv run pytest -q -p no:cacheprovider -m ""`. Portcullis takes about 10 minutes; run it in the background and read the result when it finishes.
- Report in each commit message what you ran and the pass counts. If a test fails and the cause is not in your change, stop and say so; do not weaken the test.

## Decisions fixed by this plan (the design left them open)

1. **How the library reaches each app.** Each app builds from its own Docker context (`./apps/<app>`), so a path dependency outside it breaks the images. The library therefore lives once at `libs/citadel_auth/` (package `citadel_auth`, with its own tests) and is **copied** into each app as `src/citadel_auth/` by `scripts/sync_citadel_auth.py`. Each app has one test, `tests/test_citadel_auth_in_sync.py`, that fails if its copy differs from `libs/citadel_auth/`. Never edit a copy; edit the master and run the script. Portcullis, Stronghold, Legion, Armory and Treasury all import it as `from src.citadel_auth import ...`.
2. **Token format.** Compact JWT, algorithm `EdDSA` (Ed25519), through PyJWT. Both `pyjwt` and `cryptography` are already in all five `uv.lock` files; add them to `pyproject.toml` `dependencies` where missing, nothing else new.
3. **Keys.** Each service has a private key in its **own private folder** (`CITADEL_IDENTITY_DIR`, default `<data dir>/identity`, file `key.pem`, mode 0600) and publishes only the public key to `<CITADEL_TRUST_DIR>/<service>/key.pub`. The private key never goes in the trust folder (others can read it). `kid` = first 16 hex of the SHA-256 of the public key bytes.
4. **Headers.**
   - Service assertion: `Authorization: Bearer <jwt>`. Claims `iss` (caller), `aud` (receiver), `iat`, `exp` (iat + 60 s), `jti`. 30 s clock leeway.
   - Requester token: `X-Citadel-Requester: <jwt>`; for MCP calls on a shared session also in `_meta.requester_token` of each tool call (the shared Legion-to-Armory session cannot carry per-user headers). Claims `typ="requester"`, `iss="portcullis"`, `sub` (uid), `username`, `email`, `aud` (list), `iat`, `exp` (15 min), `jti`.
   - The old `X-Internal-Token`, `X-Requester-Username`, `X-Requester-Email`, `X-Requester-Uid` headers and `_meta.requester` are removed everywhere. Receivers never read them.
5. **Who may be a requester.** Only a token signed by the `portcullis` key. A receiver accepts a requester token only when the verified caller is allowed to forward one (policy flag below). A request with no requester token is a service-level call (no user).
6. **Policy table** is a Python dict in `citadel_auth/policy.py`, the same for all services (test-checked against the table in the design). Shape: `POLICY[audience][caller] = Rule(prefixes=(...), forwards_requester=bool)`. Anything not listed is 403. `/health` is open. Start from this and adjust only where a real call needs it:

   | Audience | Caller | Prefixes | Forwards requester |
   |---|---|---|---|
   | stronghold | portcullis | `/` | yes |
   | stronghold | armory | `/brains/resolve`, `/notes`, `/memory`, `/skills`, `/tickets` (what armory calls today; confirm by grepping `STRONGHOLD_URL` users) | yes |
   | armory | portcullis | `/mcp`, `/upload`, `/download`, `/media`, `/admin`, `/capabilities`, `/extensions`, and every route Portcullis proxies today | yes |
   | armory | stronghold | `/mcp`, `/skills`, `/memory`, `/notes`, `/tickets` | yes |
   | armory | legion | `/mcp` | yes |
   | legion | portcullis | `/mcp`, `/registry`, `/agents` | yes |
   | legion | stronghold | `/mcp`, `/registry` | yes |
   | treasury | portcullis, stronghold, legion, armory | `/` (the data routes each uses today) | no |
   | portcullis | stronghold | `/internal` | no |

   `forwards_requester=yes` means "may present a requester token", not "must".
7. **Replay.** Each receiver keeps an in-memory set of `(iss, jti)` until `exp + leeway`, bounded (drop oldest above 50 000). A reused `jti` is 401.
8. **Fail closed.** Receiver cannot read the trust dir, or the caller has no public key there: 401. Unknown `kid` for a known caller: re-read that caller's folder once, then 401.
9. **Persistent MCP sessions.** The MCP client in Legion, Stronghold and Portcullis keeps a session open. Headers must be fresh per request: pass an `httpx.Auth` subclass (`ServiceAuth(audience)`, adds a cached assertion, refreshed when under 10 s from expiry) to the MCP streamable-HTTP client instead of a static `headers=` dict. **12.1 starts with a spike** proving this works against a real FastMCP server in a test (a session lasting longer than the assertion's life keeps working). If the MCP client cannot take an `httpx.Auth`, stop and report; do not invent a workaround.
10. **Test mode.** No off switch. `citadel_auth.testing` provides `make_stack(tmp_path, services=[...])` (keyrings and a trust dir in tmp), `signed(caller, audience)` (headers dict), `requester_headers(...)`. Tests in each app use these instead of `INTERNAL_TOKEN_FILE=""`.

## Library API (what 12.1 must provide)

```
keyring.py   Keyring(service, trust_dir, identity_dir)   ensure_identity(), public_key(service), reload(service)
tokens.py    sign_assertion(keyring, aud) -> str        verify_assertion(keyring, token, aud) -> Caller(name)
requester.py mint_requester(keyring, uid, username, email, aud) -> str   (raises unless keyring.service == "portcullis")
             verify_requester(keyring, token, aud) -> Requester(uid, username, email)
policy.py    POLICY, allowed(audience, caller, path) -> bool, may_forward(audience, caller) -> bool
asgi.py      ServiceAuthMiddleware(app, keyring, audience, open_paths=("/health",))
             sets contextvars current_caller(), current_requester(); 401 on bad token, 403 on policy
client.py    ServiceAuth(keyring, audience) (httpx.Auth); service_client(keyring, audience, **httpx_kwargs)
             requester_header(token) / requester_meta(token) helpers
settings.py  from_env(): CITADEL_SERVICE, CITADEL_TRUST_DIR (default ~/.citadel/trust), CITADEL_IDENTITY_DIR
testing.py   make_stack, signed, requester_headers
```

All errors are one small exception family with a short message naming the cause (expired, wrong audience, unknown caller, not allowed). Never log tokens.

## Steps

Each step ends green and committed. Update the per-app `README.md`/`AGENTS.md` auth text and `.env.example` in the same step. Delete the service's `shared_token.py`, its auth middleware module and their tests.

### 12.1 Library, sync script, compose trust mounts
- Spike from decision 9, as a test in `libs/citadel_auth/tests/`.
- Build the library and `scripts/sync_citadel_auth.py`; add `libs/citadel_auth/pyproject.toml` (tests run with `uv run pytest` there).
- Unit tests: sign/verify round trip; expired; wrong audience; wrong key; tampered claims; replayed `jti`; unknown `kid` reload; caller `iss` not matching the folder it was found in; policy allow/deny for every row of decision 6; requester can only be minted by portcullis and only verified from portcullis's key; `ServiceAuth` refreshes inside a long session; fail closed on unreadable trust dir; private key file is created 0600 and never in the trust dir.
- `docker-compose.yml`: for each of the five services a named volume `trust_<service>` mounted at `/trust/<service>` **rw in that service and `:ro` in the others**, plus a private `identity_<service>` volume at `/identity`; env `CITADEL_SERVICE=<name>`, `CITADEL_TRUST_DIR=/trust`, `CITADEL_IDENTITY_DIR=/identity`. Leave `internal_token` and `INTERNAL_TOKEN_FILE` for now (each service removes its use as it moves; 12.6 removes the volume and variable). Add a test (plain Python reading the YAML) that checks the mount modes.
- Done: library tests pass, `docker compose config` is valid, no service behaviour changed.

### 12.2 Treasury
- Replace `src/auth.py`, `src/shared_token.py`, uses in `src/api.py`, `src/run.py` with `ServiceAuthMiddleware(audience="treasury")`. Remove `INTERNAL_API_TOKEN` from `.env.example` and README.
- Tests: rewrite `treasury/tests` that send the token to send signed headers; add allowed/denied-caller tests. Note: 13 backend-contract tests are skipped without Postgres/Firestore; that is normal.
- Treasury's clients elsewhere are not changed here (their steps do that); until then cross-service calls to Treasury fail, which is expected.

### 12.3 Armory
Files that touch auth (from a grep, confirm yours): `src/services/internal_token.py`, `shared_token.py`, `identity_context.py`, `app_config.py`, `extensions.py`, `config.py`, `run.py`, `upload_routes.py`, `download_routes.py`, `media_ui_routes.py`, `capabilities/{media_downloader,memory,notes,obsidian,pdf_merger,skills,tickets}/{domain,routes,utils/*}.py`, `configs/config_extensions.json(.example)` and `docker/configs/armory/extensions.json` (they reference `${INTERNAL_API_TOKEN}` for extensions that call back into Citadel; decide per entry: tool-service entries keep their own `${BARD_TOKEN}`-style token, Citadel-internal entries switch to a service assertion).
- Inbound: `ServiceAuthMiddleware(audience="armory")` on `/mcp`, `/upload`, download and media routes. `IdentityContextMiddleware` and `_from_request_meta` read the **requester token** (header, or `_meta.requester_token`), verify it, and expose `current_uid()/current_username()/current_email()` from it. No unsigned identity anywhere. Anonymous service-level calls give `""` as today.
- Outbound: Stronghold and Treasury clients use `service_client(keyring, audience=...)`; where a user is involved, pass the requester token on.
- `${INTERNAL_API_TOKEN}` placeholders in config templates: remove or replace as decided above; update `app_config` validation so a leftover placeholder fails with a clear message.
- Tests: update the 26 test files that mention the token; add a test that a forged `X-Requester-Uid` and a forged `_meta.requester` are ignored.
- Run `-m ""` too (math tests).

### 12.4 Stronghold
Files: `src/auth.py`, `shared_token.py`, `api.py`, `run.py`, `platform.py`, `document_store.py`, `agents/{directory,gateway,mcp_session}.py`, `attachments/services.py`, `brains/gateway.py`, `memory/client.py`, `skills/client.py`, `tickets/client.py`, `tuning/limits.py`.
- Inbound: middleware for audience `stronghold`. The requester comes only from the verified requester token; delete the `X-Requester-*` reading. Routes that take the uid from the path or header use the verified one.
- Outbound: Armory, Legion (MCP, via `ServiceAuth`), Treasury (`document_store`), Portcullis `/internal` (`platform.py`), Bard/Scribe/Reader keep their own tokens (unchanged).
- Turn engine: a turn stores the requester token it was started with and, **before it expires, asks Portcullis for a fresh one** (`POST /internal/requester-token` with `{uid}`, answered only when that account has a running turn, see 12.6). If the refresh fails the turn ends as interrupted with a clear message.
- Tests: update the 9 files; add refresh tests (refresh before expiry, refresh refused ends the turn, token never used after expiry), forged-header test.

### 12.5 Legion
Files: `src/runtime/internal_auth.py`, `shared_token.py`, `gateway_settings.py`, `server.py`, `providers/gateway_client.py`, `providers/decision/gateway_client.py`, `agents/roles/router/router_service.py`, `tools/mcp_client/mcp_upstream.py`.
- Inbound: middleware for audience `legion` on `/mcp`, `/registry`, `/agents` (replaces `PROTECTED_PATHS`). `bind_requester` reads the verified requester token.
- Outbound: Armory MCP (`mcp_upstream.py`) via `ServiceAuth("armory")` and the requester token in each call's `_meta.requester_token` (shared session); Treasury via `service_client`. Model gateways keep their own per-caller tokens saved in Treasury (unchanged).
- Tests: update the 4 files; run `-m ""`.

### 12.6 Portcullis
Files: `src/utils/{config_loader,shared_token}.py`, `app.py`, `routes/{agent_admin,attachments,capability_files,internal,server_info}.py`, `services/{agent_admin,agent_directory,config_validation,db_gateway,email_service,mcp_proxy,mcp_server_info,mcp_session,server_tools,stronghold_forwarder}.py`.
- Mint: after login and permission checks, `stronghold_forwarder` and `mcp_proxy` attach a requester token (audience as in the policy) to every call made for a user. Cache per `(uid, audience)` for 10 minutes.
- Sign every outgoing call (`ServiceAuth`).
- `/internal/*`: `ServiceAuthMiddleware(audience="portcullis")`, only stronghold allowed. New route `POST /internal/requester-token` `{uid}`: returns a fresh requester token only if the account is active and has a running turn (ask Stronghold's turn registry through the existing channel, or have Stronghold pass the turn id and check it; choose the simpler and say which in the commit). 
- Replace `require_internal` and `config_validation`'s token check (`INTERNAL_API_TOKEN` is no longer a required setting).
- Remove everywhere: `INTERNAL_API_TOKEN`, `INTERNAL_TOKEN_FILE`, `internal_token` volume, `x-internal-token` in `docker-compose.yml`, the root and per-app `.env.example` lines, docs (`docs/deployment.md`, app READMEs), the `server_info` text that mentions the token.
- Tests: 18 files; rewrite fixtures once in `tests/conftest.py` (the `internal_token=` argument of `make_settings` goes away). Add: a forged `X-Requester-*` header from the browser is dropped; browser cannot reach `/internal`; refresh route rules.
- Run the full suite (about 10 minutes, background).

### 12.7 Whole-stack check (not for Codex unless Docker is available)
`docker compose up -d --build`, then: a chat turn through Portcullis to Stronghold to Legion to Armory; a note save; an upload; the admin pages; stop Stronghold mid-turn; restart Portcullis mid-turn; a forged call from a container with no key is 401; a service restarted with a new key is accepted after the unknown-`kid` reload. Record results in `docs/superpowers/plans/2026-11-17-plan-12-implementation.md` under a "Live run" heading. Claude does this step with the user.

## Definition of done (whole plan)

- `grep -ri "INTERNAL_API_TOKEN\|X-Internal-Token\|INTERNAL_TOKEN_FILE\|shared_token\|X-Requester-" apps docs docker-compose.yml` finds nothing outside historical plan files and the tool-service tokens (`BARD_TOKEN` and the like).
- All suites pass: Treasury, Armory (`-m ""`), Stronghold, Legion (`-m ""`), Portcullis, `libs/citadel_auth`, Ember vitest, `vue-tsc -b`.
- Each app's README states the new auth in two or three lines.
- A short "what changed for operators" note in `docs/deployment.md`: nothing to set; keys are made on first start; backing up `identity_*` volumes is optional (a lost key is remade).

## Changes found during work

- 12.1: MCP 1.28 accepts `httpx.Auth` through `create_mcp_http_client(auth=...)` and `streamable_http_client(http_client=...)`. Real FastMCP session remained usable after its initial 60-second assertion expired (62.70-second spike, 1 passed).
- 12.1: Decisions 7 and 9 conflict: reusing a cached signed assertion reuses its `jti`, so receivers must reject it. Preserve replay protection and sign a fresh assertion for each HTTP request; cache loaded signing key rather than reusable JWT. This strengthens freshness without changing service or requester identity rules.
- 12.2: Treasury's `dev_deploy.bat` also documented the old shared-token requirement; updated it with the service's README. `httpx` was a dev-only dependency and is now explicit runtime dependency alongside PyJWT and cryptography because the shared library exposes HTTP auth helpers.
- 12.3: Real caller scan adds these policy paths: Portcullis to Armory `/commands` (including help), `/pdf` (native UI/downloads), `/tickets/tags` (command picker options); Stronghold to Armory `/upload`, `/brains/operation`, `/ticket-admin`. Callers are `mcp_server_info.py`, Stronghold `attachments/services.py`, `brains/gateway.py`, and `tickets/client.py`.
- 12.3: Armory's ticket service also calls Legion's Laya agent through `capabilities/tickets/utils/{service,laya_transport}.py`; add Armory to Legion `/mcp`, forwarding signed requester tokens. Internal extensions now have an `audience` setting (default `legion`).
- 12.3: Additional wiring files: Armory `src/command_routes.py`, native media/PDF `utils/config.py`, new `services/service_auth.py`, and library requester context support. Authenticated HTTP request scope is retained for per-tool MCP verification; session-start identity is cleared before each call.
- 12.3: External PDF/Media extension examples use their own `PDF_MERGER_TOKEN`/`MEDIA_DOWNLOADER_TOKEN`. Tool services remain outside this cut-over: existing token headers and `_meta.requester` wire protocol remain only in external adapters, populated from verified requester context. Internal calls use `_meta.requester_token` exclusively.
- 12.4: Additional files/callers found: `src/requester.py`, `src/service_auth.py`, `turns/{engine,requester_tokens}.py`, and 21 test modules carry identity assumptions. `LegionTuning.ceiling` calls Legion `/agents/tuning`; add `/agents` to Stronghold-to-Legion policy. Legion peer delegation also calls Legion `/mcp`; add the Legion-to-Legion row with requester forwarding.
- 12.4: A requester token refreshed only in Stronghold cannot update an already-running remote Legion ask. Stronghold publishes each renewed Portcullis-signed token via existing authenticated Legion `status` calls to running agents. Step 12.5 binds these verified per-user updates so subsequent tool/delegation calls use the newest signed token. No service mints requester identities. Renewal refusal or delivery failure interrupts the turn; outbound token access refuses expiry.
