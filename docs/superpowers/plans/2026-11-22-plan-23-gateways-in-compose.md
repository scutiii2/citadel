# Plan 23: Stack gateways inside Citadel's compose, on a private network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan spans three git repos (listed below). Each task names the repo it works in; commit in that repo only.

**Goal:** ConversationGateway and DecisionGateway run as part of Citadel's `docker compose up`, reachable only by Legion over a private network with no host port, with provider keys passed to those two containers by variable name and never kept in the main `.env`.

**Architecture:** Two compose services (built from the gateways' own repos, as before commit `983d0623`) join a new network `llm_net`; Legion joins `core` and `llm_net`; nothing else does. A gateway secret field may hold `env:NAME` (a reference to a container environment variable) instead of a key; the gateway reads the variable when it makes a call and never stores or returns it. Provider keys live in a separate git-ignored file `.env.gateways` that only the two gateway services load. The admin pages of the gateways stay reachable on demand through a loopback-only compose overlay. A small script checks the compose invariants with `docker compose config`.

**Tech Stack:** Docker Compose 2.24+, Python 3.12 (`uv`, pytest), Markdown docs. No front-end change; no change to Legion, Portcullis, Stronghold, Armory or Ember code.

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md` section "Stack gateways" and rule 6 ("Models only through Legion"); `docs/superpowers/plans/2026-11-20-scope-audit.md` finding 8 and decision D4 (reverses commit `983d0623`); roadmap row 23 in `docs/superpowers/plans/2026-11-20-scope-roadmap.md`.

## Repos and paths

All paths below are on the user's machine under `D:\User\Documents\Programming`:
- **Citadel**: `Applications/Citadel` (compose, `.env.example`, docs, `scripts/`). Commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- **ConversationGateway**: `AI/ModelProviders/ConversationGateway` (its own git repo; port 29407; token prefix `cg_`).
- **DecisionGateway**: `AI/ModelProviders/DecisionGateway` (its own git repo; port 29406).

Each gateway repo has its own `AGENTS.md`. Read it fully before editing and follow it for commit author, docs to update and parity rules. The rules that matter here: never read or print `.env`, `gateways.json`, `tokens.json` or `settings.json`; secrets stay write-only in responses, logs and errors; `src/admin_api.py`, `src/tokens.py`, `src/middleware.py`, `src/runtime.py`, `web/playground.js`, `tests/test_admin_api.py`, `tests/test_tokens.py`, `tests/seed.py` and `tests/test_env_file.py` are byte-identical to the tool services and must NOT change; `web/index.html` and `tools/check_sync.py` are identical between the two gateways; `tools/check_sync.py` must exit 0; behaviour changes update `README.md`, `deployment.md`, `docs/`, `.env.example`, `AGENTS.md` and `CHANGELOG.md` in the same commit; do not push, add a remote or run `tools/publish_live.py`. This plan changes only each gateway's `src/store.py`, its tests, and those docs.

## Global Constraints

- Only Legion calls a model or a gateway. No other service joins `llm_net`; no service publishes a gateway port by default. Portcullis has no route to the gateways.
- Provider keys never enter the root `.env` (it is bind-mounted read-only into every Citadel service as `/citadel.env`, so any service could read it). They live in `.env.gateways`, loaded by the two gateway services only. This deviates from the spec's words "in the main `.env`"; record the reason in "Changes found".
- A gateway secret is never returned, logged, or written back to `gateways.json` in resolved form. Editing an entry that holds `env:NAME` and omitting the secret keeps the reference.
- A reference to a variable that is unset or empty means "no credential": the entry reports `has_api_key: false` (or the matching flag) and a call fails through the gateway's existing missing-key path. Nothing falls back to another source.
- The standalone gateway stacks (`docker-compose.yml` in each gateway repo) stay as they are for other projects. Their compose files, hostnames and published ports do not change.
- Do not read, print or write any `.env*` file that holds values. Create only `.env.gateways.example`. Do not push, publish or run `tools/publish_live.py`.
- Never add reduced-motion code anywhere. Use `uv` for Python (`UV_CACHE_DIR=D:/User/.uv-cache` and `UV_LINK_MODE=copy` on Windows, as the gateway `AGENTS.md` says).
- No data migration: the standalone gateways' volumes are not read or copied by any code (document the optional manual copy only).

## Design decisions (made here; the executor does not reopen them)

1. **Service and host names.** `conversation-gateway` and `decision-gateway` (hyphens). They differ from the standalone containers' names `conversationgateway` and `decisiongateway`, so Legion can never resolve to a standalone copy still joined to `citadel_core`. Addresses saved in Legion's Connections page become `http://conversation-gateway:29407` and `http://decision-gateway:29406` (a one-time manual step; Legion's own default is `127.0.0.1`, so an address was always saved by hand).
2. **Network.** `llm_net` (named `citadel_llm`) is an ordinary bridge, not `internal`, because the gateways must reach provider APIs on the internet. They are on `llm_net` only (not `core`), so they cannot reach Treasury, Portcullis or Stronghold, and nothing on `core` except Legion can reach them. Treasury therefore cannot probe or register them; that is Plan 25's concern, not this plan's.
3. **Only Legion's token is accepted.** The gateways already refuse every `/api` and `/mcp` call without a token created on their admin page. With no host port and no other service on `llm_net`, the only caller is Legion. The operator creates exactly one token (named `legion`) and saves it in Legion's Connections page. No gateway code changes for this.
4. **Admin access.** Admin pages are needed once to create the token and the gateway entries. A committed overlay file `docker-compose.gateway-admin.yml` publishes them on `127.0.0.1` only (ports 29407 and 29406); the operator adds it with `-f` while setting up and drops it afterwards.
5. **Keys by name.** `env:NAME` references (rule above) in both gateways' stores; names `[A-Z][A-Z0-9_]{0,63}`.
6. **Admin passwords.** `CONVERSATION_GATEWAY_ADMIN_PASSWORD` and `DECISION_GATEWAY_ADMIN_PASSWORD` in the root `.env` (required by compose with `:?`, as before `983d0623`; they are not provider keys and `rootenv.py` already says gateway admin passwords never reach a service's own settings).

## File Structure

- Gateways (each repo): modify `src/store.py`; modify or add tests in `tests/test_store.py` (or a new `tests/test_env_secrets.py` if that file is crowded); docs: `README.md`, `deployment.md`, `docs/` guide that describes gateway entries, `.env.example` (only a comment), `AGENTS.md` (one line under Rules), `CHANGELOG.md`.
- Citadel: modify `docker-compose.yml`; create `docker-compose.gateway-admin.yml`, `.env.gateways.example`, `scripts/check_compose.py`; modify `.env.example`, `.gitignore`, `tools/setup_env.py` (only if it builds the root `.env` from a table or from `.env.example`; see Task 3), `docs/deployment.md`, `apps/legion/README.md` and any other file that names `http://conversationgateway:29407` or `http://decisiongateway:29406` as Citadel's address. `docker-compose.zima.yml` needs no gateway change (the gateways publish nothing); mention the overlay in its header comment only.

## Baseline (the executor fills in before changing anything)

- ConversationGateway: `uv run pytest -q` in its folder: ______ passed, ______ failed; `uv run python tools/check_sync.py`: exit ______.
- DecisionGateway: same two commands: ______ passed, ______ failed; exit ______.
- Citadel: `docker compose config` with `CONVERSATION_GATEWAY_ADMIN_PASSWORD` unset currently succeeds (no gateway services): ______.
- Known failures: ______

## Changes found during work (the executor fills in)

______

## Assumptions to check (record each result above)

- (a) In each gateway, every code path that writes `gateways.json` starts from the raw stored entries (`GatewayStore._read()` or equivalent), never from a resolved copy. `put()` does (read it), but grep for every caller of `GatewayStore.all()` and confirm none writes its result back.
- (b) Each adapter reads the secret from the entry dict it is given at call time (`entry["api_key"]`, `entry.get("token")`, the AWS pair), so resolving `env:NAME` when `all()` builds that dict reaches every adapter. If an adapter caches a client built from the key (ConversationGateway "leases adapters"), a changed environment variable only matters after a restart; say so in the docs.
- (c) `docker compose config --format json` works offline on this machine and prints `services.<name>.networks`, `ports`, `env_file` entries for the file set it is given. If `env_file` appears only in a different shape, adjust the script's reading, not its invariants.
- (d) `tools/setup_env.py` (read it) is the only generator of the root `.env`, and whether it is table-driven.
- (e) Nothing else in the repo names the gateways' Docker hostnames (`git grep -n "conversationgateway:29407\|decisiongateway:29406"` in Citadel, excluding `docs/superpowers` plan history and `node_modules`).

---

### Task 1: ConversationGateway accepts `env:NAME` secrets

**Repo:** `AI/ModelProviders/ConversationGateway`

**Files:**
- Modify: `src/store.py`
- Test: `tests/test_env_secrets.py` (create)
- Docs: `README.md`, `deployment.md`, the `docs/` guide that explains gateway entries, `.env.example` (comment only), `AGENTS.md`, `CHANGELOG.md`

**Interfaces:**
- Produces in `src/store.py`: `ENV_REF = re.compile(r"env:([A-Z][A-Z0-9_]{0,63})")` and `resolve(entry: dict[str, Any]) -> dict[str, Any]`, a copy of `entry` where each field named in `SECRETS` whose value fully matches `ENV_REF` is replaced by `os.environ.get(name, "")` (a missing variable gives `""`); other fields untouched. `GatewayStore.all()` returns resolved entries (what adapters use); `GatewayStore.public()` reports each `has_*` flag from the resolved value, so a reference to an unset variable shows `false`; `put()` keeps working on the raw stored entries.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_env_secrets.py`. First read `tests/test_store.py` and copy the smallest valid `put()` payload it uses for an Anthropic `key` gateway and an OpenAI gateway (the `ENTRY` helpers below stand for those payloads; keep their other fields exactly as the existing tests do):

```python
import json

import pytest

from src.store import GatewayStore, resolve

KEY_ENTRY = {"provider": "anthropic", "auth": "key", "model": "claude-sonnet-5-5"}  # use the real minimal fields from test_store.py


@pytest.fixture
def store(tmp_path):
    return GatewayStore(tmp_path / "gateways.json")


def test_a_reference_is_resolved_for_calls_and_never_returned(store, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    store.put("claude", {**KEY_ENTRY, "api_key": "env:ANTHROPIC_API_KEY"})
    assert store.all()["claude"]["api_key"] == "sk-secret-value"
    public = store.public()[0]
    assert public["has_api_key"] is True
    assert "sk-secret-value" not in json.dumps(public) and "api_key" not in public


def test_the_file_keeps_the_reference_not_the_value(store, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    store.put("claude", {**KEY_ENTRY, "api_key": "env:ANTHROPIC_API_KEY"})
    text = (tmp_path / "gateways.json").read_text("utf-8")
    assert "env:ANTHROPIC_API_KEY" in text and "sk-secret-value" not in text


def test_editing_without_the_secret_keeps_the_reference(store, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    store.put("claude", {**KEY_ENTRY, "api_key": "env:ANTHROPIC_API_KEY"})
    store.put("claude", {**KEY_ENTRY, "model": "claude-haiku-5-5"})  # secret omitted on purpose
    text = (tmp_path / "gateways.json").read_text("utf-8")
    assert "env:ANTHROPIC_API_KEY" in text and "sk-secret-value" not in text


def test_an_unset_or_empty_variable_means_no_credential(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store.put("claude", {**KEY_ENTRY, "api_key": "env:ANTHROPIC_API_KEY"})
    assert store.all()["claude"]["api_key"] == ""
    assert store.public()[0]["has_api_key"] is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert store.public()[0]["has_api_key"] is False


def test_only_a_whole_well_formed_reference_is_resolved(monkeypatch):
    monkeypatch.setenv("HOME_KEY", "x")
    entry = {"api_key": "prefix env:HOME_KEY", "token": "env:lowercase", "model": "env:HOME_KEY"}
    assert resolve(entry) == entry  # not a whole reference, bad name, and not a secret field
    assert resolve({"api_key": "env:HOME_KEY"}) == {"api_key": "x"}


def test_a_literal_key_still_works_as_before(store):
    store.put("claude", {**KEY_ENTRY, "api_key": "sk-literal"})
    assert store.all()["claude"]["api_key"] == "sk-literal"
    assert store.public()[0]["has_api_key"] is True


def test_the_aws_pair_and_the_scuti_token_accept_references_too(store, monkeypatch):
    monkeypatch.setenv("AWS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET", "shh")
    monkeypatch.setenv("SCUTI_TOKEN", "tok")
    store.put("aws", {"provider": "anthropic", "auth": "bedrock", "aws_region": "us-east-1", "model": "m",
                      "aws_access_key_id": "env:AWS_KEY_ID", "aws_secret_access_key": "env:AWS_SECRET"})
    store.put("local", {"provider": "scuti", "url": "http://host.docker.internal:29200", "token": "env:SCUTI_TOKEN"})
    assert store.all()["aws"]["aws_secret_access_key"] == "shh"
    assert store.all()["local"]["token"] == "tok"
```

If a `put()` in the tests above needs another required field the existing store tests show (a `model`, a `label`), add it; keep each test's behaviour.

- [ ] **Step 2: Run to see the failure**

Run: `uv run pytest -q tests/test_env_secrets.py`
Expected: FAIL (`ImportError: cannot import name 'resolve' from 'src.store'`).

- [ ] **Step 3: Implement**

In `src/store.py`: add `import os`, `ENV_REF` and `resolve()` as described. `GatewayStore.all()` returns `{gid: resolve(entry) for gid, entry in self._read().items()}` under the lock; `put()` and `delete()` keep using `self._read()` (raw). In `_public(gid, entry)` build the `has_*` flags from `resolve(entry)`. Grep every other use of `.all()` and of `_read()` in `src/` (assumption a): any code path that writes an entry back must use `_read()`. Do not touch `src/admin_api.py`, `tokens.py`, `middleware.py`, `runtime.py`.

- [ ] **Step 4: Run to see it pass**

Run: `uv run pytest -q` and `uv run python tools/check_sync.py`
Expected: PASS and exit 0; counts equal baseline plus the new tests.

- [ ] **Step 5: Docs and commit**

Document in `README.md` (the "Gateways" section), `deployment.md` and the entries guide in `docs/`: a secret field accepts `env:NAME`; the variable is read at call time; an unset variable counts as no credential; an adapter that keeps a client open picks up a changed variable after a restart (assumption b); the reference is stored, the value never is. Add one line to `AGENTS.md` under Rules ("A secret field may hold `env:NAME`; `store.resolve()` is the only place that reads it; writers use the raw entries"). Add a short `.env.example` comment (no values) and a `CHANGELOG.md` entry. Commit with the author the gateway `AGENTS.md` names:

```bash
git add src/store.py tests/test_env_secrets.py README.md deployment.md docs .env.example AGENTS.md CHANGELOG.md
git commit -m "feat: secret fields accept env:NAME references"
```

---

### Task 2: DecisionGateway accepts `env:NAME` secrets

**Repo:** `AI/ModelProviders/DecisionGateway`

**Files:** the same set as Task 1 in this repo.

**Interfaces:** the same `ENV_REF`, `resolve(entry)` and behaviour of `all()` and `public()`; the secret fields here are `api_key` and `token` (`_SECRETS` in `src/store.py`), used by the `typesafe`, `freellmapi` and `scuti` kinds.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_env_secrets.py`. Read `tests/test_store.py` for the minimal valid `put()` payloads of a `typesafe` and a `scuti` entry, then write the same seven behaviours as Task 1 with these changes: the key test uses `{"kind": "typesafe", "url": ..., "model": ...}` plus `"api_key": "env:TYPESAFE_API_KEY"` (the variable name for the test is `TYPESAFE_API_KEY`); the last test is replaced by:

```python
def test_the_scuti_token_and_the_freellmapi_key_accept_references(store, monkeypatch):
    monkeypatch.setenv("LAYA_TOKEN", "tok")
    monkeypatch.setenv("FREELLMAPI_KEY", "k")
    store.put("laya", {"kind": "scuti", "url": "http://host.docker.internal:29220", "token": "env:LAYA_TOKEN"})
    store.put("free", {"kind": "freellmapi", "url": "http://host.docker.internal:29652", "api_key": "env:FREELLMAPI_KEY"})
    assert store.all()["laya"]["token"] == "tok" and store.all()["free"]["api_key"] == "k"
```

Use the same names for the fixtures `store` and the helper imports as Task 1, adapted to this repo's `GatewayStore(path)`.

- [ ] **Step 2: Run to see the failure**

Run: `uv run pytest -q tests/test_env_secrets.py`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement, run, document, commit**

As Task 1 steps 3 to 5, in this repo's `src/store.py` (`_SECRETS` is the secret set; `_public` builds `has_api_key` and `has_token` from `_SECRETS`; check `put()` reads raw entries). Run `uv run pytest -q` and `uv run python tools/check_sync.py` (exit 0). Commit message: `feat: secret fields accept env:NAME references`.

---

### Task 3: Compose services, network, overlay and env files (Citadel)

**Repo:** `Applications/Citadel`

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `.gitignore`, `docker-compose.zima.yml` (header comment only), `tools/setup_env.py` (only if assumption d says it should change)
- Create: `docker-compose.gateway-admin.yml`, `.env.gateways.example`

- [ ] **Step 1: Add the two services**

In `docker-compose.yml`, replace the comment block that says the gateways are not part of the file (it sits between `armory` and `legion`) with these services, and update the first comment block of the file (the stack line) to name them:

```yaml
  # Stack gateways (their own repos). Legion is their only caller: no host port, and they join llm_net only.
  # Provider keys come from .env.gateways (see .env.gateways.example), never from the root .env.
  conversation-gateway:
    build: ${CONVERSATION_GATEWAY_DIR:-../../AI/ModelProviders/ConversationGateway}
    restart: unless-stopped
    env_file:
      - path: ./.env.gateways
        required: false
    environment:
      SERVICE_ADMIN_PASSWORD: ${CONVERSATION_GATEWAY_ADMIN_PASSWORD:?set CONVERSATION_GATEWAY_ADMIN_PASSWORD in the root .env}
    volumes:
      - ${CITADEL_DATA_DIR:-./.data}/conversationgateway:/data
    # Lets a saved gateway reach a service published on the host (OmniRoute, Ollama, vLLM) as host.docker.internal.
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:29407/health')"]
      interval: 15s
      timeout: 5s
      start_period: 30s
    networks: [llm_net]

  decision-gateway:
    build: ${DECISION_GATEWAY_DIR:-../../AI/ModelProviders/DecisionGateway}
    restart: unless-stopped
    env_file:
      - path: ./.env.gateways
        required: false
    environment:
      SERVICE_ADMIN_PASSWORD: ${DECISION_GATEWAY_ADMIN_PASSWORD:?set DECISION_GATEWAY_ADMIN_PASSWORD in the root .env}
    volumes:
      - ${CITADEL_DATA_DIR:-./.data}/decisiongateway:/data
    # Lets a saved gateway reach a host-published model service (LayaModel) as host.docker.internal.
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:29406/health')"]
      interval: 15s
      timeout: 5s
      start_period: 30s
    networks: [llm_net]
```

In the `legion` service change `networks: [core]` to `networks: [core, llm_net]` and update its comment line to say the gateways' address and token are still set on the Legion admin page. Do not change `depends_on` (the gateways are not hard dependencies; Legion must start without them). In the top-level `networks:` block add:

```yaml
  # Legion and the two stack gateways only. Not internal: the gateways must reach their providers.
  llm_net:
    name: citadel_llm
```

- [ ] **Step 2: Overlay and env files**

Create `docker-compose.gateway-admin.yml`:

```yaml
# Setup overlay: opens the two gateway admin pages on this machine only (127.0.0.1), to create Legion's token and the
# gateway entries. Use it while setting up, then start without it so the gateways have no host port again.
# Start:  docker compose -f docker-compose.yml -f docker-compose.gateway-admin.yml up -d conversation-gateway decision-gateway
# Stop any standalone gateway stack first: it publishes the same host ports (29407, 29406).

services:
  conversation-gateway:
    ports:
      - "127.0.0.1:29407:29407"
  decision-gateway:
    ports:
      - "127.0.0.1:29406:29406"
```

Create `.env.gateways.example` (comments and empty values only; no real names beyond the common ones):

```
# Provider keys for the two stack gateways. Copy to .env.gateways (git-ignored).
# Only conversation-gateway and decision-gateway load this file; no other Citadel service sees it.
# A gateway entry refers to a key by name in its secret field, for example  env:ANTHROPIC_API_KEY
# (save the entry on the gateway's admin page, see docs/deployment.md). Leave a name empty to use none.
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
TYPESAFE_API_KEY=
FREELLMAPI_API_KEY=
```

Append to `.env.example`:

```
# Admin passwords of the two stack gateways (required: compose refuses to start without them).
# They unlock each gateway's admin page, where Legion's token and the gateway entries are created.
# Provider keys do NOT go in this file; they go in .env.gateways (see .env.gateways.example).
CONVERSATION_GATEWAY_ADMIN_PASSWORD=
DECISION_GATEWAY_ADMIN_PASSWORD=
```

Add `/.env.gateways` to `.gitignore` next to the other env entries. Read `tools/setup_env.py` (assumption d): if it copies `.env.example` and fills named secret keys from a list, add the two gateway passwords to that list (random values, never printed) and make it copy `.env.gateways.example` to `.env.gateways` when absent, never overwriting. If it is not table-driven, leave it alone and say so in "Changes found". Add one line to the header comment of `docker-compose.zima.yml`: the gateways publish nothing; the setup overlay works on ZimaOS as on any host.

- [ ] **Step 3: Check that compose still parses**

Run (with a throwaway value only for the check, passed in the process environment, not a file):

```bash
CONVERSATION_GATEWAY_ADMIN_PASSWORD=x DECISION_GATEWAY_ADMIN_PASSWORD=y docker compose config --quiet
CONVERSATION_GATEWAY_ADMIN_PASSWORD=x DECISION_GATEWAY_ADMIN_PASSWORD=y docker compose -f docker-compose.yml -f docker-compose.gateway-admin.yml config --quiet
docker compose config --quiet
```

Expected: the first two exit 0; the third fails with the `set CONVERSATION_GATEWAY_ADMIN_PASSWORD in the root .env` message (that is the intended guard). Record the three results.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.gateway-admin.yml docker-compose.zima.yml .env.example .env.gateways.example .gitignore tools
git commit -m "feat(compose): run both stack gateways in the stack on a private llm_net

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: A script that checks the compose invariants

**Repo:** `Applications/Citadel`

**Files:**
- Create: `scripts/check_compose.py`

**Interfaces:**
- Produces: `python scripts/check_compose.py` (exit 0 when every invariant holds, 1 with one line per failure). Functions: `load(files: list[str]) -> dict` runs `docker compose -f ... config --format json` with throwaway `CONVERSATION_GATEWAY_ADMIN_PASSWORD` and `DECISION_GATEWAY_ADMIN_PASSWORD` in the child process environment and returns the parsed JSON; `check(default: dict, overlay: dict) -> list[str]` returns failure messages; both are importable so the self-test below can run them.

Invariants (each is one message when broken):
1. `conversation-gateway` and `decision-gateway` exist in the default config.
2. Neither gateway has `ports` in the default config. In the overlay config each publishes exactly one port bound to `127.0.0.1`.
3. Each gateway's `networks` is exactly `{"llm_net"}`.
4. `llm_net` is attached to exactly these services: `legion`, `conversation-gateway`, `decision-gateway`.
5. `legion` is on both `core` and `llm_net`.
6. Only the two gateways have an `env_file` entry that ends with `.env.gateways`.
7. Neither gateway mounts `/citadel.env` or the Docker socket, and no other service's volumes or environment mention `.env.gateways`.
8. `legion.depends_on` names neither gateway.
9. The network `llm_net` is not `internal` (the gateways must reach their providers).

- [ ] **Step 1: Write the failing self-test**

Create `scripts/check_compose.py` with a `__main__` block and, below it, a `--self-test` mode implemented as plain asserts over hand-made dicts (no Docker needed): a good pair `(default, overlay)` passes (`check(...) == []`); and for each invariant one mutated copy of the good pair returns exactly one message that names it (for example adding `"ports": ["29407:29407"]` to the default `conversation-gateway` yields one message containing "ports"; adding `"core"` to a gateway's networks yields one containing "networks"; adding `.env.gateways` to `armory`'s `env_file` yields one containing "env_file"). Run `python scripts/check_compose.py --self-test` first with `check()` returning `[]` always, and see the mutation cases fail.

- [ ] **Step 2: Implement `check()` and `load()`**

Implement the nine invariants against the JSON shape `docker compose config --format json` prints (`services.<name>.networks` is a mapping of network name to settings, `ports` a list of objects with `host_ip`, `published`, `target`, `env_file` a list of objects with `path`; check assumption c on this machine and read the real shape before coding). Use only the standard library. If Docker is not installed, `load()` prints "docker not found, skipped" and the script exits 0 only in `--self-test` mode (the normal mode needs Docker and exits 2 with a clear message).

- [ ] **Step 3: Run**

Run: `python scripts/check_compose.py --self-test` (expect PASS) and `python scripts/check_compose.py` (expect exit 0 against the Task 3 files). Record both results.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_compose.py
git commit -m "test(compose): check that the stack gateways stay private to Legion

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Docs and the old address

**Repo:** `Applications/Citadel`

**Files:**
- Modify: `docs/deployment.md`, `apps/legion/README.md`, and every file `git grep -n "conversationgateway:29407\|decisiongateway:29406" -- . ':!docs/superpowers' ':!node_modules'` finds (assumption e)

- [ ] **Step 1: Rewrite the gateway parts of `docs/deployment.md`**

- The services table (top of the file): add `conversation-gateway` ("chat-model gateway for Legion, internal 29407, `llm_net` only") and `decision-gateway` ("decision-model gateway for Legion, internal 29406, `llm_net` only"). Change the sentence that says the rest talk over `core` to mention `llm_net` and that no gateway port is published.
- Section 1, step 1 ("The gateways are separate stacks"): replace it with the new facts: the gateways are part of the stack and built from `AI/ModelProviders/<name>` (set `CONVERSATION_GATEWAY_DIR` or `DECISION_GATEWAY_DIR` in the root `.env` if the folders live elsewhere, as on ZimaOS `/media/ZimaOS-HD/Apps/ModelProviders/`); the two admin passwords go in the root `.env`; provider keys go in `.env.gateways`; Legion reaches them at `http://conversation-gateway:29407` and `http://decision-gateway:29406`.
- Sections "ConversationGateway" and "DecisionGateway": rewrite "Source and start", "First start" and "Outside callers" for the new flow, in this order: (1) copy `.env.gateways.example` to `.env.gateways` and fill the keys you use; (2) start the stack with the setup overlay, `docker compose -f docker-compose.yml -f docker-compose.gateway-admin.yml up -d --build`, and stop any standalone gateway stack first (same host ports); (3) open `http://127.0.0.1:29407/admin/` (and `29406`), sign in with the admin password, create exactly one token named `legion`; (4) save the entries on `/admin/gateways.html`, typing `env:ANTHROPIC_API_KEY` (or the name you set) into the key field; (5) in the Legion admin app, Connections, save the address and token of each gateway (new addresses above); (6) restart without the overlay (`docker compose up -d`): the gateways have no host port again. Replace "Outside callers" with: there are none; a project that needs a gateway runs its own standalone copy (`AI/ModelProviders/<name>/docker-compose.yml`), which is unchanged. Say that an optional manual copy of a standalone `conversationgateway_data` volume into `.data/conversationgateway` keeps old entries and tokens (tokens would then still be valid for the old callers, so delete them on the admin page).
- Troubleshooting table: the row `network citadel_core ... not found` stays only if it still applies; replace the two gateway rows with: `Legion: ConversationGateway is unreachable` (check `docker compose ps`, the address saved in Connections is the hyphenated one, and the gateway has no host port by design), and a row for "the gateway answers 401" (Legion's token is missing or was deleted on the admin page).
- Add a short "Security" note: gateways are reachable only from Legion's network; provider keys sit in `.env.gateways`, which only the two gateway containers load; the root `.env` is mounted into every service, which is why keys are not kept there.

- [ ] **Step 2: Update the other mentions**

In `apps/legion/README.md` and any other file the grep shows, change the address Citadel uses to the hyphenated one and keep every statement about the standalone stacks only where it is about a standalone copy. Do not edit `docs/superpowers` plan history, and do not change Legion code or tests.

- [ ] **Step 3: Check the docs and the invariants**

Run `python scripts/check_compose.py` and re-run the grep from Step 2: remaining hits must be standalone-copy statements or plan history only. List them in "Changes found".

- [ ] **Step 4: Commit**

```bash
git add docs apps/legion/README.md
git commit -m "docs: stack gateways run in the stack, private to Legion

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Manual checklist (the user runs these; the executor copies it into the report as pending)

- [ ] `docker compose up -d --build` with the setup overlay builds both gateways from their repos and `docker compose ps` shows both healthy.
- [ ] After a restart without the overlay, `docker compose port conversation-gateway 29407` and `docker compose port decision-gateway 29406` print nothing, and `http://127.0.0.1:29407/health` does not answer from the host.
- [ ] `docker compose exec legion python -c "import urllib.request; print(urllib.request.urlopen('http://conversation-gateway:29407/health').status)"` prints 200. The same call from `armory`, `stronghold` and `portcullis` fails to resolve the name.
- [ ] With only the `legion` token created, a request to `http://conversation-gateway:29407/api/gateways` from Legion's container without the token answers 401, and with it answers 200.
- [ ] A key stored as `env:ANTHROPIC_API_KEY` works for a real chat turn in Ember, the admin page shows the key as present but never prints it, and removing the variable from `.env.gateways` and recreating the container turns the entry to "no key".
- [ ] `docker compose exec armory sh -c "env | grep -i API_KEY"` shows none of the gateway provider keys.
- [ ] A standalone gateway stack run for another project still starts and keeps its own host port and data.
- [ ] Laya through DecisionGateway still answers (Triage Assistant, ticket tagging) after saving `http://decision-gateway:29406` and its token in Legion.

## Known gaps (not built here; for later plans or the user)

- Treasury cannot probe or register the gateways, because they are not on `core` (Plan 25 decides how discovery works).
- Per-client budgets fed by gateway usage reports (Plan 24) will need a path from the gateways to Portcullis that this plan does not create.
- Keys are held in clear text in the gateway process environment and, if an operator also types a literal key on the admin page, in `gateways.json`; the gateway repos already document that shortcut.
- A chat model call still depends on the gateway entries having been saved by hand once; this plan does not seed them.

## Self-review (done by the plan's author)

- Spec coverage: gateway instances in the compose (Task 3), private `llm_net` with no host port (Task 3, enforced by Task 4), only Legion's token accepted (design decision 3, manual check), named key passing (Tasks 1 to 3), reversal of `983d0623` (Task 3), docs (Task 5). The spec's "main `.env`" wording is changed on purpose and recorded.
- Placeholders: the Baseline and "Changes found" blanks only. The `KEY_ENTRY` payloads in the two gateway test files tell the executor to copy the minimal valid payload from the repo's own `test_store.py`, because those payloads were not read while writing this plan; the behaviours each test asserts are complete.
- Type consistency: `resolve(entry)`, `ENV_REF` and the `has_*` flag rule are defined once in Task 1 and reused in Task 2; the service names `conversation-gateway` and `decision-gateway`, the network `llm_net` and the file names are the same in Tasks 3 to 5.
