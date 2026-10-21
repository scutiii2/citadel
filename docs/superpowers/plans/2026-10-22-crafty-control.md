# Crafty Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in user stores their own Crafty URL and API token, then lists, inspects, starts, stops and restarts their Minecraft servers from Ember chat and slash commands.

**Architecture:** ember_api stores one encrypted, revisioned Crafty connection per user (copy of the `brain_connections` pattern). Armory resolves the caller's connection from ember_api on every tool call and talks to Crafty over an address-checked, pinned HTTPS client. Connection testing also runs inside armory, so every request to a user-supplied URL passes the same guard.

**Tech Stack:** Python 3 (FastAPI, Pydantic, pytest) in `apps/Ember/ember_api` and `apps/armory`; urllib with the existing pinned HTTPS handler; Vue 3 + TypeScript + Vitest in `apps/Ember/ember_web`.

**Spec:** `docs/superpowers/specs/2026-10-22-crafty-control-design.md`

## Global Constraints

- Never add a reduced-motion setting, a `prefers-reduced-motion` query or a reduced-motion test, anywhere.
- Endpoints are HTTPS only: no credentials, query or fragment in the URL.
- The API token is write-only: encrypted at rest with `SecretBox`, never returned by any route, never logged, never in an error message.
- Outbound calls to a user URL use `personal=True` in `net_guard`: private LAN allowed; loopback, link-local, multicast, reserved, metadata addresses and redirects refused.
- Server names match `^[a-z0-9][a-z0-9_-]{0,31}$`, are unique per connection, at most 20 per connection. Server ids match `^[A-Za-z0-9-]{1,64}$`.
- Read tools (`listServers`, `getStatus`) declare `readOnlyHint=True`. `startServer`, `stopServer`, `restartServer` never do.
- Skills are edited only in `.agents/skills/` (not touched by this plan). Do not edit `CLAUDE.md`; project instructions live in `AGENTS.md`.
- Every result model ends with a `message` safe to relay verbatim.
- Run commands from the app folder named in each task. Test commands use `python -m pytest`.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/armory/src/services/net_guard.py` (create) | Address check, pinned HTTPS connection/handler, no-redirect handler (moved from obsidian). |
| `apps/armory/src/capabilities/obsidian/utils/network.py` (modify) | Thin re-export of `net_guard` so old imports keep working. |
| `apps/armory/src/capabilities/crafty/__init__.py` (create) | `META` registration, id `crafty`. |
| `apps/armory/src/capabilities/crafty/contract.py` (create) | Result models. |
| `apps/armory/src/capabilities/crafty/domain.py` (create) | Name lookup, status normalization, the five operations. |
| `apps/armory/src/capabilities/crafty/tool.py` (create) | MCP tools and slash commands, thin. |
| `apps/armory/src/capabilities/crafty/utils/client.py` (create) | `CraftyClient`, `CraftyError`. |
| `apps/armory/src/capabilities/crafty/utils/resolver.py` (create) | Fetch the caller's connection from ember_api. |
| `apps/armory/src/capabilities/crafty/help.json`, `README.md` (create) | Per-capability docs. |
| `apps/armory/src/crafty_routes.py` (create) | `POST /crafty/operation` (test only). |
| `apps/armory/src/run.py` (modify) | Install the route. |
| `apps/Ember/ember_api/src/services/crafty_connections.py` (create) | Storage, validation, resolve, purge. |
| `apps/Ember/ember_api/src/services/crafty_gateway.py` (create) | Private HTTP call to armory's test route. |
| `apps/Ember/ember_api/src/routes/crafty.py` (create) | `/api/crafty/...` routes. |
| `apps/Ember/ember_api/src/app.py`, `routes/admin.py` (modify) | Register router + error handler, purge on account delete. |
| `apps/Ember/ember_web/src/api/CraftyClient.ts` (create) | API client. |
| `apps/Ember/ember_web/src/components/CraftyConnectionForm.vue` (create) | Settings form with test and server picker. |
| `apps/Ember/ember_web/src/views/CraftyView.vue` (create), router/nav (modify) | Page that hosts the form. |

---

### Task 1: Move the network guard to `services/net_guard.py`

**Files:**
- Create: `apps/armory/src/services/net_guard.py`
- Modify: `apps/armory/src/capabilities/obsidian/utils/network.py`
- Test: `apps/armory/tests/test_net_guard.py`

**Interfaces:**
- Produces: `src.services.net_guard.checked_addresses(host, port, *, personal) -> list`, `PinnedHTTPSConnection`, `PinnedHTTPSHandler(context=, personal=)`, `NoRedirect` (an `urllib.request.HTTPRedirectHandler` whose `redirect_request` returns `None`).

- [ ] **Step 1: Write the failing test** — `apps/armory/tests/test_net_guard.py`

```python
import socket

import pytest

from src.services import net_guard


def fake_dns(address):
    def lookup(host, port, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    return lookup


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "0.0.0.0", "224.0.0.1"])
def test_personal_destinations_refuse_loopback_link_local_unspecified_and_multicast(monkeypatch, address):
    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_dns(address))
    with pytest.raises(OSError):
        net_guard.checked_addresses("crafty.example", 8443, personal=True)


def test_private_lan_is_allowed(monkeypatch):
    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_dns("192.168.1.50"))
    assert net_guard.checked_addresses("zima.lan", 8443, personal=True)


def test_no_redirect_refuses_every_redirect():
    handler = net_guard.NoRedirect()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/") is None


def test_the_old_obsidian_import_path_still_works():
    from src.capabilities.obsidian.utils import network

    assert network.checked_addresses is net_guard.checked_addresses
    assert network.PinnedHTTPSHandler is net_guard.PinnedHTTPSHandler
```

- [ ] **Step 2: Run it to verify it fails**

Run (in `apps/armory`): `python -m pytest tests/test_net_guard.py -v`
Expected: FAIL, `ImportError: cannot import name 'net_guard'`.

- [ ] **Step 3: Create `apps/armory/src/services/net_guard.py`**

```python
"""Pin each HTTPS connection to a checked DNS answer; never follow redirects.

Shared by every capability that dials a URL a user typed (Obsidian personal
brains, Crafty). Private LAN is deliberate; loopback, link-local, metadata and
other non-unicast ranges are never a personal destination, including mixed DNS.
"""
import http.client
import ipaddress
import socket
import urllib.request

from src.utils.catalog import catalog


@catalog
def checked_addresses(host: str, port: int, *, personal: bool) -> list:
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not answers:
        raise OSError("No address")
    for family, _, _, _, address in answers:
        ip = ipaddress.ip_address(address[0].split("%", 1)[0])
        ip = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip
        if personal and (ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified
                         or ip.is_reserved or str(ip) in {"100.100.100.200", "168.63.129.16"}):
            raise OSError("Destination is not allowed")
    return answers


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, personal: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.personal = personal

    def connect(self):
        answers = checked_addresses(self.host, self.port, personal=self.personal)
        last = None
        for family, socktype, proto, _, address in answers:
            sock = socket.socket(family, socktype, proto)
            try:
                sock.settimeout(self.timeout)
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as error:
                sock.close()
                last = error
        raise OSError("Unable to connect to checked destination") from last


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, *, context, personal: bool):
        super().__init__(context=context)
        self.personal = personal

    def https_open(self, request):
        def connect(*args, **kwargs):
            return PinnedHTTPSConnection(*args, personal=self.personal, **kwargs)
        return self.do_open(connect, request, context=self._context)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib otherwise forwards Authorization when following some redirects.
        return None
```

- [ ] **Step 4: Replace `apps/armory/src/capabilities/obsidian/utils/network.py` with a shim**

```python
"""Moved to services/net_guard.py; re-exported so existing imports keep working."""
from src.services.net_guard import PinnedHTTPSConnection, PinnedHTTPSHandler, checked_addresses  # noqa: F401
```

- [ ] **Step 5: Run the new test and the existing network tests**

Run: `python -m pytest tests/test_net_guard.py tests/test_brain_network.py tests/test_obsidian_capability.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/armory/src/services/net_guard.py apps/armory/src/capabilities/obsidian/utils/network.py apps/armory/tests/test_net_guard.py
git commit -m "refactor(armory): move address guard to services/net_guard"
```

---

### Task 2: ember_api connection storage

**Files:**
- Create: `apps/Ember/ember_api/src/services/crafty_connections.py`
- Test: `apps/Ember/ember_api/tests/test_crafty_connections.py`

**Interfaces:**
- Consumes: `DocumentStore` (`get/put/create/delete/query`), `SecretBox.encrypt_map/decrypt_map`, `utcnow`.
- Produces:
  - `CraftyError(message, status=409)`
  - `ConnectionInput` fields: `label, endpoint, api_token|None, verify_tls=True, enabled=True, servers: list[ServerEntry], expected_revision=0`; `ServerEntry(name, server_id)`
  - `CraftyConnections(store, box)` with `async get(uid) -> dict`, `async candidate(uid, value) -> dict`, `async save(uid, value) -> dict`, `async clear(uid) -> dict`, `snapshot(row) -> dict`, `async resolve(uid) -> dict`
  - `async purge_owner(store, uid) -> None`
  - Snapshot keys: `label, endpoint, api_token, verify_tls, servers, revision, generation`.
  - Public view keys: `id, label, endpoint, verify_tls, enabled, servers, credential_configured, revision, generation, status` (`status` is `not_configured`, `configured` or `disabled`).

- [ ] **Step 1: Write the failing tests** — `apps/Ember/ember_api/tests/test_crafty_connections.py`

```python
import asyncio

import pytest
from cryptography.fernet import Fernet

from src.services.crafty_connections import CraftyConnections, CraftyError, ConnectionInput, purge_owner
from src.services.secret_box import SecretBox
from tests.conftest import FakeDbGateway

SERVERS = [{"name": "survival", "server_id": "6f1c0a2e-0000-4000-8000-000000000001"}]


def run(coro):
    return asyncio.run(coro)


def make():
    store = FakeDbGateway()
    return store, CraftyConnections(store, SecretBox(Fernet.generate_key().decode()))


def draft(**changes):
    base = dict(label="Home", endpoint="https://zima.lan:8443", api_token="secret-crafty-token", servers=SERVERS)
    return ConnectionInput(**{**base, **changes})


def test_token_is_encrypted_hidden_and_resolvable_with_revisions():
    store, service = make()
    first = run(service.save("alice", draft()))
    assert first["revision"] == 1 and first["credential_configured"] and first["status"] == "configured"
    assert "secret-crafty-token" not in repr(first) and "secret-crafty-token" not in repr(store.records)
    second = run(service.save("alice", draft(api_token=None, label="Renamed", expected_revision=1)))
    assert second["generation"] != first["generation"]
    snapshot = run(service.resolve("alice"))
    assert snapshot["api_token"] == "secret-crafty-token" and snapshot["revision"] == 2
    assert snapshot["servers"] == SERVERS and snapshot["verify_tls"] is True
    with pytest.raises(CraftyError, match="changed"):
        run(service.save("alice", draft(api_token=None, expected_revision=1)))


def test_users_cannot_resolve_each_others_connection():
    _, service = make()
    run(service.save("alice", draft()))
    with pytest.raises(CraftyError) as refused:
        run(service.resolve("bob"))
    assert refused.value.status == 404


def test_not_configured_disabled_and_cleared_connections_refuse_to_resolve():
    _, service = make()
    with pytest.raises(CraftyError) as missing:
        run(service.resolve("alice"))
    assert missing.value.status == 404
    run(service.save("alice", draft()))
    run(service.save("alice", draft(api_token=None, enabled=False, expected_revision=1)))
    with pytest.raises(CraftyError, match="disabled"):
        run(service.resolve("alice"))
    cleared = run(service.clear("alice"))
    assert cleared["credential_configured"] is False and cleared["servers"] == [] and cleared["enabled"] is False


def test_enabling_without_a_token_is_refused():
    _, service = make()
    with pytest.raises(CraftyError) as refused:
        run(service.save("alice", draft(api_token=None)))
    assert refused.value.status == 400


@pytest.mark.parametrize("changes", [
    {"endpoint": "http://zima.lan:8443"},
    {"endpoint": "https://u:p@zima.lan"},
    {"endpoint": "https://zima.lan/?k=v"},
    {"servers": [{"name": "Bad Name", "server_id": "abc"}]},
    {"servers": [{"name": "a", "server_id": "abc"}, {"name": "a", "server_id": "def"}]},
    {"servers": [{"name": "a", "server_id": "../etc"}]},
    {"servers": [{"name": f"s{i}", "server_id": f"id{i}"} for i in range(21)]},
    {"api_token": "bad\ntoken"},
])
def test_invalid_input_is_rejected(changes):
    with pytest.raises(ValueError):
        draft(**changes)


def test_purge_owner_removes_connection_and_revisions():
    store, service = make()
    run(service.save("alice", draft()))
    run(service.save("bob", draft()))
    run(purge_owner(store, "alice"))
    with pytest.raises(CraftyError):
        run(service.resolve("alice"))
    assert run(service.resolve("bob"))["label"] == "Home"
```

- [ ] **Step 2: Run to verify failure**

Run (in `apps/Ember/ember_api`): `python -m pytest tests/test_crafty_connections.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'src.services.crafty_connections'`.

- [ ] **Step 3: Implement `apps/Ember/ember_api/src/services/crafty_connections.py`**

```python
"""Encrypted per-user Crafty connections. Immutable revisions make concurrent saves atomic.

Modeled on brain_connections.py: the head document is only a hint, readers follow
subsequent committed revisions. One connection per account; the token is write-only.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.db import utcnow
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.secret_box import SecretBox, SecretBoxError

COLLECTION = "crafty_connections"
REVISIONS = "crafty_connection_revisions"
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SERVER_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
MAX_SERVERS = 20


class CraftyError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class ServerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    server_id: str

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not NAME.fullmatch(value):
            raise ValueError("Use 1-32 lowercase letters, digits, - or _ for a server name")
        return value

    @field_validator("server_id")
    @classmethod
    def id_valid(cls, value):
        if not SERVER_ID.fullmatch(value):
            raise ValueError("Invalid Crafty server id")
        return value


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    label: str = Field(min_length=1, max_length=80)
    endpoint: str = Field(min_length=1, max_length=1000)
    api_token: str | None = Field(default=None, max_length=4096, repr=False, exclude=True)
    verify_tls: bool = True
    enabled: bool = True
    servers: list[ServerEntry] = Field(default_factory=list, max_length=MAX_SERVERS)
    expected_revision: int = Field(default=0, ge=0)

    @field_validator("endpoint")
    @classmethod
    def endpoint_valid(cls, value):
        try:
            parts = urlsplit(value)
            if (parts.scheme != "https" or not parts.hostname or parts.port == 0 or parts.username
                    or parts.password or parts.query or parts.fragment or any(c.isspace() for c in value)):
                raise ValueError()
        except ValueError:
            raise ValueError("Use an HTTPS endpoint without credentials, query or fragment") from None
        return value.rstrip("/")

    @field_validator("api_token")
    @classmethod
    def token_valid(cls, value):
        if value is not None and (not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError("Enter a valid API token, or leave it unchanged")
        return value

    @field_validator("servers")
    @classmethod
    def names_unique(cls, value):
        names = [entry.name for entry in value]
        if len(names) != len(set(names)):
            raise ValueError("Server names must be unique")
        return value


class CraftyConnections:
    def __init__(self, store: DocumentStore, box: SecretBox):
        self.store, self.box = store, box

    @staticmethod
    def connection_id(uid: str) -> str:
        if not uid:
            raise CraftyError("A signed-in owner is required", 403)
        return "crafty-" + hashlib.sha256(uid.encode()).hexdigest()[:32]

    async def current(self, uid: str) -> dict | None:
        key = self.connection_id(uid)
        row = await self.store.get(COLLECTION, key)
        revision = int(row["revision"]) if row else 0
        while True:
            following = await self.store.get(REVISIONS, f"{key}:{revision + 1}")
            if following is None:
                break
            row, revision = following, revision + 1
        if row and (row.get("id") != key or row.get("owner") != uid):
            raise CraftyError("Crafty connection is unavailable", 503)
        return row

    @staticmethod
    def public(row: dict | None) -> dict:
        if row is None:
            return {"id": None, "label": "", "endpoint": "", "verify_tls": True, "enabled": False,
                    "servers": [], "credential_configured": False, "revision": 0, "generation": None,
                    "status": "not_configured"}
        return {**{key: row[key] for key in ("id", "label", "endpoint", "verify_tls", "enabled", "servers",
                                              "revision", "generation", "updated_at")},
                "credential_configured": bool(row.get("credential")),
                "status": "configured" if row["enabled"] else "disabled"}

    async def get(self, uid: str) -> dict:
        return self.public(await self.current(uid))

    async def candidate(self, uid: str, value: ConnectionInput) -> dict:
        previous = await self.current(uid)
        if (previous["revision"] if previous else 0) != value.expected_revision:
            raise CraftyError("The connection changed. Reload before saving.")
        credential = self.box.encrypt_map({"api_token": value.api_token}) if value.api_token is not None else (
            previous.get("credential") if previous else None)
        if value.enabled and not credential:
            raise CraftyError("Enter the Crafty API token before enabling the connection", 400)
        return {**value.model_dump(exclude={"expected_revision"}),
                "id": self.connection_id(uid), "owner": uid, "credential": credential,
                "revision": value.expected_revision + 1, "generation": uuid.uuid4().hex,
                "updated_at": utcnow().isoformat()}

    async def _commit(self, row: dict) -> dict:
        if not await self.store.create(REVISIONS, f"{row['id']}:{row['revision']}", row):
            raise CraftyError("The connection changed. Reload before saving.")
        try:
            await self.store.put(COLLECTION, row["id"], row)
        except DbGatewayError:
            pass  # The committed revision remains discoverable from its predecessor.
        return self.public(row)

    async def save(self, uid: str, value: ConnectionInput) -> dict:
        return await self._commit(await self.candidate(uid, value))

    async def clear(self, uid: str) -> dict:
        previous = await self.current(uid)
        if previous is None:
            return self.public(None)
        return await self._commit({**previous, "enabled": False, "credential": None, "servers": [],
                                   "revision": previous["revision"] + 1, "generation": uuid.uuid4().hex,
                                   "updated_at": utcnow().isoformat()})

    def snapshot(self, row: dict) -> dict:
        try:
            token = self.box.decrypt_map(row["credential"])["api_token"]
        except (SecretBoxError, KeyError, TypeError):
            raise CraftyError("The Crafty token cannot be read. Enter it again.", 503) from None
        return {"label": row["label"], "endpoint": row["endpoint"], "api_token": token,
                "verify_tls": row["verify_tls"], "servers": row["servers"],
                "revision": row["revision"], "generation": row["generation"]}

    async def resolve(self, uid: str) -> dict:
        if not uid:
            raise CraftyError("A signed-in user is required", 403)
        row = await self.current(uid)
        if row is None:
            raise CraftyError("Crafty is not set up for this account", 404)
        if not row["enabled"]:
            raise CraftyError("This Crafty connection is disabled")
        return self.snapshot(row)


async def purge_owner(store: DocumentStore, uid: str) -> None:
    for collection in (COLLECTION, REVISIONS):
        while docs := await store.query(collection, {"owner": uid}, limit=500):
            for row in docs:
                key = f"{row['id']}:{row['revision']}" if collection == REVISIONS else row["id"]
                await store.delete(collection, key)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_crafty_connections.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/services/crafty_connections.py apps/Ember/ember_api/tests/test_crafty_connections.py
git commit -m "feat(ember_api): encrypted per-user Crafty connections"
```

---

### Task 3: ember_api routes, armory gateway client, wiring

**Files:**
- Create: `apps/Ember/ember_api/src/services/crafty_gateway.py`, `apps/Ember/ember_api/src/routes/crafty.py`
- Modify: `apps/Ember/ember_api/src/app.py` (router + error handler, near lines 211 and 236), `apps/Ember/ember_api/src/routes/admin.py` (purge, near line 328)
- Test: `apps/Ember/ember_api/tests/test_crafty_routes.py`

**Interfaces:**
- Consumes: Task 2 (`CraftyConnections`, `CraftyError`, `ConnectionInput`, `purge_owner`); `routes/brains.valid_account` (login + email-verified dependency).
- Produces:
  - `CraftyGateway(client, mcp_url, token).test(uid, snapshot) -> dict` (POSTs `{"operation": "test", "candidate": snapshot}` to `<mcp base>/crafty/operation`)
  - Routes under `/api/crafty`: `GET/PUT/DELETE /connection`, `POST /connection/test`, `POST /internal/resolve`.
  - `routes.crafty.gateway(request) -> CraftyGateway` (a FastAPI dependency tests override).

- [ ] **Step 1: Write the failing tests** — `apps/Ember/ember_api/tests/test_crafty_routes.py`

```python
from src.routes import crafty
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/crafty/connection"
BODY = {"label": "Home", "endpoint": "https://zima.lan:8443", "api_token": "private-crafty-token",
        "servers": [{"name": "survival", "server_id": "6f1c0a2e-0000-4000-8000-000000000001"}]}


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def test(self, uid, snapshot):
        self.calls.append((uid, snapshot))
        return {"status": "connected", "servers": [{"server_id": "abc", "server_name": "Survival"}],
                "message": "Connected"}


def test_connection_requires_login_and_never_returns_the_token(client):
    assert client.get(URL).status_code == 401
    as_admin(client)
    assert client.get(URL).json()["status"] == "not_configured"
    saved = client.put(URL, json=BODY)
    assert saved.status_code == 200, saved.text
    assert "private-crafty-token" not in saved.text and saved.json()["credential_configured"]
    assert "private-crafty-token" not in client.get(URL).text
    stale = client.put(URL, json=BODY)
    assert stale.status_code == 409
    invalid = client.put(URL, json={**BODY, "endpoint": "http://zima.lan", "expected_revision": 1})
    assert invalid.status_code == 422 and "private-crafty-token" not in invalid.text


def test_members_only_see_their_own_connection(client, email):
    make_member(client, email, "alice")
    login(client, "alice")
    assert client.put(URL, json=BODY).status_code == 200
    make_member(client, "bob@example.com", "bob")
    login(client, "bob")
    assert client.get(URL).json()["status"] == "not_configured"


def test_delete_clears_the_credential(client):
    as_admin(client)
    client.put(URL, json=BODY)
    cleared = client.delete(URL)
    assert cleared.status_code == 200
    assert cleared.json()["credential_configured"] is False and cleared.json()["servers"] == []


def test_test_endpoint_sends_the_candidate_to_armory_without_saving(client):
    as_admin(client)
    fake = FakeGateway()
    client.app.dependency_overrides[crafty.gateway] = lambda: fake
    try:
        result = client.post(URL + "/test", json=BODY)
    finally:
        client.app.dependency_overrides.pop(crafty.gateway, None)
    assert result.status_code == 200 and result.json()["servers"][0]["server_name"] == "Survival"
    assert fake.calls[0][1]["api_token"] == "private-crafty-token"
    assert client.get(URL).json()["status"] == "not_configured"


def test_internal_resolve_needs_the_internal_token_and_a_real_user(client):
    as_admin(client)
    client.put(URL, json=BODY)
    assert client.post("/api/crafty/internal/resolve").status_code == 401
    client.app.state.internal_token = "internal-crafty-token"
    bogus = {"X-Internal-Token": "internal-crafty-token", "X-Requester-Uid": "invented"}
    assert client.post("/api/crafty/internal/resolve", headers=bogus).status_code == 403
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_crafty_routes.py -v`
Expected: FAIL (`cannot import name 'crafty' from 'src.routes'`).

- [ ] **Step 3: Create `apps/Ember/ember_api/src/services/crafty_gateway.py`**

```python
"""Private HTTP transport to Armory's Crafty connection test."""
import httpx

from src.services.crafty_connections import CraftyError
from src.services.mcp_server_info import base_url


class CraftyGateway:
    def __init__(self, client, mcp_url: str, token: str | None):
        self.client, self.url, self.token = client, base_url(mcp_url) + "/crafty/operation", token

    async def test(self, uid: str, snapshot: dict) -> dict:
        if not self.token or not uid:
            raise CraftyError("Crafty transport requires configured internal authentication", 503)
        try:
            response = await self.client.post(
                self.url, headers={"X-Internal-Token": self.token, "X-Requester-Uid": uid},
                json={"operation": "test", "candidate": snapshot}, timeout=30, follow_redirects=False)
        except httpx.HTTPError:
            raise CraftyError("Crafty service is unavailable", 503) from None
        try:
            body = response.json()
        except ValueError:
            body = None
        if not response.is_success:
            # Armory writes only safe messages: no token, no raw Crafty body.
            message = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), str) else None
            raise CraftyError(message or "Crafty test failed", 502 if response.status_code >= 500 else 400)
        if not isinstance(body, dict):
            raise CraftyError("Crafty service returned an invalid response", 503)
        return body
```

- [ ] **Step 4: Create `apps/Ember/ember_api/src/routes/crafty.py`**

```python
"""Per-user Crafty connection. Internal snapshots never reach browsers."""
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from src.deps import get_db_gateway, get_db_session, get_secret_box, get_settings
from src.models import Account
from src.routes.brains import valid_account
from src.services.crafty_connections import ConnectionInput, CraftyConnections
from src.services.crafty_gateway import CraftyGateway

router = APIRouter(prefix="/api/crafty", tags=["crafty"])


def connections(store=Depends(get_db_gateway), box=Depends(get_secret_box)):
    return CraftyConnections(store, box)


def gateway(request: Request):
    return CraftyGateway(request.app.state.upstream, request.app.state.settings.mcp_server_url,
                         request.app.state.internal_token)


@router.get("/connection")
async def get_connection(account=Depends(valid_account), service=Depends(connections)):
    return await service.get(account.uid)


@router.put("/connection")
async def save_connection(body: ConnectionInput, request: Request, account=Depends(valid_account),
                          service=Depends(connections)):
    result = await service.save(account.uid, body)
    await request.app.state.logs.action(account, "crafty.connection_save", f"revision={result['revision']}")
    return result


@router.delete("/connection")
async def clear_connection(request: Request, account=Depends(valid_account), service=Depends(connections)):
    result = await service.clear(account.uid)
    await request.app.state.logs.action(account, "crafty.connection_clear", f"revision={result['revision']}")
    return result


@router.post("/connection/test")
async def test_connection(body: ConnectionInput, account=Depends(valid_account),
                          service=Depends(connections), remote=Depends(gateway)):
    candidate = await service.candidate(account.uid, body)
    return await remote.test(account.uid, service.snapshot(candidate))


@router.post("/internal/resolve")
async def resolve_connection(request: Request, service=Depends(connections),
                             session=Depends(get_db_session), settings=Depends(get_settings)):
    token = request.app.state.internal_token
    if not token or not hmac.compare_digest(token, request.headers.get("X-Internal-Token", "")):
        raise HTTPException(401, "Valid internal authentication required")
    uid = request.headers.get("X-Requester-Uid", "")
    account = await session.scalar(select(Account).where(Account.uid == uid)) if uid else None
    if account is None or not account.is_active or settings.require_email_verification and not account.email_verified:
        raise HTTPException(403, "A valid signed-in requester is required")
    return await service.resolve(account.uid)
```

- [ ] **Step 5: Wire it in `app.py` and `admin.py`**

In `apps/Ember/ember_api/src/app.py`: add `crafty` to the existing `from src.routes import ...` line (line 16 area: `from src.routes import brains` is an import in that block — add `crafty` beside it), add `from src.services.crafty_connections import CraftyError` beside line 17, then:

```python
    app.include_router(brains.router)
    app.include_router(crafty.router)
```

and next to the `BrainError` handler (line ~236):

```python
    @app.exception_handler(CraftyError)
    async def crafty_error(_request: Request, error: CraftyError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)
```

Also extend the validation handler so a bad Crafty body never echoes the token (line ~242):

```python
        if request.url.path.startswith("/api/crafty"):
            return JSONResponse({"detail": "Invalid Crafty request. Check the fields and limits."}, status_code=422)
```

Place it as a second `if` directly after the existing `/api/brains` branch; leave the brains branch and its message untouched.

In `apps/Ember/ember_api/src/routes/admin.py`, add `from src.services.crafty_connections import purge_owner as purge_crafty` beside line 37 and add `await purge_crafty(store, uid)` directly after `await purge_brains(store, uid)` (line ~328).

- [ ] **Step 6: Run the new tests plus the neighbours**

Run: `python -m pytest tests/test_crafty_routes.py tests/test_crafty_connections.py tests/test_brain_routes.py tests/test_admin.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/Ember/ember_api/src apps/Ember/ember_api/tests/test_crafty_routes.py
git commit -m "feat(ember_api): Crafty connection routes and armory gateway"
```

---

### Task 4: armory Crafty client

**Files:**
- Create: `apps/armory/src/capabilities/crafty/__init__.py`, `apps/armory/src/capabilities/crafty/utils/__init__.py`, `apps/armory/src/capabilities/crafty/utils/client.py`
- Test: `apps/armory/tests/test_crafty_client.py`

**Interfaces:**
- Produces:
  - `CraftyError(message, *, status=None)`
  - `CraftyClient(endpoint: str, api_token: str, *, verify_tls: bool = True, timeout: float = 10.0)`
  - `.list_servers() -> list[dict]` (each `{"server_id": str, "server_name": str}`)
  - `.stats(server_id: str) -> dict` (Crafty's `data` object)
  - `.action(server_id: str, action: Literal["start","stop","restart"]) -> None`
  - Network is reached only through `_send(method, path) -> bytes`, which tests replace.

- [ ] **Step 1: Write the failing tests** — `apps/armory/tests/test_crafty_client.py`

```python
import json
import urllib.error

import pytest

from src.capabilities.crafty.utils.client import CraftyClient, CraftyError


def client(verify_tls=True):
    return CraftyClient("https://zima.lan:8443", "tok-123", verify_tls=verify_tls)


def reply(payload):
    return lambda self, method, path: json.dumps(payload).encode()


def test_list_servers_returns_ids_and_names(monkeypatch):
    monkeypatch.setattr(CraftyClient, "_send", reply({"status": "ok", "data": [
        {"server_id": "abc-1", "server_name": "Survival", "extra": 1}]}))
    assert client().list_servers() == [{"server_id": "abc-1", "server_name": "Survival"}]


def test_stats_returns_the_data_object(monkeypatch):
    monkeypatch.setattr(CraftyClient, "_send", reply({"status": "ok", "data": {"running": True, "online": 2}}))
    assert client().stats("abc-1")["online"] == 2


def test_action_posts_the_crafty_action_name(monkeypatch):
    seen = []
    monkeypatch.setattr(CraftyClient, "_send", lambda self, method, path: seen.append((method, path)) or b'{"status":"ok"}')
    client().action("abc-1", "restart")
    assert seen == [("POST", "/api/v2/servers/abc-1/action/restart_server")]


def test_error_status_becomes_a_crafty_error_without_the_token(monkeypatch):
    monkeypatch.setattr(CraftyClient, "_send", reply({"status": "error", "error": "SERVER_NOT_FOUND"}))
    with pytest.raises(CraftyError) as failed:
        client().stats("abc-1")
    assert "SERVER_NOT_FOUND" in str(failed.value) and "tok-123" not in str(failed.value)


@pytest.mark.parametrize("payload", [[], {"status": "ok", "data": "nope"}, {"status": "ok"}])
def test_list_servers_rejects_malformed_replies(monkeypatch, payload):
    monkeypatch.setattr(CraftyClient, "_send", reply(payload))
    with pytest.raises(CraftyError):
        client().list_servers()


@pytest.mark.parametrize("server_id", ["../x", "a/b", "", "a b"])
def test_bad_server_ids_never_reach_the_network(monkeypatch, server_id):
    monkeypatch.setattr(CraftyClient, "_send", lambda *a: pytest.fail("sent"))
    with pytest.raises(CraftyError):
        client().stats(server_id)


def test_unknown_action_is_refused(monkeypatch):
    monkeypatch.setattr(CraftyClient, "_send", lambda *a: pytest.fail("sent"))
    with pytest.raises(CraftyError):
        client().action("abc-1", "kill")


@pytest.mark.parametrize("endpoint", ["http://zima.lan", "https://u:p@zima.lan", "https://zima.lan/?a=b", ""])
def test_endpoint_must_be_plain_https(endpoint):
    with pytest.raises(CraftyError):
        CraftyClient(endpoint, "tok")


def test_http_errors_map_to_safe_messages(monkeypatch):
    def refuse(self, method, path):
        raise CraftyError("Crafty rejected the API token.", status=401)
    monkeypatch.setattr(CraftyClient, "_send", refuse)
    with pytest.raises(CraftyError, match="rejected"):
        client().list_servers()


def test_send_maps_urllib_failures(monkeypatch):
    c = client()

    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)

    c._opener = Opener()
    with pytest.raises(CraftyError) as failed:
        c._send("GET", "/api/v2/servers")
    assert failed.value.status == 401 and "tok-123" not in str(failed.value)
```

- [ ] **Step 2: Run to verify failure**

Run (in `apps/armory`): `python -m pytest tests/test_crafty_client.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'src.capabilities.crafty'`.

- [ ] **Step 3: Create the package files**

`apps/armory/src/capabilities/crafty/utils/__init__.py`: empty file.

`apps/armory/src/capabilities/crafty/__init__.py`:

```python
"""Crafty: list, inspect, start, stop and restart the Minecraft servers in the
caller's own Crafty Controller."""

from src.services import capability_meta

META = capability_meta.register(folder="crafty", id="crafty", label="Crafty")
```

- [ ] **Step 4: Implement `apps/armory/src/capabilities/crafty/utils/client.py`**

```python
"""Crafty Controller v2 REST client, ported from TwinksDCBot's core/crafty/client.py.

Errors never include the token, the endpoint, or Crafty's raw response body.
"""

from __future__ import annotations

import json
import math
import re
import ssl
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from src.services.net_guard import NoRedirect, PinnedHTTPSHandler

MAX_RESPONSE_BYTES = 1_000_000
SERVER_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
ACTIONS = {"start": "start_server", "stop": "stop_server", "restart": "restart_server"}


class CraftyError(Exception):
    """A safe message for the caller to relay verbatim."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CraftyClient:
    def __init__(self, endpoint: str, api_token: str, *, verify_tls: bool = True, timeout: float = 10.0) -> None:
        try:
            url = urlsplit(endpoint)
            valid = (url.scheme == "https" and url.hostname and url.port != 0 and not url.username
                     and not url.password and not url.query and not url.fragment
                     and not any(char.isspace() for char in endpoint))
        except ValueError:
            valid = False
        if not valid:
            raise CraftyError("The Crafty address must be an HTTPS URL without credentials, query or fragment.")
        if not api_token.strip() or any(ord(char) < 32 or ord(char) == 127 for char in api_token):
            raise CraftyError("The Crafty API token is missing or invalid.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise CraftyError("The Crafty timeout must be a positive number of seconds.")
        self._base = endpoint.rstrip("/")
        self._token = api_token
        self._timeout = timeout
        context = ssl.create_default_context()
        if verify_tls is False:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self._opener = urllib.request.build_opener(
            PinnedHTTPSHandler(context=context, personal=True), urllib.request.ProxyHandler({}), NoRedirect())

    def list_servers(self) -> list[dict[str, str]]:
        data = self._data("GET", "/api/v2/servers")
        if not isinstance(data, list):
            raise CraftyError("Crafty returned an invalid server list.")
        servers = []
        for item in data:
            if not isinstance(item, dict) or "server_id" not in item:
                raise CraftyError("Crafty returned an invalid server list.")
            servers.append({"server_id": str(item["server_id"]), "server_name": str(item.get("server_name", ""))})
        return servers

    def stats(self, server_id: str) -> dict[str, Any]:
        data = self._data("GET", f"/api/v2/servers/{self._id(server_id)}/stats")
        if not isinstance(data, dict):
            raise CraftyError("Crafty returned invalid server stats.")
        return data

    def action(self, server_id: str, action: str) -> None:
        if action not in ACTIONS:
            raise CraftyError(f"Unsupported Crafty action: {action}.")
        self._data("POST", f"/api/v2/servers/{self._id(server_id)}/action/{ACTIONS[action]}")

    @staticmethod
    def _id(server_id: str) -> str:
        if not SERVER_ID.fullmatch(server_id):
            raise CraftyError("That Crafty server id is not valid.")
        return server_id

    def _data(self, method: str, path: str) -> Any:
        try:
            payload = json.loads(self._send(method, path))
        except (ValueError, UnicodeDecodeError):
            raise CraftyError("Crafty returned an invalid response: expected JSON.") from None
        if not isinstance(payload, dict):
            raise CraftyError("Crafty returned an invalid response.")
        if payload.get("status") != "ok":
            reason = payload.get("error")
            raise CraftyError(f"Crafty refused the request: {reason}." if isinstance(reason, str) and reason
                              else "Crafty refused the request.")
        return payload.get("data")

    def _send(self, method: str, path: str) -> bytes:
        request = urllib.request.Request(
            self._base + path, headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            method=method)
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise CraftyError("Crafty's response exceeds the 1 MB safety limit.")
                return raw
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            message = {
                401: "Crafty rejected the API token. Enter a fresh token in Settings.",
                403: "Crafty refused access to this operation. Check the token's permissions.",
                404: "Crafty could not find that server or endpoint.",
                429: "Crafty received too many requests. Try again later.",
            }.get(code, "Crafty refused a redirect." if 300 <= code < 400 else f"Crafty answered HTTP {code}.")
            raise CraftyError(message, status=code) from None
        except (urllib.error.URLError, OSError) as error:
            reason = error.reason if isinstance(error, urllib.error.URLError) else error
            if isinstance(reason, ssl.SSLError):
                message = "Crafty TLS verification failed. Trust its certificate or turn off 'Verify TLS' for this connection."
            elif isinstance(reason, TimeoutError):
                message = "Crafty timed out. Check that it is running and reachable from the Citadel server."
            else:
                message = "Could not reach Crafty. Check the address and that the Citadel server can route to it."
            raise CraftyError(message) from None
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_crafty_client.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/armory/src/capabilities/crafty apps/armory/tests/test_crafty_client.py
git commit -m "feat(armory): Crafty REST client with address guard"
```

---

### Task 5: armory contract, domain, resolver, tools, docs

**Files:**
- Create: `apps/armory/src/capabilities/crafty/contract.py`, `domain.py`, `tool.py`, `utils/resolver.py`, `help.json`, `README.md`
- Modify: `apps/armory/tests/test_read_only_declarations.py` (add `"crafty"` read tools)
- Test: `apps/armory/tests/test_crafty_domain.py`, `apps/armory/tests/test_crafty_tools.py`

**Interfaces:**
- Consumes: Task 4 (`CraftyClient`, `CraftyError`), `services.identity_context.current_uid`, `config.settings.ember_api_url` and `settings.internal_api_token`.
- Produces:
  - `utils.resolver.resolve(uid: str | None = None) -> dict` (the snapshot: `label, endpoint, api_token, verify_tls, servers, revision, generation`)
  - `domain.list_servers(snapshot) -> ServerListResult`, `domain.get_status(snapshot, server) -> ServerStatusResult`, `domain.run_action(snapshot, server, action) -> ServerActionResult`, `domain.test_connection(snapshot) -> dict`, `domain.status_fields(data: dict) -> dict`
  - Tools: `tool_crafty_listServers`, `tool_crafty_getStatus(server)`, `tool_crafty_startServer(server)`, `tool_crafty_stopServer(server)`, `tool_crafty_restartServer(server)`

- [ ] **Step 1: Write the failing domain tests** — `apps/armory/tests/test_crafty_domain.py`

```python
import pytest

from src.capabilities.crafty import domain
from src.capabilities.crafty.utils.client import CraftyError

SNAPSHOT = {"label": "Home", "endpoint": "https://zima.lan:8443", "api_token": "tok", "verify_tls": True,
            "servers": [{"name": "survival", "server_id": "id-1"}, {"name": "creative", "server_id": "id-2"}],
            "revision": 1, "generation": "g"}


class FakeClient:
    stats_by_id = {
        "id-1": {"running": True, "online": 2, "max": 20, "version": "1.21", "cpu": 12.5, "mem": "2147483648",
                 "players": '["Alex","Sam"]', "world_name": "world"},
        "id-2": {"running": False},
    }
    actions: list = []

    def __init__(self, endpoint, api_token, *, verify_tls=True, timeout=10.0):
        pass

    def stats(self, server_id):
        if server_id == "id-bad":
            raise CraftyError("Crafty timed out.")
        return self.stats_by_id[server_id]

    def action(self, server_id, action):
        self.actions.append((server_id, action))

    def list_servers(self):
        return [{"server_id": "id-1", "server_name": "Survival"}]


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    FakeClient.actions = []
    monkeypatch.setattr(domain, "CraftyClient", FakeClient)


def test_status_fields_parse_players_given_as_a_json_string_and_humanize_memory():
    fields = domain.status_fields(FakeClient.stats_by_id["id-1"])
    assert fields["players"] == ["Alex", "Sam"] and fields["mem"] == "2.0 GB" and fields["running"] is True


def test_status_fields_tolerate_missing_values():
    fields = domain.status_fields({})
    assert fields == {"running": False, "online": 0, "max": 0, "version": "Unknown", "cpu": None,
                      "mem": None, "players": [], "world_name": None}


def test_status_fields_tolerate_unparseable_players():
    assert domain.status_fields({"players": "not json"})["players"] == []


def test_list_servers_reports_each_server_and_isolates_one_failure(monkeypatch):
    snapshot = {**SNAPSHOT, "servers": SNAPSHOT["servers"] + [{"name": "broken", "server_id": "id-bad"}]}
    result = domain.list_servers(snapshot)
    by_name = {s.name: s for s in result.servers}
    assert by_name["survival"].running is True and by_name["survival"].online == 2
    assert by_name["creative"].running is False
    assert by_name["broken"].running is None and "timed out" in by_name["broken"].error
    assert "survival" in result.message


def test_list_servers_with_no_named_servers_explains_setup():
    result = domain.list_servers({**SNAPSHOT, "servers": []})
    assert result.servers == [] and "Settings" in result.message


def test_get_status_for_a_named_server():
    result = domain.get_status(SNAPSHOT, "survival")
    assert result.name == "survival" and result.online == 2 and result.players == ["Alex", "Sam"]
    assert "2 / 20" in result.message


def test_unknown_server_name_lists_the_known_names():
    with pytest.raises(KeyError) as unknown:
        domain.get_status(SNAPSHOT, "nether")
    assert "survival" in str(unknown.value) and "creative" in str(unknown.value)


@pytest.mark.parametrize("action,word", [("start", "starting"), ("stop", "stopping"), ("restart", "restarting")])
def test_run_action_calls_crafty_and_confirms(action, word):
    result = domain.run_action(SNAPSHOT, "survival", action)
    assert FakeClient.actions == [("id-1", action)]
    assert result.action == action and word in result.message


def test_test_connection_returns_the_servers_crafty_reports():
    result = domain.test_connection(SNAPSHOT)
    assert result["status"] == "connected" and result["servers"] == [{"server_id": "id-1", "server_name": "Survival"}]
```

- [ ] **Step 2: Run to verify failure**

Run (in `apps/armory`): `python -m pytest tests/test_crafty_domain.py -v`
Expected: FAIL, `ImportError: cannot import name 'domain'`.

- [ ] **Step 3: Create `contract.py`**

```python
"""Result models for the crafty tools. Every result ends with a `message`
meant to be relayed to a person verbatim."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ServerInfo(BaseModel):
    name: str = Field(description="The short name the user gave this server in Settings.")
    running: bool | None = Field(description="True when the server is running; null when Crafty could not be asked.")
    online: int = Field(default=0, description="Players online right now.")
    max: int = Field(default=0, description="Player slot limit.")
    version: str = Field(default="Unknown", description="Minecraft version.")
    error: str | None = Field(default=None, description="Why this server could not be read, when running is null.")


class ServerListResult(BaseModel):
    servers: list[ServerInfo] = Field(description="Every server the user named, with live state.")
    message: str = Field(description="Human-readable table of the same data, safe to relay verbatim.")


class ServerStatusResult(BaseModel):
    name: str = Field(description="The short server name.")
    running: bool = Field(description="True when the server is running.")
    online: int = Field(description="Players online right now.")
    max: int = Field(description="Player slot limit.")
    version: str = Field(description="Minecraft version.")
    cpu: float | None = Field(default=None, description="CPU use in percent, when running.")
    mem: str | None = Field(default=None, description="Memory use, human readable, when running.")
    world_name: str | None = Field(default=None, description="The world the server loaded.")
    players: list[str] = Field(default_factory=list, description="Names of the players online.")
    message: str = Field(description="Human-readable summary, safe to relay verbatim.")


class ServerActionResult(BaseModel):
    name: str = Field(description="The server that was acted on.")
    action: str = Field(description="Which action ran: start, stop, or restart.")
    message: str = Field(description="Human-readable confirmation, safe to relay verbatim.")
```

- [ ] **Step 4: Create `domain.py`**

```python
"""Start, stop, restart and inspect the Minecraft servers in the caller's Crafty.

Every function takes the caller's connection `snapshot` (see utils/resolver.py)
and builds a client for that call only: connections are per user, nothing is
cached between calls.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from src.capabilities.crafty.contract import (
    ServerActionResult,
    ServerInfo,
    ServerListResult,
    ServerStatusResult,
)
from src.capabilities.crafty.utils.client import CraftyClient, CraftyError

_UNITS = ("B", "KB", "MB", "GB", "TB")


def _client(snapshot: dict) -> CraftyClient:
    return CraftyClient(snapshot["endpoint"], snapshot["api_token"], verify_tls=snapshot["verify_tls"])


def _server_id(snapshot: dict, name: str) -> str:
    for entry in snapshot["servers"]:
        if entry["name"] == name:
            return entry["server_id"]
    known = ", ".join(entry["name"] for entry in snapshot["servers"])
    raise KeyError(f"No Minecraft server named {name!r}. {'Servers available: ' + known + '.' if known else 'No servers are set up yet.'}")


def _human_bytes(value) -> str | None:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return None
    unit = 0
    while size >= 1024 and unit < len(_UNITS) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f} {_UNITS[unit]}"


def status_fields(data: dict) -> dict:
    """Crafty's stats object as plain fields; ported from TwinksDCBot's MinecraftService.get_status."""
    players = data.get("players") or []
    if isinstance(players, str):
        try:
            players = json.loads(players)
        except (json.JSONDecodeError, TypeError):
            players = []
    if not isinstance(players, list):
        players = []
    return {
        "running": bool(data.get("running")),
        "online": int(data.get("online") or 0),
        "max": int(data.get("max") or 0),
        "version": data.get("version") or "Unknown",
        "cpu": data.get("cpu"),
        "mem": _human_bytes(data.get("mem")) if data.get("mem") is not None else None,
        "players": [str(player) for player in players],
        "world_name": data.get("world_name"),
    }


def list_servers(snapshot: dict) -> ServerListResult:
    entries = snapshot["servers"]
    if not entries:
        return ServerListResult(servers=[], message="No servers are set up yet. Add them in Settings, Crafty.")
    client = _client(snapshot)

    def read(entry: dict) -> ServerInfo:
        try:
            fields = status_fields(client.stats(entry["server_id"]))
        except CraftyError as error:
            return ServerInfo(name=entry["name"], running=None, error=str(error))
        return ServerInfo(name=entry["name"], running=fields["running"], online=fields["online"],
                          max=fields["max"], version=fields["version"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        servers = list(pool.map(read, entries))
    width = max(len(server.name) for server in servers)
    lines = []
    for server in servers:
        state = "unreachable" if server.running is None else "running" if server.running else "stopped"
        players = f"{server.online}/{server.max}" if server.running else "-"
        lines.append(f"{server.name:<{width}}  {state:<11} {players:<7} {server.version if server.running else ''}".rstrip())
    return ServerListResult(servers=servers, message="\n".join(lines))


def get_status(snapshot: dict, server: str) -> ServerStatusResult:
    fields = status_fields(_client(snapshot).stats(_server_id(snapshot, server)))
    if fields["running"]:
        summary = f"{server} is running: {fields['online']} / {fields['max']} players, version {fields['version']}."
        if fields["players"]:
            summary += f" Online now: {', '.join(fields['players'])}."
    else:
        summary = f"{server} is stopped."
    return ServerStatusResult(name=server, message=summary, **fields)


_WORDS = {"start": "starting", "stop": "stopping", "restart": "restarting"}


def run_action(snapshot: dict, server: str, action: str) -> ServerActionResult:
    _client(snapshot).action(_server_id(snapshot, server), action)
    return ServerActionResult(name=server, action=action, message=f"{server} is {_WORDS[action]}.")


def test_connection(snapshot: dict) -> dict:
    servers = _client(snapshot).list_servers()
    return {"status": "connected", "servers": servers, "message": f"Connected. Crafty reports {len(servers)} server(s)."}
```

- [ ] **Step 5: Create `utils/resolver.py`**

```python
"""Fetch the caller's current Crafty connection from ember_api. The token lives
only in the returned dict for the duration of one call."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from src.capabilities.crafty.utils.client import CraftyError
from src.config import settings
from src.services import identity_context
from src.services.net_guard import NoRedirect

_REFUSALS = {
    404: "Set up your Crafty connection in Settings first.",
    409: "Your Crafty connection is disabled. Enable it in Settings.",
}


def resolve(uid: str | None = None) -> dict:
    uid = uid if uid is not None else identity_context.current_uid()
    if not settings.internal_api_token or not uid:
        raise CraftyError("Crafty access requires a signed-in user and configured internal authentication.")
    request = urllib.request.Request(
        settings.ember_api_url.rstrip("/") + "/api/crafty/internal/resolve", data=b"{}", method="POST",
        headers={"X-Internal-Token": settings.internal_api_token, "X-Requester-Uid": uid,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=5) as response:
            raw = response.read(64_001)
            if len(raw) > 64_000:
                raise ValueError()
            snapshot = json.loads(raw)
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        raise CraftyError(_REFUSALS.get(code, "Crafty connection is unavailable or access was refused.")) from None
    except (OSError, ValueError):
        raise CraftyError("Crafty connection is unavailable or access was refused.") from None
    needed = {"endpoint", "api_token", "verify_tls", "servers"}
    if not isinstance(snapshot, dict) or not needed <= snapshot.keys():
        raise CraftyError("Crafty connection is unavailable or access was refused.")
    return snapshot
```

- [ ] **Step 6: Write the failing tool tests** — `apps/armory/tests/test_crafty_tools.py`

```python
import asyncio

import pytest

from src.capabilities.crafty import tool
from src.capabilities.crafty.contract import ServerActionResult

SNAPSHOT = {"endpoint": "https://zima.lan", "api_token": "t", "verify_tls": True,
            "servers": [{"name": "survival", "server_id": "id-1"}]}


@pytest.fixture
def calls(monkeypatch):
    log = []
    monkeypatch.setattr(tool.resolver, "resolve", lambda: log.append("resolve") or SNAPSHOT)
    monkeypatch.setattr(
        tool.domain, "run_action",
        lambda snapshot, server, action: log.append((action, server)) or ServerActionResult(name=server, action=action, message="m"))
    return log


@pytest.mark.parametrize("function,action", [
    (tool.tool_crafty_startServer, "start"),
    (tool.tool_crafty_stopServer, "stop"),
    (tool.tool_crafty_restartServer, "restart"),
])
def test_control_tools_resolve_the_callers_connection_then_act(calls, function, action):
    asyncio.run(function("survival"))
    assert calls == ["resolve", (action, "survival")]


def test_a_missing_connection_stops_before_any_action(monkeypatch, calls):
    from src.capabilities.crafty.utils.client import CraftyError

    def refuse():
        raise CraftyError("Set up your Crafty connection in Settings first.")

    monkeypatch.setattr(tool.resolver, "resolve", refuse)
    with pytest.raises(CraftyError):
        asyncio.run(tool.tool_crafty_startServer("survival"))
    assert calls == []
```

- [ ] **Step 7: Create `tool.py`**

```python
"""MCP tool wrappers for the crafty capability - thin on purpose.
Each call resolves the caller's own connection, then calls the domain function."""

from __future__ import annotations

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

from src.capabilities.crafty import domain
from src.capabilities.crafty.contract import ServerActionResult, ServerListResult, ServerStatusResult
from src.capabilities.crafty.utils import resolver
from src.commands import command
from src.offload import offload
from src.server import mcp

_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

ServerName = Annotated[
    str,
    Field(description="The server's short name as set in Settings, Crafty (for example 'survival'). "
                      "`tool_crafty_listServers` shows every name.", min_length=1, max_length=32),
]


@command(name="list", description="List my Minecraft servers")
@mcp.tool(
    meta={"keywords": ["minecraft", "crafty", "server", "servers", "list", "status", "players"],
          "display_label": "Listing Minecraft servers"},
    annotations=_READ_ONLY,
)
@offload
def tool_crafty_listServers() -> ServerListResult:
    """List the Minecraft servers in the caller's own Crafty, with whether each is
    running and how many players are online. Returns the exact `server` names to
    pass to the other crafty tools. If the caller has not set up Crafty, the error
    says to do it in Settings."""
    return domain.list_servers(resolver.resolve())


@command(name="status", description="Show one Minecraft server's status")
@mcp.tool(
    meta={"keywords": ["minecraft", "crafty", "server", "status", "players", "online", "cpu", "memory"],
          "display_label": "Reading Minecraft server status"},
    annotations=_READ_ONLY,
)
@offload
def tool_crafty_getStatus(server: ServerName) -> ServerStatusResult:
    """Read one Minecraft server's state: running or stopped, players online and
    their names, version, CPU, memory and world. Read-only."""
    return domain.get_status(resolver.resolve(), server)


@command(name="start", description="Start a Minecraft server")
@mcp.tool(meta={"keywords": ["minecraft", "crafty", "server", "start"], "display_label": "Starting Minecraft server"})
@offload
def tool_crafty_startServer(server: ServerName) -> ServerActionResult:
    """Start a stopped Minecraft server in the caller's Crafty. Crafty starts it in
    the background, so check `tool_crafty_getStatus` a little later."""
    return domain.run_action(resolver.resolve(), server, "start")


@command(name="stop", description="Stop a Minecraft server")
@mcp.tool(meta={"keywords": ["minecraft", "crafty", "server", "stop"], "display_label": "Stopping Minecraft server"})
@offload
def tool_crafty_stopServer(server: ServerName) -> ServerActionResult:
    """Stop a running Minecraft server in the caller's Crafty. Players are
    disconnected. The world is saved by Crafty's normal stop."""
    return domain.run_action(resolver.resolve(), server, "stop")


@command(name="restart", description="Restart a Minecraft server")
@mcp.tool(meta={"keywords": ["minecraft", "crafty", "server", "restart"], "display_label": "Restarting Minecraft server"})
@offload
def tool_crafty_restartServer(server: ServerName) -> ServerActionResult:
    """Restart a Minecraft server in the caller's Crafty: stop, then start.
    Players are disconnected."""
    return domain.run_action(resolver.resolve(), server, "restart")
```

- [ ] **Step 8: Pin the read-only tools** — in `apps/armory/tests/test_read_only_declarations.py` add to `READ_ONLY` (after the `"memory"` line):

```python
    "crafty": {"tool_crafty_listServers", "tool_crafty_getStatus"},
```

and add this test after `test_video_download_is_not_read_only`:

```python
def test_crafty_control_tools_are_not_read_only(loaded):
    for name in ("tool_crafty_startServer", "tool_crafty_stopServer", "tool_crafty_restartServer"):
        assert name in loaded and not declared(loaded[name]), name
```

- [ ] **Step 9: Create `help.json`**

```json
{
  "summary": "Start, stop, restart and inspect the Minecraft servers in your own Crafty Controller.",
  "tools": [
    {"name": "tool_crafty_listServers", "purpose": "List your servers with live state", "connection": "Crafty API", "commands": ["list"]},
    {"name": "tool_crafty_getStatus", "purpose": "One server's players, version, CPU and memory", "connection": "Crafty API", "commands": ["status"]},
    {"name": "tool_crafty_startServer", "purpose": "Start a server", "connection": "Crafty API", "commands": ["start"]},
    {"name": "tool_crafty_stopServer", "purpose": "Stop a server", "connection": "Crafty API", "commands": ["stop"]},
    {"name": "tool_crafty_restartServer", "purpose": "Restart a server", "connection": "Crafty API", "commands": ["restart"]}
  ],
  "commands": [
    {"name": "list", "tool": "tool_crafty_listServers", "params": []},
    {"name": "status", "tool": "tool_crafty_getStatus", "params": [
      {"name": "server", "required": true, "default": null, "description": "Short server name from Settings, Crafty."}]},
    {"name": "start", "tool": "tool_crafty_startServer", "params": [
      {"name": "server", "required": true, "default": null, "description": "Short server name from Settings, Crafty."}]},
    {"name": "stop", "tool": "tool_crafty_stopServer", "params": [
      {"name": "server", "required": true, "default": null, "description": "Short server name from Settings, Crafty."}]},
    {"name": "restart", "tool": "tool_crafty_restartServer", "params": [
      {"name": "server", "required": true, "default": null, "description": "Short server name from Settings, Crafty."}]}
  ],
  "workflow": [
    {"sequence": "1", "tool": "(manual - no tool)", "ai_only_step": false, "explanation": "Enter your Crafty address and API token in Settings, Crafty, test it, and name your servers."},
    {"sequence": "2", "tool": "tool_crafty_listServers", "ai_only_step": false, "explanation": "See your servers and whether they run."},
    {"sequence": "3", "tool": "tool_crafty_startServer", "ai_only_step": false, "explanation": "Start, stop or restart a server by its short name."}
  ]
}
```

- [ ] **Step 10: Create `README.md`**

```markdown
# crafty

Per-user control of Minecraft servers hosted in the caller's own Crafty Controller (v2 API). Chat id `crafty`, label "Crafty". Design: `docs/superpowers/specs/2026-10-22-crafty-control-design.md`.

Each user stores their own Crafty address and API token (Settings, Crafty in ember_web). ember_api keeps them encrypted; this capability asks ember_api for the caller's connection on every call (`utils/resolver.py`) and never caches it. There is no global Crafty config.

## Tools

| Tool | Purpose | Connection |
|---|---|---|
| `tool_crafty_listServers` | List the user's servers with running state and players | Crafty API |
| `tool_crafty_getStatus` | One server's players, version, CPU, memory, world | Crafty API |
| `tool_crafty_restartServer` | Restart a server | Crafty API |
| `tool_crafty_startServer` | Start a server | Crafty API |
| `tool_crafty_stopServer` | Stop a server | Crafty API |

## Slash commands

| Tool | Slash command | Parameters |
|---|---|---|
| `tool_crafty_listServers` | `/crafty list` | <ul><li>none</li></ul> |
| `tool_crafty_getStatus` | `/crafty status` | <ul><li>`server` - required. Short name from Settings.</li></ul> |
| `tool_crafty_startServer` | `/crafty start` | <ul><li>`server` - required. Short name from Settings.</li></ul> |
| `tool_crafty_stopServer` | `/crafty stop` | <ul><li>`server` - required. Short name from Settings.</li></ul> |
| `tool_crafty_restartServer` | `/crafty restart` | <ul><li>`server` - required. Short name from Settings.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
|---|---|---|
| 1 | (manual - no tool) | Save and test the connection in Settings, Crafty; name the servers. |
| 2 | `tool_crafty_listServers` | See servers and state. |
| 3 | `tool_crafty_startServer` | Start, stop or restart by short name. |

## Network and safety

- HTTPS only. Outbound calls go through `services/net_guard.py` in personal mode: private LAN allowed; loopback, link-local, metadata addresses and redirects refused. A `localhost` address means this server's container, not the user's computer.
- Crafty must be reachable from the Citadel server: same LAN, VPN (for example Tailscale), tunnel or a public address.
- Crafty's default certificate is self-signed: the connection's "Verify TLS" switch (default on) can be turned off per user.
- Only `list` and `status` declare `readOnlyHint`; start, stop and restart always ask in Auto approval mode.
- Not included: raw console command, `kill`.

Toggle: the capability starts offline. Refresh in ember_admin Capabilities, then switch `crafty` online.
```

- [ ] **Step 11: Run the tests**

Run (in `apps/armory`): `python -m pytest tests/test_crafty_domain.py tests/test_crafty_tools.py tests/test_read_only_declarations.py tests/test_tool_keywords.py tests/test_tool_display_labels.py -v`
Expected: all PASS. If `test_tool_keywords.py` / `test_tool_display_labels.py` import a fixed module list instead of scanning, add `from src.capabilities.crafty import tool as crafty_tool  # noqa: F401` beside the other imports there.

- [ ] **Step 12: Commit**

```bash
git add apps/armory/src/capabilities/crafty apps/armory/tests
git commit -m "feat(armory): crafty capability tools, domain and resolver"
```

---

### Task 6: armory test route for the settings page

**Files:**
- Create: `apps/armory/src/crafty_routes.py`
- Modify: `apps/armory/src/run.py` (after `install_brain_routes(app)`, line ~190)
- Test: `apps/armory/tests/test_crafty_routes.py`

**Interfaces:**
- Consumes: `domain.test_connection(snapshot)`, `CraftyError`, `settings.internal_api_token`.
- Produces: `POST /crafty/operation` with body `{"operation": "test", "candidate": {endpoint, api_token, verify_tls, ...}}` and headers `X-Internal-Token`, `X-Requester-Uid`; answers `{"status": "connected", "servers": [...], "message": str}` or `{"error": safe message}` with 401 / 413 / 422 / 400 / 503.

- [ ] **Step 1: Write the failing tests** — `apps/armory/tests/test_crafty_routes.py`

```python
import json

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src import crafty_routes
from src.capabilities.crafty.utils.client import CraftyError

CANDIDATE = {"endpoint": "https://zima.lan:8443", "api_token": "tok", "verify_tls": False, "servers": []}
HEADERS = {"X-Internal-Token": "internal", "X-Requester-Uid": "uid-1"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(crafty_routes.settings, "internal_api_token", "internal", raising=False)
    app = Starlette()
    crafty_routes.install_crafty_routes(app)
    return TestClient(app)


def post(client, body, headers=HEADERS):
    return client.post("/crafty/operation", content=json.dumps(body), headers=headers)


def test_test_operation_returns_servers(client, monkeypatch):
    monkeypatch.setattr(crafty_routes.domain, "test_connection", lambda snapshot: {
        "status": "connected", "servers": [{"server_id": "a", "server_name": "S"}], "message": "ok"})
    response = post(client, {"operation": "test", "candidate": CANDIDATE})
    assert response.status_code == 200 and response.json()["servers"][0]["server_id"] == "a"


def test_wrong_token_or_missing_uid_is_unauthorized(client):
    assert post(client, {"operation": "test", "candidate": CANDIDATE}, {**HEADERS, "X-Internal-Token": "x"}).status_code == 401
    assert post(client, {"operation": "test", "candidate": CANDIDATE}, {"X-Internal-Token": "internal"}).status_code == 401


def test_invalid_body_is_422_and_never_echoes_the_token(client):
    response = post(client, {"operation": "test", "candidate": {**CANDIDATE, "endpoint": 5}})
    assert response.status_code == 422 and "tok" not in response.text


def test_crafty_errors_are_safe_messages(client, monkeypatch):
    def fail(snapshot):
        raise CraftyError("Crafty rejected the API token. Enter a fresh token in Settings.", status=401)

    monkeypatch.setattr(crafty_routes.domain, "test_connection", fail)
    response = post(client, {"operation": "test", "candidate": CANDIDATE})
    assert response.status_code == 400 and "rejected" in response.json()["error"] and "tok" not in response.text
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_crafty_routes.py -v`
Expected: FAIL (`No module named 'src.crafty_routes'`).

- [ ] **Step 3: Create `apps/armory/src/crafty_routes.py`**

```python
"""Token-protected Crafty connection test, for ember_api's Settings page.

The URL is user-supplied, so the call is made here, behind the address guard,
not in ember_api. Only the `test` operation exists; tools resolve connections
themselves (see capabilities/crafty/utils/resolver.py)."""
import asyncio
import hmac
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse

from src.capabilities.crafty import domain
from src.capabilities.crafty.utils.client import CraftyError
from src.config import settings


class Candidate(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    endpoint: str = Field(max_length=1000)
    api_token: str = Field(max_length=4096, repr=False)
    verify_tls: bool = True
    servers: list = Field(default_factory=list)


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    operation: Literal["test"]
    candidate: Candidate


async def operate(request):
    token = request.headers.get("X-Internal-Token", "")
    uid = request.headers.get("X-Requester-Uid", "")
    if not settings.internal_api_token or not hmac.compare_digest(token, settings.internal_api_token) or not uid:
        return JSONResponse({"error": "Valid internal authentication and requester required"}, status_code=401)
    raw = await request.body()
    if len(raw) > 100_000:
        return JSONResponse({"error": "Crafty request too large"}, status_code=413)
    try:
        body = Operation.model_validate_json(raw)
        snapshot = body.candidate.model_dump()
        return JSONResponse(await asyncio.to_thread(domain.test_connection, snapshot))
    except (ValidationError, json.JSONDecodeError):
        return JSONResponse({"error": "Invalid Crafty operation"}, status_code=422)
    except CraftyError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    except (ValueError, OSError):
        return JSONResponse({"error": "Crafty operation is unavailable"}, status_code=503)


def install_crafty_routes(app):
    app.add_route("/crafty/operation", operate, methods=["POST"])
```

- [ ] **Step 4: Install it in `run.py`** — directly after `install_brain_routes(app)`:

```python
        from src.crafty_routes import install_crafty_routes
        install_crafty_routes(app)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_crafty_routes.py -v`
Expected: all PASS. (`model_dump()` keeps the token in the dict handed to `domain`; `repr=False` keeps it out of reprs and `hide_input_in_errors` keeps it out of validation errors.)

- [ ] **Step 6: Commit**

```bash
git add apps/armory/src/crafty_routes.py apps/armory/src/run.py apps/armory/tests/test_crafty_routes.py
git commit -m "feat(armory): token-protected Crafty connection test route"
```

---

### Task 7: ember_web client, form and page

**Files:**
- Create: `apps/Ember/ember_web/src/api/CraftyClient.ts`, `src/components/CraftyConnectionForm.vue`, `src/components/CraftyConnectionForm.test.ts`, `src/views/CraftyView.vue`
- Modify: the router (`src/router/index.ts`) and the navigation list that holds the Brains entry, so a "Crafty" entry opens `/crafty`.

**Interfaces:**
- Consumes: `/api/crafty/connection` (GET/PUT/DELETE), `/api/crafty/connection/test` (POST) from Task 3; `apiRequest` from `./http`, `ToggleSwitch`, `PageLayout`, `errorMessage`.
- Produces: `craftyClient.connection()`, `.save(draft)`, `.clear()`, `.test(draft)`; component `CraftyConnectionForm` (no props).

- [ ] **Step 1: Read the design rules first**

Read `.agents/skills/ember-frontend-design/` and `ember-design-system` guidance (they are loaded as skills: invoke `ember-frontend-design` and `ember-feature-scaffold` before writing UI). Read `src/router/index.ts` and find where the Brains route and nav entry are declared; the Crafty route and nav entry copy those two declarations exactly, with path `/crafty`, name `crafty`, component `() => import("../views/CraftyView.vue")`, label "Crafty".

- [ ] **Step 2: Write the failing test** — `apps/Ember/ember_web/src/components/CraftyConnectionForm.test.ts`

```ts
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CraftyConnectionForm from "./CraftyConnectionForm.vue";
import { craftyClient } from "../api/CraftyClient";

vi.mock("../api/CraftyClient", () => ({ craftyClient: { connection: vi.fn(), save: vi.fn(), clear: vi.fn(), test: vi.fn() } }));
const saved = { id: "crafty-1", label: "Home", endpoint: "https://zima.lan:8443", verify_tls: true, enabled: true,
  servers: [{ name: "survival", server_id: "id-1" }], credential_configured: true, revision: 2, generation: "g", status: "configured" };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(craftyClient.connection).mockResolvedValue({ ...saved }); });

const button = (w: ReturnType<typeof mount>, text: string) => w.findAll("button").find(b => b.text() === text)!;

it("never fills the saved token and omits it when unchanged", async () => {
  const w = mount(CraftyConnectionForm); await flushPromises();
  expect((w.get('input[type="password"]').element as HTMLInputElement).value).toBe("");
  await w.get('input[maxlength="80"]').setValue("Renamed");
  vi.mocked(craftyClient.save).mockResolvedValue({ ...saved, label: "Renamed", revision: 3 });
  await button(w, "Save connection").trigger("click"); await flushPromises();
  expect(craftyClient.save).toHaveBeenCalledWith(expect.objectContaining({ label: "Renamed", expected_revision: 2 }));
  expect(vi.mocked(craftyClient.save).mock.calls[0]![0]).not.toHaveProperty("api_token");
});

it("tests with the typed token, lists Crafty's servers and saves the named ones", async () => {
  const w = mount(CraftyConnectionForm); await flushPromises();
  await w.get('input[type="password"]').setValue("fresh-token");
  vi.mocked(craftyClient.test).mockResolvedValue({ status: "connected", message: "Connected",
    servers: [{ server_id: "id-1", server_name: "Survival" }, { server_id: "id-2", server_name: "Creative" }] });
  await button(w, "Test connection").trigger("click"); await flushPromises();
  expect(craftyClient.test).toHaveBeenCalledWith(expect.objectContaining({ api_token: "fresh-token" }));
  expect(craftyClient.save).not.toHaveBeenCalled();
  const rows = w.findAll("[data-server-row]");
  expect(rows).toHaveLength(2);
  await rows[1]!.get('input[type="checkbox"]').setValue(true);
  await rows[1]!.get('input[type="text"]').setValue("creative");
  vi.mocked(craftyClient.save).mockResolvedValue({ ...saved, revision: 3 });
  await button(w, "Save connection").trigger("click"); await flushPromises();
  const sent = vi.mocked(craftyClient.save).mock.calls[0]![0];
  expect(sent.servers).toEqual([{ name: "survival", server_id: "id-1" }, { name: "creative", server_id: "id-2" }]);
  expect(sent.api_token).toBe("fresh-token");
});

it("shows a refused save and keeps the typed token", async () => {
  const w = mount(CraftyConnectionForm); await flushPromises();
  await w.get('input[type="password"]').setValue("keep-me");
  vi.mocked(craftyClient.save).mockRejectedValue(new Error("The connection changed. Reload before saving."));
  await button(w, "Save connection").trigger("click"); await flushPromises();
  expect(w.get('[role="alert"]').text()).toContain("changed");
  expect((w.get('input[type="password"]').element as HTMLInputElement).value).toBe("keep-me");
});

it("warns when TLS verification is switched off", async () => {
  const w = mount(CraftyConnectionForm); await flushPromises();
  expect(w.text()).not.toContain("not verified");
  await w.get('input[data-verify-tls]').setValue(false);
  expect(w.text()).toContain("not verified");
});
```

- [ ] **Step 3: Run to verify failure**

Run (in `apps/Ember/ember_web`): `npx vitest run src/components/CraftyConnectionForm.test.ts`
Expected: FAIL (cannot resolve `./CraftyConnectionForm.vue`).

- [ ] **Step 4: Create `src/api/CraftyClient.ts`**

```ts
import { apiRequest } from "./http";

export interface CraftyServerEntry { name: string; server_id: string }
export interface CraftyConnection {
  id: string | null; label: string; endpoint: string; verify_tls: boolean; enabled: boolean;
  servers: CraftyServerEntry[]; credential_configured: boolean; revision: number;
  generation: string | null; status: string;
}
export interface CraftyDraft {
  label: string; endpoint: string; verify_tls: boolean; enabled: boolean;
  servers: CraftyServerEntry[]; expected_revision: number; api_token?: string;
}
export interface CraftyTestResult {
  status: string; message: string; servers: { server_id: string; server_name: string }[];
}
export const craftyClient = {
  connection: () => apiRequest<CraftyConnection>("GET", "/api/crafty/connection"),
  save: (draft: CraftyDraft) => apiRequest<CraftyConnection>("PUT", "/api/crafty/connection", draft),
  clear: () => apiRequest<CraftyConnection>("DELETE", "/api/crafty/connection"),
  test: (draft: CraftyDraft) => apiRequest<CraftyTestResult>("POST", "/api/crafty/connection/test", draft),
};
```

- [ ] **Step 5: Create `src/components/CraftyConnectionForm.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { craftyClient, type CraftyConnection, type CraftyDraft } from "../api/CraftyClient";
import ToggleSwitch from "./ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";

interface Row { server_id: string; label: string; selected: boolean; name: string }
const NAME = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const saved = ref<CraftyConnection | null>(null);
const draft = reactive<CraftyDraft>({ label: "", endpoint: "", verify_tls: true, enabled: true, servers: [], expected_revision: 0 });
const token = ref("");
const rows = ref<Row[]>([]);
const busy = ref(false);
const error = ref("");
const notice = ref("");

const chosen = computed(() => rows.value.filter(row => row.selected));
const namesValid = computed(() => {
  const names = chosen.value.map(row => row.name);
  return names.every(name => NAME.test(name)) && new Set(names).size === names.length;
});

function rowsFrom(servers: { server_id: string; label?: string; name?: string }[], selected: Set<string>, names: Map<string, string>): Row[] {
  return servers.map(server => ({
    server_id: server.server_id, label: server.label ?? server.name ?? server.server_id,
    selected: selected.has(server.server_id), name: names.get(server.server_id) ?? (server.label ?? "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+/, "").slice(0, 32),
  }));
}
function apply(row: CraftyConnection) {
  saved.value = row;
  Object.assign(draft, { label: row.label, endpoint: row.endpoint, verify_tls: row.verify_tls, enabled: row.enabled, expected_revision: row.revision });
  rows.value = row.servers.map(server => ({ server_id: server.server_id, label: server.name, selected: true, name: server.name }));
  token.value = "";
}
onMounted(async () => {
  busy.value = true;
  try { apply(await craftyClient.connection()); } catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
});
function body(): CraftyDraft {
  return { ...draft, servers: chosen.value.map(row => ({ name: row.name, server_id: row.server_id })), ...(token.value ? { api_token: token.value } : {}) };
}
async function test() {
  if (busy.value) return;
  busy.value = true; error.value = ""; notice.value = "";
  try {
    const result = await craftyClient.test(body());
    const selected = new Set(chosen.value.map(row => row.server_id));
    const names = new Map(chosen.value.map(row => [row.server_id, row.name] as const));
    rows.value = rowsFrom(result.servers.map(server => ({ server_id: server.server_id, label: server.server_name })), selected, names);
    notice.value = result.message;
  } catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
}
async function save() {
  if (busy.value || !namesValid.value) return;
  busy.value = true; error.value = ""; notice.value = "";
  try { apply(await craftyClient.save(body())); notice.value = "Connection saved"; }
  catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
}
async function clear() {
  if (busy.value) return;
  busy.value = true; error.value = ""; notice.value = "";
  try { apply(await craftyClient.clear()); notice.value = "Connection removed"; }
  catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
}
</script>
<template>
  <section class="crafty-connection" aria-label="Crafty connection" :aria-busy="busy">
    <h3>Crafty</h3>
    <p class="muted">Control your Minecraft servers from chat. Use the HTTPS address of your Crafty Controller, reachable from the Citadel server (same network, VPN or tunnel). <code>localhost</code> points at the server, not your computer.</p>
    <p v-if="saved" class="muted">Status: {{ saved.status.replaceAll('_', ' ') }} · {{ saved.credential_configured ? "API token configured" : "No API token" }}</p>
    <fieldset :disabled="busy || !saved">
      <label>Label<input v-model="draft.label" maxlength="80" autocomplete="off" /></label>
      <label>Crafty address<input v-model="draft.endpoint" type="url" placeholder="https://zima.local:8443" autocomplete="off" /></label>
      <label>API token<input v-model="token" type="password" autocomplete="new-password" :placeholder="saved?.credential_configured ? 'Leave unchanged to keep the saved token' : 'Crafty API token'" /></label>
      <label class="check"><input data-verify-tls type="checkbox" v-model="draft.verify_tls" /> Verify TLS certificate</label>
      <p v-if="!draft.verify_tls" class="warning" role="note">The certificate is not verified. Only turn this off for a Crafty on your own network with a self-signed certificate.</p>
      <ToggleSwitch :checked="draft.enabled" @change="draft.enabled = ($event.target as HTMLInputElement).checked">Enable connection</ToggleSwitch>

      <div v-if="rows.length" class="servers">
        <h4>Servers</h4>
        <p class="muted">Tick the servers to control and give each a short name (lowercase letters, digits, - or _). Chat uses these names.</p>
        <div v-for="row in rows" :key="row.server_id" class="server-row" data-server-row>
          <label class="check"><input type="checkbox" v-model="row.selected" /> {{ row.label }}</label>
          <input v-model="row.name" type="text" maxlength="32" :disabled="!row.selected" :aria-label="`Short name for ${row.label}`" />
        </div>
        <p v-if="!namesValid" class="error" role="alert">Names must be unique, lowercase, and 1-32 characters.</p>
      </div>
      <p class="muted">Test connection reads your servers from Crafty and does not save anything.</p>
      <div class="actions">
        <button type="button" :disabled="!namesValid" @click="save">{{ busy ? "Working…" : "Save connection" }}</button>
        <button type="button" @click="test">Test connection</button>
        <button type="button" :disabled="!saved?.revision" @click="clear">Remove connection</button>
      </div>
    </fieldset>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
  </section>
</template>
<style scoped>
.crafty-connection { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; background: var(--surface); margin-bottom: 16px; }
fieldset { border: 0; padding: 0; display: grid; gap: 12px; min-width: 0; }
label { display: grid; gap: 4px; }
label.check { display: flex; align-items: center; gap: 8px; }
input[type="text"], input[type="url"], input[type="password"] { width: 100%; box-sizing: border-box; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); padding: 8px; }
.server-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; align-items: center; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
button { border: 1px solid var(--border); border-radius: var(--radius-full); padding: 7px 12px; background: var(--surface); color: var(--text); cursor: pointer; }
button:first-child { background: var(--accent); color: var(--accent-contrast); }
button:disabled { opacity: .55; cursor: default; }
.muted { color: var(--muted); font-size: .9em; }
.warning { color: var(--danger); font-size: .9em; }
.error { color: var(--danger); }
</style>
```

- [ ] **Step 6: Create `src/views/CraftyView.vue` and register route + nav**

```vue
<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import CraftyConnectionForm from "../components/CraftyConnectionForm.vue";
</script>
<template>
  <PageLayout title="Crafty" description="Control your Minecraft servers from chat.">
    <CraftyConnectionForm />
  </PageLayout>
</template>
```

Add the route and nav entry exactly where Step 1 found the Brains declarations.

- [ ] **Step 7: Run the tests and the type check**

Run: `npx vitest run src/components/CraftyConnectionForm.test.ts` then `npx vue-tsc --noEmit`
Expected: PASS and no type errors. Then run the existing router/nav tests (`npx vitest run src/router src/components/AppNav`) and fix any that pin the nav list.

- [ ] **Step 8: Commit**

```bash
git add apps/Ember/ember_web/src
git commit -m "feat(ember_web): Crafty connection settings page"
```

---

### Task 8: Docs, full test run, live check

**Files:**
- Modify: `apps/armory/src/capabilities/README.md` (add a `crafty/` line to the list), `apps/Ember/ember_api/README.md` (add the five `/api/crafty` routes to its routes table, same columns as the brains rows)

- [ ] **Step 1: Add the capability line** to the list at the top of `apps/armory/src/capabilities/README.md`:

```markdown
- `crafty/` - list, inspect, start, stop and restart the Minecraft servers in the user's own Crafty Controller (`/crafty ...`).
```

- [ ] **Step 2: Add the ember_api routes** to the routes table in `apps/Ember/ember_api/README.md`: `GET/PUT/DELETE /api/crafty/connection`, `POST /api/crafty/connection/test`, `POST /api/crafty/internal/resolve` (internal token), each with auth and purpose as in the spec.

- [ ] **Step 3: Run the full suites**

Run (in `apps/armory`): `python -m pytest -q`
Run (in `apps/Ember/ember_api`): `python -m pytest -q`
Run (in `apps/Ember/ember_web`): `npx vitest run`
Expected: all PASS. Fix any regression before continuing; do not skip failing tests.

- [ ] **Step 4: Live check against the real Crafty on Zima** (cannot be automated; report results)

1. Start the stack; in ember_admin Capabilities press Refresh, switch `crafty` online.
2. In ember_web, open Crafty, enter the Zima Crafty URL and a Crafty API token (Crafty: user profile, API keys). Turn "Verify TLS" off if the certificate is self-signed. Press Test connection. Confirm the server list appears. If it fails with "invalid server list", read the raw `GET /api/v2/servers` response (`curl -k -H "Authorization: Bearer <token>" https://<crafty>/api/v2/servers`) and adjust `CraftyClient.list_servers` to match the real field names; add the observed shape to `tests/test_crafty_client.py`.
3. Tick a server, name it, Save. In chat run `/crafty list`, `/crafty status server=<name>`, then `/crafty restart server=<name>` and confirm the server restarts in Crafty.
4. Confirm in chat that a second account sees "Set up your Crafty connection in Settings first."
5. Try an address of `https://127.0.0.1:8443`: the test must be refused.

- [ ] **Step 5: Commit**

```bash
git add apps/armory/src/capabilities/README.md apps/Ember/ember_api/README.md
git commit -m "docs: document the crafty capability and API routes"
```
