# Plan 3: Legion on ConversationGateway (Anthropic-protocol agents) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Legion agents with `llm.provider: "anthropic"` send every model call through ConversationGateway instead of the Anthropic SDK, with the tool loop, failover and cooldown behaving as before.

**Architecture:** Swap the client, keep the loop. `anthropic_provider.py` already reaches the SDK only through `_get_client()` and `_get_sync_client()`, and its tests fake exactly that seam. A small shim with the same surface (`messages.stream`, `messages.create`) translates Anthropic-shaped requests to the gateway's contract and gateway replies back to Anthropic-shaped objects. Failover keeps `GatewayRoute` and `cooldown.py`; only `classify()` changes, reading the gateway's error `kind` and `Retry-After`. OpenAI-protocol agents are untouched here and move in Plan 3b with the same pattern.

**Tech Stack:** Python 3.12, httpx, pytest, uv, Docker Compose. Gateway contract: `AI/ModelProviders/ConversationGateway/README.md`.

**Spec:** `docs/superpowers/specs/2026-11-14-citadel-revision-design.md` ("Legion on the model gateways", phase 2b, resolved question 4)

## Global Constraints

- Work from `D:\User\Documents\Programming\Applications\Citadel`. Run git only inside this repo. Branch `refactor/legion-conversation-gateway`, cut from `refactor/portcullis-rename` (or `main` once Plan 1 is merged).
- Do not edit anything under `D:\User\Documents\Programming\AI\ModelProviders\`. The gateways are shared services with other callers; Legion-only needs stay in Legion.
- Use `uv`, never `pip`. Set `UV_CACHE_DIR=D:/User/.uv-cache` and `UV_LINK_MODE=copy` before uv commands.
- Never read or print `.env*`, `gateways.json`, `tokens.json` or `settings.json`. Steps that need a secret are marked **(user)**: stop and ask the user to do them.
- Keep in Legion, unchanged: the tool loop, `update_plan`, delegation, approvals, turn budgets, `GatewayRoute`, `cooldown.py`, fallback lists, per-kind cooldown tuning, `SwitchInfo`, the `models` tiers in `gateways/<provider>/*.json`.
- Compose service name is `conversationgateway` (the name its own docs and compose file use), port 29407, published on `0.0.0.0` so services outside Citadel can connect. Each outside caller uses its own token.
- Legion baseline before this plan: `1436 passed` (`docs/superpowers/plans/baseline-2026-11-14.txt`).
- Async I/O in request paths. The one sync call (`run_interpret`) stays sync because its callers are sync.
- Commit trailer, exactly: `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`

## Behavior changes accepted by the spec

Write these into `apps/legion/README.md` in Task 6. Everything else must behave as before.

1. A malformed provider stream is no longer retried once on the same gateway. The gateway reports it as `unavailable`, so Legion cools that gateway down and moves to the next one.
2. The context breakdown for Anthropic agents is always an estimate. The gateway has no token-count endpoint, so `_AnthropicRequestCounter` raises and the existing estimate path is used.
3. While a round streams, the live token meter counts answer text only, not thinking or tool-argument text. The exact total at the end of each round is unchanged.
4. A gateway counts as "has credentials" when ConversationGateway has a saved gateway with that id. Legion no longer sees provider keys.
5. Bedrock and Vertex are configured in ConversationGateway, not through Legion's AWS and Google env vars.

## File Structure

- Create `apps/legion/src/providers/gateway_client.py`: HTTP client for ConversationGateway and `GatewayCallError`. Shared with Plan 3b.
- Create `apps/legion/src/providers/language/anthropic_gateway_shim.py`: request and response translation, and the SDK-shaped shim.
- Create `apps/legion/tests/test_gateway_client.py`, `apps/legion/tests/test_anthropic_gateway_shim.py`.
- Modify `apps/legion/src/providers/gateway_failover.py` (`classify`), `apps/legion/src/providers/cooldown.py` (`extract_retry_after_seconds`).
- Modify `apps/legion/src/providers/language/anthropic_provider.py` (client construction, `_stream_pieces`, the stream error branch, imports).
- Modify `apps/legion/tests/conftest.py`, `tests/test_gateway_failover.py`, `tests/test_anthropic_gateway_failover.py`, `tests/test_anthropic_provider*.py`, `tests/test_agent_config.py`.
- Modify `apps/legion/gateways/anthropic/*.json` (drop credential fields), `apps/legion/gateways/README.md`, `apps/legion/README.md`, `apps/legion/pyproject.toml`, `apps/legion/uv.lock`.
- Modify `docker-compose.yml`, `docs/deployment.md`.

---

### Task 1: Gateway HTTP client

**Files:**
- Create: `apps/legion/src/providers/gateway_client.py`
- Test: `apps/legion/tests/test_gateway_client.py`

**Interfaces:**
- Consumes: `src.runtime.internal_auth.current_requester()` (has `.username`).
- Produces:
  - `GatewayCallError(status: int, code: str, message: str, kind: str | None = None, retry_after: float | None = None)` with those attributes; `str(error)` is the message.
  - `ConversationGatewayClient(transport: httpx.AsyncBaseTransport | None = None, sync_transport: httpx.BaseTransport | None = None)`
  - `client.stream(body: dict) -> AsyncIterator[dict]`: yields the NDJSON events; the last one has `type == "done"`.
  - `client.chat_sync(body: dict) -> dict`: one non-streamed reply.
  - `saved_gateway_ids() -> frozenset[str]`: ids saved in ConversationGateway, cached 60 s; empty when unreachable.
  - Env: `CONVERSATION_GATEWAY_URL` (default `http://127.0.0.1:29407`), `CONVERSATION_GATEWAY_TOKEN`.

- [ ] **Step 1: Create the branch**

Run: `git checkout -b refactor/legion-conversation-gateway`

- [ ] **Step 2: Write the failing tests `apps/legion/tests/test_gateway_client.py`**

```python
"""Legion's HTTP client for ConversationGateway: wire format in, typed errors out."""

from __future__ import annotations

import json

import httpx
import pytest

from src.providers import gateway_client
from src.providers.gateway_client import ConversationGatewayClient, GatewayCallError

DONE = {"type": "done", "content": [{"type": "text", "text": "Hi"}], "stop_reason": "end",
        "usage": {"input_tokens": 3, "output_tokens": 1, "cached_input_tokens": 0, "reasoning_tokens": 0}}


def ndjson(*events: dict) -> bytes:
    return "".join(json.dumps(event) + "\n" for event in events).encode()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("CONVERSATION_GATEWAY_URL", "http://gateway.test:29407/")
    monkeypatch.setenv("CONVERSATION_GATEWAY_TOKEN", "cg_test")
    gateway_client.reset_cache()
    yield
    gateway_client.reset_cache()


async def collect(client: ConversationGatewayClient, body: dict) -> list[dict]:
    return [event async for event in client.stream(body)]


async def test_stream_posts_the_body_and_yields_events():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ndjson({"type": "text", "delta": "Hi"}, DONE))

    client = ConversationGatewayClient(transport=httpx.MockTransport(handler))
    events = await collect(client, {"gateway": "claude", "messages": []})
    assert [event["type"] for event in events] == ["text", "done"]
    assert str(seen[0].url) == "http://gateway.test:29407/api/chat"
    assert seen[0].headers["x-internal-token"] == "cg_test"
    assert seen[0].headers["x-requester-username"] == "legion"
    assert json.loads(seen[0].content) == {"gateway": "claude", "messages": [], "stream": True}


async def test_http_error_becomes_a_typed_error_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "7"},
                              json={"error": {"code": "gateway_rate_limit", "message": "slow down", "kind": "rate_limit"}})

    client = ConversationGatewayClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayCallError) as caught:
        await collect(client, {"gateway": "claude"})
    error = caught.value
    assert (error.status, error.code, error.kind, error.retry_after, str(error)) == (
        429, "gateway_rate_limit", "rate_limit", 7.0, "slow down")


async def test_error_line_mid_stream_raises():
    line = {"type": "error", "status": 502, "error": {"code": "gateway_unavailable", "message": "cut", "kind": "unavailable"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson({"type": "text", "delta": "Hi"}, line))

    client = ConversationGatewayClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayCallError) as caught:
        await collect(client, {"gateway": "claude"})
    assert (caught.value.status, caught.value.kind) == (502, "unavailable")


async def test_stream_without_done_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson({"type": "text", "delta": "Hi"}))

    client = ConversationGatewayClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayCallError) as caught:
        await collect(client, {"gateway": "claude"})
    assert caught.value.kind == "unavailable"


async def test_unreachable_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = ConversationGatewayClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayCallError) as caught:
        await collect(client, {"gateway": "claude"})
    assert (caught.value.status, caught.value.kind) == (502, "unavailable")


async def test_an_error_without_kind_keeps_kind_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": {"code": "invalid_request", "message": "bad body"}})

    client = ConversationGatewayClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayCallError) as caught:
        await collect(client, {"gateway": "claude"})
    assert (caught.value.status, caught.value.kind) == (422, None)


def test_chat_sync_returns_the_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Hi"}], "stop_reason": "end"})

    client = ConversationGatewayClient(sync_transport=httpx.MockTransport(handler))
    assert client.chat_sync({"gateway": "claude"})["stop_reason"] == "end"


def test_saved_gateway_ids_is_cached(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"gateways": [{"id": "claude"}, {"id": "openrouter"}]})

    monkeypatch.setattr(gateway_client, "_SYNC_TRANSPORT", httpx.MockTransport(handler))
    assert gateway_client.saved_gateway_ids() == frozenset({"claude", "openrouter"})
    assert gateway_client.saved_gateway_ids() == frozenset({"claude", "openrouter"})
    assert calls == ["/api/gateways"]


def test_saved_gateway_ids_is_empty_and_not_cached_when_unreachable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(gateway_client, "_SYNC_TRANSPORT", httpx.MockTransport(handler))
    assert gateway_client.saved_gateway_ids() == frozenset()
    assert gateway_client._ids is None
```

- [ ] **Step 3: Run and see it fail**

Run: `cd apps/legion && uv run pytest tests/test_gateway_client.py -q`
Expected: `ModuleNotFoundError: No module named 'src.providers.gateway_client'`.

- [ ] **Step 4: Write `apps/legion/src/providers/gateway_client.py`**

```python
"""Legion's HTTP client for ConversationGateway (AI/ModelProviders/ConversationGateway).

The gateway holds provider keys and speaks to Anthropic, OpenAI and the CNV
model services. Legion sends one chat request per model round and runs the
tools itself. A failure arrives as GatewayCallError carrying the gateway's
own `kind` (rate_limit, quota, auth, unavailable), which gateway_failover.py
turns into a cooldown and a switch.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

import httpx

from src.runtime import internal_auth

DEFAULT_URL = "http://127.0.0.1:29407"
# No read timeout: a round streams for as long as the model writes. The turn
# guard and Stop end a slow turn; connect, write and pool still fail fast.
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
_SYNC_TIMEOUT = httpx.Timeout(300.0, connect=10.0)
_IDS_TIMEOUT = httpx.Timeout(5.0)
_IDS_TTL_SECONDS = 60.0
# Tests replace this to answer saved_gateway_ids() without a network.
_SYNC_TRANSPORT: httpx.BaseTransport | None = None

_ids: frozenset[str] | None = None
_ids_until = 0.0


class GatewayCallError(Exception):
    """ConversationGateway refused or failed a call. `kind` is None for a
    request the gateway rejected as invalid, which must not be retried."""

    def __init__(self, status: int, code: str, message: str,
                 kind: str | None = None, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.kind = kind
        self.retry_after = retry_after


def base_url() -> str:
    return (os.getenv("CONVERSATION_GATEWAY_URL") or DEFAULT_URL).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"X-Requester-Username": internal_auth.current_requester().username or "legion"}
    token = os.getenv("CONVERSATION_GATEWAY_TOKEN")
    if token:
        headers["X-Internal-Token"] = token
    return headers


def _unavailable(message: str) -> GatewayCallError:
    return GatewayCallError(502, "gateway_unavailable", message, kind="unavailable")


def _seconds(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _error(status: int, payload: Any, retry_after: str | None = None) -> GatewayCallError:
    """The gateway's `{error: {code, message, kind?}}` as an exception."""
    detail = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(detail, dict):
        detail = {}
    return GatewayCallError(
        status,
        str(detail.get("code") or "gateway_error"),
        str(detail.get("message") or f"ConversationGateway answered {status}"),
        kind=detail.get("kind") if isinstance(detail.get("kind"), str) else None,
        retry_after=_seconds(retry_after),
    )


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


class ConversationGatewayClient:
    """One chat round per call. Holds no state between calls."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None,
                 sync_transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport
        self._sync_transport = sync_transport

    async def stream(self, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """The round's NDJSON events in order; the last one is `done`."""
        finished = False
        try:
            # shortcut: one HTTP client per round, safe across Legion's event loops;
            # pool per loop if connection setup shows up in round latency.
            async with httpx.AsyncClient(transport=self._transport, timeout=_STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST", f"{base_url()}/api/chat", json={**body, "stream": True}, headers=_headers(),
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise _error(response.status_code, _json(response.text), response.headers.get("retry-after"))
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        event = _json(line)
                        if not isinstance(event, dict):
                            raise _unavailable("ConversationGateway sent an unreadable stream line.")
                        if event.get("type") == "error":
                            raise _error(int(event.get("status") or 502), event)
                        finished = event.get("type") == "done"
                        yield event
        except httpx.HTTPError as error:
            raise _unavailable(f"ConversationGateway is unreachable: {type(error).__name__}") from error
        if not finished:
            raise _unavailable("ConversationGateway ended the stream early.")

    def chat_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        """One non-streamed reply, for the sync `interpret` path."""
        try:
            with httpx.Client(transport=self._sync_transport, timeout=_SYNC_TIMEOUT) as client:
                response = client.post(f"{base_url()}/api/chat", json={**body, "stream": False}, headers=_headers())
        except httpx.HTTPError as error:
            raise _unavailable(f"ConversationGateway is unreachable: {type(error).__name__}") from error
        payload = _json(response.text)
        if response.status_code != 200:
            raise _error(response.status_code, payload, response.headers.get("retry-after"))
        if not isinstance(payload, dict):
            raise _unavailable("ConversationGateway sent an unreadable reply.")
        return payload


def saved_gateway_ids() -> frozenset[str]:
    """Ids of the gateways saved in ConversationGateway, cached for a minute.
    Empty (and not cached) when the service cannot be reached."""
    global _ids, _ids_until
    if _ids is not None and time.monotonic() < _ids_until:
        return _ids
    try:
        with httpx.Client(transport=_SYNC_TRANSPORT, timeout=_IDS_TIMEOUT) as client:
            response = client.get(f"{base_url()}/api/gateways", headers=_headers())
        entries = response.json().get("gateways") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        entries = None
    if not isinstance(entries, list):
        return frozenset()
    _ids = frozenset(str(entry["id"]) for entry in entries if isinstance(entry, dict) and entry.get("id"))
    _ids_until = time.monotonic() + _IDS_TTL_SECONDS
    return _ids


def reset_cache() -> None:
    """Forget the saved ids (tests, or after an admin edits gateways)."""
    global _ids, _ids_until
    _ids, _ids_until = None, 0.0
```

- [ ] **Step 5: Run and see it pass**

Run: `uv run pytest tests/test_gateway_client.py -q`
Expected: `9 passed`.

- [ ] **Step 6: Commit**

```bash
cd ../..
git add apps/legion/src/providers/gateway_client.py apps/legion/tests/test_gateway_client.py
git commit -m "feat: add ConversationGateway client to legion" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 2: Failover reads the gateway's error kind

**Files:**
- Modify: `apps/legion/src/providers/gateway_failover.py` (`classify`, near line 36)
- Modify: `apps/legion/src/providers/cooldown.py` (`extract_retry_after_seconds`, near line 56)
- Test: `apps/legion/tests/test_gateway_failover.py`, `apps/legion/tests/test_cooldown.py`

**Interfaces:**
- Consumes: `GatewayCallError` (Task 1).
- Produces: `classify(GatewayCallError)` returns the matching `FailureKind` or `None`; `cooldown.extract_retry_after_seconds(GatewayCallError)` returns its `retry_after`. SDK errors still classify as before in this task, so the OpenAI provider keeps working.

- [ ] **Step 1: Add the failing tests**

Append to `apps/legion/tests/test_gateway_failover.py`:

```python
from src.providers.gateway_client import GatewayCallError


def gateway_error(status, message="failure", retry_after=None):
    """What ConversationGateway reports for an upstream failure of this status."""
    kind = {429: "rate_limit", 402: "quota", 401: "auth", 403: "auth", 500: "unavailable"}.get(status)
    return GatewayCallError(status, "gateway_error", message, kind=kind, retry_after=retry_after)


@pytest.mark.parametrize("status,kind", [(429, "rate_limit"), (402, "quota"), (401, "auth"), (500, "unavailable")])
def test_classify_reads_the_gateway_kind(status, kind):
    assert failover.classify(gateway_error(status)) == failover.FailureKind(kind)


def test_a_gateway_error_without_kind_is_not_retried():
    assert failover.classify(GatewayCallError(422, "invalid_request", "bad body")) is None


def test_an_unknown_gateway_kind_is_not_retried():
    assert failover.classify(GatewayCallError(500, "x", "y", kind="mystery")) is None


def test_rate_limit_cooldown_uses_the_gateway_retry_after():
    error = gateway_error(429, retry_after=7.0)
    assert failover.cooldown_seconds(failover.FailureKind.rate_limit, error) == 7.0
```

- [ ] **Step 2: Run and see them fail**

Run: `cd apps/legion && uv run pytest tests/test_gateway_failover.py -q`
Expected: the new tests fail (`classify` returns `None` for the first four cases; the cooldown test returns 60.0).

- [ ] **Step 3: Teach `classify` the gateway error**

In `apps/legion/src/providers/gateway_failover.py` add the import and a lookup below `_FAILURE_WORDS`:

```python
from src.providers.gateway_client import GatewayCallError

_KINDS = {kind.value: kind for kind in FailureKind}
```

Make these the first lines of `classify()`, before the `json.JSONDecodeError` check:

```python
    if isinstance(error, GatewayCallError):
        # The gateway already classified the upstream failure. No kind means
        # the request itself was refused: never retry that.
        return _KINDS.get(error.kind or "")
```

- [ ] **Step 4: Read `Retry-After` from the gateway error**

In `apps/legion/src/providers/cooldown.py`, make these the first lines of `extract_retry_after_seconds()`:

```python
    direct = getattr(error, "retry_after", None)
    if isinstance(direct, (int, float)) and not isinstance(direct, bool):
        return float(direct)
```

- [ ] **Step 5: Run the failover and cooldown tests**

Run: `uv run pytest tests/test_gateway_failover.py tests/test_cooldown.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd ../..
git add apps/legion/src/providers/gateway_failover.py apps/legion/src/providers/cooldown.py apps/legion/tests/test_gateway_failover.py
git commit -m "feat: classify ConversationGateway errors for failover" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 3: Anthropic-shaped shim over the gateway

**Files:**
- Create: `apps/legion/src/providers/language/anthropic_gateway_shim.py`
- Test: `apps/legion/tests/test_anthropic_gateway_shim.py`

**Interfaces:**
- Consumes: `ConversationGatewayClient.stream`, `.chat_sync` (Task 1).
- Produces:
  - `request_body(gateway: str, kwargs: dict) -> dict`: the gateway chat body for the keyword arguments `anthropic_provider.run_chat` passes to `client.messages.stream(...)`.
  - `response_message(reply: dict) -> SimpleNamespace` with `.content` (blocks with `.type` of `"text"`, `"tool_use"` or `"thinking"`), `.stop_reason` (`"end_turn"`, `"tool_use"`, `"max_tokens"`, `"refusal"`, `"error"`), `.usage` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`).
  - `GatewayShim(gateway: str, client: ConversationGatewayClient)` with `.messages.stream(**kwargs)` (async context manager yielding an object with `text_stream` and `await get_final_message()`), `.messages.create(**kwargs)` (sync), `.messages.count_tokens(**kwargs)` (raises `NotImplementedError`).

- [ ] **Step 1: Write the failing tests `apps/legion/tests/test_anthropic_gateway_shim.py`**

```python
"""Anthropic-shaped requests and replies translated to and from ConversationGateway."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from src.providers.gateway_client import GatewayCallError
from src.providers.language.anthropic_gateway_shim import GatewayShim, request_body, response_message

CACHE = {"type": "ephemeral"}
TOOL = {"name": "get_time", "description": "Now.", "input_schema": {"type": "object", "properties": {}}}


def base(**extra):
    return {"model": "claude-sonnet-5-5", "max_tokens": 512, "system": "Be brief.",
            "messages": [{"role": "user", "content": "Hello"}], "tools": [], **extra}


def test_plain_request():
    assert request_body("claude", base()) == {
        "gateway": "claude", "model": "claude-sonnet-5-5", "max_tokens": 512,
        "system": "Be brief.", "messages": [{"role": "user", "content": "Hello"}],
    }


def test_cache_markers_become_the_cache_flag_and_are_stripped():
    body = request_body("claude", base(
        system=[{"type": "text", "text": "Be brief.", "cache_control": CACHE}],
        tools=[{**TOOL, "cache_control": CACHE}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "Hello", "cache_control": CACHE}]}],
    ))
    assert body["cache"] is True
    assert body["system"] == "Be brief."
    assert body["tools"] == [{"name": "get_time", "description": "Now.",
                              "parameters": {"type": "object", "properties": {}}}]
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}]


def test_options_map_to_temperature_and_reasoning():
    body = request_body("claude", base(extra_body={"temperature": 0.2}, output_config={"effort": "high"}))
    assert body["temperature"] == 0.2
    assert body["reasoning"] == {"effort": "high"}


def test_a_tool_round_trip_keeps_ids_and_reasoning_state():
    assistant = [NS(type="thinking", state="opaque-1"), NS(type="text", text="Checking."),
                 NS(type="tool_use", id="c1", name="get_time", input={"zone": "UTC"})]
    results = [{"type": "tool_result", "tool_use_id": "c1", "content": "12:00"}]
    body = request_body("claude", base(messages=[
        {"role": "user", "content": "Time?"},
        {"role": "assistant", "content": assistant},
        {"role": "user", "content": results},
    ]))
    assert body["messages"] == [
        {"role": "user", "content": "Time?"},
        {"role": "assistant", "reasoning_state": "opaque-1", "content": [
            {"type": "text", "text": "Checking."},
            {"type": "tool_call", "id": "c1", "name": "get_time", "arguments": {"zone": "UTC"}}]},
        {"role": "tool", "content": [{"type": "tool_result", "id": "c1", "text": "12:00", "is_error": False}]},
    ]


def test_empty_text_blocks_are_dropped():
    body = request_body("claude", base(messages=[
        {"role": "assistant", "content": [NS(type="text", text=""), NS(type="text", text="Hi")]}]))
    assert body["messages"] == [{"role": "assistant", "content": [{"type": "text", "text": "Hi"}]}]


def test_an_image_block_is_flattened():
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
    body = request_body("claude", base(messages=[{"role": "user", "content": [image]}]))
    assert body["messages"][0]["content"] == [{"type": "image", "media_type": "image/png", "data": "AAAA"}]


def test_an_unknown_block_is_refused():
    with pytest.raises(ValueError, match="Unsupported content block: video"):
        request_body("claude", base(messages=[{"role": "user", "content": [{"type": "video"}]}]))


def test_reply_becomes_an_anthropic_shaped_message():
    message = response_message({
        "content": [{"type": "text", "text": "Checking."},
                    {"type": "tool_call", "id": "c1", "name": "get_time", "arguments": {"zone": "UTC"}}],
        "stop_reason": "tool_call", "reasoning_state": "opaque-1",
        "usage": {"input_tokens": 100, "output_tokens": 7, "cached_input_tokens": 60, "reasoning_tokens": 0},
    })
    assert [block.type for block in message.content] == ["thinking", "text", "tool_use"]
    assert message.content[0].state == "opaque-1"
    assert (message.content[2].id, message.content[2].name, message.content[2].input) == ("c1", "get_time", {"zone": "UTC"})
    assert message.stop_reason == "tool_use"
    usage = message.usage
    # The provider adds the three input counters back together to get the whole prompt.
    assert usage.input_tokens + usage.cache_read_input_tokens + usage.cache_creation_input_tokens == 100
    assert (usage.cache_read_input_tokens, usage.output_tokens) == (60, 7)


@pytest.mark.parametrize("gateway,anthropic", [("end", "end_turn"), ("tool_call", "tool_use"),
                                               ("max_tokens", "max_tokens"), ("refusal", "refusal"), ("error", "error")])
def test_stop_reasons(gateway, anthropic):
    assert response_message({"content": [], "stop_reason": gateway}).stop_reason == anthropic


class FakeClient:
    def __init__(self, events=(), reply=None, error=None):
        self.events, self.reply, self.error, self.bodies = list(events), reply, error, []

    async def stream(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        for event in self.events:
            yield event

    def chat_sync(self, body):
        self.bodies.append(body)
        return self.reply


DONE = {"type": "done", "content": [{"type": "text", "text": "Hello"}], "stop_reason": "end",
        "usage": {"input_tokens": 3, "output_tokens": 1, "cached_input_tokens": 0}}


async def test_stream_yields_text_and_the_final_message():
    client = FakeClient([{"type": "reasoning", "delta": "hm"}, {"type": "text", "delta": "Hel"},
                         {"type": "tool_call", "id": "c", "name": "n", "arguments_delta": "{}"},
                         {"type": "text", "delta": "lo"}, DONE])
    async with GatewayShim("claude", client).messages.stream(**base()) as stream:
        chunks = [chunk async for chunk in stream.text_stream]
        message = await stream.get_final_message()
    assert chunks == ["Hel", "lo"]
    assert message.stop_reason == "end_turn"
    assert client.bodies[0]["gateway"] == "claude"


async def test_a_gateway_error_surfaces_while_streaming():
    client = FakeClient(error=GatewayCallError(429, "gateway_rate_limit", "slow", kind="rate_limit"))
    with pytest.raises(GatewayCallError):
        async with GatewayShim("claude", client).messages.stream(**base()) as stream:
            [chunk async for chunk in stream.text_stream]


def test_create_is_one_sync_reply():
    client = FakeClient(reply={"content": [{"type": "text", "text": "Hi"}], "stop_reason": "end",
                               "usage": {"input_tokens": 2, "output_tokens": 1}})
    message = GatewayShim("claude", client).messages.create(**base())
    assert message.content[0].text == "Hi"
    assert message.usage.input_tokens == 2


async def test_count_tokens_is_not_offered():
    with pytest.raises(NotImplementedError):
        await GatewayShim("claude", FakeClient()).messages.count_tokens(model="m", messages=[])
```

- [ ] **Step 2: Run and see it fail**

Run: `cd apps/legion && uv run pytest tests/test_anthropic_gateway_shim.py -q`
Expected: `ModuleNotFoundError: No module named 'src.providers.language.anthropic_gateway_shim'`.

- [ ] **Step 3: Write `apps/legion/src/providers/language/anthropic_gateway_shim.py`**

```python
"""The slice of the Anthropic SDK that anthropic_provider.py uses, served by
ConversationGateway.

The provider's tool loop builds Anthropic-shaped requests and reads
Anthropic-shaped replies. This module translates both ways, so the loop and
its tests stay as they are while the SDK and the provider keys leave Legion.
Pure functions do the translation; the classes only carry the calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

from src.providers.gateway_client import ConversationGatewayClient, GatewayCallError

_STOP_REASONS = {"end": "end_turn", "tool_call": "tool_use"}
_EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _get(block: Any, key: str) -> Any:
    """A field of a content block, which is a dict we built or an object from a reply."""
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


def _has_cache_marker(blocks: Any) -> bool:
    return isinstance(blocks, list) and any(isinstance(block, dict) and "cache_control" in block for block in blocks)


def _messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Gateway messages, and whether any block carried a cache marker.
    Anthropic sends tool results inside a user message; the gateway has a `tool` role."""
    out: list[dict[str, Any]] = []
    cache = False
    for message in messages:
        role, content = message["role"], message.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        cache = cache or _has_cache_marker(content)
        blocks: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        state: str | None = None
        for block in content or []:
            kind = _get(block, "type")
            if kind == "text":
                if _get(block, "text"):
                    blocks.append({"type": "text", "text": _get(block, "text")})
            elif kind == "tool_use":
                blocks.append({"type": "tool_call", "id": _get(block, "id"), "name": _get(block, "name"),
                               "arguments": _get(block, "input") or {}})
            elif kind == "tool_result":
                results.append({"type": "tool_result", "id": _get(block, "tool_use_id"),
                                "text": str(_get(block, "content") or ""), "is_error": bool(_get(block, "is_error"))})
            elif kind == "thinking":
                state = _get(block, "state")
            elif kind == "image":
                source = _get(block, "source") or {}
                blocks.append({"type": "image", "media_type": source.get("media_type"), "data": source.get("data")})
            else:
                raise ValueError(f"Unsupported content block: {kind}")
        if results:
            out.append({"role": "tool", "content": results})
        if blocks or state:
            converted: dict[str, Any] = {"role": role, "content": blocks}
            if state:
                converted = {"role": role, "reasoning_state": state, "content": blocks}
            out.append(converted)
    return out, cache


def request_body(gateway: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """The gateway chat body for one `messages.stream(...)` / `messages.create(...)` call."""
    system = kwargs.get("system")
    cache = _has_cache_marker(system)
    if isinstance(system, list):
        system = "".join(block["text"] for block in system)
    raw_tools = kwargs.get("tools") or []
    cache = cache or _has_cache_marker(raw_tools)
    messages, marked = _messages(kwargs["messages"])
    body: dict[str, Any] = {"gateway": gateway, "model": kwargs["model"], "max_tokens": kwargs["max_tokens"]}
    if system:
        body["system"] = system
    body["messages"] = messages
    if raw_tools:
        body["tools"] = [{"name": tool["name"], "description": tool.get("description") or "",
                          "parameters": tool.get("input_schema") or _EMPTY_SCHEMA} for tool in raw_tools]
    if cache or marked:
        body["cache"] = True
    temperature = (kwargs.get("extra_body") or {}).get("temperature")
    if temperature is not None:
        body["temperature"] = temperature
    effort = (kwargs.get("output_config") or {}).get("effort")
    if effort:
        body["reasoning"] = {"effort": effort}
    return body


def response_message(reply: dict[str, Any]) -> SimpleNamespace:
    """A gateway reply (the `done` event or a plain response) as an Anthropic-shaped message.
    `reasoning_state` rides along as a `thinking` block: the loop sends it back on the next
    round and drops it when it switches gateway, exactly as it treats SDK thinking blocks."""
    content: list[SimpleNamespace] = []
    if reply.get("reasoning_state"):
        content.append(SimpleNamespace(type="thinking", state=reply["reasoning_state"]))
    for block in reply.get("content") or []:
        if block.get("type") == "text":
            content.append(SimpleNamespace(type="text", text=block.get("text") or ""))
        elif block.get("type") == "tool_call":
            content.append(SimpleNamespace(type="tool_use", id=block["id"], name=block["name"],
                                           input=block.get("arguments") or {}))
    usage = reply.get("usage") or {}
    cached = int(usage.get("cached_input_tokens") or 0)
    stop = reply.get("stop_reason") or "end"
    return SimpleNamespace(
        content=content,
        stop_reason=_STOP_REASONS.get(stop, stop),
        # The gateway's input count already includes cache reads and writes. The provider
        # adds the three counters back together, so the cached part is split out here.
        usage=SimpleNamespace(
            input_tokens=max(int(usage.get("input_tokens") or 0) - cached, 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_input_tokens=cached,
            cache_creation_input_tokens=0,
        ),
    )


class _Stream:
    """One streamed round: text chunks first, then the whole message."""

    def __init__(self, events: AsyncIterator[dict[str, Any]]) -> None:
        self._events = events
        self._done: dict[str, Any] | None = None
        self.text_stream = self._text()

    async def _text(self) -> AsyncIterator[str]:
        async for event in self._events:
            if event.get("type") == "text" and event.get("delta"):
                yield event["delta"]
            elif event.get("type") == "done":
                self._done = event

    async def get_final_message(self) -> SimpleNamespace:
        async for _chunk in self.text_stream:  # a caller that stopped reading early
            pass
        if self._done is None:
            raise GatewayCallError(502, "gateway_unavailable", "ConversationGateway ended the stream early.",
                                   kind="unavailable")
        return response_message(self._done)


class _StreamContext:
    def __init__(self, events: AsyncIterator[dict[str, Any]]) -> None:
        self._events = events

    async def __aenter__(self) -> _Stream:
        return _Stream(self._events)

    async def __aexit__(self, *_exc: Any) -> bool:
        await self._events.aclose()
        return False


class _Messages:
    def __init__(self, gateway: str, client: ConversationGatewayClient) -> None:
        self._gateway = gateway
        self._client = client

    def stream(self, **kwargs: Any) -> _StreamContext:
        return _StreamContext(self._client.stream(request_body(self._gateway, kwargs)))

    def create(self, **kwargs: Any) -> SimpleNamespace:
        return response_message(self._client.chat_sync(request_body(self._gateway, kwargs)))

    async def count_tokens(self, **_kwargs: Any) -> Any:
        """The gateway has no token-count route; the caller settles for its estimate."""
        raise NotImplementedError("ConversationGateway does not count tokens")


class GatewayShim:
    """Stands where an Anthropic SDK client stood, for one saved gateway."""

    def __init__(self, gateway: str, client: ConversationGatewayClient) -> None:
        self.messages = _Messages(gateway, client)
```

- [ ] **Step 4: Run and see it pass**

Run: `uv run pytest tests/test_anthropic_gateway_shim.py -q`
Expected: `17 passed`.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add apps/legion/src/providers/language/anthropic_gateway_shim.py apps/legion/tests/test_anthropic_gateway_shim.py
git commit -m "feat: add Anthropic-shaped shim over ConversationGateway" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 4: Switch the Anthropic provider to the shim

**Files:**
- Modify: `apps/legion/src/providers/language/anthropic_provider.py` (imports lines 30-63; class `_Anthropic` lines 79-158; `_stream_pieces` lines 316-331; `run_chat` locals near lines 425-427 and the `except` block lines 494-540)
- Modify: `apps/legion/tests/conftest.py`, `tests/test_anthropic_provider.py`, `tests/test_anthropic_provider_streaming.py`, `tests/test_anthropic_provider_prompt_cache.py`, `tests/test_anthropic_gateway_failover.py`, `tests/test_agent_config.py`

**Interfaces:**
- Consumes: `GatewayShim` (Task 3), `gateway_client.saved_gateway_ids`, `GatewayCallError` (Task 1), `classify` (Task 2).
- Produces: `_Anthropic.get_client(gateway=None)` and `get_sync_client(gateway=None)` both return the cached `GatewayShim` for that gateway; `has_api_key(gateway=None)` is true when ConversationGateway has that id saved. Module-level `_get_client`, `_get_sync_client`, `has_api_key`, `is_available`, `PROVIDER_ID`, `DEFAULT_MODEL`, `VENDOR_LABEL`, `run_chat`, `run_interpret` keep their names and signatures.

- [ ] **Step 1: Make every test see all gateways as saved**

In `apps/legion/tests/conftest.py` add:

```python
class _EveryGateway:
    """Stands in for ConversationGateway's saved ids: tests never call the service."""

    def __contains__(self, _name: object) -> bool:
        return True


@pytest.fixture(autouse=True)
def _saved_gateways(monkeypatch):
    from src.providers import gateway_client

    monkeypatch.setattr(gateway_client, "saved_gateway_ids", lambda: _EveryGateway())
```

(`import pytest` is already at the top of that file; add it if not.)

- [ ] **Step 2: Replace the client construction in `_Anthropic`**

Replace `has_api_key`, `_build_client`, `get_client` and `get_sync_client`, and the two cache attributes, with:

```python
    _clients: dict[str, GatewayShim] = {}

    @classmethod
    def _gateway_name(cls) -> str:
        return os.getenv(cls.GATEWAY_ENV) or "claude"

    @classmethod
    def has_api_key(cls, gateway: str | None = None) -> bool:
        """Whether ConversationGateway has this gateway saved. The keys live there,
        so "saved" is all Legion can know; a bad key shows up as an `auth` failure."""
        return (gateway or cls._gateway_name()) in gateway_client.saved_gateway_ids()

    @classmethod
    def get_client(cls, gateway: str | None = None) -> GatewayShim:
        """The shim for this gateway, built once."""
        gateway_name = gateway or cls._gateway_name()
        if gateway_name not in cls._clients:
            cls._clients[gateway_name] = GatewayShim(gateway_name, gateway_client.ConversationGatewayClient())
        return cls._clients[gateway_name]

    @classmethod
    def get_sync_client(cls, gateway: str | None = None) -> GatewayShim:
        """Same object as get_client(): the shim has both the async stream and the sync create."""
        return cls.get_client(gateway)
```

Keep `is_available`, `resolve_default_model` and `resolve_vendor_label` as they are.

- [ ] **Step 3: Replace the imports**

Remove the whole `from anthropic import (...)` block and `from anthropic.lib.streaming import AsyncMessageStream`. Remove `import json` and `import traceback` if nothing else in the file uses them after Step 5 (`grep -n "json\.\|traceback\." src/providers/language/anthropic_provider.py`). Change

```python
from src.providers import cancellation, cooldown, llm_config, llm_options, token_limits
```

to

```python
from src.providers import cancellation, cooldown, gateway_client, llm_config, llm_options, token_limits
from src.providers.gateway_client import GatewayCallError
from src.providers.language.anthropic_gateway_shim import GatewayShim
```

- [ ] **Step 4: Simplify `_stream_pieces`**

```python
async def _stream_pieces(stream: Any) -> AsyncIterator[tuple[bool, str]]:
    """Yield (is_text, chunk) for what a round streams. The gateway shim streams
    answer text only, so every chunk is text."""
    async for chunk in stream.text_stream:
        yield True, chunk
```

- [ ] **Step 5: Replace the stream error branch in `run_chat`**

Delete the two locals `malformed_stream_retries: set[str] = set()` and `failed_stream_tokens = 0`, and change both `guard.check_tokens(total_tokens + failed_stream_tokens)` calls to `guard.check_tokens(total_tokens)`. Replace everything from `except Exception as error:` down to the line before `prompt_tokens = _prompt_tokens(response.usage)` with:

```python
                    except Exception as error:
                        # 422 without a kind: the provider refused the request itself.
                        # If it names an option we sent, drop that option and repeat the round.
                        if isinstance(error, GatewayCallError) and error.status == 422 and classify(error) is None:
                            if not text_parts and options.drop_rejected(str(error), model_name):
                                continue
                        switch = route.advance(error)
                        if switch is None:
                            raise
                        if on_event:
                            if text_parts:
                                await on_event(step_event("token_reset"))
                            await on_event(step_event("gateway_switch", **switch.as_dict()))
                        messages = _strip_thinking(messages)
                        client = _get_client(route.current)
                        model_name = _model_for_route(route, model)
                        use_cache = _prompt_cache_enabled(route.current)
                        system, tools = _cached_request(system_prompt, schemas) if use_cache else (system_prompt, schemas)
```

Also delete the now-unused `stream_stage` assignments and `stream_chars` if no line reads them (`grep -n "stream_stage\|stream_chars" src/providers/language/anthropic_provider.py`). Rewrite the module docstring's SDK paragraphs to two sentences: the provider talks to ConversationGateway through `anthropic_gateway_shim.py`, and keys are saved in that service.

- [ ] **Step 6: Run the Anthropic test files and sort every failure**

Run: `cd apps/legion && uv run pytest tests/test_anthropic_provider.py tests/test_anthropic_provider_streaming.py tests/test_anthropic_provider_prompt_cache.py tests/test_anthropic_gateway_failover.py tests/test_agent_config.py -q 2>&1 | tail -40`

Every failing test falls into one of these groups. Apply the stated change and nothing else:

| Group | How to recognise it | Change |
|---|---|---|
| A. SDK errors as fakes | uses `sdk_error(anthropic, ...)`, `anthropic.RateLimitError`, `anthropic.BadRequestError` or `import anthropic` | Replace with `gateway_error(status, ...)` from `tests.test_gateway_failover`. A 400 "bad request" fake becomes `GatewayCallError(422, "invalid_request", "<same message>")`. Keep every expected switch, cooldown and message. |
| B. Malformed stream | uses `_malformed_stream`, `ServerSentEvent`, `JSONDecodeError`, or asserts "invalid response stream after retrying" | Delete the test and the `_malformed_stream` helper. Accepted behavior change 1. |
| C. Credentials from env | sets `CLAUDE_API_KEY`, `OPENROUTER_*`, AWS or Google env vars and asserts on `has_api_key()`, `is_available()`, `_build_client`, `AnthropicBedrock` or `AnthropicVertex` | Delete tests of `_build_client` and of the Bedrock and Vertex classes. Rewrite `has_api_key` tests as in Step 7. A test that only sets `CLAUDE_API_KEY` as setup and then fakes `_get_client` needs no change. |
| D. SDK stream events | builds an `AsyncMessageStream`, or asserts that thinking or tool-argument text moved the live meter | Delete the test. Accepted behavior change 3. |
| E. Exact token count | asserts `messages.count_tokens` was called or `context_breakdown_exact is True` | Keep the test if it fakes the client's `count_tokens` (the provider still calls it when a client has one). Delete it only if it builds a real SDK client. |

A failure that fits no group means the swap changed behavior: stop and report it with the test name and output. Do not edit the test to make it pass.

- [ ] **Step 7: Add the new credential tests to `tests/test_anthropic_provider.py`**

```python
def test_has_api_key_means_saved_in_the_gateway(monkeypatch):
    from src.providers import gateway_client
    monkeypatch.setattr(gateway_client, "saved_gateway_ids", lambda: frozenset({"claude"}))
    assert anthropic_provider.has_api_key() is True
    assert anthropic_provider.has_api_key("claude") is True
    assert anthropic_provider.has_api_key("openrouter") is False


def test_nothing_is_available_when_the_gateway_service_is_down(monkeypatch):
    from src.providers import gateway_client
    monkeypatch.setattr(gateway_client, "saved_gateway_ids", lambda: frozenset())
    assert anthropic_provider.is_available() is False


def test_clients_are_shims_cached_per_gateway():
    cls = anthropic_provider._Anthropic
    cls._clients.clear()
    assert cls.get_client() is cls.get_client("claude") is cls.get_sync_client("claude")
    assert cls.get_client("backup") is not cls.get_client()
    cls._clients.clear()
```

- [ ] **Step 8: Run the whole Legion suite**

Run: `uv run pytest -q 2>&1 | tail -5`
Expected: `0 failed`. The pass count is 1436 plus the new tests (9 + 7 + 17 + 3) minus the tests deleted in Step 6. Write the deleted test names into the commit message.

- [ ] **Step 9: Commit**

```bash
cd ../..
git add apps/legion/src/providers/language/anthropic_provider.py apps/legion/tests
git commit -m "refactor: run Anthropic-protocol agents through ConversationGateway" -m "The tool loop is unchanged. Removed tests: <names from Step 6>." -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 5: Remove the Anthropic SDK and Legion-side credentials

**Files:**
- Modify: `apps/legion/src/providers/gateway_failover.py` (`classify`, the two error tuples)
- Modify: `apps/legion/src/providers/llm_config.py` (last lines of `model_for_gateway`, unchanged logic)
- Modify: `apps/legion/gateways/anthropic/*.json`, `apps/legion/gateways/README.md`
- Modify: `apps/legion/pyproject.toml:10`, `apps/legion/uv.lock`
- Test: `apps/legion/tests/test_gateway_failover.py`

**Interfaces:**
- Consumes: Tasks 2 and 4.
- Produces: no `import anthropic` anywhere in `apps/legion/src` or `apps/legion/tests`. `classify` still handles `openai` SDK errors until Plan 3b.

- [ ] **Step 1: Find what still imports the SDK**

Run: `cd apps/legion && grep -rn "anthropic\._\|^import anthropic\|^from anthropic\|sdk_error(anthropic" src tests`
Expected after Task 4: only `src/providers/gateway_failover.py` and parametrized cases in `tests/test_gateway_failover.py`.

- [ ] **Step 2: Drop the Anthropic cases from the failover tests**

In `tests/test_gateway_failover.py`, remove `anthropic` from every `parametrize` list of SDK modules (leaving `openai`) and delete `import anthropic`. Delete any test that builds `anthropic._streaming.ServerSentEvent`. The gateway-error tests from Task 2 cover the Anthropic path.

- [ ] **Step 3: Rewrite `classify` without the Anthropic SDK**

In `apps/legion/src/providers/gateway_failover.py` delete `import anthropic`, `import json`, `import traceback`, and replace `_SDK_ERRORS`, `_TRANSPORT_ERRORS` and `classify` with:

```python
def classify(error: Exception) -> FailureKind | None:
    """A gateway failure's kind, or None when the round must not be retried.
    ConversationGateway classifies its own failures; OpenAI-protocol agents
    still call the SDK directly until they move to the gateway too."""
    if isinstance(error, GatewayCallError):
        # No kind means the request itself was refused: never retry that.
        return _KINDS.get(error.kind or "")
    if not isinstance(error, openai.APIError):
        return None
    status = getattr(error, "status_code", None)
    if status == 402:
        return FailureKind.quota
    if status in (401, 403):
        return FailureKind.auth
    if status in (400, 429) and any(word in str(error).lower() for word in _FAILURE_WORDS[FailureKind.quota]):
        return FailureKind.quota
    if status == 429 or isinstance(error, openai.RateLimitError):
        return FailureKind.rate_limit
    if (isinstance(status, int) and 500 <= status < 600) or isinstance(error, openai.APIConnectionError):
        return FailureKind.unavailable
    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return FailureKind.auth
    if isinstance(error, openai.InternalServerError):
        return FailureKind.unavailable
    # SDK stream errors may retain the successful HTTP 200 status of the
    # connection. A plain bad request remains non-retryable unless quota-related.
    if status != 400 and any(word in str(error).lower() for word in _FAILURE_WORDS[FailureKind.unavailable]):
        return FailureKind.unavailable
    return None
```

Change the module docstring's first line to `"""Same-provider routing; only gateway failures may advance a turn."""`.

- [ ] **Step 4: Remove credential fields from the Anthropic gateway files**

```bash
uv run python - <<'EOF'
import json, pathlib

KEEP = {"label", "prompt_cache", "model", "models"}
for path in sorted(pathlib.Path("gateways/anthropic").glob("*.json")):
    block = json.loads(path.read_text(encoding="utf-8"))
    kept = {key: value for key, value in block.items() if key in KEEP}
    path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    print(path.name, "dropped:", sorted(set(block) - KEEP))
EOF
grep -rn "api_key\|auth_token\|base_url\|aws_\|project_id" gateways/anthropic src/providers/language/anthropic_provider.py
```
Expected: each file lists what it dropped; the `grep` prints nothing. If the grep finds a reader in `src/` outside the two provider files (for example an admin catalog showing key status), change that reader to call `anthropic_provider.has_api_key(<gateway>)` and add its file to the commit.

In `apps/legion/gateways/README.md`, replace the credentials paragraph ("Use `{ENV_VAR_NAME}` placeholders ...") for the `anthropic` folder with: `Files in anthropic/ hold only label, prompt_cache, model and models. The connection and its key are saved in ConversationGateway under the same id as the filename. openai/ files still hold their connection fields until those agents move too.`

- [ ] **Step 5: Remove the dependency**

In `apps/legion/pyproject.toml` delete the line `"anthropic>=0.121.0,<2.0.0",`. Then:

```bash
uv lock && uv sync
grep -c '^name = "anthropic"' uv.lock
```
Expected: `0`. If it prints `1`, another dependency still needs the SDK; say so in the commit message and leave it.

- [ ] **Step 6: Run the whole Legion suite**

Run: `uv run pytest -q 2>&1 | tail -5`
Expected: `0 failed`.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add apps/legion
git commit -m "refactor: drop the Anthropic SDK and Legion-side Anthropic credentials" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 6: ConversationGateway in the Citadel stack

**Files:**
- Modify: `docker-compose.yml`, `docs/deployment.md`, `apps/legion/README.md`, `apps/legion/.env.example`
- Modify: `D:\User\Documents\Programming\Brain\Projects\Citadel.md`, `Brain\Projects\garrison.md` (the Legion note), `Brain\log.md`

**Interfaces:**
- Consumes: `CONVERSATION_GATEWAY_URL`, `CONVERSATION_GATEWAY_TOKEN` (Task 1).
- Produces: compose service `conversationgateway` at `http://conversationgateway:29407` on the `core` network, published on `0.0.0.0:29407`.

- [ ] **Step 1: Add the service to `docker-compose.yml`**

After the `armory` service block:

```yaml
  # Shared chat-model gateway (its own repo). Part of this stack, but open to callers
  # outside Citadel: each one gets its own token on http://<host>:29407/admin/.
  conversationgateway:
    build: ${CONVERSATION_GATEWAY_DIR:-../../AI/ModelProviders/ConversationGateway}
    restart: unless-stopped
    environment:
      SERVICE_ADMIN_PASSWORD: ${CONVERSATION_GATEWAY_ADMIN_PASSWORD:?set CONVERSATION_GATEWAY_ADMIN_PASSWORD in the root .env}
    ports:
      - "0.0.0.0:29407:29407"
    volumes:
      - conversationgateway_data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:29407/health')"]
      interval: 15s
      timeout: 5s
      start_period: 30s
    networks: [core]
```

In the `legion` service add `CONVERSATION_GATEWAY_URL: http://conversationgateway:29407` under `environment` and change `depends_on: [armory]` to `depends_on: [armory, conversationgateway]`. Under the top-level `volumes:` add `conversationgateway_data:`.

- [ ] **Step 2: Validate**

Run: `CONVERSATION_GATEWAY_ADMIN_PASSWORD=x docker compose config --quiet && echo ok`
Expected: `ok`.

- [ ] **Step 3: Document the variables**

Append to `apps/legion/.env.example`:

```
# ConversationGateway: the token made for Legion on its /admin/ page (Access tokens).
CONVERSATION_GATEWAY_TOKEN=
# Only outside Docker; the compose file sets it for the container.
CONVERSATION_GATEWAY_URL=
```

In `docs/deployment.md` add a services-table row ``| `conversationgateway` | chat-model gateway, shared with callers outside Citadel | 29407 on all interfaces |`` and a short section "ConversationGateway" with these points: the source lives in `AI/ModelProviders/ConversationGateway` and `CONVERSATION_GATEWAY_DIR` in the root `.env` points at it on a server; `CONVERSATION_GATEWAY_ADMIN_PASSWORD` goes in the root `.env`; do not also start the gateway's own `docker-compose.yml` on the same host (port 29407 would clash); an outside caller connects to `http://<host>:29407` with its own token.

In `apps/legion/README.md` replace Setup step 1 (the `CLAUDE_API_KEY` line) so that Anthropic keys are said to live in ConversationGateway, and add a section "Behavior since the gateway move" listing the five accepted changes from the top of this plan.

- [ ] **Step 4: First start (user)**

Stop and ask the user to do these, since they involve secrets:
1. Put `CONVERSATION_GATEWAY_ADMIN_PASSWORD=<a password>` in the root `.env`.
2. Run `docker compose up -d --build conversationgateway`.
3. Open `http://127.0.0.1:29407/admin/`, sign in, and create an access token for Legion.
4. On `/admin/gateways.html`, save one gateway per file in `apps/legion/gateways/anthropic/` that agents use, with the **same id as the filename** (for example `claude`, `openrouter`), and press Test.
5. Put the token in `apps/legion/.env` as `CONVERSATION_GATEWAY_TOKEN=...`.

- [ ] **Step 5: Live check**

```bash
docker compose up -d --build legion
docker compose exec legion python -c "from src.providers import gateway_client; print(sorted(gateway_client.saved_gateway_ids()))"
```
Expected: the ids saved in Step 4, for example `['claude']`. An empty list means the URL or token is wrong.

Then ask the user to send one chat message in Ember to an Anthropic-protocol agent that uses a tool, and confirm: text streams, the tool step shows, and the gateway's Usage page counts the call under their username.

- [ ] **Step 6: Notes**

Read `D:\User\Documents\Programming\Brain\AGENTS.md` first. In `Brain/Projects/Citadel.md` add a line under Architecture: `2026-11-14: Anthropic-protocol Legion agents call ConversationGateway (port 29407, in the stack, open to outside callers by token). Provider keys left Legion.` Add the same line to `Brain/Projects/garrison.md`. Append to `Brain/log.md`:

```
## [2026-11-14] ingest | Legion on ConversationGateway
Updated Citadel and garrison: Anthropic-protocol agents go through ConversationGateway.
```

Run: `py "D:/User/Documents/Programming/.claude/hooks/validate_vault.py" --all`
Expected: `vault OK`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml docs/deployment.md apps/legion/README.md apps/legion/.env.example
git commit -m "feat: run ConversationGateway in the Citadel stack" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

## Self-review

- **Spec coverage:** provider code replaced by a gateway client (Tasks 1, 3, 4); `classify()` reads `kind` and `Retry-After` while `GatewayRoute`, `cooldown.py`, fallback lists, tuning and `SwitchInfo` stay (Tasks 2, 5); `reasoning_state` echoed (Task 3, test `test_a_tool_round_trip_keeps_ids_and_reasoning_state`); gateway in compose on `0.0.0.0` with a state volume and admin password (Task 6); keys moved out of Legion (Tasks 5, 6); `X-Requester-Username` sent (Task 1). `model_limits.py`, `token_limits.py` and `reasoning_effort.py` are **kept unchanged**: the loop still uses them for context trimming, output caps and effort caps, which are Legion policy.
- **Not in this plan:** the OpenAI-protocol provider (`openai_provider.py`, `gateways/openai/*.json`, the `openai` dependency, the OpenAI branch of `classify`). That is Plan 3b, same pattern. The decision provider is Plan 4.
- **Placeholders:** none. Task 4 Step 6 gives a closed rule for each kind of failing test and a stop condition for anything else.
- **Names:** `GatewayCallError(status, code, message, kind, retry_after)`, `ConversationGatewayClient.stream` / `.chat_sync`, `saved_gateway_ids`, `reset_cache`, `GatewayShim`, `request_body`, `response_message`, `gateway_error` (test helper), `CONVERSATION_GATEWAY_URL`, `CONVERSATION_GATEWAY_TOKEN`, `CONVERSATION_GATEWAY_ADMIN_PASSWORD`, `CONVERSATION_GATEWAY_DIR` and service `conversationgateway` are spelled the same in every task.
