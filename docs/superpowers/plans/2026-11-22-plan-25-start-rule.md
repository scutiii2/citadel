# Plan 25: Start rule, tool failure codes, /ready and Treasury discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Citadel service starts whatever the state of its dependencies, reports each dependency on `/ready`, returns numbered tool failures (1000 to 1005), and Treasury finds the stack's own services by probing compose names.

**Architecture:** One shared module pair in `libs/citadel_auth` (`failure.py` for the codes, `ready.py` for dependency probes), copied into the five services by `scripts/sync_citadel_auth.py`. Each service mounts `/health` (all five) and `/ready` (all five) and lists its own dependencies. Stronghold's MCP tools and Armory's tools return the numbered failure text; Legion's loop guard reads `retryable`. Treasury gets a background discovery probe. `depends_on` in compose stays a plain list and a check script keeps it that way.

**Tech Stack:** Python 3.11+, FastAPI and FastMCP, httpx (already in the library), pytest, `uv`.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md), sections "Start rule", "Tool failure codes", "Guards" and "Outside services and the catalog" (Discovery line). Audit findings 9, 10 and 12: [2026-11-20-scope-audit.md](2026-11-20-scope-audit.md). Roadmap row 25.

## Global Constraints

- A service starts whatever the state of its dependencies. `/health` is up while the process runs. `/ready` **never fails the container**: it always answers `200` with the states.
- Codes, names and retry flags are exactly: 1000 `TOOL_INTERNAL` No; 1001 `DEP_NOT_CONFIGURED` No; 1002 `DEP_UNAVAILABLE` Yes; 1003 `DEP_TIMEOUT` Yes; 1004 `DEP_AUTH_REJECTED` No; 1005 `DEP_ERROR` Maybe. Message form: `[1002] DEP_UNAVAILABLE treasury unavailable`.
- Capability-specific enums (pdf, media) stay for their own codes.
- Guards stay fail closed (see the `citadel-guards-fail-closed` rule). A failed `/ready` probe never allows a guarded action.
- `/ready` needs a signed service assertion like the other routes (it shows the stack's shape); only `/health` stays open. The Portcullis admin aggregate route needs `settings.manage`.
- `libs/citadel_auth` is edited only in `libs/`, then `python scripts/sync_citadel_auth.py`; its `--check` flag must pass at the end. Never edit a copied `src/citadel_auth/`.
- No Docker socket mount for discovery. Treasury probes names and health endpoints only.
- Models only through Legion: this plan adds no model call.
- No UI screen in this plan (the spec says admin apps show `/ready`; the route comes first, the screen is a later small plan).
- Use `uv` and `pnpm`. Add no dependency. Never read, print or write `.env*`, `secrets/` or key files.
- One commit per task, each ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push.

## Baseline (record before the first edit)

Branch `plan-25-start-rule` from `main` (Plan 22 may or may not be merged; this plan touches different files except the shared library and READMEs, so either order works. If both are open, merge one, then `git rebase main` the other). Run each suite once: `libs/citadel_auth`, Armory, Stronghold, Portcullis (about 13 minutes, 2 known failures), Legion, Treasury, all with `uv run --no-sync python -u -m pytest -q -p no:cacheprovider`. In a worktree with empty `.venv` folders use the main checkout's interpreter from the app folder. Write counts under "Baseline results".

## Assumptions to check (record each result under "Changes found during work")

- **(a)** Armory and Legion have **no** `/health` route today (the auth middleware lists `/health` as an open path, but `git grep -n "/health" -- apps/armory/src apps/legion/src` finds only the library and one outgoing probe). Portcullis exposes `/api/health` (not `/health`).
- **(b)** Armory and Legion are FastMCP servers, so a route is added with `@mcp.custom_route("/health", methods=["GET"])` as `legion/src/server.py` already does for `/registry`. Check Armory's equivalent in `src/server.py` and `src/run.py`.
- **(c)** `apps/armory/pyproject.toml` may not list `httpx` directly (the library does). If Armory's environment lacks it, stop and report; do not add a dependency.
- **(d)** Stronghold's MCP tools live in `apps/stronghold/src/mcp_tools/` (`brain_tools.py`, `ticket_tools.py`, `usage_tools.py`, `stack_tools.py`, `proposal_tools.py`, `skill_tools.py`, `scope.py`, `server.py`). Find how a tool returns a user-visible error today: `git grep -n -E "raise|return .*error|isError" -- apps/stronghold/src/mcp_tools`.
- **(e)** Legion's repeated-call detection is `TurnGuard.check_call(name, arguments)` in `apps/legion/src/providers/turn_guard.py`. Check how a tool result reaches the loop (the provider loops call `check_call` before the tool). The `retryable` read happens on the result, so find where the result text is available.
- **(f)** Treasury registration: services register their own address through `libs/citadel_auth/citadel_auth/treasury.py`; `apps/treasury/src/service_catalog.py` has `effective`, `view`, `register`, `pin`, `unpin`. A pin beats an auto entry (spec).
- **(g)** Compose today uses `depends_on: [name, ...]` lists with no `condition:` (`docker-compose.yml`). Check with `git grep -n "condition:" -- docker-compose*.yml`.

## File map

| Area | Create | Modify |
|---|---|---|
| `libs/citadel_auth` | `citadel_auth/failure.py`, `citadel_auth/ready.py`, `tests/test_failure.py`, `tests/test_ready.py` | synced copies in five apps (generated) |
| Stronghold | `src/ready.py` | `src/api.py` (mount `/ready`), `src/mcp_tools/*` (failure text), tests |
| Armory | `src/ready.py` | `src/server.py` or `src/run.py` (`/health`, `/ready`), `src/errors.py` (reuse), tests |
| Legion | `src/ready.py` | `src/server.py` (`/health`, `/ready`), `src/providers/turn_guard.py`, tests |
| Portcullis | `src/routes/ready.py` | `src/app.py` (mount), tests |
| Treasury | `src/ready.py`, `src/discovery.py` | `src/api.py`, `src/run.py` (background task), tests |
| Compose and docs | | `scripts/check_compose.py`, `docker-compose.yml` comment, `docs/deployment.md`, service READMEs |

---

### Task 1: Failure codes in the shared library

**Files:**
- Create: `libs/citadel_auth/citadel_auth/failure.py`, `libs/citadel_auth/tests/test_failure.py`
- Modify: none by hand; `scripts/sync_citadel_auth.py` copies it.

**Interfaces:**
- Produces: `Code` (an `IntEnum` with the six values), `Failure` (an `Exception` carrying `code`, `dependency`, `message`), `Failure.retryable -> bool | None` (`None` means Maybe), `Failure.text -> str`, `from_exception(dependency: str, error: BaseException) -> Failure`, `parse(text: str) -> Failure | None`.

- [x] **Step 1: Write the failing test**

```python
# libs/citadel_auth/tests/test_failure.py
import httpx

from citadel_auth.failure import Code, Failure, from_exception, parse


def test_codes_names_and_retry_flags():
    assert [c.value for c in Code] == [1000, 1001, 1002, 1003, 1004, 1005]
    assert Failure(Code.DEP_UNAVAILABLE, "treasury").retryable is True
    assert Failure(Code.DEP_TIMEOUT, "treasury").retryable is True
    assert Failure(Code.DEP_AUTH_REJECTED, "treasury").retryable is False
    assert Failure(Code.DEP_NOT_CONFIGURED, "bard").retryable is False
    assert Failure(Code.TOOL_INTERNAL, "").retryable is False
    assert Failure(Code.DEP_ERROR, "treasury").retryable is None


def test_text_form_and_round_trip():
    failure = Failure(Code.DEP_UNAVAILABLE, "treasury")
    assert failure.text == "[1002] DEP_UNAVAILABLE treasury unavailable"
    parsed = parse(failure.text)
    assert parsed is not None and parsed.code is Code.DEP_UNAVAILABLE and parsed.dependency == "treasury"
    assert parse("plain text") is None
    assert parse("[9999] NOPE x") is None


def test_exceptions_map_to_codes():
    request = httpx.Request("GET", "http://treasury/x")
    assert from_exception("treasury", httpx.ConnectError("no", request=request)).code is Code.DEP_UNAVAILABLE
    assert from_exception("treasury", httpx.ReadTimeout("slow", request=request)).code is Code.DEP_TIMEOUT
    assert from_exception("treasury", httpx.ConnectTimeout("slow", request=request)).code is Code.DEP_TIMEOUT
    for status, code in ((401, Code.DEP_AUTH_REJECTED), (403, Code.DEP_AUTH_REJECTED), (500, Code.DEP_ERROR), (404, Code.DEP_ERROR)):
        response = httpx.Response(status, request=request)
        error = httpx.HTTPStatusError("x", request=request, response=response)
        assert from_exception("treasury", error).code is code
    assert from_exception("treasury", ValueError("boom")).code is Code.TOOL_INTERNAL
    # the message never carries the exception text (it can hold paths, hosts or credentials)
    assert "boom" not in from_exception("treasury", ValueError("boom")).text
```

- [x] **Step 2: Run it; see it fail.** `uv run --no-sync python -u -m pytest tests/test_failure.py -q -p no:cacheprovider` from `libs/citadel_auth`. Expected: `ModuleNotFoundError: citadel_auth.failure`.

- [x] **Step 3: Write `failure.py`**

```python
"""Numbered tool failures: a tool that cannot reach a dependency says which one and whether to retry."""

from __future__ import annotations

import re
from enum import IntEnum

import httpx


class Code(IntEnum):
    TOOL_INTERNAL = 1000
    DEP_NOT_CONFIGURED = 1001
    DEP_UNAVAILABLE = 1002
    DEP_TIMEOUT = 1003
    DEP_AUTH_REJECTED = 1004
    DEP_ERROR = 1005


_RETRYABLE = {
    Code.TOOL_INTERNAL: False,
    Code.DEP_NOT_CONFIGURED: False,
    Code.DEP_UNAVAILABLE: True,
    Code.DEP_TIMEOUT: True,
    Code.DEP_AUTH_REJECTED: False,
    Code.DEP_ERROR: None,  # maybe
}
_WORDS = {
    Code.TOOL_INTERNAL: "failed",
    Code.DEP_NOT_CONFIGURED: "not configured",
    Code.DEP_UNAVAILABLE: "unavailable",
    Code.DEP_TIMEOUT: "timed out",
    Code.DEP_AUTH_REJECTED: "rejected the service token",
    Code.DEP_ERROR: "returned an error",
}
_LINE = re.compile(r"^\[(\d{4})\] ([A-Z_]+) (.*)$")


class Failure(Exception):
    """A failure with a number. `text` is safe to show to a model or a user."""

    def __init__(self, code: Code, dependency: str = "") -> None:
        self.code = Code(code)
        self.dependency = dependency
        super().__init__(self.text)

    @property
    def retryable(self) -> bool | None:
        return _RETRYABLE[self.code]

    @property
    def text(self) -> str:
        subject = self.dependency or "tool"
        return f"[{int(self.code)}] {self.code.name} {subject} {_WORDS[self.code]}"


def from_exception(dependency: str, error: BaseException) -> Failure:
    """Map a transport error to a code. Never copies the error's own text."""
    if isinstance(error, Failure):
        return error
    if isinstance(error, httpx.TimeoutException):
        return Failure(Code.DEP_TIMEOUT, dependency)
    if isinstance(error, (httpx.ConnectError, httpx.NetworkError)):
        return Failure(Code.DEP_UNAVAILABLE, dependency)
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in (401, 403):
            return Failure(Code.DEP_AUTH_REJECTED, dependency)
        return Failure(Code.DEP_ERROR, dependency)
    return Failure(Code.TOOL_INTERNAL, dependency)


def parse(text: str) -> Failure | None:
    """Read a failure back from its text form, or None when the text is not one."""
    match = _LINE.match(text.strip().splitlines()[0]) if text.strip() else None
    if not match:
        return None
    try:
        code = Code(int(match.group(1)))
    except ValueError:
        return None
    if code.name != match.group(2):
        return None
    subject = match.group(3).split(" ", 1)[0]
    return Failure(code, "" if subject == "tool" else subject)
```

- [x] **Step 4: Run the test; see it pass.** If `ConnectTimeout` is not a subclass of `TimeoutException` in the installed httpx, the first branch order still maps it correctly; fix only the test's expectation if httpx differs and record it.

- [x] **Step 5: Sync and check.** `python scripts/sync_citadel_auth.py` then `python scripts/sync_citadel_auth.py --check` (exit 0). Run `libs/citadel_auth` tests.

- [x] **Step 6: Commit.** `git commit -m "feat(auth): numbered tool failure codes in the shared library"`

---

### Task 2: Dependency probes and the `/ready` report in the library

**Files:**
- Create: `libs/citadel_auth/citadel_auth/ready.py`, `libs/citadel_auth/tests/test_ready.py`

**Interfaces:**
- Consumes: nothing from Task 1 except the idea of states.
- Produces: `Dependency` (dataclass: `name: str`, `address: Callable[[], str | None]`, `path: str = "/health"`), `Probe` (class) with `async check(dependencies: list[Dependency]) -> dict`, cached for `ttl` seconds. The report shape: `{"service": str, "status": "up", "dependencies": [{"name", "state", "address", "last_error"}]}` where `state` is one of `"configured"` (an address exists, not probed yet or probe not run), `"reachable"`, `"unreachable"`, `"not_configured"` (no address). `last_error` is `None` or a short fixed word (`"unavailable"`, `"timeout"`, `"rejected"`, `"error"`), never exception text.

- [x] **Step 1: Write the failing test**

```python
# libs/citadel_auth/tests/test_ready.py
import asyncio

import httpx

from citadel_auth.ready import Dependency, Probe


def transport(handler):
    return httpx.MockTransport(handler)


async def run(deps, handler, ttl=0.0):
    probe = Probe("legion", client_factory=lambda: httpx.AsyncClient(transport=transport(handler)), ttl=ttl)
    return await probe.check(deps)


def test_states_for_up_down_slow_rejected_and_missing():
    def handler(request):
        host = request.url.host
        if host == "up":
            return httpx.Response(200, json={"status": "ok"})
        if host == "rejected":
            return httpx.Response(401)
        if host == "broken":
            return httpx.Response(500)
        if host == "slow":
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("down", request=request)

    deps = [
        Dependency("up", lambda: "http://up:1"),
        Dependency("down", lambda: "http://down:1"),
        Dependency("slow", lambda: "http://slow:1"),
        Dependency("rejected", lambda: "http://rejected:1"),
        Dependency("broken", lambda: "http://broken:1"),
        Dependency("missing", lambda: None),
    ]
    report = asyncio.run(run(deps, handler))
    states = {d["name"]: (d["state"], d["last_error"]) for d in report["dependencies"]}
    assert report["service"] == "legion" and report["status"] == "up"
    assert states == {
        "up": ("reachable", None),
        "down": ("unreachable", "unavailable"),
        "slow": ("unreachable", "timeout"),
        "rejected": ("unreachable", "rejected"),
        "broken": ("unreachable", "error"),
        "missing": ("not_configured", None),
    }


def test_the_report_is_cached_for_the_ttl():
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200)

    async def go():
        probe = Probe("x", client_factory=lambda: httpx.AsyncClient(transport=transport(handler)), ttl=60.0)
        deps = [Dependency("up", lambda: "http://up:1")]
        await probe.check(deps)
        await probe.check(deps)

    asyncio.run(go())
    assert calls == ["up"]


def test_no_address_text_leaks_an_exception():
    def handler(request):
        raise httpx.ConnectError("secret-host.internal refused", request=request)

    report = asyncio.run(run([Dependency("a", lambda: "http://a:1")], handler))
    assert "secret" not in str(report)
```

- [x] **Step 2: Run it; see it fail** (`ModuleNotFoundError: citadel_auth.ready`).

- [x] **Step 3: Write `ready.py`**

```python
"""Dependency report for /ready: each dependency with state and last error. Never raises, never fails a container."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

PROBE_TIMEOUT = 2.0


@dataclass(frozen=True)
class Dependency:
    name: str
    address: Callable[[], str | None]
    path: str = "/health"


class Probe:
    """Probes dependencies at the same time and keeps the last report for `ttl` seconds."""

    def __init__(self, service: str, *, client_factory: Callable[[], httpx.AsyncClient] | None = None,
                 ttl: float = 10.0) -> None:
        self._service = service
        self._factory = client_factory or (lambda: httpx.AsyncClient(timeout=PROBE_TIMEOUT))
        self._ttl = ttl
        self._cached: dict | None = None
        self._at = 0.0
        self._lock = asyncio.Lock()

    async def check(self, dependencies: list[Dependency]) -> dict:
        async with self._lock:
            now = time.monotonic()
            if self._cached is not None and now - self._at < self._ttl:
                return self._cached
            async with self._factory() as client:
                rows = await asyncio.gather(*(self._one(client, d) for d in dependencies))
            self._cached = {"service": self._service, "status": "up", "dependencies": list(rows)}
            self._at = time.monotonic()
            return self._cached

    async def _one(self, client: httpx.AsyncClient, dependency: Dependency) -> dict:
        try:
            address = dependency.address()
        except Exception:  # an address lookup that fails is "not configured", never a crash
            address = None
        row = {"name": dependency.name, "state": "not_configured", "address": address, "last_error": None}
        if not address:
            return row
        try:
            response = await client.get(address.rstrip("/") + dependency.path, timeout=PROBE_TIMEOUT)
        except httpx.TimeoutException:
            return {**row, "state": "unreachable", "last_error": "timeout"}
        except httpx.HTTPError:
            return {**row, "state": "unreachable", "last_error": "unavailable"}
        if response.status_code in (401, 403):
            return {**row, "state": "unreachable", "last_error": "rejected"}
        if response.status_code >= 400:
            return {**row, "state": "unreachable", "last_error": "error"}
        return {**row, "state": "reachable"}
```

Note: the address is shown in the report. Treasury addresses are internal compose names, already visible to any service holder; the report itself needs a signed assertion (Global Constraints), so it adds no outside exposure.

- [x] **Step 4: Run the tests; they pass.** Sync and check. Run the library suite.

- [x] **Step 5: Commit.** `git commit -m "feat(auth): dependency probes for the /ready report"`

---

### Task 3: `/health` and `/ready` in all five services, and the Portcullis aggregate

**Files:**
- Create: `apps/<service>/src/ready.py` for stronghold, armory, legion, treasury (each: the service's dependency list); `apps/portcullis/src/routes/ready.py`; tests `apps/<service>/tests/test_ready.py`.
- Modify: `apps/stronghold/src/api.py` (next to `/health` at line ~266), `apps/treasury/src/api.py` (next to `/health` at line ~105), `apps/armory/src/server.py` or `run.py` and `apps/legion/src/server.py` (add `/health` and `/ready` custom routes, assumptions (a) and (b)), `apps/portcullis/src/app.py` (mount the aggregate router near `/api/health`, line ~319).

**Interfaces:**
- Consumes: `Dependency`, `Probe` from Task 2. Each service's own settings object already holds the addresses of its dependencies (find how the code resolves them today: `git grep -n -E "treasury_url|catalog|service_address|lookup" -- apps/<service>/src`).
- Produces: `GET /health` answers `{"status": "ok"}` in all five (Portcullis keeps `/api/health`). `GET /ready` (service assertion required) answers `200` with the Task 2 report. `GET /api/admin/ready` (Portcullis, `settings.manage`) returns `{"portcullis": <own report>, "stronghold": ..., "legion": ..., "armory": ..., "treasury": ...}` by calling each service's `/ready` with the signed service client, and an entry `{"service": name, "status": "down"}` for a service that does not answer.

Dependency lists (one list per service, from the scope table):

| Service | Dependencies it reports |
|---|---|
| Portcullis | treasury, stronghold, legion, armory |
| Legion | treasury, armory, stronghold, conversation-gateway, decision-gateway |
| Stronghold | treasury, legion, armory, portcullis |
| Armory | treasury |
| Treasury | none (its list is empty; it reports `"dependencies": []`) |

- [x] **Step 1: Check assumptions (a), (b), (c).** Record. If Armory or Legion cannot add a custom route the way the plan says, use the framework's own app object and say how.

- [x] **Step 2: Write the failing tests** (one per service; same shape). For Stronghold:

```python
def test_health_is_open_and_ready_is_always_200(client, signed_headers):
    # client and signed_headers: the fixtures the existing api tests use; copy the names from tests/test_api*.py
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/ready", headers=signed_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "stronghold" and body["status"] == "up"
    assert {d["name"] for d in body["dependencies"]} == {"treasury", "legion", "armory", "portcullis"}


def test_ready_needs_a_service_assertion(client):
    assert client.get("/ready").status_code in (401, 403)
```

Copy this pair for Legion (names: treasury, armory, stronghold, conversation-gateway, decision-gateway), Armory (treasury), Treasury (empty list). For Portcullis:

```python
def test_admin_ready_needs_settings_manage(client, member_session):
    assert client.get("/api/admin/ready", cookies=member_session).status_code == 403


def test_admin_ready_lists_every_service_and_survives_a_down_one(client, admin_session, monkeypatch):
    # monkeypatch the function that calls one service so it raises; the route must still answer 200
    response = client.get("/api/admin/ready", cookies=admin_session)
    assert response.status_code == 200
    assert set(response.json()) == {"portcullis", "stronghold", "legion", "armory", "treasury"}
```

Use the real fixture names from `apps/portcullis/tests` (look at an existing admin route test, for example the outside-clients admin test from Plan 24).

- [x] **Step 3: Run them; see them fail** (404 for `/ready`, and `/health` 404 on Armory and Legion).

- [x] **Step 4: Implement.** In each `src/ready.py`, build a module-level `Probe("<service>")` and a `dependencies()` function returning the table row's `Dependency` objects, with addresses read lazily from the service's own settings or catalog per call (the start rule: addresses are looked up per call). `/ready` calls `await probe.check(dependencies())`. Mount routes next to `/health`. Keep the existing open-path list in the auth middleware: `/health` stays open; `/ready` is not added to it.

- [x] **Step 5: Run each service suite**, then `python scripts/sync_citadel_auth.py --check`.

- [x] **Step 6: Commit.** `git commit -m "feat: /health and /ready in every service and an admin aggregate in Portcullis"`

---

### Task 4: Numbered failures in Stronghold and Armory tools, and Legion's loop guard

**Files:**
- Modify: `apps/stronghold/src/mcp_tools/ticket_tools.py`, `usage_tools.py`, `brain_tools.py`, `stack_tools.py`, `proposal_tools.py`, `skill_tools.py` (wrap the Treasury-touching calls), `apps/armory/src/errors.py` (add a helper that returns a `Failure` text for a dependency call; keep `report()` for unexpected errors), `apps/legion/src/providers/turn_guard.py`, the provider loop code that calls `check_call` (assumption (e)).
- Test: `apps/stronghold/tests/test_tool_failures.py` (create), `apps/legion/tests/test_turn_guard.py` (extend; find the existing file).

**Interfaces:**
- Consumes: `Failure`, `from_exception`, `parse` (Task 1).
- Produces: a decorator `guarded(dependency: str)` in `apps/stronghold/src/mcp_tools/failures.py` that runs an async tool function and, on any exception, returns `from_exception(dependency, error).text` instead of raising; `TurnGuard.note_result(name, arguments, text)` which records a non-retryable failure for that exact call and makes the next `check_call` of the same call raise `TurnStopped` with the failure text.

- [x] **Step 1: Check assumptions (d) and (e).** Record how a tool error is returned today and where the loop sees a result.

- [x] **Step 2: Write the failing Stronghold test**

```python
# apps/stronghold/tests/test_tool_failures.py
import asyncio

import httpx

from src.mcp_tools.failures import guarded


def test_a_treasury_outage_becomes_a_numbered_failure():
    request = httpx.Request("GET", "http://treasury/x")

    @guarded("treasury")
    async def tool():
        raise httpx.ConnectError("secret-host refused", request=request)

    text = asyncio.run(tool())
    assert text == "[1002] DEP_UNAVAILABLE treasury unavailable"
    assert "secret" not in text


def test_success_passes_through():
    @guarded("treasury")
    async def tool():
        return "ok"

    assert asyncio.run(tool()) == "ok"
```

Add one more test per tool module you wrapped: patch the store call to raise `httpx.ConnectError` and assert the tool returns text starting `[1002]`. Use the fixtures the existing tool tests use (find them: `git grep -l "ticket_tools" -- apps/stronghold/tests`).

- [x] **Step 3: Write the failing Legion test**

```python
def test_a_non_retryable_failure_stops_the_same_call_from_repeating():
    import pytest
    from src.providers.turn_guard import TurnGuard, TurnStopped

    guard = TurnGuard()
    guard.check_call("stronghold__tool_ticket_getTicket", {"id": "t1"})
    guard.note_result("stronghold__tool_ticket_getTicket", {"id": "t1"}, "[1004] DEP_AUTH_REJECTED treasury rejected the service token")
    with pytest.raises(TurnStopped) as stopped:
        guard.check_call("stronghold__tool_ticket_getTicket", {"id": "t1"})
    assert "1004" in str(stopped.value)


def test_a_retryable_failure_does_not_block_a_retry():
    from src.providers.turn_guard import TurnGuard

    guard = TurnGuard()
    guard.note_result("t", {}, "[1002] DEP_UNAVAILABLE treasury unavailable")
    guard.check_call("t", {})  # must not raise
```

If the existing guard already raises on the second identical call for another reason (repeat detection), set the first test's expectation on the message only (`"1004" in str(...)`) and keep the retryable test using a different argument each time; record how the existing rule behaves.

- [x] **Step 4: Run them; see them fail.**

- [x] **Step 5: Implement.** `failures.py`:

```python
"""Turn a dependency failure inside a Stronghold tool into numbered text a model can act on."""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from citadel_auth.failure import from_exception


def guarded(dependency: str):
    def wrap(tool: Callable[..., Awaitable[Any]]):
        @functools.wraps(tool)
        async def run(*args, **kwargs):
            try:
                return await tool(*args, **kwargs)
            except Exception as error:  # the text never carries the exception's own message
                return from_exception(dependency, error).text

        return run

    return wrap
```

Apply `@guarded("treasury")` under each tool's registration decorator in the six tool modules. Do not wrap argument-validation errors the tools already return as plain text. In Legion, add `note_result` using `citadel_auth.failure.parse`: store a key `(name, json.dumps(arguments, sort_keys=True))` when the parsed failure has `retryable is False`; `check_call` raises `TurnStopped(failure.text)` for a stored key. Call `note_result` in the provider loops where a tool result string is available (assumption (e)); if there are several loops (Anthropic, OpenAI, other), call it in the shared place the three already use, or in each one, and say which in the commit body.

- [x] **Step 6: Armory.** Add to `src/errors.py`:

```python
from citadel_auth.failure import from_exception


def dependency_failure(dependency: str, error: BaseException) -> str:
    """Numbered failure text for a tool that could not reach an outside system."""
    return from_exception(dependency, error).text
```

Use it in the Armory capabilities that call an outside service (`web_research` for Tavily, `firecrawl`, `email` for SMTP, `media_downloader` for its source) only at the place that today catches a transport error and calls `report(...)`; the unexpected-exception path keeps `report()`. Capability-specific enums (pdf, media) stay. If a capability already returns its own enum code, leave it. Add one test per capability you touched (patch the client to raise `httpx.ConnectError`, expect text starting `[1002]`). If this touches more than four capabilities, stop at four and list the rest under "Changes found during work".

- [x] **Step 7: Run Stronghold, Armory, Legion suites.** Record counts.

- [x] **Step 8: Commit.** `git commit -m "feat: numbered tool failures in Stronghold and Armory, and Legion stops repeating a non-retryable call"`

---

### Task 5: Treasury discovery

**Files:**
- Create: `apps/treasury/src/discovery.py`, `apps/treasury/tests/test_discovery.py`
- Modify: `apps/treasury/src/run.py` (start the background loop), `apps/treasury/src/api.py` (add `GET /discovery`), `apps/treasury/README.md`, `apps/treasury/src/config.py` if a setting is needed.

**Interfaces:**
- Consumes: `service_catalog.effective(db)`, `register(db, name, url)`, `view(db)`, pins (assumption (f)); the library's `Dependency`/`Probe` style (probing `/health`).
- Produces: `KNOWN: dict[str, str]` mapping each Citadel service name to its compose address (`portcullis` to `http://portcullis:<port>`, and the same for `stronghold`, `legion`, `armory`, `conversation-gateway`, `decision-gateway`; read the real ports from `docker-compose.yml` and `.env.example`, do not guess), `async discover(db, client) -> dict` returning `{"found": [name], "registered": [name], "missed": [name]}`, and `GET /discovery` returning the last result. A name that is **pinned** or already registered with an address is never overwritten. Discovery only fills gaps. A probe that fails records the name under `missed` and changes nothing.

- [x] **Step 1: Write the failing test**

```python
# apps/treasury/tests/test_discovery.py
import asyncio

import httpx

from src import discovery, service_catalog


def make_client(up_hosts):
    def handler(request):
        if request.url.host in up_hosts:
            return httpx.Response(200, json={"status": "ok"})
        raise httpx.ConnectError("down", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_it_registers_reachable_services_and_reports_the_rest(tmp_path):
    db = tmp_path / "catalog.db"
    result = asyncio.run(discovery.discover(db, make_client({"stronghold", "legion"})))
    assert set(result["registered"]) == {"stronghold", "legion"}
    assert "armory" in result["missed"]
    assert set(service_catalog.effective(db)) >= {"stronghold", "legion"}


def test_a_pin_is_never_overwritten(tmp_path):
    db = tmp_path / "catalog.db"
    service_catalog.pin(db, "stronghold", "http://custom-host:9999")
    asyncio.run(discovery.discover(db, make_client({"stronghold"})))
    assert service_catalog.effective(db)["stronghold"] == "http://custom-host:9999"


def test_a_registered_address_is_kept(tmp_path):
    db = tmp_path / "catalog.db"
    service_catalog.register(db, "legion", "http://legion-two:1234")
    result = asyncio.run(discovery.discover(db, make_client({"legion"})))
    assert "legion" not in result["registered"]
    assert service_catalog.effective(db)["legion"] == "http://legion-two:1234"
```

If `register` or `effective` need a different db argument (a path to a settings database, not a standalone file), copy how `apps/treasury/tests` builds one for the catalog tests.

- [x] **Step 2: Run it; see it fail** (`ImportError: cannot import name 'discovery'`).

- [x] **Step 3: Write `discovery.py`.** `discover` reads `service_catalog.effective(db)`, probes each `KNOWN` name that has no entry (probe `GET <url>/health`, 2-second timeout), calls `service_catalog.register(db, name, url)` for each reachable one and returns the three lists. Catch `httpx.HTTPError` per name; never raise. Cache the last result in a module variable for `/discovery`.

- [x] **Step 4: Wire it.** `run.py` starts a background task that calls `discover` every 60 seconds (create it at startup, cancel it at shutdown; a failed round logs one line and the loop continues; start does not wait for it). `GET /discovery` needs the same signed assertion as other Treasury routes and returns the last result (empty lists before the first round).

- [x] **Step 5: Run the Treasury suite.**

- [x] **Step 6: Commit.** `git commit -m "feat(treasury): discover the stack's own services by probing compose names"`

---

### Task 6: Keep `depends_on` as hints, docs and report

**Files:**
- Modify: `scripts/check_compose.py` (add a tenth invariant), `docker-compose.yml` (one comment above the first `depends_on`: "start-order hint only; no service waits for another to be healthy"), `docs/deployment.md` (start rule, `/ready`, failure codes), READMEs of Stronghold, Armory, Legion, Portcullis, Treasury (one short `/ready` and failure-code section each), the roadmap (row 25 link), `libs/citadel_auth/README` if one exists.
- Test: `scripts/check_compose.py --self-test`.

- [x] **Step 1: Check assumption (g)** and read how the nine existing invariants and the self-test are written in `scripts/check_compose.py`.

- [x] **Step 2: Write the failing check.** Add an invariant: no service's `depends_on` is a mapping with a `condition:` (it must be a plain list). Extend the self-test with a broken compose snippet (a `depends_on: {legion: {condition: service_healthy}}`) that the check must reject, and the real file must pass. Run `python scripts/check_compose.py --self-test`; it fails before the invariant exists.

- [x] **Step 3: Implement the invariant**, run the self-test and the real check; both pass.

- [x] **Step 4: Docs.** Each service README gets: `/health` (open), `/ready` (needs the service assertion, always `200`, states `configured`, `reachable`, `unreachable`, `not_configured`), and the failure code table. Say plainly that the Portcullis `/api/admin/ready` route exists and no admin screen shows it yet.

- [x] **Step 5: Sweep.** Final suites for every app and the library, `python scripts/sync_citadel_auth.py --check`, `python scripts/check_compose.py`, `docker compose config --quiet`, `git diff --check`. Record counts under "Final results".

- [x] **Step 6: Commit.** `git commit -m "docs: start rule, /ready and failure codes; check that depends_on stays a hint"`

## Self-review

- **Spec coverage:** error codes 1000 to 1005 with retry flags (Task 1); `/health` everywhere and `/ready` with state, address and last error, never failing (Tasks 2, 3); tool-level failure text and Legion reading `retryable` (Task 4); `depends_on` as hints (Task 6); Treasury discovery without the Docker socket (Task 5). "Admin apps show it": only the Portcullis aggregate route is built (Task 3); the screen is deferred and said so. Per-origin state for outside services is **not** in `/ready` yet: the lists name only stack services and gateways. Outside origins (Bard, Scribe and others) are listed in Plan 19's Tool services page; adding them to `/ready` is a follow-up.
- **Placeholders:** the "find with `git grep`" steps point at code I did not read in full (Stronghold tool modules, Legion provider loops, Armory server wiring, Treasury's test db helper). Each states what to find and what to record.
- **Names:** `Code`, `Failure`, `from_exception`, `parse`, `Dependency`, `Probe`, `guarded`, `note_result`, `discover`, `KNOWN` are used the same way in every task.
- **Risk:** Task 4 changes how many tools report errors. Wrapped tools that returned plain text errors now also return numbered text; Legion treats only `retryable is False` as a stop, so a wrong mapping can at worst stop one repeated call per turn.

## Open questions for the user

1. Should `/ready` also list each outside origin (Bard, Scribe, Reader, Lens, Mimic) from the catalog? Not in this plan.
2. Where should the admin screen for `/ready` live (Portcullis Admin or each admin app)? Not in this plan.

## Manual checklist (pending after the build)

- [ ] Stop Treasury, start the rest. Each service stays up; `/health` answers; `/ready` shows Treasury `unreachable`.
- [ ] With Treasury stopped, ask an agent to list tickets: the tool answers `[1002] DEP_UNAVAILABLE treasury unavailable`, and the agent does not loop on it.
- [ ] Break the service token for one call path: the answer is `[1004]`, and the same call is not repeated in that turn.
- [ ] Call `GET /api/admin/ready` as an administrator and as a member (403).
- [ ] Remove a service's registration in Treasury; within about a minute discovery registers it again, and a pinned name stays as pinned.

## Baseline results

All suites ran from the Plan 25 worktree with the main checkout’s app-specific virtual environment interpreter, using `python -u -m pytest -q -p no:cacheprovider` and a separate `--basetemp` inside the worktree.

| Suite | Baseline |
|---|---|
| citadel_auth | 104 passed |
| Armory | 1,237 passed, 1 skipped, 280 deselected |
| Stronghold | 1,077 passed |
| Legion | 1,489 passed, 6 deselected |
| Treasury | 119 passed, 13 skipped |
| Portcullis | 1,175 passed, 2 failed |

Portcullis reproduced both known failures: `test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`.

Windows sandbox loopback blocked asyncio initialization. Runs outside the sandbox used isolated scratch paths. The library catalog flow collected in the existing environment.

## Changes found during work

### Assumption checks

- **(a)** Armory and Legion had no incoming `/health` route. Portcullis had only `/api/health`, which remains available.
- **(b)** Armory and Legion both use the pinned MCP SDK's `FastMCP.custom_route` on their HTTP apps. Existing service-auth middleware covers `/ready`.
- **(c)** Armory does not declare httpx as a direct runtime dependency. The installed environment and lock resolve httpx 0.28.1 through existing dependencies.
- **(d)** Stronghold registers all six tool groups in `mcp_tools/server.py`. It previously returned structured refusal dictionaries, including generic storage outage text. Stack, proposals, ticket and usage tools use Treasury. Brain and skill tools use local files and keep their existing responses.
- **(e)** The Anthropic and OpenAI loops each call `TurnGuard.check_call` before dispatch and receive the finished tool text in the same loop. The existing guard stops consecutive identical successful calls on the third attempt. Numbered retryable and maybe failures allow a retry under the existing turn budgets. Non-retryable failures stop the next exact call.
- **(f)** Services advertise their addresses through the catalog client. The separate Treasury registration helper binds instances to connections. `service_catalog.effective` prefers pins, and the built-in table covers only four peers. Discovery writes built-in slots atomically and uses the outside catalog for reachable gateways.
- **(g)** The Compose sources use short-form lists. Compose normalizes a list into a map with `condition: service_started`, even with `--no-normalize`. The script checks canonical readiness conditions and source YAML independently.

### Adjustments

- The service policy originally denied some signed peer calls to new routes. Existing caller pairs now allow the exact `/ready` path. Portcullis routes it through service auth and keeps its admin aggregate under `settings.manage`. Its tests attach a real signed header because its Starlette test client uses httpx2.
- Stronghold moves Treasury registration and schema migration off the HTTP startup path. Armory installs built-in MCP handlers immediately and retries extension connections in the background. Legion makes its initial tool and decision gateway checks in the background. A failed decision initialization still keeps that agent out of the registry.
- Gateway address resolution in Legion uses the existing asynchronous settings client, with cached or default addresses when Treasury misses the lookup deadline. Probe requests have bounded deadlines and exclude credentials, query strings and fragments.
- Stronghold's document client wraps network errors and previously discarded HTTP status as structured data. Numbering now uses the original transport cause or status. FastMCP keeps the existing success schemas and returns plain numbered text in MCP error content. Argument and scope refusals still follow their existing paths.
- Legion only interprets numbered text when Armory or Stronghold set MCP's error flag. A successful tool response with matching text does not affect the retry guard.
- Armory Tavily and Firecrawl use urllib and SMTP uses smtplib. The numbering layer handles their actual errors. It preserves the unexpected-error reporting path and marks ambiguous email delivery as maybe retryable. Media download and PDF retain their capability-specific codes. Other outside-service capabilities were outside this plan.
- Treasury discovery uses compose addresses from `docker-compose.yml`. Plan 23 keeps both gateways on Legion's private network, so normal Compose reports those names as missed. Discovery never joins that network or adds a Docker socket mount.
- The Compose validator uses `--no-env-resolution` and disables automatic env-file loading. It uses PyYAML already installed in the authentication library's dev environment to distinguish the source forms in the base file and overlays, including the tagged Zima overlay. No dependency was added. The roadmap row uses the same link already present in the primary worktree's local edit.

## Final results

All suites ran from the worktree using the main checkout's app-specific Python virtual environments. Commands used `python -u -m pytest -q -p no:cacheprovider` with a dedicated scratch `--basetemp`. Targeted runs supplied the test file or `-k` selector.

| Suite | Baseline passed | Final passed | Final skips and failures |
|---|---:|---:|---|
| citadel_auth | 104 | 111 | |
| Armory | 1,237 | 1,244 | 1 skipped, 280 deselected |
| Stronghold | 1,077 | 1,088 | |
| Legion | 1,489 | 1,500 | 6 deselected |
| Treasury | 119 | 125 | 13 skipped |
| Portcullis | 1,175 | 1,178 | Same two baseline failures |

- Task 1: `test_failure.py` failed on the missing module, then passed all 3 tests. Full library suite passed 107.
- Task 2: `test_ready.py` failed on the missing module, then passed all 4 tests. Full library suite passed 111.
- Task 3: Five signed readiness route suites passed. The first full service runs passed 1,238 Armory, 1,079 Stronghold, 1,490 Legion, 120 Treasury and 1,178 Portcullis tests. Portcullis retained the two baseline failures. Startup and cached-address regressions passed after review, and revised suites are reflected in the final counts above.
- Task 4: Stronghold, Armory and Legion checks reproduced missing or unsanitized failure behavior before implementation. Their revised full suites passed with the final counts above. Both Legion provider loops distinguish first-party error results from successful lookalike text.
- Task 5: Discovery tests failed on the missing module and passed all 5 cases after implementation. Treasury passed 125 tests. An in-process ASGI smoke check verified signed `GET /discovery`, rejection without a signature, and shutdown cancellation with mock probes.
- Task 6: The Compose self-test rejected the bad fixture after implementation. The self-test and real checker passed, including validation of list-form syntax in the tagged Zima source. `docker compose config --quiet --no-env-resolution` passed for the base and Zima overlay with environment-file loading disabled. The generated auth copy check and Git whitespace checks passed.

The two Portcullis failures are `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`. Test suites used in-process signed requests and loopback fixture servers. No standalone Citadel service or Compose stack was launched for the manual checklist.
