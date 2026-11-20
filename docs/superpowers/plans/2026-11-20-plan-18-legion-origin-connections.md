# Plan 18: Legion MCP connections by origin id Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An administrator adds an MCP connection in Legion Admin by typing an address; Legion registers the origin in Treasury's outside-service catalog, stores only ids, keeps a parent token with optional per-origin overrides, and fails over to the next origin when one dies.

**Architecture:** Treasury gets a read-only `POST /outside/lookup`. Legion keeps the existing `servers` table and adds an "origins" form of an http entry (`service_id`, `path`, ordered `origins`, with the existing `auth` block as the parent token). A new Legion module `outside_origins.py` registers addresses with Treasury and builds that entry. The MCP registry resolves origin ids through the shared catalog at connect time, tries origins in order, marks a dead one down for 30 seconds, and returns to the primary when it is healthy. Portcullis passes the new fields and hides override tokens. Legion Admin's server form becomes origin-first. The old `url` form stays for Citadel's own services (Armory).

**Tech Stack:** Python 3.12+, FastAPI/Starlette, `mcp` client SDK, httpx, pytest, uv; Vue 3 + TypeScript, vitest, pnpm.

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, section "Outside services and the catalog (Treasury)". Depends on Plans 16 and 17 (merged). Roadmap: `2026-11-20-scope-roadmap.md`.

## Baseline

Branch started from `main` at `431544fc`, after Plans 16 and 17.

| Suite | Command from its app | Result |
|---|---|---|
| Treasury | `uv run pytest -q -p no:cacheprovider` | 117 passed, 13 skipped |
| Legion | `uv run pytest -q -p no:cacheprovider -m "not slow"` | 1,411 passed, 6 deselected |
| Portcullis | `uv run pytest -q -p no:cacheprovider` (background, log file) | 965 passed, 2 failed |
| Legion Admin | `pnpm exec vue-tsc -b` and `pnpm exec vitest run` | Type-check passed, 88 tests passed |

Portcullis baseline failures both reject `http://127.0.0.1:0`:

- `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup`
- `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`

Python tests used local execution outside the sandbox. The sandbox could not lock the configured uv cache, and Python's Windows asyncio loopback socket setup stalled in the fallback.

## Global Constraints

- MCP connections to outside services are entered in Legion; Treasury stores addresses only. Tokens stay in Legion's `settings.db`, write-only in every view (the existing parent-token rule extends to overrides).
- Origin first: the form takes the address, Treasury says whether it is known; a known origin fills in its group name, an unknown one needs a name; a new name makes a group, an existing name adds the origin to it.
- Citadel service names are refused by Treasury; a connection's origins must all belong to one outside service.
- A token goes only to an origin in that connection's own list: the override if set, else the parent.
- Failover only on connection failure or timeout (`ConnectionError`, `TimeoutError`, `httpx.TransportError`, MCP request timeout 408), never on any other error. One call stays on one origin: a failed call is not retried on the next origin; the next call uses it. Return to an earlier origin when it is out of cooldown.
- Treasury down while saving: the save is refused with `[1002] Treasury is unavailable. Nothing was saved.` (HTTP 502); nothing is written.
- Legacy `url` entries keep working unchanged (Armory `main`). The Armory extensions proxy is not touched here (Plan 22 removes it); an admin recreates any extension in Legion with this form.
- Edits still apply at Legion's next start (existing rule); live apply is out of scope.
- UI: read `.agents/skills/ember-frontend-design/SKILL.md` and `ember-design-system` first; reuse existing components and tokens; no new radius values; never add reduced-motion code.
- Python through `uv`, JS through `pnpm`. After any change in `libs/citadel_auth` run `uv run scripts/sync_citadel_auth.py` then `--check` (this plan changes none). Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File structure

| File | Responsibility |
|---|---|
| `apps/treasury/src/outside_catalog.py`, `src/api.py`, tests (modify) | `lookup` and `POST /outside/lookup` |
| `apps/legion/src/tools/mcp_client/config.py` (modify) | `OriginRef`, new `ServerConfig` fields, validation |
| `apps/legion/src/tools/mcp_client/registry.py` (modify) | Origin order, token choice, failover, return to primary |
| `apps/legion/src/tools/mcp_client/sync_wrapper.py`, `mcp_upstream.py` (modify) | Pass `catalog.outside_origin` to the registry |
| `apps/legion/src/runtime/outside_origins.py` (create) | Register addresses in Treasury, build the stored entry, view helper |
| `apps/legion/src/server.py` (modify) | `POST /agents/servers/lookup`, address-based `PUT`, view with resolved addresses |
| `apps/portcullis/src/routes/agent_admin.py`, `src/services/agent_admin.py` (modify) | New fields, hide overrides, lookup route |
| `apps/legion_admin/src/api/AgentsAdminClient.ts`, `src/views/ServersView.vue` and tests (modify) | Origin-first form |
| READMEs of Legion, Portcullis, Legion Admin (modify) | Document |

### Task 1: Treasury lookup route

**Files:**
- Modify: `apps/treasury/src/outside_catalog.py` (append), `apps/treasury/src/api.py` (route after `add_outside_origin`, model near `OutsideBody`)
- Test: `apps/treasury/tests/test_outside_catalog.py`, `apps/treasury/tests/test_api.py`

**Interfaces:**
- Produces: `outside_catalog.lookup(db: Path, address: object) -> dict` returning `{"found": bool, "origin": str, "path": str, "origin_id": str | None, "group": <group row> | None}`; HTTP `POST /outside/lookup` body `{"address": str}` for any signed service; 400 on a bad address. It records nothing.

- [x] **Step 1: Write the failing tests**

```python
# append to apps/treasury/tests/test_outside_catalog.py
def test_lookup_finds_an_origin_with_its_group_and_path_and_records_nothing(db):
    group = oc.add_origin(db, "http://bard:29400", "bard", "legion")
    found = oc.lookup(db, "http://BARD:29400/mcp/")
    assert found["found"] is True and found["path"] == "/mcp"
    assert found["origin_id"] == group["origins"][0]["origin_id"] and found["group"]["name"] == "bard"
    missing = oc.lookup(db, "http://other:1/x")
    assert missing == {"found": False, "origin": "http://other:1", "path": "/x", "origin_id": None, "group": None}
    assert oc.view(db)["groups"][0]["used_by"] == ["legion"] and len(oc.view(db)["groups"]) == 1
    with pytest.raises(oc.OutsideCatalogError):
        oc.lookup(db, "nope")
```

```python
# append to apps/treasury/tests/test_api.py (uses the `registering` fixture)
async def test_any_service_can_look_an_address_up_without_changing_anything(registering):
    caller, _ = registering
    async with caller("legion") as legion, caller("armory") as armory:
        await legion.post("/outside/origins", json={"origin": "http://bard:29400", "name": "bard"})
        found = (await armory.post("/outside/lookup", json={"address": "http://bard:29400/mcp"})).json()
        assert found["found"] is True and found["path"] == "/mcp" and found["group"]["name"] == "bard"
        assert (await armory.post("/outside/lookup", json={"address": "http://x:1"})).json()["found"] is False
        assert (await armory.post("/outside/lookup", json={"address": "bad"})).status_code == 400
        assert (await armory.get("/outside")).json()["groups"][0]["used_by"] == ["legion"]
```

- [x] **Step 2: Run to verify failure.** From `apps/treasury`: `uv run pytest tests/test_outside_catalog.py tests/test_api.py -q -p no:cacheprovider -k lookup`. Expected: FAIL (`AttributeError` / 404).

- [x] **Step 3: Implement.** Append to `outside_catalog.py`:

```python
def lookup(db: Path, address: object) -> dict:
    """Is this address's origin in the catalog? Read only: nothing is recorded."""
    origin, path = split_origin(address)
    groups, origins, users = _state(db)
    for origin_id, row in origins.items():
        if row["origin"] == origin:
            return {"found": True, "origin": origin, "path": path, "origin_id": origin_id,
                    "group": _row(row["service_id"], groups, origins, users)}
    return {"found": False, "origin": origin, "path": path, "origin_id": None, "group": None}
```

In `api.py` add the model and route (after `add_outside_origin`, so `_outside_error` exists):

```python
class LookupBody(BaseModel):
    address: str
```

```python
    @app.post("/outside/lookup")
    async def lookup_outside(body: LookupBody) -> dict[str, Any]:
        """Which group an address belongs to, for a consumer form. Records nothing."""
        if settings_db is None:
            raise HTTPException(409, "this Treasury keeps no settings database")
        try:
            return await asyncio.to_thread(outside_catalog.lookup, settings_db, body.address)
        except outside_catalog.OutsideCatalogError as error:
            raise _outside_error(error) from error
```

- [x] **Step 4: Run to verify pass, then the Treasury suite.** `uv run pytest -q -p no:cacheprovider`. Expected: PASS, no new failures (baseline after Plan 16: 117 passed, 13 skipped).

- [x] **Step 5: Commit** `feat(treasury): look an address up in the outside catalog` (files: the four above).

### Task 2: Legion server config with origins

**Files:**
- Modify: `apps/legion/src/tools/mcp_client/config.py`
- Test: `apps/legion/tests/test_server_settings.py`

**Interfaces:**
- Produces: `OriginRef(origin_id: str, header_value: str | None = None)` (frozen dataclass, `header_value` not in `repr`); `ServerConfig` gains `service_id: str | None = None`, `path: str = "/mcp"`, `origins: tuple[OriginRef, ...] = ()`. A stored http entry is either `url` (legacy) or `service_id` + `origins` (+ optional `path`), never both. `load_servers_config` leaves origin entries alone when applying the `main` URL defaults.

- [x] **Step 1: Write the failing tests** (append to `test_server_settings.py`)

```python
from src.tools.mcp_client.config import OriginRef, validate_server

ORIGIN_ENTRY = {"label": "Bard", "transport": "http", "service_id": "s-bard", "path": "/mcp",
                "auth": {"type": "header", "header_name": "X-Internal-Token", "header_value": "parent"},
                "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}


def test_an_origin_entry_loads_with_ordered_origins_and_no_url():
    config = validate_server("bard", ORIGIN_ENTRY)
    assert config.url is None and config.service_id == "s-bard" and config.path == "/mcp"
    assert config.origins == (OriginRef("o1"), OriginRef("o2", "second"))
    assert "second" not in repr(config.origins[1])


@pytest.mark.parametrize("change", [
    {"url": "http://x:1/mcp"},                 # url and origins together
    {"origins": []},                            # no origin
    {"service_id": ""},                         # no service
    {"origins": [{"origin_id": "o1"}, {"origin_id": "o1"}]},  # listed twice
    {"origins": [{}]},                          # no id
    {"path": "mcp"}, {"path": "/m?x=1"},        # bad path
    {"transport": "stdio", "command": "x"},     # origins need http
])
def test_a_bad_origin_entry_is_refused(change):
    with pytest.raises(ConfigError):
        validate_server("bard", {**ORIGIN_ENTRY, **change})


def test_the_main_defaults_do_not_touch_an_origin_entry(db):
    settings_store.put(db, "servers", "main", {k: v for k, v in ORIGIN_ENTRY.items() if k != "auth"})
    servers = load_servers_config(db, {"main": "http://other/mcp"})
    assert servers["main"].url is None and len(servers["main"].origins) == 2
```

- [x] **Step 2: Run to verify failure.** From `apps/legion`: `uv run pytest tests/test_server_settings.py -q -p no:cacheprovider -k origin`. Expected: FAIL (`ImportError: cannot import name 'OriginRef'`).

- [x] **Step 3: Implement** in `config.py`. Change the import to `from dataclasses import dataclass, field, replace`. Add before `ServerConfig`:

```python
@dataclass(frozen=True)
class OriginRef:
    """One address of an outside service: an id from Treasury's catalog and an optional token of its own."""

    origin_id: str
    header_value: str | None = field(default=None, repr=False)
```

Add three fields at the end of `ServerConfig`:

```python
    service_id: str | None = None
    path: str = "/mcp"
    origins: tuple[OriginRef, ...] = ()
```

Replace the whole `if transport == "http": ... else: ...` block of `_build_server` and its `return` with:

```python
    service_id = raw.get("service_id")
    raw_origins = raw.get("origins")
    origins: tuple[OriginRef, ...] = ()
    path = "/mcp"
    if transport == "http":
        if raw.get("command"):
            raise ConfigError(f"{server_id!r}: transport 'http' must not set 'command'")
        command, args = None, None
        if service_id or raw_origins:
            if raw.get("url"):
                raise ConfigError(f"{server_id!r}: use either 'url' or 'origins', not both")
            if not isinstance(service_id, str) or not service_id:
                raise ConfigError(f"{server_id!r}: 'origins' requires 'service_id'")
            if not isinstance(raw_origins, list) or not raw_origins:
                raise ConfigError(f"{server_id!r}: 'service_id' requires at least one origin")
            origins = tuple(_build_origin(server_id, item) for item in raw_origins)
            if len({origin.origin_id for origin in origins}) != len(origins):
                raise ConfigError(f"{server_id!r}: an origin is listed twice")
            path = raw.get("path", "/mcp")
            if not isinstance(path, str) or not path.startswith("/") or any(char in path for char in "?# \\"):
                raise ConfigError(f"{server_id!r}: 'path' must start with / and hold no query or space")
            url = None
        else:
            url = raw.get("url")
            if not url:
                raise ConfigError(f"{server_id!r}: transport 'http' requires 'url'")
    else:
        command = raw.get("command")
        if not command:
            raise ConfigError(f"{server_id!r}: transport 'stdio' requires 'command'")
        if raw.get("url") or service_id or raw_origins:
            raise ConfigError(f"{server_id!r}: transport 'stdio' must not set 'url' or 'origins'")
        url = None
        args = raw.get("args", [])

    return ServerConfig(
        id=server_id,
        label=label,
        description=description,
        transport=transport,
        url=url,
        command=command,
        args=args,
        auth=_build_auth(server_id, raw.get("auth")),
        service_id=service_id if origins else None,
        path=path,
        origins=origins,
    )
```

Add above `_build_server`:

```python
def _build_origin(server_id: str, raw: Any) -> OriginRef:
    origin_id = raw.get("origin_id") if isinstance(raw, dict) else None
    if not isinstance(origin_id, str) or not origin_id:
        raise ConfigError(f"{server_id!r}: every origin needs an 'origin_id'")
    token = raw.get("header_value")
    return OriginRef(origin_id, token if isinstance(token, str) and token else None)
```

In `load_servers_config` change the two guards: `if main.get("transport") == "http" and not main.get("url") and not main.get("origins"):` and `if config is not None and config.transport == "http" and not config.origins:`.

- [x] **Step 4: Run to verify pass, then the module.** `uv run pytest tests/test_server_settings.py -q -p no:cacheprovider`. Expected: PASS.

- [x] **Step 5: Commit** `feat(legion): MCP server entries can name origins from the outside catalog`.

### Task 3: Registry failover

**Files:**
- Modify: `apps/legion/src/tools/mcp_client/registry.py`, `sync_wrapper.py`, `mcp_upstream.py`
- Test: `apps/legion/tests/test_registry_origins.py` (create)

**Interfaces:**
- Consumes: `OriginRef`, `ServerConfig.origins/path/service_id` (Task 2); `catalog.outside_origin(origin_id) -> str` (Plan 16, `src.runtime.service_catalog.catalog`).
- Produces:
  - `McpClientRegistry(resolve_origin: Callable[[str], str] | None = None)`
  - `is_connection_failure(error: BaseException) -> bool` (module function)
  - `ServerStatus.origin_id: str | None = None` (the origin in use)
  - `ORIGIN_COOLDOWN_SECONDS = 30.0`
  - Behaviour: connect tries origins in order, skipping ones in cooldown unless all are; token = override else parent (header auth only); a failed origin is down for the cooldown; a call that fails with a connection failure marks the active origin down, reconnects (next origin) and re-raises the original error without retrying the call; `list_tools()` returns to an earlier origin once it is out of cooldown.

- [x] **Step 1: Write the failing tests**

```python
# apps/legion/tests/test_registry_origins.py
"""Origins of one outside service: order, token choice, failover and the way back."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from mcp import types
from mcp.shared.exceptions import McpError

from src.tools.mcp_client import registry as registry_module
from src.tools.mcp_client.config import validate_server
from src.tools.mcp_client.registry import McpClientRegistry, is_connection_failure

ENTRY = {"label": "Bard", "transport": "http", "service_id": "s", "path": "/mcp",
         "auth": {"type": "header", "header_name": "X-Internal-Token", "header_value": "parent"},
         "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}
ADDRESS = {"o1": "http://one:1", "o2": "http://two:2"}


class _Listed:
    tools: list = []


class _Session:
    def __init__(self, url, error=None):
        self.url, self.error = url, error

    async def list_tools(self):
        return _Listed()

    async def call_tool(self, name, arguments, read_timeout_seconds, **extra):
        if self.error is not None:
            raise self.error
        return self.url


@pytest.fixture
def world(monkeypatch):
    state = {"down": set(), "opened": [], "clock": 100.0, "call_error": None}

    async def fake_open(stack, config, timeout, extra_headers=None, auth=None):
        if config.url in state["down"]:
            raise ConnectionError("refused")
        token = config.auth.header_value if config.auth else None
        state["opened"].append((config.url, token))
        return _Session(config.url, state["call_error"])

    monkeypatch.setattr(registry_module, "open_session", fake_open)
    registry = McpClientRegistry(resolve_origin=ADDRESS.__getitem__)
    registry._clock = lambda: state["clock"]
    registry._configs = {"bard": validate_server("bard", ENTRY)}
    return registry, state


def test_it_uses_the_first_origin_with_the_parent_token(world):
    registry, state = world
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.status == "connected" and status.origin_id == "o1"
    assert state["opened"] == [("http://one:1/mcp", "parent")]


def test_it_falls_to_the_next_origin_and_uses_its_override_token(world):
    registry, state = world
    state["down"].add("http://one:1/mcp")
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.origin_id == "o2" and state["opened"] == [("http://two:2/mcp", "second")]
    assert len(registry.statuses()) == 1


def test_all_origins_down_is_one_error_status(world):
    registry, state = world
    state["down"] |= {"http://one:1/mcp", "http://two:2/mcp"}
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.status == "error" and "refused" in status.error
    assert [s.status for s in registry.statuses()] == ["error"]


def test_an_unknown_origin_id_is_skipped(world, monkeypatch):
    registry, state = world
    registry._resolve_origin = {"o2": "http://two:2"}.__getitem__  # o1 left the catalog (KeyError)
    status = asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert status.origin_id == "o2"


def test_a_call_that_loses_its_origin_fails_once_and_the_next_call_uses_the_next_origin(world):
    registry, state = world
    asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    registry._sessions["bard"] = _Session("http://one:1/mcp", error=ConnectionError("gone"))
    with pytest.raises(ConnectionError):
        asyncio.run(registry.call_tool("bard__x", {}))
    assert registry._active["bard"] == "o2"
    assert asyncio.run(registry.call_tool("bard__x", {})) == "http://two:2/mcp"


def test_an_answer_that_is_not_a_connection_failure_does_not_fail_over(world):
    registry, state = world
    asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    registry._sessions["bard"] = _Session("http://one:1/mcp", error=ValueError("bad arguments"))
    with pytest.raises(ValueError):
        asyncio.run(registry.call_tool("bard__x", {}))
    assert registry._active["bard"] == "o1"


def test_it_returns_to_the_primary_when_the_cooldown_has_passed(world):
    registry, state = world
    state["down"].add("http://one:1/mcp")
    asyncio.run(registry._connect_one("bard", registry._configs["bard"]))
    assert registry._active["bard"] == "o2"
    state["down"].clear()
    asyncio.run(registry.list_tools())
    assert registry._active["bard"] == "o2"          # still cooling down
    state["clock"] += registry_module.ORIGIN_COOLDOWN_SECONDS + 1
    asyncio.run(registry.list_tools())
    assert registry._active["bard"] == "o1"


@pytest.mark.parametrize("error, expected", [
    (ConnectionError("x"), True), (TimeoutError(), True), (httpx.ConnectError("x"), True),
    (httpx.ReadTimeout("x"), True),
    (McpError(types.ErrorData(code=408, message="timed out")), True),
    (McpError(types.ErrorData(code=-32602, message="bad params")), False),
    (ValueError("x"), False), (RuntimeError("Session terminated"), False),
])
def test_only_a_dead_or_silent_origin_counts_as_a_connection_failure(error, expected):
    assert is_connection_failure(error) is expected
```

- [x] **Step 2: Run to verify failure.** From `apps/legion`: `uv run pytest tests/test_registry_origins.py -q -p no:cacheprovider`. Expected: FAIL (`ImportError: cannot import name 'is_connection_failure'`).

- [x] **Step 3: Implement** in `registry.py`.

Imports: add `import time`, `import httpx`, `from dataclasses import replace` (extend the existing dataclass import), `from mcp.shared.exceptions import McpError`, `from src.citadel_auth import UnknownService`, and change the config import to `from src.tools.mcp_client.config import OriginRef, ServerConfig, load_servers_config`. (`types.REQUEST_TIMEOUT` is 408 in `mcp.types`; if the installed SDK lacks it, compare with `408`.)

Add constants and the classifier after `CALL_TIMEOUT_SECONDS`:

```python
# How long an origin that failed is skipped before it is tried again.
ORIGIN_COOLDOWN_SECONDS = 30.0


def is_connection_failure(error: BaseException) -> bool:
    """A dead or silent origin justifies the next one. Any answer (a refusal, a bad request) never does."""
    if isinstance(error, McpError):
        return error.error.code == 408
    return isinstance(error, (ConnectionError, TimeoutError, httpx.TransportError))
```

Add `origin_id: str | None = None` as the last field of `ServerStatus`.

Change `__init__` to take and store the resolver and the failover state:

```python
    def __init__(self, resolve_origin: Callable[[str], str] | None = None) -> None:
        ...existing lines...
        self._resolve_origin = resolve_origin
        self._active: dict[str, str] = {}
        self._down: dict[tuple[str, str], float] = {}
        self._clock: Callable[[], float] = time.monotonic
```

Replace `_connect_one` with:

```python
    async def _open(self, server_id: str, target: ServerConfig):
        """One connection attempt: (stack, session, tools), or the error text."""
        local_stack = AsyncExitStack()
        try:
            auth = self._auth_by_server.get(server_id)
            session = await open_session(local_stack, target, CONNECT_TIMEOUT_SECONDS, self._extra_headers,
                                         **({"auth": auth} if auth is not None else {}))
            listed = await session.list_tools()
        except Exception as error:  # noqa: BLE001 - one bad server must not block the others
            try:
                await local_stack.aclose()
            except Exception:  # noqa: BLE001 - a messy close must not escape a failed connect
                pass
            return str(error) or type(error).__name__
        return local_stack.pop_all(), session, _namespace(server_id, listed.tools)

    def _origin_order(self, server_id: str, config: ServerConfig) -> list[OriginRef]:
        now = self._clock()
        up = [ref for ref in config.origins if self._down.get((server_id, ref.origin_id), 0.0) <= now]
        return up or list(config.origins)

    def _target_for(self, config: ServerConfig, ref: OriginRef) -> ServerConfig:
        """The config for one origin: its address, and its own token or else the parent's."""
        if self._resolve_origin is None:
            raise KeyError(ref.origin_id)
        auth = config.auth
        if auth is not None and auth.type == "header":
            auth = replace(auth, header_value=ref.header_value or auth.header_value)
        return replace(config, url=self._resolve_origin(ref.origin_id) + config.path, auth=auth)

    async def _connect_one(self, server_id: str, config: ServerConfig) -> ServerStatus:
        self._statuses = [status for status in self._statuses if status.id != server_id]
        attempts: list[tuple[str | None, ServerConfig]]
        if config.origins:
            attempts = []
            for ref in self._origin_order(server_id, config):
                try:
                    attempts.append((ref.origin_id, self._target_for(config, ref)))
                except (KeyError, UnknownService):
                    self._down[(server_id, ref.origin_id)] = self._clock() + ORIGIN_COOLDOWN_SECONDS
        else:
            attempts = [(None, config)]
        failure = "no origin of this service is in the catalog"
        for origin_id, target in attempts:
            opened = await self._open(server_id, target)
            if isinstance(opened, str):
                failure = opened
                if origin_id is not None:
                    self._down[(server_id, origin_id)] = self._clock() + ORIGIN_COOLDOWN_SECONDS
                continue
            stack, session, tools = opened
            self._stacks[server_id] = stack
            self._sessions[server_id] = session
            self._last_known_tools[server_id] = tools
            if origin_id is not None:
                self._active[server_id] = origin_id
            status = ServerStatus(id=server_id, label=config.label, description=config.description,
                                  status="connected", tools=[tool.name for tool in tools], origin_id=origin_id)
            self._statuses.append(status)
            return status
        status = ServerStatus(id=server_id, label=config.label, description=config.description,
                              status="error", error=failure)
        self._statuses.append(status)
        return status
```

(The old per-call status duplicate removal in `_recover_catalog_connections` stays harmless.)

Add after `_recover_catalog_connections`:

```python
    async def _return_to_primary(self) -> None:
        """Go back to an earlier origin of a service once it is out of cooldown."""
        for server_id, config in self._configs.items():
            ids = [ref.origin_id for ref in config.origins]
            active = self._active.get(server_id)
            if len(ids) < 2 or server_id not in self._sessions or active not in ids:
                continue
            now = self._clock()
            if any(self._down.get((server_id, earlier), 0.0) <= now for earlier in ids[: ids.index(active)]):
                await self._reconnect(server_id)

    async def _fail_over(self, server_id: str) -> None:
        active = self._active.get(server_id)
        if active is not None:
            self._down[(server_id, active)] = self._clock() + ORIGIN_COOLDOWN_SECONDS
        await self._reconnect(server_id)
```

In `list_tools`, after `await self._recover_catalog_connections()` add `await self._return_to_primary()`.

In `call_tool` replace the final `try/except` with:

```python
        try:
            return await call(session)
        except RuntimeError as error:
            if str(error) != "Session terminated":
                raise
            await self._reconnect(server_id)
            recovered_session = self._sessions.get(server_id)
            if recovered_session is None:
                raise
            return await call(recovered_session)
        except Exception as error:
            if self._configs[server_id].origins and is_connection_failure(error):
                await self._fail_over(server_id)  # the next call uses the next origin; this one is not retried
            raise
```

(`_reconnect` already pops the session, closes the stack and calls `_connect_one`.)

In `sync_wrapper.py` give `SyncMcpClient.__init__` an optional `resolve_origin` parameter and pass it to `McpClientRegistry(resolve_origin=resolve_origin)`. In `mcp_upstream.py`, where the client is created, pass `resolve_origin=catalog.outside_origin` using `from src.runtime.service_catalog import catalog` (the file already imports from `src.runtime`).

- [x] **Step 4: Run to verify pass, then the Legion suite.** `uv run pytest tests/test_registry_origins.py tests/test_registry.py -q -p no:cacheprovider` then `uv run pytest -q -p no:cacheprovider -m "not slow"`. Expected: PASS; baseline at Plan 16: 1,411 passed, 6 deselected.

- [x] **Step 5: Commit** `feat(legion): MCP origins in order with failover and return to the primary`.

### Task 4: Legion routes and the Treasury registration

**Files:**
- Create: `apps/legion/src/runtime/outside_origins.py`
- Modify: `apps/legion/src/server.py` (the `/agents/servers` routes, line ~486)
- Test: `apps/legion/tests/test_outside_origins.py` (create)

**Interfaces:**
- Consumes: Treasury `POST /outside/lookup`, `POST /outside/origins` (Plan 16 and Task 1); `validate_server` (Task 2).
- Produces:
  - `outside_origins.OutsideError(message, status)`
  - `async outside_origins.lookup(address) -> dict` (Treasury's lookup answer)
  - `async outside_origins.entry_from_addresses(entry: dict, previous: dict | None) -> dict`: the stored entry from a form body that has `addresses: [{address, name?, header_value?}]`
  - `outside_origins.origin_address(origin_id) -> str | None`
  - HTTP: `POST /agents/servers/lookup` body `{"address"}`; `PUT /agents/servers/{id}` accepts `addresses`; `GET /agents/servers` adds `origin` (resolved address or null) to each origin of an entry.

- [x] **Step 1: Write the failing tests**

```python
# apps/legion/tests/test_outside_origins.py
"""Saving an MCP connection by address: Legion registers each origin in Treasury and stores only ids."""

import httpx
import pytest
from starlette.testclient import TestClient

from src import server
from src.citadel_auth import settings_store
from src.runtime import config_files, outside_origins


class FakeTreasury:
    def __init__(self):
        self.origins, self.calls = {}, []  # origin -> (service_id, origin_id)

    @staticmethod
    def _split(address):
        parts = address.split("/", 3)
        return "/".join(parts[:3]), ("/" + parts[3]) if len(parts) > 3 else ""

    async def post(self, path, body):
        self.calls.append((path, body))
        origin, tail = self._split(body.get("address") or body["origin"])
        if path == "/outside/origins" and origin not in self.origins:
            if not body.get("name"):
                return httpx.Response(400, json={"error": "this address is new: give it a name"})
            self.origins[origin] = ("s-" + body["name"], f"o{len(self.origins) + 1}")
        found = self.origins.get(origin)
        group = None if found is None else {"service_id": found[0], "name": found[0][2:], "origins": [], "used_by": ["legion"]}
        if path == "/outside/origins":
            return httpx.Response(200, json=group)
        return httpx.Response(200, json={"found": found is not None, "origin": origin, "path": tail,
                                         "origin_id": found[1] if found else None, "group": group})


@pytest.fixture
def treasury(monkeypatch):
    fake = FakeTreasury()
    monkeypatch.setattr(outside_origins, "_post", fake.post)
    monkeypatch.setattr(outside_origins, "origin_address", lambda origin_id: {"o1": "http://bard:29400"}.get(origin_id))
    return fake


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "settings.db"
    monkeypatch.setattr(config_files, "SETTINGS_DB", path)
    return path


@pytest.fixture
def client(db):
    return TestClient(server.mcp.streamable_http_app())


BODY = {"label": "Bard", "transport": "http",
        "auth": {"type": "header", "header_name": "X-Internal-Token", "header_value": "parent"},
        "addresses": [{"address": "http://bard:29400/mcp", "name": "bard"},
                      {"address": "http://bard2:29400/mcp", "name": "bard", "header_value": "second"}]}


def test_lookup_passes_treasurys_answer_on(client, treasury):
    assert client.post("/agents/servers/lookup", json={"address": "http://x:1/mcp"}).json()["found"] is False
    treasury.origins["http://x:1"] = ("s-x", "o9")
    found = client.post("/agents/servers/lookup", json={"address": "http://x:1/mcp"}).json()
    assert found["found"] is True and found["path"] == "/mcp" and found["group"]["name"] == "x"


def test_saving_addresses_registers_them_and_stores_only_ids_and_tokens(client, treasury, db):
    assert client.put("/agents/servers/bard", json=BODY).status_code == 200
    stored = settings_store.read_all(db, "servers")["bard"]
    assert stored == {"label": "Bard", "transport": "http", "service_id": "s-bard", "path": "/mcp",
                      "auth": BODY["auth"],
                      "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}
    assert "addresses" not in stored and "http://bard" not in str(stored)
    assert [call[0] for call in treasury.calls].count("/outside/origins") == 2


def test_an_override_that_is_not_retyped_is_kept(client, treasury, db):
    client.put("/agents/servers/bard", json=BODY)
    again = {**BODY, "addresses": [{"address": "http://bard:29400/mcp"}, {"address": "http://bard2:29400/mcp"}]}
    assert client.put("/agents/servers/bard", json=again).status_code == 200
    assert settings_store.read_all(db, "servers")["bard"]["origins"][1] == {"origin_id": "o2", "header_value": "second"}


def test_a_new_address_needs_a_name_and_all_addresses_need_one_service(client, treasury, db):
    unnamed = {**BODY, "addresses": [{"address": "http://new:1/mcp"}]}
    refused = client.put("/agents/servers/bard", json=unnamed)
    assert refused.status_code == 400 and "give it a name" in refused.json()["error"]
    mixed = {**BODY, "addresses": [{"address": "http://a:1/mcp", "name": "a"}, {"address": "http://b:1/mcp", "name": "b"}]}
    assert "same outside service" in client.put("/agents/servers/bard", json=mixed).json()["error"]
    assert settings_store.read_all(db, "servers") == {}


def test_treasury_down_refuses_the_save_and_writes_nothing(client, monkeypatch, db):
    async def down(path, body):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(outside_origins, "_post", down)
    refused = client.put("/agents/servers/bard", json=BODY)
    assert refused.status_code == 502 and refused.json()["error"].startswith("[1002]")
    assert settings_store.read_all(db, "servers") == {}


def test_the_list_shows_the_resolved_address_of_each_origin(client, treasury, db):
    client.put("/agents/servers/bard", json=BODY)
    origins = client.get("/agents/servers").json()["servers"]["bard"]["origins"]
    assert [o["origin"] for o in origins] == ["http://bard:29400", None]
```

- [x] **Step 2: Run to verify failure.** `uv run pytest tests/test_outside_origins.py -q -p no:cacheprovider`. Expected: FAIL (`ImportError: cannot import name 'outside_origins'`).

- [x] **Step 3: Implement.** Create `apps/legion/src/runtime/outside_origins.py`:

```python
"""Saving an MCP connection by address: register each origin in Treasury's outside catalog, keep only ids."""

from __future__ import annotations

from typing import Any

import httpx

from src.citadel_auth import UnknownService, service_client
from src.runtime import internal_auth
from src.runtime.service_catalog import catalog


class OutsideError(Exception):
    """A refusal the admin can read; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


async def _post(path: str, body: dict[str, Any]) -> httpx.Response:
    async with service_client(internal_auth.keyring, "treasury", base_url=catalog.url("treasury"), timeout=10.0) as client:
        return await client.post(path, json=body)


def _text(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error") or "Treasury refused the address.")
    except ValueError:
        return "Treasury refused the address."


async def _call(path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await _post(path, body)
    except httpx.HTTPError:
        raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502) from None
    if response.status_code == 200:
        return response.json()
    if response.status_code == 400:
        raise OutsideError(_text(response), 400)
    raise OutsideError(f"[1005] Treasury answered {response.status_code}. Nothing was saved.", 502)


async def lookup(address: str) -> dict[str, Any]:
    return await _call("/outside/lookup", {"address": address})


def origin_address(origin_id: str) -> str | None:
    try:
        return catalog.outside_origin(origin_id)
    except UnknownService:
        return None


async def entry_from_addresses(entry: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """The stored entry for a form body with `addresses`. Each address is registered in Treasury (which also notes that
    Legion uses it); an override token that is not retyped is kept from `previous`."""
    addresses = entry.get("addresses")
    if not isinstance(addresses, list) or not addresses or not all(
            isinstance(item, dict) and isinstance(item.get("address"), str) for item in addresses):
        raise OutsideError("addresses must be a list of {address, name?, header_value?}")
    kept = {item.get("origin_id"): item.get("header_value")
            for item in (previous or {}).get("origins", []) if isinstance(item, dict)}
    service_id: str | None = None
    path = "/mcp"
    origins: list[dict[str, str]] = []
    for item in addresses:
        group = await _call("/outside/origins", {"origin": item["address"], "name": item.get("name")})
        found = await lookup(item["address"])
        if service_id is None:
            service_id = group["service_id"]
            path = found["path"] or "/mcp"
        elif group["service_id"] != service_id:
            raise OutsideError("All addresses of one connection must belong to the same outside service.")
        origin_id = found["origin_id"]
        if any(existing["origin_id"] == origin_id for existing in origins):
            raise OutsideError("An address is listed twice.")
        origin = {"origin_id": origin_id}
        token = item.get("header_value") or kept.get(origin_id)
        if token:
            origin["header_value"] = token
        origins.append(origin)
    stored = {key: value for key, value in entry.items() if key != "addresses"}
    stored.update({"transport": "http", "service_id": service_id, "path": path, "origins": origins})
    return stored
```

In `server.py`, add near the other imports `from src.runtime import outside_origins`, and replace the three `/agents/servers` routes:

```python
@mcp.custom_route("/agents/servers", methods=["GET"])
async def servers_get(_request: Request) -> JSONResponse:
    """The MCP servers Legion connects to, as stored; an origin also shows its current address. Edits apply at the next start."""
    servers = await asyncio.to_thread(settings_store.read_all, config_files.SETTINGS_DB, "servers")
    for entry in servers.values():
        for origin in entry.get("origins", []) if isinstance(entry, dict) else []:
            origin["origin"] = outside_origins.origin_address(origin.get("origin_id", ""))
    return JSONResponse({"servers": servers})


@mcp.custom_route("/agents/servers/lookup", methods=["POST"])
async def servers_lookup(request: Request) -> JSONResponse:
    """Is this address already in Treasury's outside catalog? Body {address}; changes nothing."""
    body = await _json_object(request)
    if body is None or not isinstance(body.get("address"), str):
        return JSONResponse({"error": "body must be {address}"}, status_code=400)
    try:
        return JSONResponse(await outside_origins.lookup(body["address"]))
    except outside_origins.OutsideError as error:
        return JSONResponse({"error": str(error)}, status_code=error.status)


@mcp.custom_route("/agents/servers/{server_id}", methods=["PUT"])
async def servers_put(request: Request) -> JSONResponse:
    """Body: one server entry (transport, url or command or addresses, optional auth). Checked before it is saved."""
    entry = await _json_object(request)
    if entry is None:
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    server_id = request.path_params["server_id"]
    if "addresses" in entry:
        previous = (await asyncio.to_thread(settings_store.read_all, config_files.SETTINGS_DB, "servers")).get(server_id)
        try:
            entry = await outside_origins.entry_from_addresses(entry, previous)
        except outside_origins.OutsideError as error:
            return JSONResponse({"error": str(error)}, status_code=error.status)
    try:
        mcp_config.validate_server(server_id, entry)
    except mcp_config.ConfigError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    await asyncio.to_thread(settings_store.put, config_files.SETTINGS_DB, "servers", server_id, entry)
    return JSONResponse({"saved": server_id, "applies": "next start"})
```

Keep `servers_delete` as it is. The `lookup` route is declared before the `{server_id}` routes.

- [x] **Step 4: Run to verify pass, then the Legion suite.** `uv run pytest tests/test_outside_origins.py tests/test_server_settings.py -q -p no:cacheprovider` then `uv run pytest -q -p no:cacheprovider -m "not slow"`. Expected: PASS.

- [x] **Step 5: Commit** `feat(legion): save MCP connections by address through Treasury's outside catalog`.

### Task 5: Portcullis pass-through

**Files:**
- Modify: `apps/portcullis/src/routes/agent_admin.py` (models near `ServerIn`, a route near `/servers`), `apps/portcullis/src/services/agent_admin.py` (`_without_secret`, new `lookup_origin`)
- Test: `apps/portcullis/tests/test_agent_admin.py`

**Interfaces:**
- Produces: `ServerIn` accepts `path: str | None` and `addresses: list[ServerAddressIn] | None`; `ServerAddressIn {address: str, name: str | None, header_value: str | None}` (forbid extra, `header_value` not in repr); `POST /api/admin/servers/lookup` body `{"address": str}` (needs `agents.manage`) forwards to Legion `POST /agents/servers/lookup`; the list view replaces each origin's `header_value` with `has_override` and drops nothing else.

- [x] **Step 1: Write the failing tests** (append to `test_agent_admin.py`; reuse `servers_agent`, extended for the lookup path)

```python
def test_origin_overrides_are_hidden_and_addresses_pass_through(client, upstream: FakeUpstream) -> None:
    stored = {"bard": {"label": "Bard", "transport": "http", "service_id": "s", "path": "/mcp",
                       "auth": {"type": "header", "header_name": "X-Token", "header_value": "parent"},
                       "origins": [{"origin_id": "o1", "origin": "http://bard:29400"},
                                   {"origin_id": "o2", "origin": None, "header_value": "second"}]}}
    sent = {}

    def handler(request):
        if request.url.path == "/agents/servers/lookup":
            sent["lookup"] = json.loads(request.content)
            return httpx.Response(200, json={"found": False, "origin": "http://x:1", "path": "", "origin_id": None, "group": None})
        if request.method == "PUT":
            sent["put"] = json.loads(request.content)
            return httpx.Response(200, json={"saved": "bard", "applies": "next start"})
        return servers_agent(stored)(request)

    upstream.handler = handler
    as_admin(client)
    listed = client.get("/api/admin/servers")
    assert "second" not in listed.text and "parent" not in listed.text
    origins = listed.json()["servers"]["bard"]["origins"]
    assert origins[0] == {"origin_id": "o1", "origin": "http://bard:29400", "has_override": False}
    assert origins[1] == {"origin_id": "o2", "origin": None, "has_override": True}

    body = {"label": "Bard", "transport": "http", "path": "/mcp",
            "auth": {"type": "header", "header_name": "X-Token"},
            "addresses": [{"address": "http://bard:29400/mcp", "name": "bard", "header_value": "x"}]}
    assert client.put("/api/admin/servers/bard", json=body).status_code == 200
    assert sent["put"]["addresses"][0]["address"] == "http://bard:29400/mcp"
    assert sent["put"]["auth"]["header_value"] == "parent"          # the parent token is kept when not retyped
    assert client.post("/api/admin/servers/lookup", json={"address": "http://x:1"}).json()["found"] is False
    assert sent["lookup"] == {"address": "http://x:1"}
    assert client.post("/api/admin/servers/lookup", json={"address": "x", "extra": 1}).status_code == 422
```

```python
def test_lookup_needs_agents_manage(client_factory, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = servers_agent({})
    assert client_factory().post("/api/admin/servers/lookup", json={"address": "http://x:1"}).status_code == 401
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.post("/api/admin/servers/lookup", json={"address": "http://x:1"}).status_code == 403
    assert upstream.requests == []
```

- [x] **Step 2: Run to verify failure.** From `apps/portcullis`: `uv run pytest tests/test_agent_admin.py -q -p no:cacheprovider -k "origin or lookup"`. Expected: FAIL (422 or 404).

- [x] **Step 3: Implement.** In `routes/agent_admin.py`:

```python
class ServerAddressIn(BaseModel):
    model_config = {"extra": "forbid"}

    address: str = Field(max_length=500)
    name: str | None = Field(default=None, max_length=40)
    header_value: str | None = Field(default=None, max_length=2000, repr=False)


class LookupIn(BaseModel):
    model_config = {"extra": "forbid"}

    address: str = Field(max_length=500)
```

Add to `ServerIn`:

```python
    path: str | None = Field(default=None, max_length=200)
    addresses: list[ServerAddressIn] | None = Field(default=None, max_length=10)
```

Add the route after `list_servers`:

```python
@prompts_router.post("/servers/lookup")
async def lookup_server_address(
    body: LookupIn, account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin),
) -> Any:
    """Is this address in Treasury's outside catalog? Legion asks; nothing is saved."""
    return await _call(admin.lookup_origin(account, body.address))
```

In `services/agent_admin.py` replace `_without_secret` with:

```python
def _without_secret(entry: Any) -> Any:
    """The entry with its token values replaced by `has_value` and `has_override`, so no secret reaches the browser."""
    if not isinstance(entry, dict):
        return entry
    shown = entry
    auth = entry.get("auth")
    if isinstance(auth, dict) and "header_value" in auth:
        kept = {key: value for key, value in auth.items() if key != "header_value"}
        shown = {**shown, "auth": {**kept, "has_value": bool(auth["header_value"])}}
    origins = entry.get("origins")
    if isinstance(origins, list):
        shown = {**shown, "origins": [
            {**{k: v for k, v in item.items() if k != "header_value"}, "has_override": bool(item.get("header_value"))}
            if isinstance(item, dict) else item for item in origins]}
    return shown
```

and add to `AgentAdmin`:

```python
    async def lookup_origin(self, account: Account, address: str) -> dict[str, Any]:
        """Legion's answer about an address: whether Treasury's outside catalog knows it, and its group."""
        return await self._request("POST", "/agents/servers/lookup", account, json={"address": address})
```

`set_server` already re-attaches the stored parent token when the form omits it; leave it unchanged (Legion keeps overrides itself).

- [x] **Step 4: Run to verify pass, then Portcullis.** `uv run pytest tests/test_agent_admin.py -q -p no:cacheprovider` then, in the background writing to a file, `uv run pytest -q -p no:cacheprovider` (about 10 minutes). Expected: PASS; only the two known failures `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`.

- [x] **Step 5: Commit** `feat(portcullis): pass origin-based MCP connections to Legion and hide override tokens`.

### Task 6: Legion Admin origin-first form

**Files:**
- Modify: `apps/legion_admin/src/api/AgentsAdminClient.ts`, `apps/legion_admin/src/views/ServersView.vue`, `apps/legion_admin/src/views/ServersView.test.ts`

**Interfaces:**
- Consumes: Portcullis `POST /api/admin/servers/lookup`, and the list view with `origins[].origin`, `has_override` (Task 5).
- Produces (client): `McpOrigin { origin_id: string; origin?: string | null; has_override?: boolean }`; `McpServer` gains `path?: string; service_id?: string; origins?: McpOrigin[]; addresses?: { address: string; name?: string; header_value?: string }[]`; `OriginLookup { found: boolean; origin: string; path: string; origin_id: string | null; group: { service_id: string; name: string } | null }`; `agentsAdminClient.lookupOrigin(address: string): Promise<OriginLookup>`.

- [x] **Step 1: Write the failing tests** (append inside `describe("ServersView", ...)` in `ServersView.test.ts`; import `PasswordInput` from `../components/PasswordInput.vue`)

```ts
  it("fills the name of a known address and locks it", async () => {
    vi.spyOn(agentsAdminClient, "lookupOrigin").mockResolvedValue(
      { found: true, origin: "http://bard:29400", path: "/mcp", origin_id: "o1", group: { service_id: "s", name: "bard" } });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="address-0"]').setValue("http://bard:29400/mcp");
    await wrapper.get('[data-test="address-0"]').trigger("blur");
    await flushPromises();
    const name = wrapper.get('[data-test="name-0"]');
    expect((name.element as HTMLInputElement).value).toBe("bard");
    expect(name.attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("asks for a name when the address is new and sends addresses with an override token", async () => {
    vi.spyOn(agentsAdminClient, "lookupOrigin").mockResolvedValue(
      { found: false, origin: "http://bard:29400", path: "/mcp", origin_id: null, group: null });
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "bard" });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="id"]').setValue("bard");
    await wrapper.get('[data-test="label"]').setValue("Bard");
    await wrapper.get('[data-test="address-0"]').setValue("http://bard:29400/mcp");
    await wrapper.get('[data-test="address-0"]').trigger("blur");
    await flushPromises();
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined(); // a new address needs a name
    await wrapper.get('[data-test="name-0"]').setValue("bard");
    await wrapper.get('[data-test="add-address"]').trigger("click");
    await wrapper.get('[data-test="address-1"]').setValue("http://bard2:29400/mcp");
    vi.mocked(agentsAdminClient.lookupOrigin).mockResolvedValue(
      { found: true, origin: "http://bard2:29400", path: "/mcp", origin_id: "o2", group: { service_id: "s", name: "bard" } });
    await wrapper.get('[data-test="address-1"]').trigger("blur");
    await flushPromises();
    wrapper.findAllComponents(PasswordInput).at(-1)!.vm.$emit("update:modelValue", "second");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("bard", {
      label: "Bard", description: "", transport: "http",
      addresses: [{ address: "http://bard:29400/mcp", name: "bard" }, { address: "http://bard2:29400/mcp", header_value: "second" }],
    });
    wrapper.unmount();
  });

  it("shows the origins of a catalog connection and keeps unretyped overrides", async () => {
    vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({ bard: { label: "Bard", transport: "http", service_id: "s", path: "/mcp",
      origins: [{ origin_id: "o1", origin: "http://bard:29400", has_override: false }, { origin_id: "o2", origin: "http://bard2:29400", has_override: true }] } });
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "bard" });
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="row-bard"]').text()).toContain("http://bard:29400, http://bard2:29400");
    await wrapper.get('[data-test="edit"]').trigger("click");
    expect((wrapper.get('[data-test="address-1"]').element as HTMLInputElement).value).toBe("http://bard2:29400/mcp");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save.mock.calls[0][1].addresses).toEqual([{ address: "http://bard:29400/mcp" }, { address: "http://bard2:29400/mcp" }]);
    wrapper.unmount();
  });
```

Also update the existing test "adds a server and sends the typed entry": new entries now start in catalog mode, so first run `await wrapper.get('[data-test="mode"]').setValue("direct");` before filling `url`. Record this in the plan's "Changes found during work".

- [x] **Step 2: Run to verify failure.** From `apps/legion_admin`: `pnpm exec vitest run src/views/ServersView.test.ts`. Expected: FAIL (no `lookupOrigin`, no `address-0`).

- [x] **Step 3: Client.** In `AgentsAdminClient.ts` extend `McpServer` and add the new types and method:

```ts
export interface McpOrigin { origin_id: string; origin?: string | null; has_override?: boolean; }

export interface OriginLookup {
  found: boolean;
  origin: string;
  path: string;
  origin_id: string | null;
  group: { service_id: string; name: string } | null;
}
```

Add to `McpServer`:

```ts
  /** Outside-service form: ids from Treasury's catalog, in the order Legion tries them. */
  service_id?: string;
  path?: string;
  origins?: McpOrigin[];
  /** Sent on save only; Legion registers each address and stores ids. A token is write-only. */
  addresses?: { address: string; name?: string; header_value?: string }[];
```

Add to `agentsAdminClient`:

```ts
  /** Does Treasury's outside catalog know this address? Changes nothing. */
  lookupOrigin: (address: string) => apiRequest<OriginLookup>("POST", "/api/admin/servers/lookup", { address }),
```

- [x] **Step 4: Page.** In `ServersView.vue` `<script setup>`: add `import { type OriginLookup } ...` is not needed; add state

```ts
type AddressRow = { address: string; name: string; found: boolean | null; overrideSet: boolean; token: string };
const mode = ref<"catalog" | "direct">("catalog");
const addressRows = ref<AddressRow[]>([{ address: "", name: "", found: null, overrideSet: false, token: "" }]);
```

Replace `valid` with:

```ts
const valid = computed(
  () =>
    /^[a-z0-9][a-z0-9_-]{0,62}$/.test(id.value) &&
    label.value.trim() !== "" &&
    (transport.value === "stdio"
      ? command.value.trim() !== ""
      : mode.value === "direct"
        ? url.value.trim() !== ""
        : addressRows.value.length > 0 &&
          addressRows.value.every((row) => row.address.trim() !== "" && (row.found === true || row.name.trim() !== ""))),
);
```

In `open(serverId)`, after the existing assignments, set the rows:

```ts
  const path = server?.path ?? "/mcp";
  if (server?.origins?.length) {
    mode.value = "catalog";
    addressRows.value = server.origins.map((o) => ({ address: (o.origin ?? "") + path, name: "", found: true, overrideSet: !!o.has_override, token: "" }));
  } else {
    mode.value = server?.url ? "direct" : "catalog";
    addressRows.value = [{ address: "", name: "", found: null, overrideSet: false, token: "" }];
  }
```

Add helpers:

```ts
async function check(index: number) {
  const row = addressRows.value[index];
  if (!row.address.trim()) { row.found = null; return; }
  try {
    const result = await agentsAdminClient.lookupOrigin(row.address.trim());
    row.found = result.found;
    if (result.found && result.group) row.name = result.group.name;
  } catch (err) { error.value = errorMessage(err); }
}
function addAddress() { addressRows.value.push({ address: "", name: "", found: null, overrideSet: false, token: "" }); }
function removeAddress(index: number) { addressRows.value.splice(index, 1); }
```

In `entry()` replace `if (transport.value === "http") body.url = url.value.trim();` with:

```ts
  if (transport.value === "http" && mode.value === "direct") body.url = url.value.trim();
  else if (transport.value === "http") {
    body.addresses = addressRows.value.map((row) => ({
      address: row.address.trim(),
      ...(row.found ? {} : { name: row.name.trim() }),
      ...(row.token ? { header_value: row.token } : {}),
    }));
  }
```

(keep the existing `else { body.command ... }` for stdio attached to this chain.)

In the template replace the `Address` field block (`v-if="transport === 'http'"` with `server-url`) by:

```vue
      <div v-if="transport === 'http'" class="field">
        <label for="server-mode">Connects to</label>
        <select id="server-mode" v-model="mode" :disabled="saving" data-test="mode">
          <option value="catalog">An outside service (saved in Treasury, backups allowed)</option>
          <option value="direct">One address (a Citadel service such as Armory)</option>
        </select>
      </div>
      <div v-if="transport === 'http' && mode === 'direct'" class="field">
        <label for="server-url">Address</label>
        <input id="server-url" v-model="url" type="url" inputmode="url" :disabled="saving" autocomplete="off" spellcheck="false" data-test="url" />
      </div>
      <template v-if="transport === 'http' && mode === 'catalog'">
        <fieldset v-for="(row, index) in addressRows" :key="index" class="field origin">
          <legend>{{ index === 0 ? "Address" : `Backup address ${index}` }}</legend>
          <input v-model="row.address" type="url" inputmode="url" :disabled="saving" autocomplete="off" spellcheck="false"
                 :aria-label="`Address ${index + 1}`" :data-test="`address-${index}`" @blur="check(index)" />
          <input v-model="row.name" :disabled="saving || row.found === true" autocomplete="off"
                 :aria-label="`Service name for address ${index + 1}`" :data-test="`name-${index}`"
                 :placeholder="row.found === false ? 'This address is new: give its service a name' : 'Found in Treasury'" />
          <PasswordInput v-model="row.token" :label="`Token for this address (optional)`" autocomplete="off" :disabled="saving"
                         :placeholder="row.overrideSet ? 'Leave empty to keep its saved token' : 'Empty uses the connection token below'" />
          <button v-if="addressRows.length > 1" type="button" class="chip" :disabled="saving" @click="removeAddress(index)">Remove address</button>
        </fieldset>
        <button type="button" class="chip" :disabled="saving" data-test="add-address" @click="addAddress">Add a backup address</button>
        <p class="help">Legion tries the addresses in this order, switches only when one cannot be reached, and goes back when the first answers again.</p>
      </template>
```

In the table, replace the "Where" cell expression with:

```vue
<td>{{ server.transport !== "http" ? `${server.command} ${(server.args ?? []).join(" ")}` : server.origins?.length ? server.origins.map((o) => o.origin ?? "(removed from Treasury)").join(", ") : server.url }}</td>
```

Add to `<style scoped>`: `.origin { display: grid; gap: 8px; margin: 0; padding: 0; border: 0; } .origin legend { font-size: 0.9em; font-weight: 600; padding: 0; }`. The existing "Token header (optional)" and "Token" fields stay: they are the connection's parent token.

- [x] **Step 5: Run to verify pass, then the app.** `pnpm exec vitest run src/views/ServersView.test.ts` then `pnpm exec vue-tsc -b` then `pnpm exec vitest run`. Expected: PASS everywhere, including `radiusScale.test.ts`. Baseline at Plan 14: Legion Admin 88 tests.

- [x] **Step 6: Commit** `feat(legion_admin): origin-first MCP connection form with backups and per-address tokens`.

### Task 7: Docs and verification

- [x] **Step 1:** Add a short section to `apps/legion/README.md` ("Outside MCP connections": the entry shape with `service_id`, `path`, `origins`, parent token and overrides; failover rules; cooldown 30 s; applies at next start; Armory stays a `url` entry), to `apps/portcullis/README.md` (the lookup route; override tokens hidden) and to `apps/legion_admin/README.md` (the form). Add one line to `apps/treasury/README.md` for `POST /outside/lookup`.
- [x] **Step 2:** Run every affected suite: Treasury, Legion (`-m "not slow"`), Portcullis (background, to a file), Legion Admin (`pnpm exec vue-tsc -b`, `pnpm exec vitest run`). Expected: only the two known Portcullis failures.
- [x] **Step 3:** Add a "Verification" section to this plan with commands, counts and any "Changes found during work".
- [x] **Step 4: Commit** `docs: Legion origin connections and the lookup route`.

## Self-review notes
- **Spec coverage:** origin-first form and fill-in of a known name (Tasks 1, 4, 6); new name creates a group, an existing name adds the origin (Treasury `add_origin`, called by Task 4); Citadel names refused (Treasury, surfaced as a 400 message); consumer-side ordered list with parent token and per-origin override (Tasks 2, 3, 4); a token goes only to an origin in the list (Task 3 `_target_for`); failover only on connection failure or timeout, one call stays on one origin, return to the primary (Task 3); Treasury down refuses the save with `[1002]` (Task 4); `used_by` fills because saving calls `POST /outside/origins` as `legion` (Task 4); secrets write-only (Tasks 4 to 6).
- **Not in this plan:** removing the Armory extensions proxy (Plan 22), live apply without a restart, numeric error codes for tool failures and `/ready` per origin (Plan 25), Stronghold's REST form (Plan 19), Stronghold's own MCP server as a Legion connection (Plan 20a).
- **Assumptions to check at build time:** `mcp.types.REQUEST_TIMEOUT` equals 408; `SyncMcpClient` is constructed in `mcp_upstream.py` where the resolver can be passed; the Legion routes sit on `mcp.custom_route` as shown; the existing `PasswordInput` forwards `update:modelValue` (used by the UI test).
- **Names match across tasks:** `OriginRef`, `ServerConfig.origins/path/service_id`, `McpClientRegistry(resolve_origin=...)`, `is_connection_failure`, `ORIGIN_COOLDOWN_SECONDS`, `ServerStatus.origin_id`, `outside_origins.lookup/entry_from_addresses/origin_address/OutsideError`, `lookup_origin`, `lookupOrigin`, `McpOrigin`, `OriginLookup`.


## Changes found during work

1. **Treasury lookup.** `_state` takes an open connection, so lookup uses the same read transaction as `view`. The API uses the actual application's inline HTTP 400 mapping. The focused test filter must include `look_an_address_up` to select the API case.
2. **Legion config.** The origin form is detected by field presence so an empty origin list cannot silently become a direct entry. Legacy Armory URL overrides still apply.
3. **Registry.** A transport refusal stops the origin sequence. A TCP/DNS failure from opening an origin is normalized into a connection failure, and nested transport exceptions are classified as a group. Each origin transport's AnyIO scopes live on a dedicated owner task so reconnect and shutdown close them in the correct task. Recovery probes keep an active backup available, and running calls stay on the session they started with. An origin can recover when all origins were down at start. Origin connections receive their configured token without Armory service auth or requester metadata. Connection status reports the exception type to avoid exposing upstream error text that may contain tokens.
4. **Legion routes.** Legion redacts parent tokens and overrides before responding and retains omitted token values inside Legion. Addresses share a path, so Legion verifies normalized addresses, group names, paths, and duplicates before registering them. Registration returns the origin ID in its group and the catalog refreshes when a new ID is absent from cache. The fake Treasury now supplies the real registration response shape. A failure prevents the Legion settings write. Treasury registrations are individual catalog operations, so a registration completed before a later Treasury outage can remain in the catalog.
5. **Portcullis.** The lookup uses the existing `agents.manage` route guard. The redactor preserves presence flags already supplied by Legion and still handles older Legion responses. Audit entries identify the connection by ID. The proxy forwards the specified Treasury `[1002]` refusal as HTTP 502 instead of masking it as a Legion outage.
6. **Legion Admin.** The existing direct-address test selects direct mode. The added override test sets the actual password input, which is before the parent field in the DOM. Catalog rows keep stable keys, discard lookup responses for an address that changed, and require a completed lookup before a new address is saved. The backup count matches the API limit.

### Review fixes

- A refused handshake leaves the primary eligible for the next lookup. When the MCP SDK masks an HTTP refusal as a timeout during a call, Legion uses the transport owner's error for the failover decision. A closed session can be opened again on the next lookup or call.
- The catalog transport enforces exact scheme, host, and port before HTTP requests, including redirects. Legacy direct connections keep their transport behavior.
- Legion validates local connection fields before registering addresses. Both Legion and the form require a connection token before an address override can be saved or retained.
- Each Treasury lookup or registration has a 10-second deadline. Catalog saves accept at most ten addresses, and the post-save cache refresh has a 20-second budget. Portcullis allows a 240-second response wait for that save path.

### Build-time assumptions

| Check | Result |
|---|---|
| `mcp.types.REQUEST_TIMEOUT` | Missing from installed SDK. Compare the error code with `408`. |
| `SyncMcpClient` construction | One module-level client in `mcp_upstream.py`. Pass `catalog.outside_origin` there. |
| `mcp.custom_route` | Existing `/agents/servers` endpoints use decorators with explicit `methods`, async `Request` handlers, and `JSONResponse`. |
| `PasswordInput` | Uses Vue's `defineModel<string>`; the native input's `v-model` emits `update:modelValue`. |


## Verification

| Suite | Command from its app | Baseline | Result |
|---|---|---:|---:|
| Treasury | `uv run pytest -q -p no:cacheprovider` | 117 passed, 13 skipped | 119 passed, 13 skipped |
| Legion | `uv run pytest -q -p no:cacheprovider -m "not slow"` | 1,411 passed, 6 deselected | 1,451 passed, 6 deselected |
| Portcullis | `uv run pytest -q -p no:cacheprovider --basetemp <fresh-test-dir>` (background, redirected log) | 965 passed, 2 failed | 968 passed, 2 baseline failures |
| Legion Admin | `pnpm exec vue-tsc -b` and `pnpm exec vitest run` | Type-check passed, 88 passed | Type-check passed, 91 passed across 13 files, including the radius scale test |

The Task 5 full suite and the final reviewed full suite each passed 968 tests and reproduced both baseline port-zero failures. The final reviewed log is `.plan18-test-tmp/portcullis-reviewed.log` in this checkout.

Focused checks passed 15 Legion settings tests in Task 2, 19 Legion registry tests in Task 3,
23 Legion settings and outside-origin tests in Task 4, 19 Portcullis agent-admin tests, and
seven Legion Admin server-form tests. The combined Legion focus run passed 45 tests after
the first review fixes. The final registry-only focus run passed 21 tests after the SDK
refusal fix.

Local smoke tests used actual loopback HTTP processes. Two MCP origins verified primary and
override authentication, a disconnect during a call, no replay, and return to the recovered
primary. A separate check verified that HTTP 401 during the handshake or an established
tool call does not select the backup. Signed Treasury lookup and registration passed over
loopback HTTP, including the unsigned request rejection.

### Limits and remaining checks

- Agent-facing discovery in `mcp_upstream.list_tools` still filters to `main__` and the existing private extensions. Outside connections work in the registry. Ordinary agent turns cannot discover the additional server namespaces through that provider path.
- Preferred-origin probes run on registry tool listing. A caller that only invokes tools can remain on a working backup.
- Catalog registrations are individual operations. A later failed registration or lost Treasury response can leave an earlier Treasury catalog entry in place. In those cases Legion declines to save the connection.
- Portcullis's existing request-validation handler can echo invalid submitted input in a 422 response. The MCP server read routes only report saved token presence.
- Browser layout at desktop and phone widths, the full deployed admin-to-Treasury save path, and live Docker remain unverified.

### Vault notes to update

`Brain/Projects/Citadel.md`, `Brain/Projects/garrison.md` (Legion), `Brain/Projects/legion_admin.md`,
`Brain/Projects/portcullis.md`, `Brain/Projects/treasury.md`, and
`Brain/Notes/Decision - Outside services register once in Treasury's catalog with ids and consumer-side backups.md`.
