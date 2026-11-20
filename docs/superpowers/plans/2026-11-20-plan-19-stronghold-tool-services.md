# Plan 19: Stronghold holds the REST connections to Bard, Scribe and Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speech, dictation and attached audio or documents reach Bard, Scribe and Reader through connections that Stronghold holds (origins from Treasury's outside catalog, a parent token, per-origin overrides, failover), not through Armory's REST façade. Portcullis streams audio and dictation from Stronghold.

**Architecture:** A new Stronghold package `src/tool_services/` holds the records (`store.py`), a Treasury registration helper (`outside.py`), the REST client with failover (`client.py`, same `call` and `post_file` surface as today's `ArmoryConnections`, so the Bard and attachment routes barely change), the dictation relay moved from Armory (`dictation.py`), and routes (`routes.py`): status, audio stream, dictation socket, admin. Portcullis points its two stream relays and its readiness check at Stronghold and proxies a new admin API. Stronghold Admin gets a "Tool services" page. Armory's façade, records and Connections page are left in place and unused; Plan 22 removes them.

**Tech Stack:** Python 3.12+, FastAPI/Starlette, httpx, `websockets`, pytest, uv; Vue 3 + TypeScript, vitest, pnpm.

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md` (Stronghold owns "REST connections to outside tool services (Bard, Scribe, Reader)"; section "Outside services and the catalog"). Reverses the REST half of Plan 14. Depends on Plans 16 to 18b (merged). Roadmap: `2026-11-20-scope-roadmap.md`.

## Global Constraints

- Only Bard, Scribe and Reader are supported here (fixed names `bard`, `scribe`, `reader`). Optional extra REST connections are dropped; extra MCP connections live in Legion.
- Treasury stores addresses only. Tokens live in Stronghold's `settings.db`, write-only in every view. Header `X-Internal-Token` carries the token, as the tool services expect.
- Origin first: the admin types an address; Treasury says whether it is known (Plan 18's `POST /outside/lookup`); a new address needs a service name; Citadel names are refused; all addresses of one connection belong to one outside service. Saving registers each origin with Treasury (so `used_by` shows `stronghold`). Treasury down: the save is refused with `[1002]`; nothing is written.
- A token goes only to an origin in that connection's own list: the override if set, else the parent.
- Failover: a connection that was never made (`httpx.ConnectError`, `httpx.ConnectTimeout`) moves to the next origin in the same call; any other transport error or timeout marks the origin down for 30 s and fails the call with `[1002] <Label> is unreachable. Try again.` (HTTP 502) without trying another origin; an HTTP answer never fails over. A call about an existing file (`file_id`) goes only to the origin that holds it (remembered in memory, 2,000 entries); the next new call uses the next origin.
- Requests keep the existing bounds: 20 MB per file, 1 MB JSON (4 KB for Reader), 120 s per request, 64 MB audio, one dictation stream per account, 150 s of audio, frame, idle and final limits as in Armory's `DictationRelay`. Redact the token from results and error text.
- Error text names Stronghold Admin instead of Armory Admin. Status reasons: `"<Label> is disabled in Stronghold Admin."`, `"Configure <Label> in Stronghold Admin."`, `"Set the <Label> token in Stronghold Admin."`.
- Only Portcullis may call `/admin/tool-services*` on Stronghold; Portcullis checks `extensions.manage` first.
- Do not edit Armory, `libs/citadel_auth` or any copied `src/citadel_auth/` folder. Armory's façade stays and is unused.
- UI: read `.agents/skills/ember-frontend-design/SKILL.md` and `ember-design-system` first; reuse existing components and tokens; no new radius values; never add reduced-motion code.
- Python through `uv`, JS through `pnpm`. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File structure

| File | Responsibility |
|---|---|
| `apps/stronghold/src/tool_services/__init__.py` (create) | Package marker |
| `apps/stronghold/src/tool_services/outside.py` (create) | `OutsideRegistry`: look up and register addresses in Treasury, build `{service_id, origins}` |
| `apps/stronghold/src/tool_services/store.py` (create) | `ToolStore`, `ready_status`, `view`, `token_for` |
| `apps/stronghold/src/tool_services/client.py` (create) | `ToolServices`: REST features with failover, audio stream |
| `apps/stronghold/src/tool_services/dictation.py` (create) | `DictationRelay`, moved from Armory |
| `apps/stronghold/src/tool_services/routes.py` (create) | `/tool-services/status`, `/speech/audio/{file_id}`, websocket `/speech/dictate`, `/admin/tool-services*` |
| `apps/stronghold/src/api.py` (modify) | Build the objects, mount the router, open the websocket path |
| `apps/stronghold/src/attachments/services.py`, `attachments/routes.py`, `bard/routes.py` (modify) | Use `ToolServices` in place of `ArmoryConnections` |
| `apps/stronghold/pyproject.toml` (modify) | `websockets` dependency |
| `apps/stronghold/tests/` (create and modify) | Tests per task |
| `apps/portcullis/src/services/armory_streams.py` (rename to `tool_streams.py`), `routes/bard.py`, `routes/attachments.py`, `routes/connections.py`, `routes/config_issues.py` (modify) | Streams and readiness from Stronghold; admin proxy |
| `apps/stronghold_admin/src/api/ToolServicesClient.ts`, `views/ToolServicesView.vue` and test, router, pages (create and modify) | The admin page |

## Baseline

Baseline at `02d7acf3`, before implementation. Python ran through each app's `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` after `uv run` hit a cache permission error. The successful baseline runs used normal Windows filesystem and loopback access.

| Suite | Result |
|---|---|
| Stronghold | 732 passed |
| Portcullis | 968 passed, 2 failed in 8m 41s |
| Armory (`-m "not slow"`) | 1,559 passed, 1 skipped, 280 deselected |
| Stronghold Admin (`pnpm exec vue-tsc -b`, `pnpm exec vitest run`) | Type check passed, 260 tests passed |

Both known Portcullis failures occur because startup rejects `http://127.0.0.1:0`.

- `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup`
- `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`

### Task 1: Treasury registration helper

**Files:**
- Create: `apps/stronghold/src/tool_services/__init__.py` (empty), `apps/stronghold/src/tool_services/outside.py`
- Test: `apps/stronghold/tests/test_tool_services_outside.py`

**Interfaces:**
- Consumes: Treasury `POST /outside/lookup` and `POST /outside/origins` (Plans 16 and 18).
- Produces: `OutsideError(message, status=400)`; `OutsideRegistry(keyring, catalog)` with `async lookup(address) -> dict` (Treasury's answer), `async entry_from_addresses(addresses: list[dict], previous: dict | None) -> {"service_id": str, "origins": [{"origin_id", "header_value"?}]}` and `origin_address(origin_id) -> str | None`. An address item is `{address, name?, header_value?}`; an override that is not retyped is kept from `previous["origins"]`. This duplicates Legion's `runtime/outside_origins.py` on purpose (two consumers).

- [x] **Step 1: Write the failing tests**

```python
# apps/stronghold/tests/test_tool_services_outside.py
import httpx
import pytest

from src.tool_services.outside import OutsideError, OutsideRegistry


class FakeTreasury:
    def __init__(self):
        self.origins = {}  # origin -> (service_id, origin_id)

    @staticmethod
    def _split(address):
        parts = address.split("/", 3)
        return "/".join(parts[:3]), ("/" + parts[3]) if len(parts) > 3 else ""

    async def post(self, path, body):
        origin, tail = self._split(body.get("address") or body["origin"])
        if path == "/outside/origins" and origin not in self.origins:
            if not body.get("name"):
                return httpx.Response(400, json={"error": "this address is new: give it a name"})
            self.origins[origin] = ("s-" + body["name"], f"o{len(self.origins) + 1}")
        found = self.origins.get(origin)
        group = None if found is None else {"service_id": found[0], "name": found[0][2:], "origins": [], "used_by": ["stronghold"]}
        if path == "/outside/origins":
            return httpx.Response(200, json=group)
        return httpx.Response(200, json={"found": found is not None, "origin": origin, "path": tail,
                                         "origin_id": found[1] if found else None, "group": group})


@pytest.fixture
def registry(monkeypatch):
    fake = FakeTreasury()
    registry = OutsideRegistry(keyring=None, catalog=None)
    monkeypatch.setattr(registry, "_post", fake.post)
    return registry, fake


async def test_addresses_become_ids_and_an_override_is_kept_when_not_retyped(registry):
    reg, _ = registry
    first = await reg.entry_from_addresses(
        [{"address": "http://bard:29400", "name": "bard"}, {"address": "http://bard2:29400", "name": "bard", "header_value": "second"}], None)
    assert first == {"service_id": "s-bard", "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}
    again = await reg.entry_from_addresses([{"address": "http://bard:29400"}, {"address": "http://bard2:29400"}], first)
    assert again["origins"][1] == {"origin_id": "o2", "header_value": "second"}


async def test_a_new_address_needs_a_name_and_one_service(registry):
    reg, _ = registry
    with pytest.raises(OutsideError, match="give it a name"):
        await reg.entry_from_addresses([{"address": "http://new:1"}], None)
    with pytest.raises(OutsideError, match="same outside service"):
        await reg.entry_from_addresses([{"address": "http://a:1", "name": "a"}, {"address": "http://b:1", "name": "b"}], None)
    with pytest.raises(OutsideError, match="listed twice"):
        await reg.entry_from_addresses([{"address": "http://a:1", "name": "a"}, {"address": "http://a:1/x"}], None)


async def test_treasury_down_refuses_with_1002(registry, monkeypatch):
    reg, _ = registry

    async def down(path, body):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(reg, "_post", down)
    with pytest.raises(OutsideError) as error:
        await reg.lookup("http://bard:29400")
    assert str(error.value).startswith("[1002]") and error.value.status == 502
```

- [x] **Step 2: Run to verify failure.** From `apps/stronghold`: `uv run pytest tests/test_tool_services_outside.py -q -p no:cacheprovider`. Expected: FAIL (`ModuleNotFoundError: src.tool_services`).

- [x] **Step 3: Implement** `outside.py`:

```python
"""Register an address in Treasury's outside catalog and keep only ids. Same rules as Legion's runtime/outside_origins.py."""

from __future__ import annotations

from typing import Any

import httpx

from src.citadel_auth import UnknownService, service_client


class OutsideError(Exception):
    """A refusal the admin can read; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class OutsideRegistry:
    def __init__(self, keyring, catalog) -> None:
        self._keyring = keyring
        self._catalog = catalog

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        async with service_client(self._keyring, "treasury", base_url=self._catalog.url("treasury"), timeout=10.0) as client:
            return await client.post(path, json=body)

    async def _call(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._post(path, body)
        except httpx.HTTPError:
            raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502) from None
        if response.status_code == 200:
            return response.json()
        if response.status_code == 400:
            try:
                raise OutsideError(str(response.json().get("error") or "Treasury refused the address."), 400)
            except ValueError:
                raise OutsideError("Treasury refused the address.", 400) from None
        raise OutsideError(f"[1005] Treasury answered {response.status_code}. Nothing was saved.", 502)

    async def lookup(self, address: str) -> dict[str, Any]:
        return await self._call("/outside/lookup", {"address": address})

    def origin_address(self, origin_id: str) -> str | None:
        try:
            return self._catalog.outside_origin(origin_id)
        except UnknownService:
            return None

    async def entry_from_addresses(self, addresses: list[dict[str, Any]], previous: dict[str, Any] | None) -> dict[str, Any]:
        if not addresses or not all(isinstance(item, dict) and isinstance(item.get("address"), str) for item in addresses):
            raise OutsideError("addresses must be a list of {address, name?, header_value?}")
        kept = {item.get("origin_id"): item.get("header_value")
                for item in (previous or {}).get("origins", []) if isinstance(item, dict)}
        service_id: str | None = None
        origins: list[dict[str, str]] = []
        for item in addresses:
            group = await self._call("/outside/origins", {"origin": item["address"], "name": item.get("name")})
            found = await self.lookup(item["address"])
            if service_id is None:
                service_id = group["service_id"]
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
        return {"service_id": service_id, "origins": origins}
```

- [x] **Step 4: Run to verify pass.** `uv run pytest tests/test_tool_services_outside.py -q -p no:cacheprovider`. Expected: PASS (Stronghold's pytest uses asyncio auto mode; if not, add `@pytest.mark.asyncio` as the other Stronghold async tests do).

- [x] **Step 5: Commit** `feat(stronghold): register tool service addresses in Treasury's outside catalog`.

### Task 2: Connection records

**Files:**
- Create: `apps/stronghold/src/tool_services/store.py`
- Test: `apps/stronghold/tests/test_tool_services_store.py`

**Interfaces:**
- Produces: `REQUIRED = {"bard": "Bard", "scribe": "Scribe", "reader": "Reader"}`; `ToolStore(path: Path)` with `get(name) -> dict`, `records() -> dict[str, dict]`, `put(name, record)`, `clear(name)`; a record is `{"enabled": bool, "service_id": str | None, "origins": [{"origin_id", "header_value"?}], "token": str}`; `ready_status(name, record) -> {"ready": bool, "reason": str | None}`; `token_for(record, origin) -> str`; `view(name, record, resolve) -> dict` (no secret: `has_token`, per-origin `has_override`, resolved `origin`); the table is `tool_services` in the settings database file Stronghold already uses (`<data_dir>/settings.db`).

- [x] **Step 1: Write the failing tests**

```python
# apps/stronghold/tests/test_tool_services_store.py
from src.tool_services.store import REQUIRED, ToolStore, ready_status, token_for, view


def test_an_unconfigured_service_is_not_ready_and_says_what_to_do(tmp_path):
    store = ToolStore(tmp_path / "settings.db")
    assert store.get("bard") == {"enabled": True, "service_id": None, "origins": [], "token": ""}
    assert ready_status("bard", store.get("bard")) == {"ready": False, "reason": "Configure Bard in Stronghold Admin."}
    assert set(store.records()) == set(REQUIRED)


def test_ready_needs_an_origin_and_a_token_for_every_origin_and_not_disabled():
    record = {"enabled": True, "service_id": "s", "origins": [{"origin_id": "o1"}], "token": ""}
    assert ready_status("scribe", record)["reason"] == "Set the Scribe token in Stronghold Admin."
    assert ready_status("scribe", {**record, "token": "t"}) == {"ready": True, "reason": None}
    both = {**record, "origins": [{"origin_id": "o1", "header_value": "a"}, {"origin_id": "o2"}]}
    assert ready_status("scribe", both)["ready"] is False            # o2 has no token of its own and there is no parent
    assert ready_status("scribe", {**record, "token": "t", "enabled": False})["reason"] == "Scribe is disabled in Stronghold Admin."


def test_an_override_wins_over_the_parent_token():
    record = {"token": "parent"}
    assert token_for(record, {"origin_id": "o1"}) == "parent"
    assert token_for(record, {"origin_id": "o2", "header_value": "second"}) == "second"


def test_the_view_never_carries_a_token(tmp_path):
    record = {"enabled": True, "service_id": "s", "token": "parent-secret",
              "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "override-secret"}]}
    shown = view("bard", record, {"o1": "http://bard:29400"}.get)
    assert "secret" not in str(shown)
    assert shown["has_token"] is True and shown["label"] == "Bard" and shown["ready"] is True
    assert shown["origins"] == [{"origin_id": "o1", "origin": "http://bard:29400", "has_override": False},
                                {"origin_id": "o2", "origin": None, "has_override": True}]


def test_put_get_and_clear_round_trip(tmp_path):
    store = ToolStore(tmp_path / "settings.db")
    record = {"enabled": False, "service_id": "s", "origins": [{"origin_id": "o1"}], "token": "t"}
    store.put("reader", record)
    assert store.get("reader") == record
    store.clear("reader")
    assert store.get("reader")["origins"] == []
```

- [x] **Step 2: Run to verify failure.** Expected: FAIL (`ModuleNotFoundError: src.tool_services.store`).

- [x] **Step 3: Implement** `store.py`:

```python
"""The Bard, Scribe and Reader connections Stronghold holds: Treasury origin ids, a parent token and per-origin overrides."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.citadel_auth import settings_store

REQUIRED = {"bard": "Bard", "scribe": "Scribe", "reader": "Reader"}
TABLE = "tool_services"


def _empty() -> dict:
    return {"enabled": True, "service_id": None, "origins": [], "token": ""}


class ToolStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, name: str) -> dict:
        return {**_empty(), **settings_store.read_all(self._path, TABLE).get(name, {})}

    def records(self) -> dict[str, dict]:
        saved = settings_store.read_all(self._path, TABLE)
        return {name: {**_empty(), **saved.get(name, {})} for name in REQUIRED}

    def put(self, name: str, record: dict) -> None:
        settings_store.put(self._path, TABLE, name, record)

    def clear(self, name: str) -> None:
        settings_store.delete(self._path, TABLE, name)


def token_for(record: dict, origin: dict) -> str:
    """The origin's own token, else the connection's."""
    return origin.get("header_value") or record["token"]


def ready_status(name: str, record: dict) -> dict:
    label = REQUIRED[name]
    if not record["enabled"]:
        return {"ready": False, "reason": f"{label} is disabled in Stronghold Admin."}
    if not record["origins"]:
        return {"ready": False, "reason": f"Configure {label} in Stronghold Admin."}
    if not all(token_for(record, origin) for origin in record["origins"]):
        return {"ready": False, "reason": f"Set the {label} token in Stronghold Admin."}
    return {"ready": True, "reason": None}


def view(name: str, record: dict, resolve: Callable[[str], str | None]) -> dict:
    """What the admin page may see: no token, only whether one is set."""
    return {
        "name": name, "label": REQUIRED[name], "enabled": record["enabled"], "service_id": record["service_id"],
        "has_token": bool(record["token"]),
        "origins": [{"origin_id": o["origin_id"], "origin": resolve(o["origin_id"]), "has_override": bool(o.get("header_value"))}
                    for o in record["origins"]],
        **ready_status(name, record),
    }
```

- [x] **Step 4: Run to verify pass.** `uv run pytest tests/test_tool_services_store.py -q -p no:cacheprovider`. Expected: PASS.

- [x] **Step 5: Commit** `feat(stronghold): connection records for Bard, Scribe and Reader`.

### Task 3: The REST client with failover

**Files:**
- Create: `apps/stronghold/src/tool_services/client.py`
- Test: `apps/stronghold/tests/test_tool_services_client.py`

**Interfaces:**
- Consumes: `ToolStore`, `ready_status`, `token_for`, `REQUIRED` (Task 2); the library's `current_requester()` (`src.citadel_auth`).
- Produces: `ToolServices(store, client: httpx.AsyncClient, resolve_origin: Callable[[str], str], clock=time.monotonic)` with
  - `async call(method: str, path: str, body: dict | None = None) -> dict`
  - `async post_file(path: str, filename: str, content: bytes) -> dict`
  - `async open_audio(file_id: str, range_header: str | None) -> httpx.Response` (a streaming response the caller must close)
  - feature paths kept from today's callers: `/connections/bard/speak`, `/connections/bard/voices`, `/connections/scribe/transcribe`, `/connections/scribe/transcribe-partial`, `/connections/scribe/files`, `/connections/reader/files`, `/connections/reader/parse`. They are names for features only; the request goes to the tool service's own `/api/...` route.
  - Errors are `fastapi.HTTPException`: 400 and 413 pass the service's message through (token redacted), 502 for everything else.

Feature table (old façade path to tool-service route):

| Feature path | Service | Tool-service route | Method | Body |
|---|---|---|---|---|
| `/connections/bard/speak` | bard | `/api/speak` | POST | json |
| `/connections/bard/voices` | bard | `/api/voices` | GET | none |
| `/connections/scribe/transcribe` | scribe | `/api/transcribe` | POST | file |
| `/connections/scribe/transcribe-partial` | scribe | `/api/transcribe-partial` | POST | file |
| `/connections/scribe/files` | scribe | `/api/files` | POST | file |
| `/connections/reader/files` | reader | `/api/files` | POST | file |
| `/connections/reader/parse` | reader | `/api/parse` | POST | json (`file_id` required) |
| audio | bard | `/api/files/{file_id}` | GET | none |

- [x] **Step 1: Write the failing tests**

```python
# apps/stronghold/tests/test_tool_services_client.py
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from src.tool_services import client as client_module
from src.tool_services.client import ToolServices
from src.tool_services.store import ToolStore

ADDRESS = {"o1": "http://one:1", "o2": "http://two:2"}
FID = "a" * 32


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module, "current_requester",
                        lambda: SimpleNamespace(uid="u-1", username="ana", email="ana@example.com"))
    store = ToolStore(tmp_path / "settings.db")
    store.put("bard", {"enabled": True, "service_id": "s", "token": "parent",
                       "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]})
    state = {"seen": [], "down": set(), "timeout": set(), "clock": 100.0,
             "reply": lambda request: httpx.Response(200, json={"file_id": FID, "duration_s": 1.0, "voice": "v"})}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host in state["down"]:
            raise httpx.ConnectError("refused")
        if host in state["timeout"]:
            raise httpx.ReadTimeout("slow")
        state["seen"].append((host, request.url.path, request.headers.get("x-internal-token")))
        return state["reply"](request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    services = ToolServices(store, http, ADDRESS.__getitem__, clock=lambda: state["clock"])
    return services, state, store


async def test_speak_goes_to_the_first_origin_with_the_parent_token_and_the_requester(world):
    services, state, _ = world
    result = await services.call("POST", "/connections/bard/speak", {"text": "hi", "voice": None})
    assert result["file_id"] == FID
    assert state["seen"] == [("one", "/api/speak", "parent")]


async def test_a_refused_connection_moves_to_the_next_origin_with_its_override(world):
    services, state, _ = world
    state["down"].add("one")
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert state["seen"] == [("two", "/api/speak", "second")]


async def test_a_timeout_fails_the_call_without_trying_another_origin_and_the_next_call_skips_it(world):
    services, state, _ = world
    state["timeout"].add("one")
    with pytest.raises(HTTPException) as error:
        await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert error.value.status_code == 502 and error.value.detail.startswith("[1002]")
    assert state["seen"] == []
    state["timeout"].clear()
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert state["seen"] == [("two", "/api/speak", "second")]     # one is cooling down
    state["clock"] += 31
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert state["seen"][-1][0] == "one"


async def test_a_call_about_a_file_goes_to_the_origin_that_holds_it(world):
    services, state, _ = world
    state["down"].add("one")
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})   # made on "two"
    state["down"].clear()
    state["clock"] += 31
    response = await services.open_audio(FID, None)
    await response.aclose()
    assert state["seen"][-1] == ("two", f"/api/files/{FID}", "second")


async def test_a_not_ready_service_says_what_to_do(world):
    services, state, _ = world
    with pytest.raises(HTTPException) as error:
        await services.call("POST", "/connections/scribe/transcribe", None)
    assert error.value.status_code == 502 and error.value.detail == "Configure Scribe in Stronghold Admin."
    assert state["seen"] == []


@pytest.mark.parametrize("status, expected", [(400, 400), (413, 413), (401, 502), (403, 502), (503, 502)])
async def test_the_services_answer_maps_to_the_callers_status(world, status, expected):
    services, state, _ = world
    state["reply"] = lambda request: httpx.Response(status, json={"message": "no (parent)"})
    with pytest.raises(HTTPException) as error:
        await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert error.value.status_code == expected
    assert "parent" not in error.value.detail or "[redacted]" in error.value.detail
    if status in (401, 403):
        assert "Stronghold Admin" in error.value.detail


async def test_a_file_upload_sends_the_filename_and_bytes(world):
    services, state, store = world
    store.put("scribe", {"enabled": True, "service_id": "s", "token": "t", "origins": [{"origin_id": "o1"}]})
    seen = {}

    def reply(request):
        seen["name"], seen["body"] = request.headers["x-filename"], request.content
        return httpx.Response(200, json={"file_id": FID, "duration_s": 1.0, "expires_at": 9.0})

    state["reply"] = reply
    await services.post_file("/connections/scribe/files", "a.mp3", b"abc")
    assert seen == {"name": "a.mp3", "body": b"abc"}
    with pytest.raises(HTTPException) as error:
        await services.post_file("/connections/scribe/files", "../x", b"abc")
    assert error.value.status_code == 400


async def test_the_token_is_redacted_from_a_result(world):
    services, state, _ = world
    state["reply"] = lambda request: httpx.Response(200, json={"voices": ["v-parent"]})
    assert await services.call("GET", "/connections/bard/voices") == {"voices": ["v-[redacted]"]}
```

- [x] **Step 2: Run to verify failure.** Expected: FAIL (`ModuleNotFoundError: src.tool_services.client`).

- [x] **Step 3: Implement** `client.py`:

```python
"""Bard, Scribe and Reader over REST, from the connections Stronghold holds. Moved from Armory's connection_routes.py."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from src.citadel_auth import UnknownService, current_requester
from src.tool_services.store import REQUIRED, ToolStore, ready_status, token_for

MAX_FILE = 20 * 1024 * 1024
MAX_JSON = 1024 * 1024
READ_SECONDS = 15
REQUEST_SECONDS = 120
COOLDOWN_SECONDS = 30.0
REMEMBERED_FILES = 2000
_FILE_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class Feature:
    service: str
    upstream: str
    method: str = "POST"
    body: str | None = None  # "json" | "file" | None


FEATURES = {
    "/connections/bard/speak": Feature("bard", "/api/speak", "POST", "json"),
    "/connections/bard/voices": Feature("bard", "/api/voices", "GET"),
    "/connections/scribe/transcribe": Feature("scribe", "/api/transcribe", "POST", "file"),
    "/connections/scribe/transcribe-partial": Feature("scribe", "/api/transcribe-partial", "POST", "file"),
    "/connections/scribe/files": Feature("scribe", "/api/files", "POST", "file"),
    "/connections/reader/files": Feature("reader", "/api/files", "POST", "file"),
    "/connections/reader/parse": Feature("reader", "/api/parse", "POST", "json"),
}
AUDIO = Feature("bard", "/api/files/{file_id}", "GET")


def valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_FILE_ID.fullmatch(value))


def _redacted(value, token: str):
    if isinstance(value, str):
        return value.replace(token, "[redacted]") if token else value
    if isinstance(value, dict):
        return {_redacted(key, token): _redacted(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item, token) for item in value]
    return value


class ToolServices:
    def __init__(self, store: ToolStore, client: httpx.AsyncClient, resolve_origin: Callable[[str], str],
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._store, self._client, self._resolve, self._clock = store, client, resolve_origin, clock
        self._down: dict[tuple[str, str], float] = {}
        self._files: OrderedDict[str, str] = OrderedDict()

    def _mark_down(self, name: str, origin_id: str) -> None:
        self._down[(name, origin_id)] = self._clock() + COOLDOWN_SECONDS

    def _remember(self, file_id: object, origin_id: str) -> None:
        if valid_id(file_id):
            self._files[file_id] = origin_id
            self._files.move_to_end(file_id)
            while len(self._files) > REMEMBERED_FILES:
                self._files.popitem(last=False)

    def _candidates(self, name: str, record: dict, file_id: str | None) -> list[dict]:
        if file_id and file_id in self._files:  # the file exists on one origin only
            return [o for o in record["origins"] if o["origin_id"] == self._files[file_id]]
        now = self._clock()
        up = [o for o in record["origins"] if self._down.get((name, o["origin_id"]), 0.0) <= now]
        return up or list(record["origins"])

    async def _send(self, feature: Feature, *, content: bytes | None = None, headers: dict[str, str] | None = None,
                    file_id: str | None = None):
        """Send to the first origin that accepts a connection. Returns (response, origin, token), response still open."""
        name, label = feature.service, REQUIRED[feature.service]
        record = self._store.get(name)
        state = ready_status(name, record)
        if not state["ready"]:
            raise HTTPException(502, state["reason"])
        who = current_requester()
        if who is None or not who.username:
            raise HTTPException(400, "Missing requester identity")
        unreachable = HTTPException(502, f"[1002] {label} is unreachable. Try again.")
        for origin in self._candidates(name, record, file_id):
            try:
                address = self._resolve(origin["origin_id"])
            except (KeyError, UnknownService):
                self._mark_down(name, origin["origin_id"])
                continue
            token = token_for(record, origin)
            sent = {"X-Requester-Username": who.username, "X-Requester-Email": who.email, "X-Requester-Uid": who.uid,
                    "X-Internal-Token": token, "Accept-Encoding": "identity", **(headers or {})}
            request = self._client.build_request(feature.method, address + feature.upstream.format(file_id=file_id or ""),
                                                 headers=sent, content=content, timeout=REQUEST_SECONDS)
            try:
                async with asyncio.timeout(REQUEST_SECONDS):
                    response = await self._client.send(request, stream=True, follow_redirects=False)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                self._mark_down(name, origin["origin_id"])  # never reached the service: the next origin is safe
                continue
            except (httpx.HTTPError, TimeoutError):
                self._mark_down(name, origin["origin_id"])
                raise unreachable from None
            return response, origin, token
        raise unreachable

    async def _refusal(self, name: str, response: httpx.Response, token: str) -> HTTPException:
        label, status = REQUIRED[name], response.status_code
        if status in (401, 403):
            return HTTPException(502, f"{label} refused the token. Check Stronghold Admin.")
        if status in (400, 413) or (name == "reader" and status == 422):
            message = None
            try:
                message = (await _read_json(response)).get("message")
            except (ValueError, httpx.HTTPError):
                pass
            detail = message.replace(token, "[redacted]") if isinstance(message, str) and message and token else None
            return HTTPException(413 if status == 413 else 400, (detail or f"{label} refused the request.")[:500])
        return HTTPException(502, f"{label} is unavailable. Try again.")

    async def _finish(self, feature: Feature, response: httpx.Response, origin: dict, token: str) -> dict:
        try:
            if response.status_code != 200:
                raise await self._refusal(feature.service, response, token)
            try:
                result = await _read_json(response)
            except (ValueError, UnicodeError):
                raise HTTPException(502, f"{REQUIRED[feature.service]} sent an invalid response.") from None
            self._remember(result.get("file_id"), origin["origin_id"])
            return _redacted(result, token)
        finally:
            await response.aclose()

    async def call(self, method: str, path: str, body: dict | None = None) -> dict:
        feature = FEATURES[path]
        content = None
        headers = {}
        file_id = None
        if feature.body == "json":
            content = json.dumps(body or {}).encode()
            if len(content) > (4096 if feature.service == "reader" else MAX_JSON):
                raise HTTPException(413, "Request is too large.")
            headers["Content-Type"] = "application/json"
            if feature.service == "reader":
                file_id = (body or {}).get("file_id")
                if not valid_id(file_id):
                    raise HTTPException(400, "Send an uploaded file ID.")
        response, origin, token = await self._send(feature, content=content, headers=headers, file_id=file_id)
        return await self._finish(feature, response, origin, token)

    async def post_file(self, path: str, filename: str, content: bytes) -> dict:
        feature = FEATURES[path]
        if (not filename or len(filename) > 255 or filename in {".", ".."}
                or any(c in "/\\" or ord(c) < 32 or ord(c) > 126 for c in filename)):
            raise HTTPException(400, "Send a valid filename.")
        if len(content) > MAX_FILE:
            raise HTTPException(413, "Request is too large.")
        response, origin, token = await self._send(
            feature, content=content, headers={"X-Filename": filename, "Content-Type": "application/octet-stream"})
        return await self._finish(feature, response, origin, token)

    async def open_audio(self, file_id: str, range_header: str | None) -> httpx.Response:
        """The audio file as an open stream the caller must close. Only the origin that made it can serve it."""
        if not valid_id(file_id):
            raise HTTPException(404, "Audio file not found.")
        if range_header is not None and len(range_header) > 256:
            raise HTTPException(416, "Invalid audio range.")
        response, _origin, _token = await self._send(AUDIO, file_id=file_id,
                                                      headers={"Range": range_header} if range_header else None)
        return response


async def _read_json(response: httpx.Response) -> dict:
    data = bytearray()
    async with asyncio.timeout(READ_SECONDS * 8):
        async for chunk in response.aiter_bytes(chunk_size=65536):
            if len(data) + len(chunk) > MAX_JSON:
                raise ValueError("Response is too large.")
            data.extend(chunk)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Response is not an object.")
    return value
```

(The bounded audio stream and the `Content-Range` header handling stay in the route, Task 4.)

- [x] **Step 4: Run to verify pass.** `uv run pytest tests/test_tool_services_client.py -q -p no:cacheprovider`. Expected: PASS. If `current_requester` from `src.citadel_auth` has a different return shape, adapt the monkeypatch and the three header lines; the library type is the one Armory's `requester_headers()` used.

- [x] **Step 5: Commit** `feat(stronghold): reach Bard, Scribe and Reader through held connections with failover`.

### Task 4: Routes, dictation relay and wiring

**Files:**
- Create: `apps/stronghold/src/tool_services/dictation.py`, `apps/stronghold/src/tool_services/routes.py`
- Modify: `apps/stronghold/src/api.py`, `apps/stronghold/src/attachments/services.py`, `apps/stronghold/src/attachments/routes.py`, `apps/stronghold/src/bard/routes.py`, `apps/stronghold/pyproject.toml`, `apps/stronghold/tests/conftest.py`, `apps/stronghold/tests/test_bard.py`, `apps/stronghold/tests/test_attachments.py`
- Test: `apps/stronghold/tests/test_tool_services_routes.py` (create)

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces (HTTP, signed service calls; Portcullis is the caller):
  - `GET /tool-services/status` returns `{"bard": {"ready", "reason"}, "scribe": ..., "reader": ...}`
  - `GET /speech/audio/{file_id}` streams audio (200 or 206 with `content-type: audio/mpeg`, and `content-length`, `accept-ranges`, valid `content-range` kept); 404 and 416 for an expired or bad range; 502 with `{"detail": ...}` otherwise
  - WebSocket `/speech/dictate`: PCM frames and `{"type":"stop"}` in; `partial` and `final` events out; one stream per account
  - `GET /admin/tool-services` returns `{"services": [view...]}`; `POST /admin/tool-services/lookup` body `{"address"}`; `PUT /admin/tool-services/{name}` body `{"enabled"?: bool, "token"?: str, "addresses"?: [...]}`; `DELETE /admin/tool-services/{name}`; `POST /admin/tool-services/{name}/test`. The admin routes answer 403 unless the caller is `portcullis`.
- `app.state.connections` is now a `ToolServices`; `app.state.tool_store`, `app.state.outside` hold the store and registry. `create_app(..., tool_http: httpx.AsyncClient | None = None, tool_origins: Callable[[str], str] | None = None)` lets tests inject the HTTP client and the origin resolver (defaults: a plain `httpx.AsyncClient` and `catalog.outside_origin`).

- [x] **Step 1: Dependency.** From `apps/stronghold`: `uv add websockets` (Portcullis already depends on it; keep the same lower bound if `apps/portcullis/pyproject.toml` pins one).

- [x] **Step 2: Move the relay.** Copy `apps/armory/src/services/dictation.py` to `apps/stronghold/src/tool_services/dictation.py` with these edits only:
  1. Docstring: "owned by Stronghold".
  2. The 401/403 reason becomes `"Scribe refused the token. Check Stronghold Admin."`.
  3. `_relay` returns a bool: `True` when the upstream could not be reached (`OSError` or `TimeoutError` before or while connecting), else `False`; `stream` returns that bool (`False` for the "already active" refusal). Concretely: in `_relay` set `unreachable = False` before the `try`; in `except (OSError, TimeoutError, WebSocketException, ValueError, TypeError, AttributeError) as error:` add `unreachable = isinstance(error, (OSError, TimeoutError))`; after the final `try/except` that closes the socket, `return unreachable`. In `stream`, `unreachable = await self._relay(...)` and `return unreachable` after the `finally`.
  Then port Armory's relay tests (the dictation cases in `apps/armory/tests/test_connection_routes.py`) into `apps/stronghold/tests/test_dictation_relay.py` with the new import path, asserting the new reason text and that `stream` returns `True` when the upstream refuses the connection and `False` after a normal stop. Leave Armory's copy and tests alone.

- [x] **Step 3: Write the failing route tests**

```python
# apps/stronghold/tests/test_tool_services_routes.py
"""Status, admin and audio routes of the tool services, through the app with the shared fixtures."""

import httpx
from tests.auth_helpers import identity, service_auth  # the helpers the other route tests use

from src.tool_services.store import ToolStore


def seed(app_state, name="bard", token="parent"):
    ToolStore(app_state.settings.data_dir / "settings.db").put(
        name, {"enabled": True, "service_id": "s", "token": token, "origins": [{"origin_id": "o1"}]})


def test_status_lists_the_three_services_with_reasons(client):
    body = client.get("/tool-services/status").json()
    assert set(body) == {"bard", "scribe", "reader"}
    assert body["bard"] == {"ready": False, "reason": "Configure Bard in Stronghold Admin."}


def test_the_admin_routes_refuse_every_caller_but_portcullis(client, as_service):
    # as_service("legion") sends a signed call from another service; see the fixture note in Step 3
    for method, path in (("get", "/admin/tool-services"), ("delete", "/admin/tool-services/bard")):
        assert getattr(as_service("legion"), method)(path).status_code == 403


def test_the_admin_view_never_shows_a_token(client, as_service):
    seed(client.app.state)
    shown = as_service("portcullis").get("/admin/tool-services")
    assert shown.status_code == 200 and "parent" not in shown.text
    bard = next(s for s in shown.json()["services"] if s["name"] == "bard")
    assert bard["has_token"] is True and bard["ready"] is True


def test_saving_by_address_registers_origins_and_keeps_an_unretyped_token(client, as_service, monkeypatch):
    registered = {}

    async def entry(addresses, previous):
        registered["addresses"], registered["previous"] = addresses, previous
        return {"service_id": "s-bard", "origins": [{"origin_id": "o1"}]}

    monkeypatch.setattr(client.app.state.outside, "entry_from_addresses", entry)
    admin = as_service("portcullis")
    first = admin.put("/admin/tool-services/bard", json={"token": "parent", "addresses": [{"address": "http://bard:29400", "name": "bard"}]})
    assert first.status_code == 200 and first.json()["has_token"] is True
    again = admin.put("/admin/tool-services/bard", json={"enabled": False})
    assert again.json()["enabled"] is False and again.json()["has_token"] is True   # the token was kept
    assert ToolStore(client.app.state.settings.data_dir / "settings.db").get("bard")["token"] == "parent"


def test_a_treasury_refusal_saves_nothing(client, as_service, monkeypatch):
    from src.tool_services.outside import OutsideError

    async def refuse(addresses, previous):
        raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502)

    monkeypatch.setattr(client.app.state.outside, "entry_from_addresses", refuse)
    response = as_service("portcullis").put("/admin/tool-services/bard", json={"addresses": [{"address": "http://x:1", "name": "x"}]})
    assert response.status_code == 502 and response.json()["detail"].startswith("[1002]")
    assert ToolStore(client.app.state.settings.data_dir / "settings.db").get("bard")["origins"] == []


def test_an_unknown_service_name_is_a_404(client, as_service):
    assert as_service("portcullis").put("/admin/tool-services/lens", json={"enabled": True}).status_code == 404
```

Note on fixtures: the `as_service(name)` helper is new and belongs in `apps/stronghold/tests/conftest.py`: it returns a `TestClient` for the same app whose requests carry a signed assertion from the named service (use `tests/auth_helpers.py`'s existing `caller`/`service_auth` helpers the way `test_bard.py` signs as Portcullis; the default `client` fixture signs as Portcullis already, so `as_service("portcullis")` may simply return `client`). Audio: add `test_audio_streams_with_range_and_maps_errors` that seeds Bard, makes the injected `tool_http` answer `206` with `content-range: bytes 0-3/10` and checks the headers; answers `404` and `416` map through; a body larger than 64 MB is cut.

- [x] **Step 4: Run to verify failure.** `uv run pytest tests/test_tool_services_routes.py -q -p no:cacheprovider`. Expected: FAIL (404 on the new routes).

- [x] **Step 5: Implement the routes** in `routes.py`:

```python
"""Tool services: status for Portcullis, the audio and dictation streams, and the admin API behind Portcullis."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from src.citadel_auth import current_caller, current_requester
from src.requester import Requester, current_requester as requester_dependency
from src.tool_services.client import ToolServices, valid_id
from src.tool_services.outside import OutsideError, OutsideRegistry
from src.tool_services.store import REQUIRED, ToolStore, ready_status, view

MAX_AUDIO = 64 * 1024 * 1024
STREAM_SECONDS = 120
_CONTENT_RANGE = re.compile(r"bytes [0-9]+-[0-9]+/(?:[0-9]+|\*)")

router = APIRouter(tags=["tool-services"])


def _services(request: Request) -> ToolServices:
    return request.app.state.connections


def _store(request: Request) -> ToolStore:
    return request.app.state.tool_store


def _outside(request: Request) -> OutsideRegistry:
    return request.app.state.outside


def _admin() -> None:
    caller = current_caller()
    if caller is None or caller.name != "portcullis":
        raise HTTPException(403, "only Portcullis may change tool services")


def _known(name: str) -> str:
    if name not in REQUIRED:
        raise HTTPException(404, "No such tool service.")
    return name


@router.get("/tool-services/status")
async def status(store: ToolStore = Depends(_store)) -> dict:
    return {name: ready_status(name, record) for name, record in store.records().items()}


@router.get("/speech/audio/{file_id}")
async def audio(file_id: str, request: Request, services: ToolServices = Depends(_services),
                _who: Requester = Depends(requester_dependency)):
    if not valid_id(file_id):
        raise HTTPException(404, "Audio file not found.")
    remote = await services.open_audio(file_id, request.headers.get("range"))
    if remote.status_code not in (200, 206):
        await remote.aclose()
        if remote.status_code in (404, 416):
            raise HTTPException(remote.status_code, "The audio expired or is unavailable.")
        raise HTTPException(502, "Bard audio is unavailable. Check Stronghold Admin, Tool services.")
    length = remote.headers.get("content-length")
    if length is not None and (not length.isdecimal() or int(length) > MAX_AUDIO):
        await remote.aclose()
        raise HTTPException(502, "Bard audio exceeds the stream limit.")
    kept = {"content-type": "audio/mpeg"}
    if length is not None:
        kept["content-length"] = length
    if remote.headers.get("accept-ranges") == "bytes":
        kept["accept-ranges"] = "bytes"
    if _CONTENT_RANGE.fullmatch(remote.headers.get("content-range", "")):
        kept["content-range"] = remote.headers["content-range"]
    return StreamingResponse(_audio_chunks(remote), status_code=remote.status_code, headers=kept,
                             background=BackgroundTask(remote.aclose))


async def _audio_chunks(remote: httpx.Response) -> AsyncIterator[bytes]:
    try:
        remaining = MAX_AUDIO
        async with asyncio.timeout(STREAM_SECONDS):
            async for chunk in remote.aiter_bytes(chunk_size=65536):
                if len(chunk) > remaining:
                    raise RuntimeError("Bard audio exceeded the stream limit.")
                remaining -= len(chunk)
                yield chunk
    finally:
        await remote.aclose()


@router.websocket("/speech/dictate")
async def dictate(socket: WebSocket) -> None:
    app = socket.app
    who = current_requester()
    if who is None or not who.username:
        await socket.close(4401)
        return
    services: ToolServices = app.state.connections
    try:
        origin, headers = services.stream_target("scribe")
    except HTTPException as error:
        await socket.accept()
        await socket.send_json({"type": "error", "message": str(error.detail)})
        await socket.close(1011)
        return
    origin_id = headers.pop("_origin_id")  # bookkeeping only: it never goes on the wire
    unreachable = await app.state.dictation.stream(who.uid, origin, headers, socket)
    if unreachable:
        services.mark_down("scribe", origin_id)


@router.get("/admin/tool-services")
async def admin_list(store: ToolStore = Depends(_store), outside: OutsideRegistry = Depends(_outside)) -> dict:
    _admin()
    return {"services": [view(name, record, outside.origin_address) for name, record in store.records().items()]}


@router.post("/admin/tool-services/lookup")
async def admin_lookup(body: dict, outside: OutsideRegistry = Depends(_outside)) -> dict:
    _admin()
    address = body.get("address")
    if not isinstance(address, str):
        raise HTTPException(400, "body must be {address}")
    try:
        return await outside.lookup(address)
    except OutsideError as error:
        raise HTTPException(error.status, str(error)) from None


@router.put("/admin/tool-services/{name}")
async def admin_save(name: str, body: dict, store: ToolStore = Depends(_store),
                     outside: OutsideRegistry = Depends(_outside)) -> dict:
    _admin()
    name = _known(name)
    record = store.get(name)
    if "addresses" in body:
        try:
            entry = await outside.entry_from_addresses(body["addresses"], record)
        except OutsideError as error:
            raise HTTPException(error.status, str(error)) from None
        record = {**record, **entry}
    if isinstance(body.get("enabled"), bool):
        record["enabled"] = body["enabled"]
    if isinstance(body.get("token"), str) and body["token"]:
        record["token"] = body["token"]  # an empty token keeps the saved one
    store.put(name, record)
    return view(name, record, outside.origin_address)


@router.delete("/admin/tool-services/{name}")
async def admin_clear(name: str, store: ToolStore = Depends(_store), outside: OutsideRegistry = Depends(_outside)) -> dict:
    _admin()
    name = _known(name)
    store.clear(name)
    return view(name, store.get(name), outside.origin_address)
```

Also give `ToolServices` two small methods used by `dictate` (add to `client.py` and cover them in `test_tool_services_client.py`):

```python
    def stream_target(self, name: str) -> tuple[str, dict[str, str]]:
        """The first healthy origin and the headers a stream to it needs (the token is never logged)."""
        record = self._store.get(name)
        state = ready_status(name, record)
        if not state["ready"]:
            raise HTTPException(502, state["reason"])
        who = current_requester()
        if who is None or not who.username:
            raise HTTPException(400, "Missing requester identity")
        for origin in self._candidates(name, record, None):
            try:
                address = self._resolve(origin["origin_id"])
            except (KeyError, UnknownService):
                continue
            return address, {"X-Requester-Username": who.username, "X-Requester-Email": who.email,
                             "X-Requester-Uid": who.uid, "X-Internal-Token": token_for(record, origin),
                             "_origin_id": origin["origin_id"]}
        raise HTTPException(502, f"[1002] {REQUIRED[name]} is unreachable. Try again.")

    def mark_down(self, name: str, origin_id: str) -> None:
        self._mark_down(name, origin_id)
```

The `_origin_id` key must not go on the wire: `dictate` pops it before calling the relay (as written above). Add a test that the dictation upstream headers contain no `_origin_id`. Add the test for `/admin/tool-services/{name}/test` as described below, then implement it in `routes.py`:

```python
@router.post("/admin/tool-services/{name}/test")
async def admin_test(name: str, request: Request, store: ToolStore = Depends(_store),
                     outside: OutsideRegistry = Depends(_outside)) -> dict:
    """Per origin: the health route, then one authenticated read that creates nothing."""
    _admin()
    name = _known(name)
    record = store.get(name)
    state = ready_status(name, record)
    if not state["ready"]:
        return {"ok": False, "message": state["reason"], "origins": []}
    http: httpx.AsyncClient = request.app.state.tool_http
    check = {"bard": ("GET", "/api/voices", 200, None), "scribe": ("POST", "/api/transcribe?voice_gate=invalid", 422, "bad_voice_gate"),
             "reader": ("POST", "/api/parse", 422, "invalid_request")}[name]
    results = []
    for origin in record["origins"]:
        address = outside.origin_address(origin["origin_id"])
        token = origin.get("header_value") or record["token"]
        if address is None:
            results.append({"origin_id": origin["origin_id"], "ok": False, "message": "This address left Treasury's catalog."})
            continue
        results.append({"origin_id": origin["origin_id"], **await _probe(http, address, token, check, name == "reader")})
    return {"ok": all(r["ok"] for r in results), "message": "Every address is ready." if all(r["ok"] for r in results) else "Some addresses are not ready.",
            "origins": results}


async def _probe(http: httpx.AsyncClient, address: str, token: str, check, json_body: bool) -> dict:
    method, path, expected, error_code = check
    headers = {"X-Internal-Token": token}
    try:
        async with asyncio.timeout(10):
            health = await http.get(address + "/health", headers=headers, follow_redirects=False)
            if health.status_code in (401, 403):
                return {"ok": False, "message": "The token was refused."}
            if not health.is_success:
                return {"ok": False, "message": f"Health returned HTTP {health.status_code}."}
            who = current_requester()
            headers.update({"X-Requester-Username": who.username, "X-Requester-Email": who.email, "X-Requester-Uid": who.uid})
            answer = await http.request(method, address + path, headers=headers, json={} if json_body else None, follow_redirects=False)
            if answer.status_code in (401, 403):
                return {"ok": False, "message": "The token was refused."}
            if answer.status_code == expected and (not error_code or answer.json().get("error") == error_code):
                return {"ok": True, "message": "Ready."}
            return {"ok": False, "message": f"The authenticated check returned HTTP {answer.status_code}."}
    except (httpx.HTTPError, TimeoutError, ValueError):
        return {"ok": False, "message": "Unreachable."}
```

Test: with `tool_http` answering `/health` 200 and `/api/voices` 200 for Bard, `POST /admin/tool-services/bard/test` returns `ok: true` with one origin result; a 401 on voices returns `ok: false` with "The token was refused."; no token appears in any response.

- [x] **Step 6: Wire it in `api.py`.** In the lifespan block, replace `app.state.connections = ArmoryConnections(armory_client, keyring)` with:

```python
        data_settings = settings.data_dir / "settings.db"
        app.state.tool_store = ToolStore(data_settings)
        app.state.outside = OutsideRegistry(keyring, catalog)
        app.state.tool_http = tool_http or httpx.AsyncClient(timeout=120)
        app.state.connections = ToolServices(app.state.tool_store, app.state.tool_http, tool_origins or catalog.outside_origin)
        app.state.dictation = DictationRelay()
```

Add `tool_http` and `tool_origins` parameters to `create_app`, close `tool_http` at shutdown only when it was created here, add `from src.tool_services...` imports, `app.include_router(tool_services_routes.router)`, and change the middleware line to `app.add_middleware(ServiceAuthMiddleware, keyring=keyring, audience="stronghold", websocket_paths=("/speech/dictate",))`. In `attachments/services.py` delete `ArmoryConnections` (keep `ArmoryUploads`); in `attachments/routes.py` and `bard/routes.py` import `ToolServices` from `src.tool_services.client` and rename the type hints (`get_connections` returns `request.app.state.connections`; no other change). Edit the three connection error messages in `bard/routes.py` docstrings from Armory to "Bard".

- [x] **Step 7: Adapt the fixtures and the old tests.** In `tests/conftest.py` replace the `tools` fixture and `armory_dispatch` so the three tool services are fake HTTP servers at `http://bard.test`, `http://scribe.test`, `http://reader.test`: `tools` still returns `{name: FakeArmory()}` (rename the class to `FakeTool` if you wish), `create_app(..., tool_http=httpx.AsyncClient(transport=MockTransport(by_host)), tool_origins={"bard": "http://bard.test", ...}.__getitem__)`, and the fixture seeds `ToolStore(tmp_path / "data" / "settings.db")` with one origin per service (`origin_id` equal to the service name) and token `t`. Update the assertions in `test_bard.py` and `test_attachments.py` mechanically with the feature table above: `/connections/bard/speak` becomes `/api/speak`, `/connections/bard/voices` `/api/voices`, `/connections/scribe/files` `/api/files` on `scribe.test`, `/connections/scribe/transcribe` `/api/transcribe`, `/connections/scribe/transcribe-partial` `/api/transcribe-partial`, `/connections/reader/files` `/api/files` on `reader.test`; the sent request now carries `x-internal-token: t` and `x-requester-username: ana` headers instead of a signed assertion (`caller(sent, "armory")` checks go; assert the token header and `"parent"`-style redaction cases where the old tests asserted none). The 401, 403 messages now say "Stronghold Admin". Record each changed test in the plan's "Changes found during work".

- [x] **Step 8: Run to verify pass, then the Stronghold suite.** `uv run pytest tests/test_tool_services_routes.py tests/test_dictation_relay.py tests/test_bard.py tests/test_attachments.py -q -p no:cacheprovider` then `uv run pytest -q -p no:cacheprovider`. Expected: PASS; baseline after Plan 14: 730 to 738 passed (record the real baseline first).

- [x] **Step 9: Commit** `feat(stronghold): tool service routes, dictation relay and admin API`.

### Task 5: Portcullis streams, readiness and admin proxy

**Files:**
- Rename: `apps/portcullis/src/services/armory_streams.py` to `tool_streams.py` (class `ToolStreams`)
- Modify: `apps/portcullis/src/routes/bard.py`, `routes/attachments.py`, `routes/connections.py`, `routes/config_issues.py`, and the Portcullis tests that name `ArmoryStreams`, `/connections/bard/audio` or `/connections/scribe/dictate` (`tests/test_dictation_stream.py`, `tests/test_bard.py`, connection and config-issue tests)
- Test: `apps/portcullis/tests/test_tool_services_admin.py` (create)

**Interfaces:**
- Consumes: Stronghold routes of Task 4; `StrongholdForwarder.forward(method, path, account, params=None, json=None)` and `pass_on(request, stronghold, account, path)` (existing).
- Produces: `ToolStreams(client, catalog, identity)` with `open_audio(file_id, account, range_header)` and `dictate(account, browser, on_final)` against Stronghold; `readiness(stronghold, account)` reading `GET /tool-services/status`; Portcullis routes (permission `extensions.manage`): `GET /api/admin/tool-services`, `POST /api/admin/tool-services/lookup`, `PUT` and `DELETE /api/admin/tool-services/{name}`, `POST /api/admin/tool-services/{name}/test`, each passed on to Stronghold's `/admin/tool-services...` with `pass_on`. `GET /api/connection-status` and `/api/config-issues` keep their shapes.

- [x] **Step 1: Write the failing tests.** In `test_tool_services_admin.py`, following `test_agent_admin.py` and `test_admin_treasury.py`: with the Stronghold fake of the existing fixtures recording requests, assert each of the five admin routes reaches the matching `/admin/tool-services...` path with the same method and JSON body; that a member without `extensions.manage` gets 403 and nothing is forwarded; that `GET /api/connection-status` returns `{ready: true}` or the Stronghold reason only when it is one of the three allowed reason texts per service (any other text becomes `"Check Stronghold Admin, Tool services."`); that a Stronghold outage makes every service `ready: false` with that same fallback; and that `/api/config-issues` lists an issue with `file="Stronghold Tool services"` for each not-ready service.

- [x] **Step 2: Run to verify failure.** From `apps/portcullis`: `uv run pytest tests/test_tool_services_admin.py -q -p no:cacheprovider`. Expected: FAIL.

- [x] **Step 3: Implement.**
  1. `git mv src/services/armory_streams.py src/services/tool_streams.py`; rename the class to `ToolStreams`; in `open_audio` use `url = f"{logical_url('stronghold')}/speech/audio/{file_id}"`, `auth=ServiceAuth(self.identity, "stronghold")` and the error text `"Stronghold is unreachable. Try again."`; in `dictate` use `urlsplit(self.catalog.url("stronghold"))`, the path `"/speech/dictate"` and `sign_assertion(self.identity, "stronghold")`; replace the `_SAFE_ERRORS` texts with their Stronghold Admin versions (`"Configure Scribe in Stronghold Admin."`, `"Set the Scribe token in Stronghold Admin."`, `"Scribe is disabled in Stronghold Admin."`, `"Scribe refused the token. Check Stronghold Admin."`, and the unchanged `"Dictation is unavailable. Try again."`).
  2. In `routes/bard.py` and `routes/attachments.py` replace the import and the `ArmoryStreams(...)` construction with `ToolStreams(...)`; change the fallback detail to `"Bard audio is unavailable. Check Stronghold Admin, Tool services."`.
  3. In `routes/connections.py` keep the old Armory admin proxy routes (Plan 22 removes them) and replace `readiness` with:

```python
ALLOWED_REASONS = {f"{label} is disabled in Stronghold Admin." for label in ("Bard", "Scribe", "Reader")} | {
    f"Configure {label} in Stronghold Admin." for label in ("Bard", "Scribe", "Reader")} | {
    f"Set the {label} token in Stronghold Admin." for label in ("Bard", "Scribe", "Reader")}


async def readiness(stronghold: StrongholdForwarder, account: Account) -> dict[str, Readiness]:
    """The three fixed status fields from Stronghold; any other text becomes the generic reason."""
    try:
        forwarded = await stronghold.forward("GET", "/tool-services/status", account)
        payload = json.loads(forwarded.body) if forwarded.status == 200 else {}
    except Exception:  # noqa: BLE001 - an unreachable Stronghold means "not ready", never an error page
        payload = {}
    result = {}
    for name in REQUIRED:
        status = payload.get(name) if isinstance(payload, dict) else None
        if isinstance(status, dict) and status.get("ready") is True:
            result[name] = Readiness(ready=True)
        else:
            reason = status.get("reason") if isinstance(status, dict) else None
            result[name] = Readiness(ready=False, reason=reason if reason in ALLOWED_REASONS else "Check Stronghold Admin, Tool services.")
    return result
```

   `connection_status` and `config_issues.list_config_issues` take `stronghold: StrongholdForwarder = Depends(get_stronghold)` instead of `info`; the config issue uses `file="Stronghold Tool services"`. Add the five admin routes:

```python
@router.get("/admin/tool-services")
async def tool_services(request: Request, account: Account = Depends(manage),
                        stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/admin/tool-services")


@router.post("/admin/tool-services/lookup")
async def tool_services_lookup(request: Request, account: Account = Depends(manage),
                               stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/admin/tool-services/lookup")


@router.api_route("/admin/tool-services/{name}", methods=["PUT", "DELETE"])
async def tool_service(request: Request, name: str = Path(pattern=r"^(bard|scribe|reader)$"),
                       account: Account = Depends(manage), stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/admin/tool-services/{name}")


@router.post("/admin/tool-services/{name}/test")
async def tool_service_test(request: Request, name: str = Path(pattern=r"^(bard|scribe|reader)$"),
                            account: Account = Depends(manage), stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/admin/tool-services/{name}/test")
```

   with the imports `json`, `Request`, `from src.deps import get_stronghold`, `from src.routes.stronghold import pass_on`, `from src.services.stronghold_forwarder import StrongholdForwarder`.
  4. Update the Portcullis tests that name the old module, the Armory stream paths or the old reason texts (`test_dictation_stream.py`: the assertions on `armory` audience and URI become `stronghold`, `/speech/dictate`; `test_bard.py`: the audio path and fallback text; the config-issue and connection-status tests). Record each in "Changes found during work".

- [x] **Step 4: Run to verify pass, then Portcullis.** `uv run pytest tests/test_tool_services_admin.py tests/test_dictation_stream.py tests/test_bard.py -q -p no:cacheprovider`, then in the background writing to a file `uv run pytest -q -p no:cacheprovider` (about 10 minutes). Expected: PASS; only the two known failures `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`.

- [x] **Step 5: Commit** `feat(portcullis): stream speech and dictation from Stronghold and pass the tool service admin API on`.

### Task 6: Stronghold Admin "Tool services" page

**Files:**
- Create: `apps/stronghold_admin/src/api/ToolServicesClient.ts`, `apps/stronghold_admin/src/views/ToolServicesView.vue`, `apps/stronghold_admin/src/views/ToolServicesView.test.ts`
- Modify: `apps/stronghold_admin/src/router/index.ts`, `apps/stronghold_admin/src/router/pages.ts` (and any router or nav test that counts pages)

**Interfaces:**
- Consumes: Portcullis admin routes of Task 5.
- Produces (client `toolServicesClient`): types `ToolOrigin { origin_id: string; origin: string | null; has_override: boolean }`, `ToolService { name: "bard" | "scribe" | "reader"; label: string; enabled: boolean; service_id: string | null; has_token: boolean; origins: ToolOrigin[]; ready: boolean; reason: string | null }`, `OriginLookup { found: boolean; origin: string; path: string; origin_id: string | null; group: { service_id: string; name: string } | null }`, `ToolTestResult { ok: boolean; message: string; origins: { origin_id: string; ok: boolean; message: string }[] }`; methods `list(): Promise<ToolService[]>`, `lookup(address)`, `save(name, body: { enabled?: boolean; token?: string; addresses?: { address: string; name?: string; header_value?: string }[] })`, `clear(name)`, `test(name)`.

- [x] **Step 1: Write the failing page tests** (`ToolServicesView.test.ts`, same style as `legion_admin/src/views/ServersView.test.ts`: `mount(..., { attachTo: document.body })`, `vi.spyOn(toolServicesClient, ...)`, the `HTMLDialogElement` shim in `beforeAll`). Cases: (1) lists the three services with their state and reason and no token anywhere; (2) a known address (lookup `found: true`, group name `bard`) fills the name and locks it; an unknown address asks for a name and keeps Save disabled until one is typed; (3) saving sends `addresses` (a found address sends no name, an unknown one sends its name, a typed override token sends `header_value`) plus `token` only when typed and `enabled`; an unretyped parent token is not sent; (4) the test button shows each origin's result message; (5) a Treasury refusal (`[1002] Treasury is unavailable. Nothing was saved.`) is shown and the draft stays; (6) clearing asks for confirmation first (`ConfirmModal` emits `confirm`), then calls `clear`. Override fields use `PasswordInput`; set them in tests with `wrapper.findAllComponents(PasswordInput)[n].vm.$emit("update:modelValue", "x")`.

- [x] **Step 2: Run to verify failure.** From `apps/stronghold_admin`: `pnpm exec vitest run src/views/ToolServicesView.test.ts`. Expected: FAIL (cannot resolve the view).

- [x] **Step 3: Implement.** Client:

```ts
import { apiRequest } from "./http";

export interface ToolOrigin { origin_id: string; origin: string | null; has_override: boolean; }

export interface ToolService {
  name: "bard" | "scribe" | "reader";
  label: string;
  enabled: boolean;
  service_id: string | null;
  has_token: boolean;
  origins: ToolOrigin[];
  ready: boolean;
  reason: string | null;
}

export interface OriginLookup {
  found: boolean;
  origin: string;
  path: string;
  origin_id: string | null;
  group: { service_id: string; name: string } | null;
}

export interface ToolTestResult { ok: boolean; message: string; origins: { origin_id: string; ok: boolean; message: string }[]; }

export interface ToolSaveBody {
  enabled?: boolean;
  /** Write-only: left out, the saved token stays. */
  token?: string;
  addresses?: { address: string; name?: string; header_value?: string }[];
}

/** portcullis's /api/admin/tool-services (needs extensions.manage), passed on to Stronghold. No token is ever returned. */
export const toolServicesClient = {
  list: async () => (await apiRequest<{ services: ToolService[] }>("GET", "/api/admin/tool-services")).services,
  lookup: (address: string) => apiRequest<OriginLookup>("POST", "/api/admin/tool-services/lookup", { address }),
  save: (name: string, body: ToolSaveBody) => apiRequest<ToolService>("PUT", `/api/admin/tool-services/${encodeURIComponent(name)}`, body),
  clear: (name: string) => apiRequest<ToolService>("DELETE", `/api/admin/tool-services/${encodeURIComponent(name)}`),
  test: (name: string) => apiRequest<ToolTestResult>("POST", `/api/admin/tool-services/${encodeURIComponent(name)}/test`),
};
```

The view `ToolServicesView.vue` renders one card per service (reuse `PageLayout`, `ConfirmModal`, `PasswordInput`, `ToggleSwitch` from this app; the card layout, spacing and tokens follow `UsageSettingsView.vue`). Per card: title and ready state with the reason; an enable switch; the token field (`PasswordInput`, placeholder "Leave empty to keep the saved token" when `has_token`); address rows exactly as in Legion Admin's server form (`address`, `name` locked when found, an optional per-address token, "Add a backup address", "Remove address"), rows prefilled from `origins` (`origin` shown, `found: true`); `Save`, `Test` and `Remove connection` (confirm first). Row state and `check(index)` on blur follow `legion_admin/src/views/ServersView.vue` (`AddressRow`, `valid`, `entry()`), with `entry()` building a `ToolSaveBody`: `addresses` (a found row sends `{address}`, an unknown one `{address, name}`, plus `header_value` when typed), `token` only when typed, `enabled` always. Explain in the page description: "Citadel services call Bard, Scribe and Reader through these addresses. Addresses are saved in Treasury; tokens stay here and are never shown again. Add a backup address to keep working when the first one is down."

Router: add `{ path: "/tool-services", name: "tool-services", component: () => import("../views/ToolServicesView.vue"), meta: { permission: "extensions.manage" } }` and a `STRONGHOLD_PAGES` entry `{ to: "/tool-services", label: "Tool services", icon: ["M4 7h16", "M4 12h16", "M4 17h16", "M8 5v4", "M16 10v4", "M10 15v4"], permission: "extensions.manage" }`.

- [x] **Step 4: Run to verify pass, then the app.** `pnpm exec vitest run src/views/ToolServicesView.test.ts`, `pnpm exec vue-tsc -b`, `pnpm exec vitest run`. Expected: PASS everywhere, including `radiusScale.test.ts` (baseline at Plan 14: Stronghold Admin 260 tests; update any router or nav test that counts pages and record it).

- [x] **Step 5: Commit** `feat(stronghold_admin): Tool services page with origins, backups and per-address tokens`.

### Task 7: Docs and verification

- [x] **Step 1:** Add a "Tool services" section to `apps/stronghold/README.md` (what it holds, the record shape, failover rules, bounds, the routes), `apps/portcullis/README.md` (the five admin routes, streams now from Stronghold, readiness), `apps/stronghold_admin/README.md` (the page), and `docs/deployment.md` (a "Tool services" section: enter Bard, Scribe and Reader in Stronghold Admin, Tool services before the speaker, dictation or attachments work; Armory's Connections page and façade are no longer used for them; tokens are the same per-caller tokens as before). Mention that Armory's REST façade and Connections page remain until Plan 22.
- [x] **Step 2:** Run every affected suite: Stronghold, Portcullis (background, to a file), Stronghold Admin (`pnpm exec vue-tsc -b`, `pnpm exec vitest run`); also run Armory's suite unchanged to show nothing there broke (`uv run pytest -q -p no:cacheprovider -m "not slow"`). Expected: only the two known Portcullis failures.
- [x] **Step 3:** Add a "Baseline" section (before Task 1) and a "Verification" section (after) to this plan with commands, counts and "Changes found during work".
- [x] **Step 4: Commit** `docs: Stronghold tool services, routes and rollout`.

## Self-review notes
- **Spec coverage:** REST connections live in Stronghold with origin-first form, parent token and overrides (Tasks 1, 2, 4, 6); backups with failover that never replays a call and keeps a file on its origin (Task 3); Treasury down refuses the save with `[1002]` (Task 1); `used_by` shows `stronghold` (Task 1 registers); dictation relay moves (Task 4); Portcullis holds no tool tokens and streams from Stronghold (Task 5); required-connection status and config issues come from Stronghold (Task 5); secrets write-only (Tasks 2, 4, 6).
- **Not in this plan:** removing Armory's façade, records, Connections page and the Portcullis `/api/admin/connections*` proxy (Plan 22); MCP side of Bard, Scribe and Reader (an admin creates Legion connections with Plan 18's form; agents see them with Plan 18b); `/ready` per origin and numeric codes beyond the `[1002]` text (Plan 25); live apply is unaffected (REST connections apply at once because Stronghold reads the store per call).
- **Assumptions to check at build time:** `src.citadel_auth.current_requester()` exposes `uid`, `username`, `email` and works inside Stronghold's websocket route once `websocket_paths` opts the path in; `StrongholdForwarder.forward` returns an object with `.status` and `.body`; Stronghold's tests use `asyncio_mode = auto`; Stronghold has a `settings_store`-compatible `settings.db` under `data_dir` (it does: `usage/admin_settings.py`); the Portcullis fixtures for Stronghold calls record requests.
- **Names match across tasks:** `OutsideRegistry`, `OutsideError`, `entry_from_addresses`, `origin_address`, `ToolStore`, `ready_status`, `token_for`, `view`, `ToolServices`, `call`, `post_file`, `open_audio`, `stream_target`, `mark_down`, `DictationRelay`, `ToolStreams`, `readiness`, `toolServicesClient`.

## Changes found during work

- **Task 1.** Treasury's FastAPI errors use `detail`. Read-only lookups validate names, groups and duplicates before registration. The registration result supplies the canonical origin ID. No token or override is sent to Treasury. Transport errors, deadline expiry, and Treasury 5xx responses use `[1002]`. Other refusals use plain text.
- **Task 2.** Reused the existing settings-store API. Production routes and clients run synchronous SQLite operations off the event loop. Views report unconfigured if none of the saved origins still resolve, and retain readiness when a resolvable backup remains configured with credentials.
- **Task 3.** The 2,000-entry in-memory file map is keyed by service, requester, and file ID. An unknown or removed origin returns 404. REST applies one request deadline across headers and JSON. A transport error while reading the body cools down the origin without replaying the call. New calls skip origins during their cooldown.
- **Task 4.** Reused Portcullis's `websockets>=15,<17` constraint. The relay refuses redirects, so a handshake token cannot cross origins. Origin bookkeeping travels separately from the outbound headers. Focused signed tests verified portcullis UID, username and email reach the relay, with no stored token in a transcript. The test client sets `.auth` after construction.
- **Task 4 review fixes.** Invalid admin JSON gets a static 422, so draft tokens cannot appear in validation errors. The HTTP client rejects cookies, including cross-port cookies on the same host. Origins populate the catalog snapshot before a Stronghold save. Save preparation is bounded to 18 seconds to leave time for the SQLite write within Portcullis's 30-second read timeout.
- **Task 4 fixture changes.** Stronghold's tool fixtures now dispatch by Bard, Scribe, and Reader host, validate direct requester/token headers, and send service errors in `message`. Fixture tokens are synthetic and long enough to avoid matching unrelated JSON keys.
- **Task 5.** Portcullis preserves the safe 502 body on the tool-service admin paths, which exposes the Treasury `[1002]` refusal to the page. Readiness accepts only the individual service's three reason strings. Stronghold's existing forwarding fixture records the target, method, body and signed headers.
- **Task 6.** Reused the local page, switch, password and confirmation components. Inputs retain their draft on Treasury failure. No nav test depended on the old page count.
- **Compatibility.** The strict file-origin rule means Bard clips from MCP, previous deployments, or mappings lost after restart or eviction return 404 through the new audio route. The separate Legion MCP origin selection can also miss Scribe and Reader attachment IDs when Stronghold uploads to a backup with separate storage. Static source checks confirmed Bard and Scribe each expose MCP and REST on the same listener. MCP origin routing is outside Plan 19. Treasury registrations are individual operations. An outage during a multi-origin save can leave an earlier address registered in Treasury while Stronghold declines to write the connection.

### Existing test expectations updated

- Stronghold `test_bard.py` updated `test_speak_and_installed_voices_are_asked_from_bard` and `test_speak_maps_bard_failures`. Renamed `test_audio_is_owned_by_armory` to `test_the_old_bard_audio_path_is_absent`, preserving its old-path 404 check.
- Stronghold `test_attachments.py` updated `test_audio_is_forwarded_to_scribe_with_identity`, `test_scribe_rejecting_audio_is_a_400_with_its_message`, `test_scribe_errors_map_to_statuses`, `test_dictation_returns_the_transcript_and_logs_no_words`, `test_a_partial_dictation_leaves_no_log_line`, `test_a_document_is_forwarded_to_reader_with_identity`, and `test_reader_rejection_is_a_400_and_outage_is_a_502`.
- Portcullis `test_bard.py` renamed `test_audio_streams_from_armory_with_identity_and_range` to `test_audio_streams_from_stronghold_with_identity_and_range` and updated `test_a_refusal_behind_stronghold_is_not_shown_as_a_browser_auth_error`.
- Portcullis `test_dictation_stream.py::test_stream_proxies_pcm_stop_transcripts_and_identity` expects `/speech/dictate` and the Stronghold assertion audience.
- Portcullis `test_config_issues.py::test_missing_required_connection_is_reported` uses the Stronghold upstream fixture and verifies the new source and reason.

### Build-time assumptions

| Assumption | Result |
|---|---|
| `src.citadel_auth.current_requester()` exposes `uid`, `username`, and `email` in opted-in WebSocket routes | Confirmed by a signed `/speech/dictate` request. The outbound Scribe handshake carried all three values. |
| `StrongholdForwarder.forward` returns `.status` and `.body` | Confirmed in `ForwardedResponse` and exercised by the Portcullis readiness tests. |
| Stronghold uses pytest asyncio auto mode | Confirmed by `asyncio_mode = "auto"` in `pyproject.toml` and unmarked async tests. |
| Stronghold has a settings-store-compatible `data_dir/settings.db` | Confirmed at config load and usage settings routes. Tool records round-trip in their own table in the same file. |
| Portcullis fixtures record Stronghold requests | Confirmed in `FakeUpstream.requests`. Admin proxy tests inspect method, path, body, requester and assertion audience. |

## Verification

| Task | Focused command from the app | Result |
|---|---|---|
| 1 | `.venv/Scripts/python.exe -m pytest tests/test_tool_services_outside.py -q -p no:cacheprovider` | 3 passed |
| 2 | `.venv/Scripts/python.exe -m pytest tests/test_tool_services_store.py -q -p no:cacheprovider` | 5 passed |
| 3 | `.venv/Scripts/python.exe -m pytest tests/test_tool_services_client.py -q -p no:cacheprovider` | 15 passed |
| 4 | `uv run pytest tests/test_tool_services_routes.py tests/test_dictation_relay.py tests/test_tool_services_client.py tests/test_bard.py tests/test_attachments.py -q -p no:cacheprovider` | 80 before review, 84 after review, 88 with the Task 7 regression checks |
| 5 | `uv run pytest tests/test_tool_services_admin.py tests/test_dictation_stream.py tests/test_bard.py tests/test_config_issues.py -q -p no:cacheprovider` | 44 passed |
| 6 | `pnpm exec vitest run src/views/ToolServicesView.test.ts` | 7 passed |

| Task 7 full suite | Command from the app | Baseline | Reviewed result |
|---|---|---|---|
| Stronghold | `uv run pytest -q -p no:cacheprovider` | 732 passed | 781 passed (+49) |
| Portcullis | `uv run pytest -q -p no:cacheprovider` (background, logged) | 968 passed, 2 failed | 979 passed (+11), same 2 baseline failures in 8m 39s |
| Armory | `uv run --locked pytest -q -p no:cacheprovider -m "not slow"` | 1,559 passed, 1 skipped, 280 deselected | 1,559 passed, 1 skipped, 280 deselected |
| Stronghold Admin | `pnpm exec vue-tsc -b` and `pnpm exec vitest run` | Type-check passed, 260 tests passed | Type-check passed, 267 tests passed (+7), including `radiusScale.test.ts` |

The Task 5 Portcullis full run passed 979 tests and reproduced both baseline port-0 startup failures. Its log is `apps/portcullis/.venv/plan19-task5-pytest.log`. The final rerun reproduced the same two failures and is logged in `apps/portcullis/.venv/plan19-final.log`. Task 7 added regression checks for the streaming body cap, signed Legion WebSocket denial, Scribe token refusal, and backup selection after a cooldown.

### Remaining verification

- Live Bard, Scribe, and Reader with two real origins.
- Microphone dictation through Portcullis and Stronghold.
- A live signed Treasury lookup, registration and catalog refresh round trip.
- Desktop and phone browser layout, and a live Docker run.

### Vault notes to update

- `Brain/Projects/Citadel.md`, `Brain/Projects/stronghold.md`, `Brain/Projects/stronghold_admin.md`, and `Brain/Projects/portcullis.md`
- `Brain/Projects/armory.md` and `Brain/Projects/armory_admin.md` for the legacy REST façade and Connections page
- `Brain/Projects/treasury.md` and `Brain/Notes/Decision - Outside services register once in Treasury's catalog with ids and consumer-side backups.md` for Stronghold's consumer role
- `Brain/Projects/Bard.md` and `Brain/Projects/Scribe.md` for the updated Citadel call path
