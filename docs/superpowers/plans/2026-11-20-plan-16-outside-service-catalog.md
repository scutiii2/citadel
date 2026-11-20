# Plan 16: Treasury outside-service catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treasury keeps a catalog of outside services (groups with a hidden service id, origins with origin ids, `used_by`), and every Citadel service can read it through the shared client.

**Architecture:** A new Treasury module `outside_catalog.py` stores three tables in `settings.db` through `settings_store`, next to the existing Citadel-service catalog, which stays unchanged. Treasury adds read, add-origin and admin routes. `libs/citadel_auth` `ServiceCatalog` reads `/outside`, caches it on disk, and answers `outside_origin(origin_id)`. Consumers (Plans 18 and 19) keep their own ordered origin lists; Treasury stores no tokens and no order.

**Tech Stack:** Python 3.12+, FastAPI, SQLite through `citadel_auth.settings_store`, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, section "Outside services and the catalog (Treasury)". Roadmap: `2026-11-20-scope-roadmap.md`.

**Status:** Complete on `plan-16-outside-catalog`.

## Baseline

Baseline at `4030fe6d`. Each suite ran from its own project directory with
`uv run pytest -q -p no:cacheprovider`, using `-m "not slow"` for Armory and Legion
and an isolated pytest temporary directory.

- Treasury: 81 passed, 13 skipped.
- Shared auth: 90 passed, one existing Pydantic warning.
- Legion: 1,411 passed, 6 deselected.
- Stronghold: 732 passed.
- Armory: 1,559 passed, 1 skipped, 280 deselected.
- Portcullis: 961 passed, 2 failed. Both known failures reject `http://127.0.0.1:0` in `checked_address`.
  - `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup`
  - `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`

## Global Constraints

- Treasury stores addresses only, never tokens.
- Citadel service names (`portcullis`, `stronghold`, `armory`, `legion`, `treasury`) are refused as outside group names; group names are unique, lowercase, `[a-z0-9][a-z0-9-]{0,39}`.
- An origin is `scheme://host[:port]`: no credentials, query or fragment; default ports dropped; a path is split off and never stored.
- Only `legion` and `stronghold` may add origins from a consumer form; only Portcullis may call `/admin/*`; every service may read `/outside`.
- Only Treasury admin deletes origins and groups and renames groups; a delete of a used group or origin needs `confirm=true`.
- Deviation from the spec text: consumers resolve an origin id to an address with `catalog.outside_origin(origin_id)`. The `http://<service-id>.citadel` logical host cannot work with consumer-side ordered lists, so it is not built. Update the spec line when this plan is done.
- Python code runs through `uv` and the project `.venv`. After any change in `libs/citadel_auth` run `uv run scripts/sync_citadel_auth.py`, then `uv run scripts/sync_citadel_auth.py --check`.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File structure

| File | Responsibility |
|---|---|
| `apps/treasury/src/outside_catalog.py` (create) | Storage and rules for groups, origins, `used_by` |
| `apps/treasury/src/api.py` (modify) | Routes `/outside`, `/outside/origins`, `/admin/outside...` |
| `apps/treasury/tests/test_outside_catalog.py` (create) | Unit tests of the module |
| `apps/treasury/tests/test_api.py` (modify) | Route and caller-rule tests |
| `libs/citadel_auth/citadel_auth/catalog.py` (modify) | Read, cache and look up outside groups |
| `libs/citadel_auth/tests/test_catalog.py` (modify) | Client tests |
| `apps/*/src/citadel_auth/` (generated) | Vendored copies from the sync script |
| `apps/treasury/README.md` (modify) | Document the new routes |

### Task 1: The outside catalog module

**Files:**
- Create: `apps/treasury/src/outside_catalog.py`
- Test: `apps/treasury/tests/test_outside_catalog.py`

**Interfaces:**
- Produces:
  - `class OutsideCatalogError(ValueError)`, `class NotFound(OutsideCatalogError)`, `class InUse(OutsideCatalogError)` with attribute `users: list[str]`
  - `split_origin(value: object) -> tuple[str, str]` returns `(origin, path)`
  - `view(db: Path) -> dict` returns `{"groups": [{"service_id", "name", "origins": [{"origin_id", "origin"}], "used_by": [str]}]}`
  - `add_origin(db: Path, origin: object, name: object, consumer: str) -> dict` returns one group row
  - `rename_group(db: Path, service_id: str, name: object) -> dict`
  - `delete_origin(db: Path, origin_id: str, confirm: bool = False) -> None`
  - `delete_group(db: Path, service_id: str, confirm: bool = False) -> None`

- [x] **Step 1: Write the failing tests**

```python
# apps/treasury/tests/test_outside_catalog.py
import pytest

from src import outside_catalog as oc


@pytest.fixture
def db(tmp_path):
    return tmp_path / "settings.db"


@pytest.mark.parametrize("text, expected", [
    ("http://bard:29400", ("http://bard:29400", "")),
    ("HTTP://Bard:29400/mcp/", ("http://bard:29400", "/mcp")),
    ("http://bard:80/api", ("http://bard", "/api")),
    ("https://bard.lan:443", ("https://bard.lan", "")),
    ("http://[::1]:29400/x", ("http://[::1]:29400", "/x")),
])
def test_an_address_is_split_into_origin_and_path(text, expected):
    assert oc.split_origin(text) == expected


@pytest.mark.parametrize("text", [
    "", "bard:29400", "ftp://bard", "http://u:p@bard", "http://bard?x=1", "http://bard#f", "http://bard:0", "http://bard:abc", None, 5,
])
def test_a_bad_address_is_refused(text):
    with pytest.raises(oc.OutsideCatalogError):
        oc.split_origin(text)


def test_a_new_origin_needs_a_name_and_creates_a_group_with_ids(db):
    with pytest.raises(oc.OutsideCatalogError, match="give it a name"):
        oc.add_origin(db, "http://bard:29400", None, "legion")
    group = oc.add_origin(db, "http://bard:29400/mcp", "Bard", "legion")
    assert group["name"] == "bard" and group["used_by"] == ["legion"]
    assert len(group["service_id"]) == 32 and len(group["origins"][0]["origin_id"]) == 32
    assert group["origins"][0]["origin"] == "http://bard:29400"


def test_a_known_origin_returns_its_group_and_ignores_the_given_name(db):
    first = oc.add_origin(db, "http://bard:29400", "bard", "legion")
    again = oc.add_origin(db, "http://bard:29400/api", "other-name", "stronghold")
    assert again["service_id"] == first["service_id"] and again["name"] == "bard"
    assert again["used_by"] == ["legion", "stronghold"]
    assert len(again["origins"]) == 1


def test_an_existing_name_takes_the_new_origin_as_a_backup(db):
    first = oc.add_origin(db, "http://bard:29400", "bard", "legion")
    backup = oc.add_origin(db, "http://bard2:29400", "BARD", "legion")
    assert backup["service_id"] == first["service_id"]
    assert [o["origin"] for o in backup["origins"]] == ["http://bard2:29400", "http://bard:29400"]


@pytest.mark.parametrize("name", ["armory", "Treasury", "legion", "", " ", "bad name", "-x", "x" * 41])
def test_citadel_names_and_bad_names_are_refused(db, name):
    with pytest.raises(oc.OutsideCatalogError):
        oc.add_origin(db, "http://x:1", name, "legion")
    assert oc.view(db) == {"groups": []}


def test_rename_keeps_the_service_id_and_names_stay_unique(db):
    bard = oc.add_origin(db, "http://bard:1", "bard", "legion")
    oc.add_origin(db, "http://scribe:1", "scribe", "legion")
    renamed = oc.rename_group(db, bard["service_id"], "Speech")
    assert renamed["service_id"] == bard["service_id"] and renamed["name"] == "speech"
    with pytest.raises(oc.OutsideCatalogError):
        oc.rename_group(db, bard["service_id"], "scribe")
    with pytest.raises(oc.OutsideCatalogError):
        oc.rename_group(db, bard["service_id"], "armory")
    with pytest.raises(oc.NotFound):
        oc.rename_group(db, "0" * 32, "x")


def test_deleting_a_used_group_or_origin_needs_confirmation(db):
    group = oc.add_origin(db, "http://bard:1", "bard", "legion")
    origin_id = group["origins"][0]["origin_id"]
    with pytest.raises(oc.InUse) as error:
        oc.delete_origin(db, origin_id)
    assert error.value.users == ["legion"]
    with pytest.raises(oc.InUse):
        oc.delete_group(db, group["service_id"])
    oc.delete_origin(db, origin_id, confirm=True)
    assert oc.view(db)["groups"][0]["origins"] == []
    oc.delete_group(db, group["service_id"], confirm=True)
    assert oc.view(db) == {"groups": []}


def test_deleting_a_group_removes_its_origins_and_its_users(db):
    from src.citadel_auth import settings_store

    group = oc.add_origin(db, "http://bard:1", "bard", "legion")
    oc.delete_group(db, group["service_id"], confirm=True)
    assert settings_store.read_all(db, "outside_origins") == {}
    assert settings_store.read_all(db, "outside_users") == {}
    with pytest.raises(oc.NotFound):
        oc.delete_origin(db, "0" * 32)
    with pytest.raises(oc.NotFound):
        oc.delete_group(db, group["service_id"])
```

- [x] **Step 2: Run the tests to verify they fail**

Run (from `apps/treasury`): `uv run pytest tests/test_outside_catalog.py -q -p no:cacheprovider`
Expected: FAIL, `ImportError: cannot import name 'outside_catalog'`.

- [x] **Step 3: Write the implementation**

```python
# apps/treasury/src/outside_catalog.py
"""Outside services: where the tool services and gateways Citadel calls are. Addresses only, never tokens.

Three tables in `.data/treasury/settings.db`: `outside_groups` (service id -> name), `outside_origins`
(origin id -> service id and origin) and `outside_users` (which Citadel service uses which group).
The name is a label; consumers store the ids, so a rename breaks nothing.
"""

from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from src.citadel_auth import settings_store

GROUPS_TABLE = "outside_groups"
ORIGINS_TABLE = "outside_origins"
USERS_TABLE = "outside_users"
RESERVED = frozenset({"portcullis", "stronghold", "armory", "legion", "treasury"})
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_DEFAULT_PORT = {"http": 80, "https": 443}
# shortcut: one lock per process, enough for one Treasury; use a database transaction if Treasury ever scales out.
_LOCK = threading.Lock()


class OutsideCatalogError(ValueError):
    """A rejected change; the message is safe to show."""


class NotFound(OutsideCatalogError):
    pass


class InUse(OutsideCatalogError):
    def __init__(self, users: list[str]) -> None:
        super().__init__("in use by " + ", ".join(users))
        self.users = users


def split_origin(value: object) -> tuple[str, str]:
    """`(origin, path)` of an address. The origin is `scheme://host[:port]` with default ports dropped."""
    text = value.strip() if isinstance(value, str) else ""
    try:
        parts = urlsplit(text)
        port = parts.port  # raises on a malformed port
        if (parts.scheme not in _DEFAULT_PORT or not parts.hostname
                or parts.username is not None or parts.password is not None
                or "?" in text or "#" in text or "\\" in text or port == 0 or parts.netloc.endswith(":")
                or any(char.isspace() or ord(char) < 32 for char in text)):
            raise ValueError
    except ValueError:
        raise OutsideCatalogError("an address looks like http://host:port, optionally followed by a path") from None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    shown = f":{port}" if port not in (None, _DEFAULT_PORT[parts.scheme]) else ""
    return f"{parts.scheme}://{host}{shown}", parts.path.rstrip("/")


def _clean_name(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise OutsideCatalogError("this address is new: give it a name")
    text = name.strip().lower()
    if not _NAME.fullmatch(text):
        raise OutsideCatalogError("a name uses lowercase letters, digits and hyphens, up to 40 characters")
    if text in RESERVED:
        raise OutsideCatalogError(f"{text!r} is the name of a Citadel service")
    return text


def _state(db: Path) -> tuple[dict, dict, dict]:
    return (settings_store.read_all(db, GROUPS_TABLE), settings_store.read_all(db, ORIGINS_TABLE),
            settings_store.read_all(db, USERS_TABLE))


def _row(service_id: str, groups: dict, origins: dict, users: dict) -> dict:
    mine = sorted((o["origin"], oid) for oid, o in origins.items() if o["service_id"] == service_id)
    return {
        "service_id": service_id,
        "name": groups[service_id]["name"],
        "origins": [{"origin_id": oid, "origin": origin} for origin, oid in mine],
        "used_by": sorted(u["consumer"] for u in users.values() if u["service_id"] == service_id),
    }


def view(db: Path) -> dict:
    groups, origins, users = _state(db)
    ordered = sorted(groups, key=lambda sid: groups[sid]["name"])
    return {"groups": [_row(sid, groups, origins, users) for sid in ordered]}


def _one(db: Path, service_id: str) -> dict:
    groups, origins, users = _state(db)
    if service_id not in groups:
        raise NotFound("no such service")
    return _row(service_id, groups, origins, users)


def add_origin(db: Path, origin: object, name: object, consumer: str) -> dict:
    """Find the origin and return its group (the name is then ignored), or create it under `name`:
    a new name makes a group, an existing name adds the origin to that group. Records the consumer."""
    clean, _ = split_origin(origin)
    with _LOCK:
        groups, origins, _users = _state(db)
        found = next((o for o in origins.values() if o["origin"] == clean), None)
        if found is not None:
            service_id = found["service_id"]
        else:
            label = _clean_name(name)
            service_id = next((sid for sid, g in groups.items() if g["name"] == label), None)
            if service_id is None:
                service_id = uuid.uuid4().hex
                settings_store.put(db, GROUPS_TABLE, service_id, {"name": label})
            settings_store.put(db, ORIGINS_TABLE, uuid.uuid4().hex, {"service_id": service_id, "origin": clean})
        settings_store.put(db, USERS_TABLE, f"{service_id}:{consumer}", {"service_id": service_id, "consumer": consumer})
    return _one(db, service_id)


def rename_group(db: Path, service_id: str, name: object) -> dict:
    label = _clean_name(name)
    with _LOCK:
        groups, _origins, _users = _state(db)
        if service_id not in groups:
            raise NotFound("no such service")
        if any(sid != service_id and g["name"] == label for sid, g in groups.items()):
            raise OutsideCatalogError(f"the name {label!r} is already used")
        settings_store.put(db, GROUPS_TABLE, service_id, {"name": label})
    return _one(db, service_id)


def _users_of(users: dict, service_id: str) -> list[str]:
    return sorted(u["consumer"] for u in users.values() if u["service_id"] == service_id)


def delete_origin(db: Path, origin_id: str, confirm: bool = False) -> None:
    with _LOCK:
        _groups, origins, users = _state(db)
        if origin_id not in origins:
            raise NotFound("no such origin")
        used = _users_of(users, origins[origin_id]["service_id"])
        if used and not confirm:
            raise InUse(used)
        settings_store.delete(db, ORIGINS_TABLE, origin_id)


def delete_group(db: Path, service_id: str, confirm: bool = False) -> None:
    with _LOCK:
        groups, origins, users = _state(db)
        if service_id not in groups:
            raise NotFound("no such service")
        used = _users_of(users, service_id)
        if used and not confirm:
            raise InUse(used)
        for oid, o in origins.items():
            if o["service_id"] == service_id:
                settings_store.delete(db, ORIGINS_TABLE, oid)
        for key, u in users.items():
            if u["service_id"] == service_id:
                settings_store.delete(db, USERS_TABLE, key)
        settings_store.delete(db, GROUPS_TABLE, service_id)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_outside_catalog.py -q -p no:cacheprovider`
Expected: PASS (all tests).

- [x] **Step 5: Commit**

```bash
git add apps/treasury/src/outside_catalog.py apps/treasury/tests/test_outside_catalog.py
git commit -m "feat(treasury): keep a catalog of outside services with ids"
```

### Task 2: Treasury routes

**Files:**
- Modify: `apps/treasury/src/api.py` (import line 22; models near line 52; routes after `unpin_service`, line ~189)
- Test: `apps/treasury/tests/test_api.py`

**Interfaces:**
- Consumes: `outside_catalog` from Task 1.
- Produces (HTTP):
  - `GET /outside` any service: `{"groups": [...]}`
  - `POST /outside/origins` body `{"origin": str, "name": str | null}`; callers `legion`, `stronghold` only; returns the group row; 400 on `OutsideCatalogError`
  - `GET /admin/outside` Portcullis only: `{"groups": [...]}`
  - `PATCH /admin/outside/{service_id}` body `{"name": str}` returns the group; 404 unknown
  - `DELETE /admin/outside/origins/{origin_id}?confirm=true|false` returns `{"groups": [...]}`; 409 `{"error", "used_by"}` when in use and not confirmed
  - `DELETE /admin/outside/{service_id}?confirm=true|false` same

- [x] **Step 1: Write the failing tests** (append to `apps/treasury/tests/test_api.py`; uses the existing `registering` fixture, which yields `(caller, db)`)

```python
async def test_a_consumer_adds_an_origin_and_everyone_reads_it(registering):
    caller, _ = registering
    async with caller("legion") as legion, caller("armory") as armory:
        added = await legion.post("/outside/origins", json={"origin": "http://bard:29400/mcp", "name": "Bard"})
        assert added.status_code == 200
        group = added.json()
        assert group["name"] == "bard" and group["used_by"] == ["legion"]
        seen = (await armory.get("/outside")).json()
        assert seen["groups"][0]["service_id"] == group["service_id"]


async def test_only_legion_and_stronghold_add_origins_and_citadel_names_are_refused(registering):
    caller, _ = registering
    async with caller("armory") as armory, caller("portcullis") as portcullis, caller("stronghold") as stronghold:
        assert (await armory.post("/outside/origins", json={"origin": "http://x:1", "name": "x"})).status_code == 403
        assert (await portcullis.post("/outside/origins", json={"origin": "http://x:1", "name": "x"})).status_code == 403
        assert (await stronghold.post("/outside/origins", json={"origin": "http://x:1", "name": "armory"})).status_code == 400
        assert (await stronghold.post("/outside/origins", json={"origin": "http://x:1"})).status_code == 400


async def test_outside_admin_routes_belong_to_portcullis_and_deletes_list_the_users(registering):
    caller, _ = registering
    async with caller("legion") as legion, caller("portcullis") as portcullis, caller("stronghold") as stronghold:
        group = (await legion.post("/outside/origins", json={"origin": "http://bard:1", "name": "bard"})).json()
        sid, oid = group["service_id"], group["origins"][0]["origin_id"]
        assert (await stronghold.get("/admin/outside")).status_code == 403
        assert (await stronghold.delete(f"/admin/outside/{sid}?confirm=true")).status_code == 403
        renamed = await portcullis.patch(f"/admin/outside/{sid}", json={"name": "speech"})
        assert renamed.status_code == 200 and renamed.json()["service_id"] == sid
        refused = await portcullis.delete(f"/admin/outside/origins/{oid}")
        assert refused.status_code == 409 and refused.json()["used_by"] == ["legion"]
        assert (await portcullis.delete(f"/admin/outside/origins/{oid}?confirm=true")).status_code == 200
        gone = await portcullis.delete(f"/admin/outside/{sid}?confirm=true")
        assert gone.status_code == 200 and gone.json() == {"groups": []}
        assert (await portcullis.patch(f"/admin/outside/{sid}", json={"name": "x"})).status_code == 404
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_api.py -q -p no:cacheprovider -k outside`
Expected: FAIL, 404 or 405 on the new routes.

- [x] **Step 3: Implement**

In `apps/treasury/src/api.py` change the import and add models:

```python
from src import connection_admin, outside_catalog, service_catalog
```

```python
class OutsideBody(BaseModel):
    origin: str
    name: str | None = None


class RenameBody(BaseModel):
    name: str
```

Add after `unpin_service`:

```python
    outside_consumers = frozenset({"legion", "stronghold"})

    def _outside_error(error: outside_catalog.OutsideCatalogError) -> HTTPException | JSONResponse:
        if isinstance(error, outside_catalog.InUse):
            return JSONResponse(status_code=409, content={"error": f"This is in use by {', '.join(error.users)}. Confirm to delete it.",
                                                          "used_by": error.users})
        return HTTPException(404 if isinstance(error, outside_catalog.NotFound) else 400, str(error))

    @app.get("/outside")
    async def outside() -> dict[str, Any]:
        """The outside services every Citadel service may read: groups with their origins. Addresses only."""
        if settings_db is None:
            return {"groups": []}
        return await asyncio.to_thread(outside_catalog.view, settings_db)

    @app.post("/outside/origins")
    async def add_outside_origin(body: OutsideBody) -> dict[str, Any]:
        """A consumer form saves an origin: Legion for MCP connections, Stronghold for REST ones."""
        caller = current_caller()
        if caller is None or caller.name not in outside_consumers:
            raise HTTPException(403, f"{caller.name if caller else 'this caller'} may not add outside origins")
        if settings_db is None:
            raise HTTPException(409, "this Treasury keeps no settings database")
        try:
            return await asyncio.to_thread(outside_catalog.add_origin, settings_db, body.origin, body.name, caller.name)
        except outside_catalog.OutsideCatalogError as error:
            raise _outside_error(error) from error

    async def _outside_admin(action, *args):
        _admin_only()
        try:
            return await asyncio.to_thread(action, settings_db, *args)
        except outside_catalog.OutsideCatalogError as error:
            result = _outside_error(error)
            if isinstance(result, JSONResponse):
                return result
            raise result from error

    @app.get("/admin/outside")
    async def admin_outside() -> Any:
        return await _outside_admin(outside_catalog.view)

    @app.patch("/admin/outside/{service_id}")
    async def rename_outside(service_id: str, body: RenameBody) -> Any:
        return await _outside_admin(outside_catalog.rename_group, service_id, body.name)

    @app.delete("/admin/outside/origins/{origin_id}")
    async def delete_outside_origin(origin_id: str, confirm: bool = False) -> Any:
        result = await _outside_admin(outside_catalog.delete_origin, origin_id, confirm)
        return result if isinstance(result, JSONResponse) else await _outside_admin(outside_catalog.view)

    @app.delete("/admin/outside/{service_id}")
    async def delete_outside_group(service_id: str, confirm: bool = False) -> Any:
        result = await _outside_admin(outside_catalog.delete_group, service_id, confirm)
        return result if isinstance(result, JSONResponse) else await _outside_admin(outside_catalog.view)
```

- [x] **Step 4: Run to verify pass, then the whole Treasury suite**

Run: `uv run pytest tests/test_api.py -q -p no:cacheprovider -k outside`
Expected: PASS.
Run: `uv run pytest -q -p no:cacheprovider`
Expected: no new failures (baseline: 81 passed, 13 skipped at Plan 14).

- [x] **Step 5: Commit**

```bash
git add apps/treasury/src/api.py apps/treasury/tests/test_api.py
git commit -m "feat(treasury): routes for the outside-service catalog"
```

### Task 3: Shared client lookup

**Files:**
- Modify: `libs/citadel_auth/citadel_auth/catalog.py` (`__init__`, `_load_cache`, `refresh`, `_write_cache`, new methods)
- Test: `libs/citadel_auth/tests/test_catalog.py`

**Interfaces:**
- Consumes: `GET /outside` from Task 2.
- Produces on `ServiceCatalog`:
  - `outside_groups() -> list[dict]` copies of `{"service_id","name","origins":[{"origin_id","origin"}]}`
  - `outside_origin(origin_id: str) -> str` raises `UnknownService(origin_id)` if absent
  - `outside_group(service_id: str) -> dict` raises `UnknownService(service_id)` if absent
  - `refresh()` also reads `/outside`; a failing or missing `/outside` never fails the refresh; the disk cache stores the groups under key `"_outside"`.

- [x] **Step 1: Write the failing tests** (append to `libs/citadel_auth/tests/test_catalog.py`, using its `make` helper)

```python
OUTSIDE = {"groups": [{"service_id": "a" * 32, "name": "bard", "used_by": ["legion"],
                       "origins": [{"origin_id": "b" * 32, "origin": "http://bard:29400"},
                                   {"origin_id": "c" * 32, "origin": "http://bard2:29400"}]}]}


def _handler(outside_status=200):
    def handler(request):
        if request.url.path == "/services":
            return httpx.Response(200, json={"services": {}})
        if request.url.path == "/outside":
            return httpx.Response(outside_status, json=OUTSIDE)
        return httpx.Response(404)
    return handler


async def test_refresh_reads_the_outside_groups_and_resolves_origin_ids(tmp_path):
    catalog = make(_handler(), tmp_path)
    assert await catalog.refresh() is True
    assert catalog.outside_origin("c" * 32) == "http://bard2:29400"
    group = catalog.outside_group("a" * 32)
    assert group["name"] == "bard" and [o["origin"] for o in group["origins"]] == ["http://bard:29400", "http://bard2:29400"]
    assert [g["name"] for g in catalog.outside_groups()] == ["bard"]
    with pytest.raises(UnknownService):
        catalog.outside_origin("0" * 32)


async def test_the_outside_groups_survive_a_restart_through_the_disk_cache(tmp_path):
    await make(_handler(), tmp_path).refresh()
    fresh = make(_handler(outside_status=500), tmp_path)  # no refresh: only the cache
    assert fresh.outside_origin("b" * 32) == "http://bard:29400"
    assert (await fresh.refresh()) is True  # services answered; a failing /outside changes nothing
    assert fresh.outside_origin("b" * 32) == "http://bard:29400"


async def test_a_treasury_without_outside_still_refreshes(tmp_path):
    catalog = make(_handler(outside_status=404), tmp_path)
    assert await catalog.refresh() is True
    assert catalog.outside_groups() == []


async def test_a_bad_outside_entry_is_dropped(tmp_path):
    bad = {"groups": [{"service_id": "a" * 32, "name": "x", "origins": [{"origin_id": "b" * 32, "origin": "http://u:p@x"}]}, {"nope": 1}]}

    def handler(request):
        return httpx.Response(200, json={"services": {}} if request.url.path == "/services" else bad)

    catalog = make(handler, tmp_path)
    await catalog.refresh()
    assert catalog.outside_groups()[0]["origins"] == []
```

- [x] **Step 2: Run to verify failure**

Run (from `libs/citadel_auth`): `uv run pytest tests/test_catalog.py -q -p no:cacheprovider -k outside`
Expected: FAIL, `AttributeError: 'ServiceCatalog' object has no attribute 'outside_origin'`.

- [x] **Step 3: Implement**

In `catalog.py`, add a module helper above `class ServiceCatalog`:

```python
def _clean_outside(groups: object) -> list[dict]:
    """The outside groups a refresh or the cache returned, keeping only well-formed entries and valid addresses."""
    cleaned = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict) or not isinstance(group.get("service_id"), str) or not isinstance(group.get("name"), str):
            continue
        origins = []
        for item in group.get("origins") if isinstance(group.get("origins"), list) else []:
            try:
                origins.append({"origin_id": str(item["origin_id"]), "origin": checked_address(item["origin"])})
            except (KeyError, TypeError, ValueError):
                continue
        cleaned.append({"service_id": group["service_id"], "name": group["name"], "origins": origins})
    return cleaned
```

In `__init__` add `self._outside: list[dict] = []` before `self._load_cache()`.

In `_load_cache`, after `self._merge(stored)` add:

```python
        if isinstance(stored, dict):
            self._outside = _clean_outside(stored.get("_outside"))
```

Add methods after `mcp_url`:

```python
    def outside_groups(self) -> list[dict]:
        return [{**group, "origins": [dict(o) for o in group["origins"]]} for group in self._outside]

    def outside_group(self, service_id: str) -> dict:
        for group in self.outside_groups():
            if group["service_id"] == service_id:
                return group
        raise UnknownService(service_id)

    def outside_origin(self, origin_id: str) -> str:
        for group in self._outside:
            for item in group["origins"]:
                if item["origin_id"] == origin_id:
                    return item["origin"]
        raise UnknownService(origin_id)

    async def _refresh_outside(self) -> None:
        """Read the outside groups. Any failure keeps what is known; an old Treasury without `/outside` is fine."""
        try:
            async with self._client() as client:
                response = await client.get("/outside")
            groups = response.json().get("groups") if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError, AttributeError):
            return
        if isinstance(groups, list):
            self._outside = _clean_outside(groups)
```

In `refresh`, replace the tail with:

```python
        before, outside_before = dict(self._known), list(self._outside)
        self._known = dict(self._defaults)
        self._merge(services)
        await self._refresh_outside()
        if (self._known != before or self._outside != outside_before
                or (self._cache_path is not None and not self._cache_path.exists())):
            await asyncio.to_thread(self._write_cache)
        return True
```

In `_write_cache` change the dumped value to:

```python
json.dumps({**{k: v for k, v in self._known.items() if k != "treasury"}, "_outside": self._outside})
```

- [x] **Step 4: Run to verify pass, then the library suite**

Run: `uv run pytest tests/test_catalog.py -q -p no:cacheprovider -k outside` then `uv run pytest -q -p no:cacheprovider`
Expected: PASS; baseline 87 passed plus the new tests. If an existing test compares the exact cache file contents, update it to include `"_outside": []`.

- [x] **Step 5: Sync the vendored copies and commit**

Run (repo root): `uv run scripts/sync_citadel_auth.py` then `uv run scripts/sync_citadel_auth.py --check`
Expected: the check exits 0 (the Treasury test `test_citadel_auth_in_sync.py` also passes).

```bash
git add libs/citadel_auth apps/*/src/citadel_auth
git commit -m "feat(auth): read, cache and resolve outside services"
```

### Task 4: Documentation and full verification

**Files:**
- Modify: `apps/treasury/README.md` (routes section), `docs/superpowers/specs/2026-11-20-service-scopes-design.md` (logical-host line), this plan's status line

- [x] **Step 1: Document the routes in the Treasury README**

Add a section "Outside services" listing the six routes from Task 2 with their callers, the three tables, the origin rule, and the sentence "Treasury stores addresses only; each consumer keeps its own tokens and ordered origin list."

- [x] **Step 2: Fix the spec line**

In the spec, in "Outside services and the catalog", replace "Consumers store ids and use `http://<service-id>.citadel`." with "Consumers store ids and resolve an origin id to an address with `catalog.outside_origin(origin_id)`; each consumer keeps its own ordered origin list."

- [x] **Step 3: Run every affected suite**

Run: `uv run pytest -q -p no:cacheprovider` in `apps/treasury` and `libs/citadel_auth`; then in `apps/legion`, `apps/stronghold`, `apps/armory`, `apps/portcullis` run `uv run pytest -q -p no:cacheprovider` (add `-m "not slow"` for Armory and Legion) to prove the vendored copies broke nothing.
Expected: Treasury and library green; the others match the Plan 14 baseline (Portcullis keeps its two known port-0 failures).

- [x] **Step 4: Commit**

```bash
git add apps/treasury/README.md docs/superpowers/specs/2026-11-20-service-scopes-design.md docs/superpowers/plans/2026-11-20-plan-16-outside-service-catalog.md
git commit -m "docs: outside-service catalog routes and the origin-id lookup"
```

## Self-review notes
- Spec coverage for this plan's slice: ids at two levels (Task 1), origin-first split and default-port drop (Task 1), found-origin fills the name and new name creates or joins a group (Task 1), Citadel names refused and names unique (Task 1), Treasury-admin-only delete and rename (Task 2), `used_by` in the delete confirmation (Tasks 1 and 2), shared read for all services (Tasks 2 and 3), no tokens stored (global constraint, no token field anywhere). Not in this plan, by roadmap: the admin UI and Portcullis proxy (Plan 17), consumer forms, parent token, overrides and failover (Plans 18 and 19), `/ready` per origin and discovery (Plan 25).
- Treasury down while saving: the consumer form calls `POST /outside/origins`; the refusal with error 1002 is built in the consumer plans, where the form exists.
- Names used across tasks match: `split_origin`, `add_origin`, `rename_group`, `delete_origin`, `delete_group`, `view`, `outside_origin`, `outside_group`, `outside_groups`, `OutsideCatalogError`, `NotFound`, `InUse`.

## Changes found during work

- Windows sandbox blocked the uv cache and the loopback sockets used by asyncio. Baseline and full suites ran with Windows loopback enabled and disposable pytest directories. The first focused storage run used the existing environment via uv run --no-sync.
- Task 1 uses one SQLite transaction per mutation and one snapshot per read. It reuses the settings-store table format and connection setup. This replaces separate writes under an in-process lock. A trigger-induced failure verifies rollback of the group and origin. Review cases cover malformed host names that HTTPX otherwise accepts.
- Task 2 reuses the existing Portcullis admin guard and maps outside-catalog exceptions to 400, 404 or 409. The route test selector includes all three outside tests. Treasury's own signed identity needed an outside-specific receiver-policy entry. The route tests verify that it can read the catalog and still receives 403 for adding origins and reading /services.
- Task 3 reuses one signed HTTP client per refresh. The outside read can succeed when `/services` returns 403. The client serializes refreshes and persists each successful internal snapshot before awaiting the outside response. The existing outage test exposed the delayed cache write. A controlled slow-response test reproduced it and now verifies both in-process and restart reads. Existing mock handlers receive a 404 for the extra route unless a test supplies an outside handler. Added coverage for defensive copies, empty snapshots, partial refresh and delayed outside responses.
- Task 4 uses the clean Plan 15 worktree at the same commit as main for dependent-app baselines. It runs with the existing app environments via uv run --no-sync. Portcullis output goes to an ignored local log for each run.

## Verification

| Suite | Baseline | Plan 16 |
|---|---|---|
| Treasury | 81 passed, 13 skipped | 117 passed, 13 skipped |
| Shared auth | 90 passed | 97 passed |
| Legion | 1,411 passed, 6 deselected | 1,411 passed, 6 deselected |
| Stronghold | 732 passed | 732 passed |
| Armory | 1,559 passed, 1 skipped, 280 deselected | 1,559 passed, 1 skipped, 280 deselected |
| Portcullis | 961 passed, 2 failed | 961 passed, the same 2 failures |

Focused suites passed 33 storage tests, 3 route tests and 7 outside-client tests.
`uv run scripts/sync_citadel_auth.py --check` passed for all five copies.
Treasury reported an aiosqlite thread-shutdown warning in `tests/test_cache.py::test_create_drops_cached_not_found` during the final full run.

Live Docker, a real Postgres instance and simultaneous multi-service startup remain unverified.
