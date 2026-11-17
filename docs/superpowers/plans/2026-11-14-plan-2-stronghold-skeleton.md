# Plan 2: Stronghold skeleton and Portcullis forwarder Implementation Plan

<!-- history-note -->
> **History (noted 2026-11-18).** This document names files and settings that no longer exist: `specifics/`, seed files,
> `config_*.json` toggle, tuning and connection files, and tokens or addresses kept in `.env`. Those settings are now saved
> in each service's database and edited in its admin app; see `apps/armory/docs/settings.md` and each service's
> `configs/README.md`. Kept as it was written; do not follow its file paths.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A running, empty `stronghold` service that only Portcullis can call, plus a forwarder in Portcullis that sends an authenticated account's request to it without cookies.

**Architecture:** Stronghold is a FastAPI app shaped like `treasury`: plain ASGI internal-token middleware, `/health` open, everything else needs `X-Internal-Token`. It learns who is asking from `X-Requester-Uid`, `X-Requester-Username` and `X-Requester-Email`, the headers Portcullis already sends to Armory. Portcullis gets one `StrongholdForwarder` service and one proof route, `GET /api/stronghold/whoami`. No product logic moves in this plan.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx, pytest, uv, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-14-citadel-revision-design.md` (phase 2, "Request flow")

## Global Constraints

- Work from `D:\User\Documents\Programming\Applications\Citadel`. Run git only inside this repo.
- Branch `feat/stronghold-skeleton`, cut from `refactor/portcullis-rename` (or from `main` once Plan 1 is merged).
- Use `uv`, never `pip`. On this machine set `UV_CACHE_DIR=D:/User/.uv-cache` and `UV_LINK_MODE=copy` before uv commands.
- Stronghold port: **29650**. Legion takes one port per agent from 29603 and is at 29621 today, so 29603 to 29649 is left to Legion. This is a deliberate gap in the "next free port" rule; record it in the port note (Task 5).
- Stronghold never reads cookies and never sees a session. Portcullis never forwards `Cookie` or `Authorization`.
- `src/shared_token.py` must stay byte-identical in armory, legion, treasury, portcullis and stronghold.
- Never read or print `.env*` files.
- Async I/O only in request paths. No blocking calls.
- No reduced-motion code anywhere (project rule).
- Commit trailer, exactly: `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`

## File Structure

New service `apps/stronghold/`:
- `pyproject.toml`: project metadata and dependencies.
- `src/__init__.py`: empty.
- `src/shared_token.py`: copy of `apps/treasury/src/shared_token.py`.
- `src/seed.py`: copy of `apps/treasury/src/seed.py`.
- `src/auth.py`: copy of `apps/treasury/src/auth.py` (`load_token`, `InternalTokenMiddleware`).
- `src/requester.py`: `Requester` and the `current_requester` dependency.
- `src/api.py`: `create_app(token)`, `/health`, `/whoami`.
- `src/run.py`: entry point.
- `tests/__init__.py`, `tests/conftest.py`, `tests/test_api.py`, `tests/test_shared_token.py`.
- `Dockerfile`, `.dockerignore`, `.env.example`, `dev_deploy.bat`, `shell.bat`, `README.md`.

Portcullis:
- Create `apps/portcullis/src/services/stronghold_forwarder.py`: the forwarder.
- Create `apps/portcullis/src/routes/stronghold.py`: the proof route.
- Create `apps/portcullis/tests/test_stronghold_forward.py`.
- Modify `apps/portcullis/src/config.py` (new setting), `src/app.py` (wire it), `src/deps.py` (dependency), `configs/config_app.json.example`.

Stack: `docker-compose.yml`, `docker/configs/portcullis/app.json`, `.gitignore`, `tools/deploy.bat`, `tools/publish_live.py`, `docs/deployment.md`.

---

### Task 1: Stronghold service with token auth and requester identity

**Files:**
- Create: everything under `apps/stronghold/` listed above except `Dockerfile`, `.dockerignore`, `dev_deploy.bat`, `shell.bat`, `README.md` (Task 4)
- Test: `apps/stronghold/tests/test_api.py`, `apps/stronghold/tests/test_shared_token.py`

**Interfaces:**
- Produces: `src.api.create_app(token: str) -> FastAPI`; `src.requester.Requester(uid: str, username: str, email: str)`; `src.requester.current_requester` (FastAPI dependency returning `Requester`, 400 when `X-Requester-Uid` is missing); `GET /health` → `{"status": "ok"}`; `GET /whoami` → `{"uid", "username", "email"}`. Plan 5 domain routes depend on `current_requester`.

- [ ] **Step 1: Create the branch and the folder with copied files**

```bash
git checkout -b feat/stronghold-skeleton
mkdir -p apps/stronghold/src apps/stronghold/tests
cp apps/treasury/src/shared_token.py apps/treasury/src/seed.py apps/treasury/src/auth.py apps/stronghold/src/
cp apps/treasury/tests/test_shared_token.py apps/stronghold/tests/
touch apps/stronghold/src/__init__.py apps/stronghold/tests/__init__.py
printf 'INTERNAL_API_TOKEN=\n' > apps/stronghold/.env.example
```

- [ ] **Step 2: Write `apps/stronghold/pyproject.toml`**

```toml
[project]
name = "stronghold"
description = "Product logic for Citadel and Ember, called only by Portcullis"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.27"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Write `apps/stronghold/tests/conftest.py`**

```python
"""Shared fixtures. Tests never read the real .env or the shared token file."""

import os

os.environ["INTERNAL_TOKEN_FILE"] = ""
```

- [ ] **Step 4: Write the failing test `apps/stronghold/tests/test_api.py`**

```python
from fastapi.testclient import TestClient

from src.api import create_app

TOKEN = "t0ken"
IDENTITY = {
    "X-Requester-Uid": "u-1",
    "X-Requester-Username": "ana",
    "X-Requester-Email": "ana@example.com",
}


def client(token: str = TOKEN) -> TestClient:
    return TestClient(create_app(token))


def test_health_is_open():
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_a_missing_token():
    response = client().get("/whoami", headers=IDENTITY)
    assert response.status_code == 401
    assert response.json() == {"error": "Invalid or missing internal API token"}


def test_rejects_a_wrong_token():
    response = client().get("/whoami", headers={**IDENTITY, "X-Internal-Token": "nope"})
    assert response.status_code == 401


def test_whoami_returns_the_requester():
    response = client().get("/whoami", headers={**IDENTITY, "X-Internal-Token": TOKEN})
    assert response.status_code == 200
    assert response.json() == {"uid": "u-1", "username": "ana", "email": "ana@example.com"}


def test_missing_uid_is_a_bad_request():
    headers = {"X-Internal-Token": TOKEN, "X-Requester-Username": "ana"}
    response = client().get("/whoami", headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing requester identity"}


def test_open_when_no_token_is_configured():
    response = client("").get("/whoami", headers=IDENTITY)
    assert response.status_code == 200
```

- [ ] **Step 5: Run the test and see it fail**

Run: `cd apps/stronghold && uv sync && uv run pytest -q`
Expected: collection error, `ModuleNotFoundError: No module named 'src.api'`.

- [ ] **Step 6: Write `apps/stronghold/src/requester.py`**

```python
"""Who is asking. Portcullis authenticates the account and sends its identity in
headers; Stronghold trusts them because the internal token was already checked."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class Requester:
    """The account a request is made for. `uid` never changes; data is keyed on it."""

    uid: str
    username: str
    email: str


async def current_requester(
    x_requester_uid: str = Header(""),
    x_requester_username: str = Header(""),
    x_requester_email: str = Header(""),
) -> Requester:
    """The requester from Portcullis's headers, or 400 when the uid is missing."""
    if not x_requester_uid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing requester identity")
    return Requester(uid=x_requester_uid, username=x_requester_username, email=x_requester_email)
```

- [ ] **Step 7: Write `apps/stronghold/src/api.py`**

```python
"""Stronghold's HTTP app. Every route but /health needs the internal token."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, FastAPI

from src.auth import InternalTokenMiddleware
from src.requester import Requester, current_requester


def create_app(token: str) -> FastAPI:
    """token: the shared internal token; "" leaves the app open (tests, loopback)."""
    app = FastAPI(title="stronghold", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(InternalTokenMiddleware, token=token)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami")
    async def whoami(requester: Requester = Depends(current_requester)) -> dict[str, str]:
        """Echoes the identity Portcullis sent. Proves the forwarding path end to end."""
        return asdict(requester)

    return app
```

- [ ] **Step 8: Write `apps/stronghold/src/run.py`**

```python
"""Start Stronghold: `python -m src.run`."""

from __future__ import annotations

import logging
import os

import uvicorn

from src.api import create_app
from src.auth import load_token

DEFAULT_PORT = 29650


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.getenv("STRONGHOLD_HOST", "127.0.0.1")
    port = int(os.getenv("STRONGHOLD_PORT", str(DEFAULT_PORT)))
    uvicorn.run(create_app(load_token()), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Run the tests and see them pass**

Run: `uv run pytest -q`
Expected: `9 passed` (6 in `test_api.py`, 3 in `test_shared_token.py`).

- [ ] **Step 10: Add Stronghold to the shared-token note in all five copies**

```bash
cd ../..
sed -i 's/Keep this file identical in armory, legion, treasury and portcullis\./Keep this file identical in armory, legion, treasury, portcullis and stronghold./' \
  apps/armory/src/services/shared_token.py apps/legion/src/runtime/shared_token.py \
  apps/treasury/src/shared_token.py apps/portcullis/src/utils/shared_token.py apps/stronghold/src/shared_token.py
for f in apps/armory/src/services/shared_token.py apps/legion/src/runtime/shared_token.py apps/portcullis/src/utils/shared_token.py apps/stronghold/src/shared_token.py; do
  cmp apps/treasury/src/shared_token.py "$f" && echo "same: $f"
done
```
Expected: four `same:` lines. A `differ` line means a copy had drifted before this plan: stop and report it, do not overwrite.

- [ ] **Step 11: Commit**

```bash
git add apps/stronghold apps/armory/src/services/shared_token.py apps/legion/src/runtime/shared_token.py apps/treasury/src/shared_token.py apps/portcullis/src/utils/shared_token.py
git commit -m "feat: add stronghold service skeleton" -m "Internal-token auth, requester identity from headers, /health and /whoami." -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 2: Portcullis forwarder service

**Files:**
- Create: `apps/portcullis/src/services/stronghold_forwarder.py`
- Modify: `apps/portcullis/src/config.py:236` (Settings field) and `:285` (loader)
- Modify: `apps/portcullis/configs/config_app.json.example:11`
- Test: `apps/portcullis/tests/test_stronghold_forward.py` (unit part)

**Interfaces:**
- Consumes: `Account` (`src.models`), `TrafficRecorder` (`src.services.traffic`).
- Produces: `Settings.stronghold_url: str` (default `"http://127.0.0.1:29650"`); `StrongholdForwarder(client: httpx.AsyncClient, base_url: str, internal_token: str | None, traffic: TrafficRecorder | None = None)`; `await forwarder.forward(method: str, path: str, account: Account, *, params: dict[str, str] | None = None, json: Any = None) -> ForwardedResponse`; `ForwardedResponse(status: int, body: bytes, content_type: str)`; `StrongholdUnavailable(Exception)`.

- [ ] **Step 1: Write the failing unit tests in `apps/portcullis/tests/test_stronghold_forward.py`**

```python
"""Portcullis -> Stronghold: identity and the internal token go across, cookies never do."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable
from tests.conftest import FakeUpstream

ACCOUNT = SimpleNamespace(uid="u-1", username="ana", email="ana@example.com")


def forwarder(upstream: FakeUpstream, token: str | None = "secret-token") -> StrongholdForwarder:
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    return StrongholdForwarder(client, "http://stronghold.internal:29650/", token)


async def test_sends_identity_and_token():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(200, json={"ok": True}))
    result = await forwarder(upstream).forward("GET", "/whoami", ACCOUNT, params={"a": "1"})
    sent = upstream.requests[0]
    assert str(sent.url) == "http://stronghold.internal:29650/whoami?a=1"
    assert sent.headers["x-internal-token"] == "secret-token"
    assert sent.headers["x-requester-uid"] == "u-1"
    assert sent.headers["x-requester-username"] == "ana"
    assert sent.headers["x-requester-email"] == "ana@example.com"
    assert "cookie" not in sent.headers and "authorization" not in sent.headers
    assert (result.status, result.body, result.content_type) == (200, b'{"ok":true}', "application/json")


async def test_no_token_header_when_none_is_configured():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(200, json={}))
    await forwarder(upstream, token=None).forward("GET", "/whoami", ACCOUNT)
    assert "x-internal-token" not in upstream.requests[0].headers


async def test_passes_a_refusal_through_unchanged():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(404, json={"detail": "No such note"}))
    result = await forwarder(upstream).forward("GET", "/notes/9", ACCOUNT)
    assert result.status == 404
    assert result.body == b'{"detail":"No such note"}'


async def test_sends_a_json_body():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(201, json={"id": 1}))
    await forwarder(upstream).forward("POST", "/notes", ACCOUNT, json={"title": "t"})
    sent = upstream.requests[0]
    assert sent.content == b'{"title":"t"}'
    assert sent.headers["content-type"] == "application/json"


async def test_unreachable_raises():
    upstream = FakeUpstream(unreachable=True)
    with pytest.raises(StrongholdUnavailable):
        await forwarder(upstream).forward("GET", "/whoami", ACCOUNT)


async def test_a_server_error_raises():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(StrongholdUnavailable):
        await forwarder(upstream).forward("GET", "/whoami", ACCOUNT)
```

- [ ] **Step 2: Run and see it fail**

Run: `cd apps/portcullis && uv run pytest tests/test_stronghold_forward.py -q`
Expected: `ModuleNotFoundError: No module named 'src.services.stronghold_forwarder'`.

- [ ] **Step 3: Write `apps/portcullis/src/services/stronghold_forwarder.py`**

```python
"""Portcullis's one way into Stronghold.

Portcullis has already authenticated the account and checked its permission.
This sends the request on with the account's identity and the internal token.
The browser's cookies and headers are never forwarded: only what is built here
leaves, so Stronghold cannot see a session. Stronghold's own answers below 500
go back unchanged, so a route keeps the status and body Stronghold chose.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from src.models import Account
from src.services.traffic import TrafficRecorder

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class StrongholdUnavailable(Exception):
    """Stronghold could not be reached or answered 5xx (maps to 502)."""


@dataclass(frozen=True)
class ForwardedResponse:
    """Stronghold's answer, ready to hand back as it came."""

    status: int
    body: bytes
    content_type: str


class StrongholdForwarder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        internal_token: str | None,
        traffic: TrafficRecorder | None = None,
    ) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._internal_token = internal_token
        self._traffic = traffic or TrafficRecorder()

    def _headers(self, account: Account) -> dict[str, str]:
        headers = {"X-Requester-Username": account.username, "X-Requester-Email": account.email}
        if account.uid:
            headers["X-Requester-Uid"] = account.uid
        if self._internal_token:
            headers["X-Internal-Token"] = self._internal_token
        return headers

    async def forward(
        self,
        method: str,
        path: str,
        account: Account,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> ForwardedResponse:
        """One call to a fixed Stronghold path. `path` is built by the route, never by the browser."""
        try:
            with self._traffic.timed("stronghold", f"{method} {path}") as timing:
                response = await self._client.request(
                    method,
                    f"{self._base}{path}",
                    params=params,
                    json=json,
                    headers=self._headers(account),
                    timeout=_TIMEOUT,
                )
                timing.ok = response.status_code < 500
        except httpx.HTTPError as error:
            logger.warning("stronghold %s %s unreachable: %s", method, path, error)
            raise StrongholdUnavailable(str(error)) from error
        if response.status_code >= 500:
            raise StrongholdUnavailable(f"stronghold answered {response.status_code}")
        return ForwardedResponse(
            response.status_code,
            response.content,
            response.headers.get("content-type", "application/json"),
        )
```

- [ ] **Step 4: Add the setting**

In `apps/portcullis/src/config.py`, after the `mcp_server_url: str = "http://127.0.0.1:29600/mcp"` field of `Settings`:

```python
    # Stronghold (product logic): reached only from here, never by the browser.
    stronghold_url: str = "http://127.0.0.1:29650"
```

In `load_settings()`, after the `mcp_server_url=raw.get("mcp_server_url") or ...` line:

```python
        stronghold_url=raw.get("stronghold_url") or "http://127.0.0.1:29650",
```

In `apps/portcullis/configs/config_app.json.example`, after the `"mcp_server_url"` line:

```json
  "stronghold_url": "http://127.0.0.1:29650",
```

- [ ] **Step 5: Run and see the unit tests pass**

Run: `uv run pytest tests/test_stronghold_forward.py -q`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
cd ../..
git add apps/portcullis/src/services/stronghold_forwarder.py apps/portcullis/src/config.py apps/portcullis/configs/config_app.json.example apps/portcullis/tests/test_stronghold_forward.py
git commit -m "feat: add Stronghold forwarder to portcullis" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 3: Proof route through Portcullis

**Files:**
- Create: `apps/portcullis/src/routes/stronghold.py`
- Modify: `apps/portcullis/src/deps.py` (new dependency after `get_db_gateway`), `apps/portcullis/src/app.py` (lifespan near line 162, router list near line 255, exception handler near line 280)
- Test: `apps/portcullis/tests/test_stronghold_forward.py` (append route tests)

**Interfaces:**
- Consumes: `StrongholdForwarder`, `ForwardedResponse`, `StrongholdUnavailable` (Task 2); `current_account` (`src.deps`).
- Produces: `src.deps.get_stronghold(request) -> StrongholdForwarder`; `src.routes.stronghold.as_response(forwarded: ForwardedResponse) -> Response` (Plan 5 routes reuse both); `GET /api/stronghold/whoami`; a 502 `{"detail": "Stronghold is unavailable"}` for `StrongholdUnavailable` anywhere.

- [ ] **Step 1: Append the failing route tests to `tests/test_stronghold_forward.py`**

```python
from tests.test_registration import as_admin


def stronghold_calls(upstream: FakeUpstream) -> list[httpx.Request]:
    return [request for request in upstream.requests if request.url.path == "/whoami"]


def test_route_forwards_for_a_logged_in_account(client_factory, upstream):
    upstream.handler = lambda request: httpx.Response(200, json={"uid": request.headers["x-requester-uid"]})
    client = as_admin(client_factory(internal_token="secret-token"))
    response = client.get("/api/stronghold/whoami")
    assert response.status_code == 200
    sent = stronghold_calls(upstream)[0]
    assert str(sent.url) == "http://127.0.0.1:29650/whoami"
    assert sent.headers["x-internal-token"] == "secret-token"
    assert sent.headers["x-requester-username"] == "root"
    assert response.json() == {"uid": sent.headers["x-requester-uid"]}
    assert "cookie" not in sent.headers


def test_route_needs_a_login(client, upstream):
    response = client.get("/api/stronghold/whoami")
    assert response.status_code == 401
    assert stronghold_calls(upstream) == []


def test_route_reports_an_outage_as_502(client_factory, upstream):
    client = as_admin(client_factory())
    upstream.unreachable = True
    response = client.get("/api/stronghold/whoami")
    assert response.status_code == 502
    assert response.json() == {"detail": "Stronghold is unavailable"}
```

- [ ] **Step 2: Run and see them fail**

Run: `cd apps/portcullis && uv run pytest tests/test_stronghold_forward.py -q`
Expected: 3 failed with 404 (route does not exist), 6 passed.

- [ ] **Step 3: Add the dependency in `src/deps.py`**

Add the import beside the other service imports:

```python
from src.services.stronghold_forwarder import StrongholdForwarder
```

Add after `get_db_gateway`:

```python
def get_stronghold(request: Request) -> StrongholdForwarder:
    return request.app.state.stronghold
```

- [ ] **Step 4: Write `src/routes/stronghold.py`**

```python
"""/api/stronghold: routes Portcullis answers by asking Stronghold.

Portcullis checks the login (and, on later routes, the permission) and builds
the Stronghold path itself. This file holds only the proof route; each product
domain adds its own route file and reuses `as_response`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from src.deps import current_account, get_stronghold
from src.models import Account
from src.services.stronghold_forwarder import ForwardedResponse, StrongholdForwarder

router = APIRouter(prefix="/api/stronghold", tags=["stronghold"])


def as_response(forwarded: ForwardedResponse) -> Response:
    """Stronghold's status, body and content type, unchanged."""
    return Response(forwarded.body, status_code=forwarded.status, media_type=forwarded.content_type)


@router.get("/whoami")
async def whoami(
    account: Account = Depends(current_account),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Who Stronghold sees for this session. Any logged-in account."""
    return as_response(await stronghold.forward("GET", "/whoami", account))
```

- [ ] **Step 5: Wire it into `src/app.py`**

Add to the imports: `stronghold` in the `from src.routes import ...` list, and

```python
from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable
```

In `lifespan`, right after the `app.state.mcp_proxy = McpProxy(...)` line:

```python
        app.state.stronghold = StrongholdForwarder(
            upstream, settings.stronghold_url, internal_token or None, recorder
        )
```

After `app.include_router(calendar_routes.router)`:

```python
    app.include_router(stronghold.router)
```

Beside the other exception handlers (before the catch-all `Exception` handler):

```python
    @app.exception_handler(StrongholdUnavailable)
    async def stronghold_unavailable(_request: Request, _error: StrongholdUnavailable) -> JSONResponse:
        return JSONResponse({"detail": "Stronghold is unavailable"}, status_code=502)
```

- [ ] **Step 6: Run the new tests**

Run: `uv run pytest tests/test_stronghold_forward.py -q`
Expected: `9 passed`.

- [ ] **Step 7: Run the whole Portcullis suite**

Run: `uv run pytest -q` (about 19 minutes; run it in the background)
Expected: `1593 passed` (1584 from the Plan 1 baseline plus 9).

- [ ] **Step 8: Commit**

```bash
cd ../..
git add apps/portcullis/src/routes/stronghold.py apps/portcullis/src/deps.py apps/portcullis/src/app.py apps/portcullis/tests/test_stronghold_forward.py
git commit -m "feat: forward /api/stronghold/whoami to stronghold" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 4: Container, compose and deploy tooling

**Files:**
- Create: `apps/stronghold/Dockerfile`, `.dockerignore`, `dev_deploy.bat`, `shell.bat`, `README.md`
- Modify: `docker-compose.yml`, `docker/configs/portcullis/app.json:11`, `.gitignore`, `tools/deploy.bat:12`, `tools/publish_live.py:37`, `docs/deployment.md`

**Interfaces:**
- Consumes: `python -m src.run`, `STRONGHOLD_HOST`, `STRONGHOLD_PORT` (Task 1); `stronghold_url` (Task 2).
- Produces: compose service `stronghold`, reachable inside the `core` network at `http://stronghold:29650`. No published port.

- [ ] **Step 1: Copy the container files from treasury and adapt them**

```bash
cp apps/treasury/Dockerfile apps/treasury/.dockerignore apps/treasury/dev_deploy.bat apps/treasury/shell.bat apps/stronghold/
sed -i 's/EXPOSE 29602/EXPOSE 29650/' apps/stronghold/Dockerfile
sed -i 's/treasury/stronghold/g' apps/stronghold/dev_deploy.bat apps/stronghold/shell.bat
grep -n "EXPOSE\|SERVICE=" apps/stronghold/Dockerfile apps/stronghold/dev_deploy.bat
```
Expected: `EXPOSE 29650` and `set "SERVICE=stronghold"`. Read `shell.bat` after the `sed` and confirm nothing in it still refers to treasury's database.

- [ ] **Step 2: Write `apps/stronghold/README.md`**

```markdown
# stronghold

Product logic for Citadel and Ember. Only `portcullis` calls it.

- Every route but `/health` needs `X-Internal-Token` (the shared internal token).
- The asking account arrives in `X-Requester-Uid`, `X-Requester-Username` and `X-Requester-Email`. Data is keyed on the uid.
- No cookies, no sessions and no login here. Portcullis owns those.

## Run

    uv sync
    uv run python -m src.run

Default address `127.0.0.1:29650`. `STRONGHOLD_HOST` and `STRONGHOLD_PORT` override it.

In Docker: `dev_deploy.bat` rebuilds and restarts the `stronghold` container from the root `docker-compose.yml`.

## Test

    uv run pytest -q

## Routes

| Route | Purpose |
|---|---|
| `GET /health` | Open. `{"status": "ok"}` |
| `GET /whoami` | Echoes the requester. Portcullis exposes it as `GET /api/stronghold/whoami` |
```

- [ ] **Step 3: Add the compose service**

In `docker-compose.yml`, after the `treasury` service block and before `portcullis`:

```yaml
  stronghold:
    build: ./apps/stronghold
    restart: unless-stopped
    env_file:
      - path: ./apps/stronghold/.env
        required: false
    environment:
      <<: *internal_token
      STRONGHOLD_HOST: 0.0.0.0
      STRONGHOLD_PORT: "29650"
    volumes:
      - internal_token:/run/citadel
    depends_on: [treasury]
    networks: [core]
```

Change the `portcullis` service's `depends_on: [armory, legion, treasury]` to `depends_on: [armory, legion, treasury, stronghold]`. Update the comment on line 1 to read `... -> portcullis -> armory / legion / treasury / stronghold; ...`.

- [ ] **Step 4: Point the container config at the service name**

In `docker/configs/portcullis/app.json`, after the `"mcp_server_url": "http://armory:29600/mcp",` line:

```json
  "stronghold_url": "http://stronghold:29650",
```

- [ ] **Step 5: Ignore the secret file and add the app to the deploy tools**

In `.gitignore`, after the `/apps/treasury/firestore-debug.log` line add `/apps/stronghold/.env`.
In `tools/deploy.bat` line 12, append ` apps/stronghold` inside the `APPS` value.
In `tools/publish_live.py`, add `"apps/stronghold",` after the `"apps/portcullis",` entry.
In `docs/deployment.md`, add a row under the `portcullis` row of the services table: ``| `stronghold` | product logic, called only by portcullis | internal |``, and add `apps/stronghold` to the two lists of service folders (lines 30 and 167).

- [ ] **Step 6: Validate and build**

```bash
docker compose config --quiet && echo ok
docker compose build stronghold
```
Expected: `ok`, then `Image citadel-stronghold Built`. If Docker is not running, say so in the commit message.

- [ ] **Step 7: Check it end to end in Docker (skip if Docker is not running)**

```bash
docker compose up -d --build stronghold portcullis
docker compose exec stronghold python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:29650/health').read())"
docker compose exec portcullis python -c "import urllib.request,urllib.error
try: urllib.request.urlopen('http://stronghold:29650/whoami')
except urllib.error.HTTPError as e: print(e.code)"
```
Expected: `b'{"status":"ok"}'`, then `401` (no token sent, so Stronghold refuses).

- [ ] **Step 8: Commit**

```bash
git add apps/stronghold docker-compose.yml docker/configs/portcullis/app.json .gitignore tools/deploy.bat tools/publish_live.py docs/deployment.md
git commit -m "feat: run stronghold in the compose stack" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 5: Notes

**Files:**
- Create: `D:\User\Documents\Programming\Brain\Projects\stronghold.md`
- Modify: `D:\User\Documents\Programming\Brain\Projects\Citadel.md`, `Brain\Notes\Port blocks give each kind of project its own range.md`, `Brain\index.md`, `Brain\log.md`

- [ ] **Step 1: Read `D:\User\Documents\Programming\Brain\AGENTS.md`** and follow it (frontmatter, at least two links per note, index and log updates).

- [ ] **Step 2: Write `Brain/Projects/stronghold.md`**

```markdown
---
type: project
status: active
tags: [project, python, fastapi]
created: 2026-11-14
repo: Applications/Citadel/apps/stronghold
---

# stronghold

Product logic for [[Citadel]] and Ember. Only [[portcullis]] calls it.

## Purpose
Hold the features that are not login or gateway work, so portcullis stays thin. Empty for now: only `/health` and `/whoami`.

## Architecture
- Every route but `/health` needs the shared internal token.
- The asking account arrives in `X-Requester-Uid`, `X-Requester-Username`, `X-Requester-Email`. Data is keyed on the uid.
- No cookies or sessions. portcullis authenticates and checks permissions, then forwards.

## Run
`uv run python -m src.run` in `Applications/Citadel/apps/stronghold`. Port 29650.

## Open questions
- Which product domain moves first (planned: calendar).
```

- [ ] **Step 3: Update the other notes**

In `Citadel.md` add a Components row: ``| `stronghold` | Product logic, called only by portcullis (port 29650); skeleton since 2026-11-14 | [[stronghold]] |``.
In the port note add: `stronghold 29650. Legion takes one port per agent from 29603, so 29603 to 29649 is left to Legion.`
In `index.md` add `- [[stronghold]]: product logic service behind portcullis` beside the other Citadel entries.
Append to `log.md`:

```
## [2026-11-14] ingest | stronghold
New Projects/stronghold.md. Updated Citadel, the port blocks note and index.
```

- [ ] **Step 4: Validate the vault**

Run: `py "D:/User/Documents/Programming/.claude/hooks/validate_vault.py" --all`
Expected: `vault OK`.

---

## Self-review

- **Spec coverage:** FastAPI app (Task 1), health (Task 1), internal-token auth (Task 1), compose service (Task 4), port (Global Constraints, Task 4), Portcullis forwarder with a test (Tasks 2 and 3), cookies never reach Stronghold (asserted in both test groups).
- **Placeholders:** none.
- **Names:** `StrongholdForwarder.forward`, `ForwardedResponse(status, body, content_type)`, `StrongholdUnavailable`, `get_stronghold`, `as_response`, `current_requester`, `stronghold_url` and port 29650 are spelled the same in every task.
- **Not covered here, on purpose:** per-route permission checks (each domain route in Plan 5 adds its own `require_permission`), request bodies other than JSON (added with the first domain that needs uploads), streaming responses (added with chats).

## Execution notes (2026-11-14)

- Task 2 tests run their coroutines with `asyncio.run(...)` in plain `def` tests. Portcullis has no async pytest plugin, so the `async def` tests written above do not run there.
- Task 4 Steps 6 and 7 (image build and the Docker end-to-end check) were not run: Docker was not running. Stronghold was started locally on test port 29901 instead: `/health` answered, `/whoami` gave 401 without the token and the requester with it.
