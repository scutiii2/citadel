# Plan 24: Outside clients at Portcullis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portcullis can admit a program that is not a user account (an "outside client") to one narrow door, the Legion level: it holds client records (key, allowed services, rate limit, token budget, audit log), applies its own IP allow and deny lists to outside traffic, and refuses a call whenever it cannot prove the client is within every limit.

**Architecture:** Two new tables (`outside_clients`, `outside_client_events`) in Portcullis's own database. One new route, `POST /api/outside/legion/ask`, authenticates a client key, runs a fixed chain of fail-closed checks (IP, key, service, rate, budget), asks Legion's entry agent with no tools and no memory, adds the tokens Legion reports to the client's budget, and writes an audit event. Admin routes under `/api/admin/outside-clients` manage the records. The existing IP filter gets a second pair of lists that apply only to `/api/outside/*`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async (SQLite), Alembic, MCP client (`mcp_session`), pytest. Portcullis only; no change to Legion, Stronghold, Armory, Ember or any admin app.

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, sections "Outside clients and access levels" and the Portcullis row of the scope table; audit finding 11 in `docs/superpowers/plans/2026-11-20-scope-audit.md`; roadmap row 24.

## Scope and what is deliberately not here

- **Legion level only.** The spec names two outside levels (Legion, stateless; Stronghold, with memory). The Stronghold level needs work outside Portcullis: a client identity that Stronghold accepts as its own memory namespace, and a Stronghold route for outside questions. That is a later plan (call it 24b). Records store `allowed_services` as a list so adding `"stronghold"` later changes no schema; for now only `"legion"` is accepted and any other value is refused.
- **No admin screen.** The admin routes are the whole interface for now (create, list, edit, rotate key, delete, read the audit log). A Portcullis Admin page is a later front-end plan.
- **No tools, no memory.** The client gets a model answer only. Tool access per client (an allow list of tools) is a later decision.
- **No gateway-to-Portcullis usage channel.** The roadmap says the budget is "fed by gateway usage reports". The gateways are private to Legion (Plan 23), so the report that feeds the budget is Legion's own per-request usage in its `ask` result (`agent_usage` and `total_tokens`), the same data Stronghold records for chats.

## Global Constraints

- Outside clients cannot reach any model, gateway, tool, brain, account or admin route. The only outside route is `POST /api/outside/legion/ask`. Models are still reached only through Legion.
- Fail closed. If any check cannot be decided (database error, budget unreadable, limiter error, Legion not reachable), the call is refused with a 5xx or 4xx and no answer text is returned. Nothing falls back to "allow".
- The key is shown once, when a client is created or its key is rotated. Only its SHA-256 hash and an 8-character display prefix are stored. A key, a hash or a question or answer text is never written to a log, to the audit events or to an error message.
- A key that is unknown, malformed or wrong, and a client that is disabled, all answer the same `401` text (no way to tell which). A known client's refusals are audited; an unknown key is not (there is no client to attribute it to).
- The audit log holds no question or answer text: client id, time, service, action, status, tokens, IP and a short reason code only.
- The IP allow list of the main filter (which may confine the whole app to a LAN) does not apply to `/api/outside/*`; the main deny list still does. The outside lists and the client's own allow list apply there instead.
- Admin routes need the existing `settings.manage` permission (no new permission, no migration of roles). Admin changes are logged through `LogWriter.action` with ids and field names only.
- Use `uv` (`uv run --no-sync python -u -m pytest -q -p no:cacheprovider` in `apps/portcullis`). In a worktree the `.venv` folders are empty: run the main checkout's `apps/portcullis/.venv/Scripts/python.exe -u -m pytest ...` from the worktree app folder. The full Portcullis suite takes about ten minutes (two known failures: `test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`): run the whole suite once at the baseline and once at the end, and single files in between.
- Never read, print or write `.env*`, `secrets/` or key files. Never add reduced-motion code. Do not push or publish.

## Decisions made here (the executor does not reopen them)

1. **Key format:** `ock_` plus 32 random bytes in URL-safe base64 (`secrets.token_urlsafe(32)`), sent as `Authorization: Bearer <key>`. Stored: `sha256(key).hexdigest()` (unique index) and `key_prefix` = the first 8 characters.
2. **Identity toward Legion:** uid `oc_<12 hex chars>` fixed at creation (never changes, never reused), username = `outside:<uid>` (account usernames match `[A-Za-z0-9_.-]`, so `:` can never collide with an account; the client's display name is never sent, since an admin could name a client `alice`), email empty. Legion sees an ordinary signed requester.
3. **Limits per client:** `rate_per_minute` (1 to 600, default 10; a sliding window in memory, like `PublicReadLimiter`) and a token budget: `budget_tokens` (required, 1 to 100,000,000, no "unlimited") per rolling `budget_days` (1 to 366, default 30). Spent tokens = the sum of `tokens` over the client's `call` events inside the window.
4. **Budget timing:** the check runs before the call (`spent >= budget_tokens` refuses with `429`, `Retry-After` = seconds until the oldest counted event leaves the window); the tokens are added after. The budget is checked before the call and recorded after, so the overshoot is bounded by the calls in flight at once (up to `rate_per_minute` within the 120 s ask window), not by one call. Shortcut comment in the code: `shortcut: the cap is checked before the call and recorded after it, so the overshoot is bounded by the calls in flight (up to rate_per_minute within the ask window), not one call; add a per-call token ceiling from Legion's limits if that matters.`
5. **Recording failure:** if the tokens of a finished call cannot be recorded, the answer is withheld (`503`) and nothing is returned; the spend is then uncounted, which is the accepted gap and is stated in the README.
6. **Status codes:** `401` bad key or disabled client; `403` IP not allowed or service not allowed; `422` bad body; `429` rate or budget (with `Retry-After`); `503` database, budget, Legion or entry agent unavailable.
7. **Stateless ask:** the call to Legion's `ask` tool passes `enabled_extensions=[]`, `approval_mode="deny"`, `allowed_tools=[]`, `disabled_tools=["*"]`, `plan=False`, `ask_user=False`, `caveman=False`, no private extensions, and the client's history (at most 20 turns). With every tool refused, the entry agent can only answer from the model. The executor must prove this (assumption b).

## File Structure

Create in `apps/portcullis`:
- `migrations/versions/0027_outside_clients.py`
- `src/models/outside_client.py` (`OutsideClient`, `OutsideClientEvent`); register in `src/models/__init__.py`
- `src/services/outside_clients.py` (records, keys, budget, events)
- `src/services/outside_guard.py` (the chain of checks, the rate limiter)
- `src/services/legion_ask.py` (the stateless ask client)
- `src/routes/outside.py` (the outside route)
- `src/routes/outside_clients_admin.py` (admin routes)
- Tests: `tests/test_outside_clients.py`, `test_outside_ip.py`, `test_outside_guard.py`, `test_outside_routes.py`, `test_outside_admin.py`, `test_legion_ask.py`

Modify: `src/security.py`, `src/config.py`, `src/services/app_policy.py` (the outside IP lists), `src/app.py` (routers, state), `tests/test_migrations.py` (head revision), `tests/test_app_policy.py`, `README.md`.

## Assumptions to check (record each result under "Changes found during work")

- (a) `SecuritySettings` and `app_policy.py` keep `ip_filter` as `{allow_list, deny_list}` mapped onto `ip_allow_list` and `ip_deny_list`. Find where `config.py` reads the `security` block and where `SecurityMiddleware` is built, and follow exactly that path for the new `outside_ip_filter` group (`outside_ip_allow_list`, `outside_ip_deny_list`).
- (b) In `apps/legion/src/runtime/approvals.py` and `agent_config.run_chat`, `approval_mode="deny"` with `allowed_tools=[]` refuses every tool the entry agent could call, including delegation (`delegate_to_agent`), the plan tool and built-in tools. Read the code and its tests; do not edit Legion. If any tool can still run, stop and report: the stateless guarantee is then not met and this plan must be revised (do not ship the route).
  - Note (result): `deny` + `allowed_tools=[]` does not stop recall/skill tools called via `mcp_upstream.call_tool` (brain search, skill search, skill propose). The route also passes `disabled_tools=["*"]` (Legion's wildcard; exact names are not needed) and `plan=False`. See "Changes found during work".
- (c) Legion's `ask(limits=...)` accepts a lower-only cap. If the key names are easy to find (`apps/legion/src/runtime`), pass a per-call output-token cap from a Portcullis setting; if not, skip it and say so (decision 4 already accepts overshoot).
- (d) `identity_headers(username, email, uid)` and Legion accept an empty email. If `mint_requester` or Legion refuses it, use `f"{uid}@outside.invalid"` and record that.
- (e) Legion's `ask` result carries the answer in `response` (a string) and tokens in `agent_usage` (a list of `{total_tokens, ...}`) or `total_tokens`. Read `apps/legion/src/server.py` (`ask`, `run_chat`'s result) and `apps/stronghold/src/usage/rows.py`; the tokens of one outside call are the sum of `agent_usage[*].total_tokens` when present, else `total_tokens`, else 0 (and a 0 on a successful non-empty answer is recorded as 0, with a warning log that names no text).
- (f) The names of the Portcullis test fixtures (`client`, the admin login helper, the fake agent directory, the fake Legion). Read `tests/conftest.py` and `tests/test_tickets.py` and use the real names; the tests below use `client`, `login_admin(client)` and `fake_legion` as stand-ins.
- (g) `tests/test_migrations.py` pins the head revision; update it to `0027` and make `test_migrations.py` pass.

## Baseline (the executor fills in before changing anything)

- Portcullis whole suite: ______ passed, ______ failed (known two failures above).

## Changes found during work (the executor fills in)

- **(b) failed, fixed in Portcullis (Task 3).** `deny` + `allowed_tools=[]` only gates tools that reach `approvals.review` in the provider loop. Legion's `run_chat` also calls `mcp_upstream.call_tool` directly for memory recall (`stronghold__tool_brain_search`, Ember has `memory_recall: true`), skill recall (`stronghold__tool_skill_search`, `skill_recall: true`) and skill learning (`stronghold__tool_skill_propose`, when `skill_learning` is on), all outside review; a `mode: "plan"` entry agent would also delegate through `submit_plan` outside review. User decision: Portcullis-only fix. The outside ask now also passes `disabled_tools=["*"]` and keeps `plan=False`. `tool_filter.is_blocked` treats `"*"` as every tool (not exact-name only) and `mcp_upstream.call_tool` checks it first, so all three raise `PermissionError` before any upstream call; `delegation.call` passes the set (and `approval_mode="deny"`) on to every delegate. `plan=False` only removes the `update_plan` checklist; plan mode comes from the agent file's `mode` (Ember has none, so legacy) and `role` (Ember is `orchestrator`, not `architect`), which this call cannot change. If the entry agent is ever made plan-mode or architect it can still delegate (delegates get `"*"` + deny, so no tool runs, but model calls do). Proven by `tests/test_legion_ask.py::test_legion_refuses_every_tool_the_outside_ask_could_reach`, which drives Legion's real recall, skill recall, skill learning and `call_tool` with a recording fake upstream (Legion's own Python, no model, no `.env`).
- **(c)** Legion `ask(limits=...)` takes `{"max_output_tokens", "max_tool_rounds"}` (lower only). Not passed: it needs a Portcullis setting the plan does not give; decision 4 accepts the overshoot (`# shortcut:` comment at the budget check in `outside_guard.py`).
- **(d)** Met: an empty email is accepted by `mint_requester` and Legion; `identity_headers(f"outside:{uid}", "", uid)` is used.
- **(e)** Met: answer in `response`; tokens = sum of `agent_usage[*].total_tokens` when non-empty, else `total_tokens`, else 0 (0 logs a warning naming only the request id); dict results arrive as `structuredContent`.
- **(f)** Real names: `client`/`client_factory` fixtures (`tests/conftest.py`); admin login `tests.test_admin.login(...)` wrapped as `login_admin`; no existing fakes, so `test_outside_routes.py` defines `FakeDirectory` and `FakeLegion` (`next`, `fail`, `calls`) on `app.state`; clients are created through `OutsideClients` on the app's database via `client.portal.call`. No pytest-asyncio: helpers use `with_db` / `asyncio.run`.

---

### Task 1: Records, keys, budget and audit events

**Files:**
- Create: `migrations/versions/0027_outside_clients.py`, `src/models/outside_client.py`, `src/services/outside_clients.py`
- Modify: `src/models/__init__.py`, `tests/test_migrations.py`
- Test: `tests/test_outside_clients.py`

**Interfaces:**
- Produces:
  - `OutsideClient`: `id`, `uid` (`oc_<12 hex>`), `name` (unique, 1 to 60 chars: letters, digits, space, `-`, `_`, `.`), `key_prefix`, `key_hash`, `services` (JSON list), `ip_allow` (JSON list of addresses or networks), `rate_per_minute`, `budget_tokens`, `budget_days`, `enabled`, `created_at`, `last_used_at`.
  - `OutsideClientEvent`: `id`, `client_id` (FK, `ondelete="CASCADE"`, indexed), `at` (indexed), `service`, `action` (`"call"` or `"refused"`), `reason` (short code, empty for a call), `status` (HTTP status given), `tokens` (int, 0 for a refusal), `ip`.
  - `OutsideClientError(ValueError)`: a refused change; the message is safe to show.
  - `OutsideClients(session)` with: `async create(name, services, rate_per_minute=10, budget_tokens=..., budget_days=30, ip_allow=()) -> tuple[OutsideClient, str]` (the second value is the key, shown once); `async authenticate(key) -> OutsideClient | None`; `async get(client_id) -> OutsideClient | None`; `async list() -> list[OutsideClient]`; `async update(client_id, **changes) -> OutsideClient` (fields: `name`, `services`, `ip_allow`, `rate_per_minute`, `budget_tokens`, `budget_days`, `enabled`); `async rotate_key(client_id) -> tuple[OutsideClient, str]`; `async delete(client_id) -> bool`; `async spent(client, now=None) -> tuple[int, datetime | None]` (tokens used in the window, and when the oldest counted event leaves it, or None); `async record(client, *, service, action, reason="", status, tokens=0, ip="") -> None`; `async events(client_id, limit=50, before_id=None) -> list[OutsideClientEvent]` (newest first).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_outside_clients.py`:

```python
from datetime import timedelta

import pytest

from src.db import Database, utcnow
from src.services.outside_clients import OutsideClientError, OutsideClients


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_tables()
    yield database
    await database.engine.dispose()


async def make(db, **extra):
    async with db.sessions() as session:
        clients = OutsideClients(session)
        args = dict(name="Docs bot", services=["legion"], budget_tokens=1000)
        client, key = await clients.create(**{**args, **extra})
        await session.commit()
        return client.id, key


async def test_a_client_is_created_with_a_key_shown_once_and_only_its_hash_kept(db):
    client_id, key = await make(db)
    assert key.startswith("ock_") and len(key) > 40
    async with db.sessions() as session:
        client = await OutsideClients(session).get(client_id)
    assert client.key_hash != key and key not in (client.key_hash, client.key_prefix)
    assert client.key_prefix == key[:8] and client.uid.startswith("oc_") and len(client.uid) == 15
    assert client.enabled is True and client.rate_per_minute == 10 and client.budget_days == 30


async def test_the_key_finds_its_client_and_nothing_else_does(db):
    client_id, key = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        assert (await clients.authenticate(key)).id == client_id
        assert await clients.authenticate(key + "x") is None
        assert await clients.authenticate("") is None
        assert await clients.authenticate("Bearer " + key) is None


async def test_rotating_the_key_ends_the_old_one(db):
    client_id, old = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        _client, new = await clients.rotate_key(client_id)
        await session.commit()
        assert await clients.authenticate(old) is None
        assert (await clients.authenticate(new)).id == client_id


@pytest.mark.parametrize("extra, message", [
    ({"name": " "}, "name"), ({"name": "x" * 61}, "name"), ({"name": "bad/name"}, "name"),
    ({"services": ["stronghold"]}, "service"), ({"services": []}, "service"), ({"services": ["legion", "legion"]}, "service"),
    ({"rate_per_minute": 0}, "rate"), ({"rate_per_minute": 601}, "rate"),
    ({"budget_tokens": 0}, "budget"), ({"budget_tokens": 100_000_001}, "budget"), ({"budget_days": 0}, "days"), ({"budget_days": 367}, "days"),
    ({"ip_allow": ["not-an-address"]}, "address"),
])
async def test_a_bad_record_is_refused_in_words(db, extra, message):
    with pytest.raises(OutsideClientError, match=message):
        await make(db, **extra)


async def test_names_are_unique_ignoring_case(db):
    await make(db)
    with pytest.raises(OutsideClientError, match="already"):
        await make(db, name="docs BOT")


async def test_update_validates_and_a_disabled_client_still_authenticates_but_is_marked(db):
    client_id, key = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        updated = await clients.update(client_id, enabled=False, ip_allow=["203.0.113.0/24"], budget_tokens=5)
        await session.commit()
        assert updated.enabled is False and updated.ip_allow == ["203.0.113.0/24"]
        assert (await clients.authenticate(key)).enabled is False
        with pytest.raises(OutsideClientError, match="budget"):
            await clients.update(client_id, budget_tokens=0)
        with pytest.raises(OutsideClientError, match="Unknown"):
            await clients.update(client_id, uid="oc_hacked")


async def test_the_budget_counts_only_calls_inside_the_window(db):
    client_id, _ = await make(db, budget_tokens=100, budget_days=2)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        client = await clients.get(client_id)
        await clients.record(client, service="legion", action="call", status=200, tokens=40, ip="1.1.1.1")
        await clients.record(client, service="legion", action="refused", reason="rate", status=429, ip="1.1.1.1")
        await session.commit()
        used, reset = await clients.spent(client)
        assert used == 40 and reset is not None and reset > utcnow()
        later = utcnow() + timedelta(days=3)
        assert await clients.spent(client, now=later) == (0, None)


async def test_events_are_newest_first_page_by_id_and_hold_no_text(db):
    client_id, _ = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        client = await clients.get(client_id)
        for number in range(5):
            await clients.record(client, service="legion", action="call", status=200, tokens=number, ip="1.1.1.1")
        await session.commit()
        first = await clients.events(client_id, limit=2)
        assert [e.tokens for e in first] == [4, 3]
        rest = await clients.events(client_id, limit=10, before_id=first[-1].id)
        assert [e.tokens for e in rest] == [2, 1, 0]
        assert {"question", "answer", "text"}.isdisjoint(vars(first[0]))


async def test_deleting_a_client_deletes_its_events(db):
    client_id, _ = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        client = await clients.get(client_id)
        await clients.record(client, service="legion", action="call", status=200, tokens=1, ip="1.1.1.1")
        await session.commit()
        assert await clients.delete(client_id) is True
        await session.commit()
        assert await clients.events(client_id) == [] and await clients.get(client_id) is None
        assert await clients.delete(client_id) is False
```

- [ ] **Step 2: Run to see the failure**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_clients.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.services.outside_clients'`).

- [ ] **Step 3: Implement**

Write the two models (follow `src/models/usage.py` style; JSON columns with `sqlalchemy.JSON`, naive UTC times from `utcnow`). Write migration `0027` (`down_revision = "0026"`, create both tables and the indexes `ix_outside_clients_key_hash` unique, `ix_outside_client_events_client_id`, `ix_outside_client_events_at`; `downgrade` drops them; follow `0026` for the header and `batch_alter_table` use). Write `OutsideClients`: validation messages must contain the words the parametrised test looks for (`name`, `service`, `rate`, `budget`, `days`, `address`, `already`, `Unknown`); name uniqueness is case-insensitive (store `name` as typed and compare lowercased); `ip_allow` entries are checked with `ipaddress.ip_network(entry, strict=False)` and stored stripped; the key is `"ock_" + secrets.token_urlsafe(32)`, `key_hash = hashlib.sha256(key.encode()).hexdigest()`, `authenticate` rejects anything that does not start with `ock_` before it hashes; `spent` sums `tokens` of `call` events with `at >= now - budget_days` and returns `(sum, oldest_at + budget_days)` or `(0, None)`; `update` accepts only the seven listed fields (anything else raises `OutsideClientError("Unknown field ...")`). Add the models to `src/models/__init__.py`. Update `tests/test_migrations.py` to the new head (assumption g).

- [ ] **Step 4: Run to see it pass**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_clients.py tests/test_migrations.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/portcullis
git commit -m "feat(portcullis): outside client records, keys, budget and audit events

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Outside IP lists

**Files:**
- Modify: `src/security.py`, `src/config.py`, `src/services/app_policy.py`
- Test: `tests/test_outside_ip.py`, `tests/test_app_policy.py`

**Interfaces:**
- Produces:
  - `SecuritySettings.outside_ip_allow_list` and `outside_ip_deny_list` (tuples, default empty).
  - `app_policy` key `outside_ip_filter` with `{allow_list, deny_list}`, validated like `ip_filter`, shown by `view`, saved by `update`, used from the next start (the same "applies next start" rule).
  - `SecurityMiddleware` rule: for a path starting with `/api/outside/`, refuse with `403` when the address is on the main deny list, or on the outside deny list, or when the outside allow list is non-empty and the address is not on it. The main allow list is ignored for these paths. All other paths behave exactly as before.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_outside_ip.py`. First read `tests/test_security.py` to see how `SecurityMiddleware` is exercised (a tiny ASGI app with a fake `scope["client"]`), and reuse that helper; then write:

```python
import pytest

from src.config import SecuritySettings
from src.security import SecurityMiddleware


async def call(settings, path, ip):
    """Run one request through SecurityMiddleware around a trivial app; return the status (use the helper test_security.py uses)."""
    ...  # replace with the helper from tests/test_security.py


def settings(**extra):
    return SecuritySettings(**extra)


async def test_the_main_allow_list_does_not_apply_to_outside_paths():
    config = settings(ip_allow_list=("192.168.0.0/16",))
    assert await call(config, "/api/chats", "203.0.113.5") == 403
    assert await call(config, "/api/outside/legion/ask", "203.0.113.5") != 403


async def test_the_main_deny_list_still_applies_to_outside_paths():
    config = settings(ip_deny_list=("203.0.113.5",))
    assert await call(config, "/api/outside/legion/ask", "203.0.113.5") == 403


async def test_the_outside_lists_apply_only_to_outside_paths():
    config = settings(outside_ip_allow_list=("203.0.113.0/24",), outside_ip_deny_list=("203.0.113.9",))
    assert await call(config, "/api/outside/legion/ask", "203.0.113.5") != 403
    assert await call(config, "/api/outside/legion/ask", "198.51.100.1") == 403
    assert await call(config, "/api/outside/legion/ask", "203.0.113.9") == 403
    assert await call(config, "/api/chats", "198.51.100.1") != 403


async def test_no_lists_means_everything_is_allowed_as_before():
    assert await call(settings(), "/api/outside/legion/ask", "198.51.100.1") != 403
    assert await call(settings(), "/api/chats", "198.51.100.1") != 403
```

The `call` stub above must be replaced by the real helper before the run; the four behaviours are the test. Then add to `tests/test_app_policy.py` the three cases the existing `ip_filter` tests have (view lists the group, update saves and validates a bad address with a message naming "Outside"/"address", `None` returns the group to its default), copying their shape.

- [ ] **Step 2: Run to see the failure**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_ip.py tests/test_app_policy.py`
Expected: FAIL (the new settings and the rule do not exist).

- [ ] **Step 3: Implement**

Follow the path of `ip_filter` everywhere (assumption a): `SecuritySettings` gets the two fields; the place that parses the `security` block reads `outside_ip_filter` into them; `app_policy.SECURITY_PARTS`, `KEYS`, `_in_use`, `_checked` (labels "Outside allow list" and "Outside deny list", reuse `_networks`) and the saved-overlay code handle the new group. In `SecurityMiddleware.__init__` build a second `IpFilter` for the outside lists. In `__call__`, take the path from `scope["path"]`; `outside = path.startswith("/api/outside/")`. Add a small method `IpFilter.denies(address)` (true when on the deny list) so that for an outside path the check is `main.denies(ip) or not outside_filter.allows(ip)`, and for other paths the existing `main.allows(ip)` check is unchanged.

- [ ] **Step 4: Run to see it pass**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_ip.py tests/test_app_policy.py tests/test_security.py tests/test_hardening.py`
Expected: PASS (the existing security tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add apps/portcullis
git commit -m "feat(portcullis): separate IP allow and deny lists for outside clients

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The guard, the stateless Legion ask and the outside route

**Files:**
- Create: `src/services/outside_guard.py`, `src/services/legion_ask.py`, `src/routes/outside.py`
- Modify: `src/app.py`
- Test: `tests/test_outside_guard.py`, `tests/test_legion_ask.py`, `tests/test_outside_routes.py`

**Interfaces:**
- Consumes: `OutsideClients` (Task 1), `client_ip(request)` from `src/security.py`, `AgentDirectory.entry()`, `mcp_session`, `identity_headers`.
- Produces:
  - `OutsideRefused(Exception)` with `status: int`, `code: str`, `message: str`, `retry_after: int | None`, `client: OutsideClient | None`.
  - `ClientRateLimiter(clock=monotonic)` with `retry_after(client_id, per_minute) -> int | None` (in memory; a sliding 60 second window; refused calls are not recorded; at most 1,000 tracked clients).
  - `OutsideGuard(limiter)` with `async admit(clients: OutsideClients, key: str | None, service: str, ip: str) -> OutsideClient`: runs, in this order, (1) key present and well formed, `authenticate`, enabled, else `OutsideRefused(401, "invalid_key", "Invalid or missing key.")`; (2) service in `client.services`, else `403 service_not_allowed`; (3) the client's own `ip_allow` (when not empty) contains `ip`, else `403 ip_not_allowed`; (4) rate, else `429 rate_limited` with `retry_after`; (5) budget: `spent >= budget_tokens` gives `429 budget_exhausted` with `retry_after`; any exception reading it gives `503 budget_unavailable`. Every refusal of a known client writes a `refused` event first (a failure to write it does not change the refusal).
  - `LegionAnswer` (`text: str`, `tokens: int`, `request_id: str`) and `class LegionAsk` with `async ask(url: str, client: OutsideClient, question: str, history: list[dict]) -> LegionAnswer`, which opens `mcp_session(url, identity_headers(client.name, "", client.uid), timeout)` and calls the `ask` tool with exactly the arguments of decision 7 plus a fresh `request_id`; raises `LegionUnavailable` when the session or the call fails or the result has no text.
  - Route `POST /api/outside/legion/ask` with body `{question: str (1..8000), history: list[{role: "user"|"assistant", content: str (1..8000)}] (0..20, default [])}`, answer `{answer, usage: {total_tokens, budget_remaining}, request_id}`.

- [ ] **Step 1: Write the failing guard tests**

Create `tests/test_outside_guard.py` (uses the `db` fixture pattern of Task 1; copy it into this file):

```python
import pytest

from src.db import Database
from src.services.outside_clients import OutsideClients
from src.services.outside_guard import ClientRateLimiter, OutsideGuard, OutsideRefused


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_tables()
    yield database
    await database.engine.dispose()


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


async def setup(db, **extra):
    async with db.sessions() as session:
        client, key = await OutsideClients(session).create(
            **{**dict(name="bot", services=["legion"], budget_tokens=100, rate_per_minute=2), **extra})
        await session.commit()
        return client.id, key


def guard():
    clock = Clock()
    return OutsideGuard(ClientRateLimiter(clock=clock)), clock


async def admit(db, the_guard, key, service="legion", ip="203.0.113.5"):
    async with db.sessions() as session:
        try:
            return await the_guard.admit(OutsideClients(session), key, service, ip)
        finally:
            await session.commit()


async def refusal(db, the_guard, key, **kwargs):
    with pytest.raises(OutsideRefused) as caught:
        await admit(db, the_guard, key, **kwargs)
    return caught.value


async def test_a_good_key_is_admitted(db):
    _id, key = await setup(db)
    the_guard, _ = guard()
    assert (await admit(db, the_guard, key)).name == "bot"


@pytest.mark.parametrize("key", [None, "", "nope", "ock_unknown"])
async def test_a_missing_or_wrong_key_is_401_with_one_message(db, key):
    await setup(db)
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code, refused.message) == (401, "invalid_key", "Invalid or missing key.")


async def test_a_disabled_client_looks_like_a_wrong_key_but_is_audited(db):
    client_id, key = await setup(db)
    async with db.sessions() as session:
        await OutsideClients(session).update(client_id, enabled=False)
        await session.commit()
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.message) == (401, "Invalid or missing key.")
    async with db.sessions() as session:
        events = await OutsideClients(session).events(client_id)
    assert [(e.action, e.reason) for e in events] == [("refused", "disabled")]


async def test_a_service_the_client_may_not_use_is_403(db):
    _id, key = await setup(db)
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key, service="stronghold")
    assert (refused.status, refused.code) == (403, "service_not_allowed")


async def test_the_clients_own_ip_list_is_enforced(db):
    _id, key = await setup(db, ip_allow=["203.0.113.0/24"])
    the_guard, _ = guard()
    await admit(db, the_guard, key, ip="203.0.113.7")
    refused = await refusal(db, the_guard, key, ip="198.51.100.1")
    assert (refused.status, refused.code) == (403, "ip_not_allowed")


async def test_the_rate_limit_answers_429_with_retry_after_and_recovers(db):
    _id, key = await setup(db)
    the_guard, clock = guard()
    await admit(db, the_guard, key)
    await admit(db, the_guard, key)
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code) == (429, "rate_limited") and 1 <= refused.retry_after <= 60
    clock.now = 61.0
    await admit(db, the_guard, key)


async def test_an_exhausted_budget_answers_429_with_the_time_it_resets(db):
    client_id, key = await setup(db, budget_tokens=50)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        await clients.record(await clients.get(client_id), service="legion", action="call", status=200, tokens=50, ip="1.1.1.1")
        await session.commit()
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code) == (429, "budget_exhausted") and refused.retry_after > 0


async def test_when_the_budget_cannot_be_read_the_call_is_refused(db, monkeypatch):
    _id, key = await setup(db)
    the_guard, _ = guard()

    async def broken(self, client, now=None):
        raise RuntimeError("database is down")

    monkeypatch.setattr(OutsideClients, "spent", broken)
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code) == (503, "budget_unavailable")


async def test_every_refusal_of_a_known_client_leaves_an_event_without_text(db):
    client_id, key = await setup(db)
    the_guard, _ = guard()
    await refusal(db, the_guard, key, service="stronghold")
    async with db.sessions() as session:
        events = await OutsideClients(session).events(client_id)
    assert [(e.action, e.reason, e.status, e.tokens) for e in events] == [("refused", "service_not_allowed", 403, 0)]
```

- [ ] **Step 2: Write the failing Legion ask tests**

Create `tests/test_legion_ask.py`. First read `tests/test_mcp_proxy.py` or the nearest test that replaces `mcp_session` with a fake (monkeypatch `src.services.legion_ask.mcp_session`), and write:

```python
import pytest

from src.services import legion_ask
from src.services.legion_ask import LegionAsk, LegionUnavailable


class FakeClient:
    uid, name = "oc_abc123def456", "bot"


class FakeResult:
    def __init__(self, data, error=False):
        self.structuredContent, self.isError, self.content = data, error, []


class FakeSession:
    def __init__(self, result=None, raises=None):
        self.result, self.raises, self.calls = result, raises, []

    async def call_tool(self, name, arguments, **kwargs):
        self.calls.append((name, arguments))
        if self.raises:
            raise self.raises
        return self.result


def patch(monkeypatch, session):
    seen = {}

    class Context:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *exc):
            return False

    def fake_session(url, headers, timeout):
        seen["url"], seen["headers"] = url, headers
        return Context()

    monkeypatch.setattr(legion_ask, "mcp_session", fake_session)
    monkeypatch.setattr(legion_ask, "identity_headers", lambda username, email, uid, **kw: {"X-Citadel-Requester": f"token-for-{uid}"})
    return seen


async def test_the_call_is_stateless_and_carries_the_clients_identity(monkeypatch):
    session = FakeSession(FakeResult({"response": "Hello!", "agent_usage": [{"total_tokens": 30}, {"total_tokens": 12}]}))
    seen = patch(monkeypatch, session)
    answer = await LegionAsk().ask("http://legion/mcp", FakeClient(), "Hi", [{"role": "user", "content": "earlier"}])
    name, arguments = session.calls[0]
    assert name == "ask" and arguments["question"] == "Hi" and arguments["history"] == [{"role": "user", "content": "earlier"}]
    assert arguments["enabled_extensions"] == [] and arguments["approval_mode"] == "deny" and arguments["allowed_tools"] == []
    assert arguments["plan"] is False and arguments["ask_user"] is False and not arguments.get("private_extensions")
    assert arguments["request_id"] == answer.request_id and answer.request_id
    assert seen["url"] == "http://legion/mcp" and seen["headers"]["X-Citadel-Requester"] == "token-for-oc_abc123def456"
    assert (answer.text, answer.tokens) == ("Hello!", 42)


async def test_tokens_fall_back_to_the_total_and_then_to_zero(monkeypatch):
    patch(monkeypatch, FakeSession(FakeResult({"response": "x", "total_tokens": 7})))
    assert (await LegionAsk().ask("u", FakeClient(), "q", [])).tokens == 7
    patch(monkeypatch, FakeSession(FakeResult({"response": "x"})))
    assert (await LegionAsk().ask("u", FakeClient(), "q", [])).tokens == 0


@pytest.mark.parametrize("session", [
    FakeSession(raises=RuntimeError("down")), FakeSession(FakeResult({}, error=True)),
    FakeSession(FakeResult({"response": "  "})), FakeSession(FakeResult(None)),
])
async def test_any_failure_or_empty_answer_is_unavailable(monkeypatch, session):
    patch(monkeypatch, session)
    with pytest.raises(LegionUnavailable):
        await LegionAsk().ask("u", FakeClient(), "q", [])
```

- [ ] **Step 3: Write the failing route tests**

Create `tests/test_outside_routes.py`. Read `tests/conftest.py` and `tests/test_tickets.py` (assumption f) for the real `client` fixture, the admin login helper and how to put a fake agent directory (with an entry agent) and a fake Legion ask into the app (`app.state.agent_directory` and a new `app.state.legion_ask`); write these tests with the real names:

```python
BODY = {"question": "What is 2 + 2?"}


def auth(key):
    return {"Authorization": f"Bearer {key}"}


def make_client(client, **extra):
    """Create an outside client through the admin route; return (id, key). Uses the admin helper of the suite."""
    ...


def test_a_valid_call_returns_the_answer_and_counts_the_tokens(client, fake_legion):
    client_id, key = make_client(client, budget_tokens=1000)
    fake_legion.next = {"text": "Four.", "tokens": 25}
    response = client.post("/api/outside/legion/ask", json=BODY, headers=auth(key))
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Four." and body["usage"] == {"total_tokens": 25, "budget_remaining": 975} and body["request_id"]
    assert fake_legion.calls[0]["question"] == "What is 2 + 2?"


def test_there_is_no_login_cookie_path_in(client):
    response = client.post("/api/outside/legion/ask", json=BODY)
    assert response.status_code == 401 and response.json()["detail"] == "Invalid or missing key."


def test_a_bad_body_is_422_and_spends_nothing(client, fake_legion):
    _id, key = make_client(client)
    for body in ({}, {"question": ""}, {"question": "x" * 8001}, {"question": "q", "history": [{"role": "system", "content": "x"}]},
                 {"question": "q", "history": [{"role": "user", "content": "x"}] * 21}, {"question": "q", "extra": 1}):
        assert client.post("/api/outside/legion/ask", json=body, headers=auth(key)).status_code == 422
    assert fake_legion.calls == []


def test_the_budget_runs_out_and_the_next_call_is_refused_with_retry_after(client, fake_legion):
    _id, key = make_client(client, budget_tokens=30)
    fake_legion.next = {"text": "a", "tokens": 30}
    assert client.post("/api/outside/legion/ask", json=BODY, headers=auth(key)).status_code == 200
    refused = client.post("/api/outside/legion/ask", json=BODY, headers=auth(key))
    assert refused.status_code == 429 and int(refused.headers["retry-after"]) > 0
    assert len(fake_legion.calls) == 1


def test_legion_down_is_503_and_no_tokens_are_counted(client, fake_legion):
    client_id, key = make_client(client, budget_tokens=1000)
    fake_legion.fail = True
    assert client.post("/api/outside/legion/ask", json=BODY, headers=auth(key)).status_code == 503
    detail = client.get(f"/api/admin/outside-clients/{client_id}").json()
    assert detail["budget"]["used"] == 0


def test_no_entry_agent_is_503(client, fake_legion, no_entry_agent):
    _id, key = make_client(client)
    assert client.post("/api/outside/legion/ask", json=BODY, headers=auth(key)).status_code == 503


def test_if_the_tokens_cannot_be_recorded_the_answer_is_withheld(client, fake_legion, monkeypatch):
    _id, key = make_client(client)
    from src.services.outside_clients import OutsideClients

    async def broken(self, *args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(OutsideClients, "record", broken)
    response = client.post("/api/outside/legion/ask", json=BODY, headers=auth(key))
    assert response.status_code == 503 and "answer" not in response.json()


def test_a_session_cookie_or_account_login_does_not_open_the_door(client):
    login_admin(client)
    assert client.post("/api/outside/legion/ask", json=BODY).status_code == 401


def test_the_outside_route_is_the_only_one_a_client_key_opens(client):
    _id, key = make_client(client)
    for path in ("/api/chats", "/api/admin/outside-clients", "/api/usage", "/api/agent"):
        assert client.get(path, headers=auth(key)).status_code in (401, 403, 404)
```

The `make_client` stub is completed in Task 4 once the admin route exists (or build the client through `OutsideClients` directly on the app's database in the test). Mark `test_the_budget_runs_out...` and the others that need `make_client` with the same helper; they all run after Task 4's route exists, but the route tests can be written and made to pass in this task by creating the clients through `OutsideClients` and the app's database session directly. The fake Legion offers `next` (a dict with `text` and `tokens`), `fail` (a bool) and `calls` (the question and history it received).

- [ ] **Step 4: Run to see the failures**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_guard.py tests/test_legion_ask.py tests/test_outside_routes.py`
Expected: FAIL (modules missing).

- [ ] **Step 5: Implement**

`outside_guard.py`: `ClientRateLimiter` (a deque per client id; evict idle clients first when over 1,000; the retry value is `ceil(oldest + 60 - now)`, at least 1); `OutsideGuard.admit` as specified, with the audit event written through `clients.record(...)` inside a `try/except Exception` that never changes the refusal (write the event for 403, 429, 503 and for a disabled client; no event for a missing, malformed or unknown key). Compute `retry_after` for a budget refusal from `spent`'s second value. Never include the key, the question or any text in a refusal or an event.

`legion_ask.py`: as specified. Build the arguments as decision 7 says; use `asyncio.timeout(120)` around the session; wrap every exception (including the SDK's `BaseExceptionGroup`, use `root_cause` from `mcp_session`) as `LegionUnavailable` with a message that contains no question text. Parse tokens per assumption (e). Add the per-call cap from assumption (c) only if the key names are clear.

`outside.py`: a pydantic body model with `extra="forbid"`; the route reads `Authorization`, calls `guard.admit(...)` inside the request's database session, then `entry = await agent_directory.entry()` (503 `"No agent is running"` when None, and a `refused` event with reason `upstream`), then `legion_ask.ask(...)`; on `LegionUnavailable` record a `refused` event (reason `upstream`, status 503) and answer 503; on success `await clients.record(client, service="legion", action="call", status=200, tokens=answer.tokens, ip=ip)` and commit before returning; if that record or commit raises, answer 503 with no answer text (decision 5); the response includes `budget_remaining = max(0, budget_tokens - used_after)`. Update `last_used_at` on a successful call. Map `OutsideRefused` to a JSON `{"detail": message}` with the status and, when set, a `Retry-After` header. In `app.py` include the router, set `app.state.outside_guard = OutsideGuard(ClientRateLimiter())` and `app.state.legion_ask = LegionAsk()`.

- [ ] **Step 6: Run to see them pass**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_guard.py tests/test_legion_ask.py tests/test_outside_routes.py tests/test_outside_clients.py tests/test_security.py`
Expected: PASS.

- [ ] **Step 7: Prove the stateless guarantee (assumption b)**

Read `apps/legion/src/runtime/approvals.py` and the Legion tests for `deny`. Write down in "Changes found" which tools exist for the entry agent and how `deny` with `allowed_tools=[]` handles each (built-in tools, delegation, plan tool). If any can run, stop here, do not commit the route, and report.

- [ ] **Step 8: Commit**

```bash
git add apps/portcullis
git commit -m "feat(portcullis): outside Legion route with key, IP, rate and budget guard

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Admin routes, docs and the end-to-end pass

**Files:**
- Create: `src/routes/outside_clients_admin.py`
- Modify: `src/app.py`, `README.md`
- Test: `tests/test_outside_admin.py`

**Interfaces:**
- Produces, all under `/api/admin/outside-clients`, all needing `settings.manage`, all logged with `LogWriter.action` (action names `outside_client.create`, `.update`, `.rotate`, `.delete`; the message holds the client's id and name and the changed field names, never a key):
  - `POST` body `{name, services?, rate_per_minute?, budget_tokens, budget_days?, ip_allow?}` gives `201 {client, key}`; the key appears only here.
  - `GET` gives `{clients: [...]}`; each client is `{id, uid, name, key_prefix, services, ip_allow, rate_per_minute, enabled, created_at, last_used_at, budget: {tokens, days, used, remaining, resets_at}}`; never the hash.
  - `GET /{id}` gives the client plus `events` (the newest 50; query `limit` 1 to 200 and `before_id` page it).
  - `PATCH /{id}` (any of `name, services, ip_allow, rate_per_minute, budget_tokens, budget_days, enabled`) gives the client.
  - `POST /{id}/rotate-key` gives `{client, key}`.
  - `DELETE /{id}` gives `204`.
  - Errors: `404` unknown id, `400` for an `OutsideClientError` with its message, `422` for a malformed body.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_outside_admin.py` with the suite's real `client` and admin helpers (assumption f):

```python
def test_only_staff_with_settings_manage_may_use_the_admin_routes(client):
    assert client.get("/api/admin/outside-clients").status_code in (401, 403)
    login_member(client)  # an account without settings.manage
    assert client.get("/api/admin/outside-clients").status_code == 403
    assert client.post("/api/admin/outside-clients", json={"name": "x", "budget_tokens": 10}).status_code == 403


def test_create_shows_the_key_once_and_never_the_hash(client):
    login_admin(client)
    created = client.post("/api/admin/outside-clients", json={"name": "Docs bot", "budget_tokens": 5000})
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("ock_") and body["client"]["name"] == "Docs bot" and body["client"]["services"] == ["legion"]
    listed = client.get("/api/admin/outside-clients").json()["clients"]
    assert len(listed) == 1 and "key" not in listed[0] and "key_hash" not in listed[0]
    assert listed[0]["key_prefix"] == body["key"][:8] and listed[0]["budget"]["used"] == 0 and listed[0]["budget"]["remaining"] == 5000


def test_bad_input_is_400_in_words_or_422(client):
    login_admin(client)
    assert client.post("/api/admin/outside-clients", json={"name": "x"}).status_code == 422  # budget is required
    refused = client.post("/api/admin/outside-clients", json={"name": "x", "budget_tokens": 0})
    assert refused.status_code == 400 and "budget" in refused.json()["detail"]
    assert client.post("/api/admin/outside-clients", json={"name": "x", "budget_tokens": 5, "services": ["stronghold"]}).status_code == 400
    assert client.post("/api/admin/outside-clients", json={"name": "x", "budget_tokens": 5, "key": "ock_mine"}).status_code == 422


def test_patch_disable_rotate_and_delete(client, fake_legion):
    login_admin(client)
    created = client.post("/api/admin/outside-clients", json={"name": "Docs bot", "budget_tokens": 5000}).json()
    client_id, key = created["client"]["id"], created["key"]
    assert client.patch(f"/api/admin/outside-clients/{client_id}", json={"enabled": False}).json()["enabled"] is False
    fake_legion.next = {"text": "a", "tokens": 1}
    assert call_outside(key).status_code == 401
    client.patch(f"/api/admin/outside-clients/{client_id}", json={"enabled": True})
    assert call_outside(key).status_code == 200
    rotated = client.post(f"/api/admin/outside-clients/{client_id}/rotate-key").json()
    assert rotated["key"] != key and call_outside(key).status_code == 401 and call_outside(rotated["key"]).status_code == 200
    assert client.delete(f"/api/admin/outside-clients/{client_id}").status_code == 204
    assert client.get(f"/api/admin/outside-clients/{client_id}").status_code == 404
    assert call_outside(rotated["key"]).status_code == 401


def test_the_detail_shows_the_audit_events_and_no_text(client, fake_legion):
    login_admin(client)
    created = client.post("/api/admin/outside-clients", json={"name": "Docs bot", "budget_tokens": 5000, "ip_allow": ["203.0.113.0/24"]}).json()
    fake_legion.next = {"text": "SECRET ANSWER", "tokens": 9}
    call_outside(created["key"], question="SECRET QUESTION", ip="203.0.113.7")
    call_outside(created["key"], ip="198.51.100.1")  # outside the client's own list
    detail = client.get(f"/api/admin/outside-clients/{created['client']['id']}").json()
    assert [(e["action"], e["reason"], e["status"]) for e in detail["events"]] == [("refused", "ip_not_allowed", 403), ("call", "", 200)]
    assert "SECRET" not in str(detail) and detail["budget"]["used"] == 9


def test_admin_changes_are_logged_without_a_key(client, platform_logs):
    login_admin(client)
    created = client.post("/api/admin/outside-clients", json={"name": "Docs bot", "budget_tokens": 5000}).json()
    client.patch(f"/api/admin/outside-clients/{created['client']['id']}", json={"rate_per_minute": 5})
    messages = " ".join(platform_logs())
    assert "outside_client.create" in messages or "Docs bot" in messages
    assert created["key"] not in messages and created["key"][:8] not in messages.replace("Docs bot", "")
```

`call_outside(key, question="q", ip=None)` posts to `/api/outside/legion/ask` with the Bearer header (and `X-Forwarded-For` when a test client configuration trusts it; use the same trick `tests/test_security.py` uses for a client address). `login_member`, `login_admin`, `fake_legion` and `platform_logs` are the suite's real helpers; if the suite has no log reader, read `LogEntry` rows through the app's database like `tests/test_logs.py` does. The last assertion line must be rewritten against whatever the log message really looks like; keep the rule that no key and no key prefix appears in any log message.

- [ ] **Step 2: Run to see the failure**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_admin.py`
Expected: FAIL (route missing, 404).

- [ ] **Step 3: Implement**

Write `outside_clients_admin.py` to the interface above, following `src/routes/app_policy_routes.py` for the dependency style (`require_permission(SETTINGS_MANAGE)`, `get_log_writer`). Request models use `extra="forbid"`. Budget numbers come from `OutsideClients.spent`. Include the router in `app.py`. Then document in `README.md`: the outside door and its status codes, the key format and how to send it, the client record fields and limits, the budget rule (checked before, added after, overshoot bounded by the calls in flight, withheld answer if the record fails), the audit log fields (and that it holds no text), the two new IP lists and the rule that the main allow list does not apply to `/api/outside/*`, the admin routes with their examples, the "no tools, no memory" guarantee, and the list of what is not built (Stronghold level, admin screen, tool access).

- [ ] **Step 4: Run to see it pass, then the whole suite**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_outside_admin.py tests/test_outside_routes.py` and then the whole Portcullis suite (about ten minutes: use a background run or a long timeout).
Expected: PASS; only the two known failures remain. Record the count against the baseline.

- [ ] **Step 5: Commit**

```bash
git add apps/portcullis
git commit -m "feat(portcullis): admin routes and docs for outside clients

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Manual checklist (the user runs these; the executor copies it into the report as pending)

- [ ] With the stack running, create a client with `POST /api/admin/outside-clients` (staff session), keep the returned key, then `curl -H "Authorization: Bearer <key>" -H "Content-Type: application/json" -d '{"question":"Say hello"}' http://<host>:29601/api/outside/legion/ask` returns an answer and `usage.budget_remaining` falls by the tokens used.
- [ ] Ask the client's question "list my notes" or "run a tool": the answer is text only and no tool step runs in Legion's logs.
- [ ] A wrong key, a disabled client and a deleted client all answer the same 401 text.
- [ ] A client whose budget is set to 1 token is refused on the second call with 429 and a `Retry-After`.
- [ ] Setting the client's `ip_allow` to another network makes the call 403; the audit log of the client shows the refusal with reason `ip_not_allowed`.
- [ ] With the main IP allow list set to the LAN only, an outside call from another network still reaches the route (and is refused or admitted by the outside lists and the key), while the admin app still refuses that network.
- [ ] Stopping Legion makes the call 503, and the client's budget does not change.
- [ ] The client's key and the question text appear nowhere in Portcullis logs or the audit events.
- [ ] A signed-in browser session cannot call `/api/outside/legion/ask`; an outside key cannot call `/api/chats` or any admin route.

## Known gaps (not built here)

- Stronghold level (a client with its own memory namespace) and any Stronghold outside route: needs Stronghold work.
- A Portcullis Admin page for clients.
- Per-client tool access; per-call token ceiling; refusals of unknown keys are not audited or counted (a flood of bad keys is limited only by the main IP lists and the traffic counters).
- The outside lists, like the other policy values, apply from the next Portcullis start.

## Self-review (done by the plan's author)

- Spec coverage: client records with key, allowed services, rate limit, spend cap and audit log (Tasks 1, 3, 4); allow/deny list built on the IP filter (Task 2); per-client budget as a fail-closed guard fed by usage reports (Task 3, decisions 4 and 5); "outside clients cannot reach the model level" (Global Constraints, route test); the Stronghold level is split out on purpose and says why.
- Placeholders: only the Baseline and "Changes found" blanks. Three test files contain stand-in helpers (`call`, `make_client`, fixture names) that each tell the executor which existing file to copy the real one from; every behaviour the tests check is written out.
- Type consistency: `OutsideClients` method names, the `spent` return pair, the event fields, the refusal codes (`invalid_key`, `service_not_allowed`, `ip_not_allowed`, `rate_limited`, `budget_exhausted`, `budget_unavailable`) and the route and admin paths are the same in every task and test.
