# MCP Elicitation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. One agent runs this straight through and reports once at the end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An MCP server that speaks protocol `2026-07-28` can ask the user something in the middle of a tool call, and the user answers in Ember.

**Architecture:** Legion runs the input rounds on the connection that made the call, turns each question into an `elicitation_request` event, and waits on a broker that the new `answer_elicitation` MCP tool resolves. A parent agent records which specialist each forwarded question came from and passes the answer down. Stronghold, Portcullis and Ember mirror the existing question card flow.

**Tech Stack:** Python 3.11+, `mcp` 2.3 (Legion), `mcp` 1.x (Stronghold), FastAPI, pytest, uv, Vue 3, Pinia, Vitest, pnpm.

**Spec:** `docs/superpowers/specs/2026-11-26-legion-sdk-v2-elicitation-design.md`, parts 2 and 3. Part 1 is built (commit `ca5d4f63`).

## Global Constraints

- All paths are relative to `Applications/Citadel/`. Legion paths start with `apps/legion/`.
- Every new argument and flag defaults to off: `elicit`, `can_elicit`.
- Limits, copied from the spec: message 2,000 characters; 10 fields; 20 options per choice; labels 80; descriptions 200; text values 2,000; URL `https` only, no embedded credentials, 2,048; 5 input rounds; wait 600 seconds; keepalive 20 seconds; tool timeout 120 seconds per round.
- The server's text never reaches the model. Answers are never logged, never saved, never given to the model by Citadel.
- Only the account that asked can answer, at every level.
- The server name shown on a card comes from Citadel's own configuration.
- Never replay a tool call on another connection.
- Do not edit `src/citadel_auth/` in any app.
- A progress callback in Legion must not `await` before it hands its event on.
- No reduced-motion setting, media query or test.
- Do not read anything under `.venv/`.
- Run only the tests listed in each task. If a run takes longer than about 2 minutes, stop and ask.
- Work in the current checkout and branch. One commit, at the end of Task 7.

## Two things the spec did not cover

- The turn time limit (300 seconds by default) and the architect unit limit (120 seconds) would end a turn before the 600 second wait. Task 1 pauses both while a question is open.
- "Saved steps keep the outcome only": Stronghold stores no question, form or answer. The step's own result text carries the outcome note.

## File map

| File | Responsibility |
|---|---|
| `apps/legion/src/providers/deadlines.py` (new) | Time limits that pause while the user answers |
| `apps/legion/src/runtime/elicitations.py` (new) | Checking questions and answers, waiting, relay records |
| `apps/legion/src/tools/mcp_client/input_loop.py` (new) | The input rounds of one tool call |
| `apps/legion/src/tools/mcp_client/transports.py`, `registry.py`, `sync_wrapper.py`, `mcp_upstream.py`; `tools/private_extensions/pool.py` | Carry the question callback to the connection |
| `apps/legion/src/providers/base_provider.py`, `turn_guard.py`; `agents/agent_config.py`, `agent_events.py`; `agents/roles/architect/executor.py`; `agents/roles/orchestrator/delegation.py`; `server.py` | Turn wiring and relay |
| `apps/stronghold/src/turns/elicitation_events.py` (new), `engine.py`, `routes.py`, `agents/gateway.py` | Turn state and answer route |
| `apps/portcullis/src/routes/chats.py` | Pass-through route |
| `apps/ember/src/features/chat/components/ElicitationCard.vue` (new), `MessageList.vue`, `views/ChatView.vue`, `stores/chat.ts`, `api/ChatsClient.ts`, `api/types.ts` | The card and its state |

---

### Task 1: Legion core: pausable limits and the elicitation broker

**Files:**
- Create: `apps/legion/src/providers/deadlines.py`, `apps/legion/src/runtime/elicitations.py`, `apps/legion/tests/test_elicitation.py`
- Modify: `apps/legion/src/providers/base_provider.py`, `apps/legion/src/providers/turn_guard.py`, `apps/legion/src/agents/roles/architect/executor.py`

**Interfaces produced:**
- `deadlines.deadline(seconds)` async context manager; `deadlines.UserWaits()` with `note(event)` and `close()`.
- `elicitations.Policy(enabled, uid, request_id)`, `bind(policy)`, `reset(token)`, `current()`.
- `elicitations.bind_channel(on_event, loop)`, `reset_channel(token)`.
- `elicitations.asker(notes: list[str])` returns `None` or `async (server_label, tool, params) -> ElicitResult`.
- `elicitations.parse_request(params) -> (request | None, reason)`, `check_content(fields, content) -> (clean | None, problem | None)`.
- `elicitations.BROKER.wait(request_id, elicitation_id, uid, fields, request_event, on_event) -> Reply`; `BROKER.answer(request_id, elicitation_id, uid, action, content) -> dict | None`.
- `elicitations.note_relayed(policy, event, url, child_request_id)`, `drop_relays(request_id, child_request_id) -> list[str]`, `relay_for(request_id, elicitation_id, uid) -> Relay | None` where `Relay` has `url`, `request_id`, `uid`.
- `elicitations.ElicitationStopped`, `DECLINED_NOTE`.

- [ ] **Step 1: Create `deadlines.py`**

```python
"""Turn and unit time limits that stop counting while the user answers a server's question."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from typing import Any


class Deadline:
    """One asyncio.timeout that can be paused. Use it only on its own event loop."""

    def __init__(self, timeout: asyncio.Timeout) -> None:
        self._timeout = timeout
        self._holds = 0
        self._remaining: float | None = None

    def hold(self) -> None:
        self._holds += 1
        if self._holds > 1:
            return
        when = self._timeout.when()
        if when is not None:
            self._remaining = max(0.0, when - asyncio.get_running_loop().time())
            self._move(None)

    def release(self) -> None:
        if self._holds == 0:
            return
        self._holds -= 1
        if self._holds == 0 and self._remaining is not None:
            self._move(asyncio.get_running_loop().time() + self._remaining)
            self._remaining = None

    def _move(self, when: float | None) -> None:
        with suppress(RuntimeError):  # already expired, or already left
            self._timeout.reschedule(when)


_active: ContextVar[tuple[Deadline, ...]] = ContextVar("deadlines", default=())


@asynccontextmanager
async def deadline(seconds: float) -> AsyncIterator[Deadline]:
    """asyncio.timeout(seconds) that UserWaits can pause."""
    async with asyncio.timeout(seconds) as timeout:
        entry = Deadline(timeout)
        token = _active.set((*_active.get(), entry))
        try:
            yield entry
        finally:
            _active.reset(token)


class UserWaits:
    """Pauses the limits active now while any question seen by one tool step is open."""

    def __init__(self) -> None:
        self._deadlines = _active.get()
        self._open: set[str] = set()

    def note(self, event: dict[str, Any]) -> None:
        kind, key = event.get("type"), str(event.get("id") or "")
        if kind == "elicitation_request" and key not in self._open:
            self._open.add(key)
            for entry in self._deadlines:
                entry.hold()
        elif kind == "elicitation_resolved" and key in self._open:
            self._open.remove(key)
            for entry in self._deadlines:
                entry.release()

    def close(self) -> None:
        for key in list(self._open):
            self.note({"type": "elicitation_resolved", "id": key})
```

- [ ] **Step 2: Create `elicitations.py`**

It must not import `base_provider` (which imports it).

```python
"""A server's questions to the user in the middle of a tool call (MCP elicitation).

Same shape as questions.py: an ``elicitation_request`` event goes to the caller and a broker waits until the
``answer_elicitation`` MCP tool resolves it. The question comes from an outside server, so its form and link
are checked and bounded here, and only the account that asked may answer.

The server's text goes to the user only, never to the model. Answers are never logged or saved.
"""

from __future__ import annotations

import asyncio
import math
import threading
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from mcp_types import ElicitRequestParams, ElicitRequestURLParams, ElicitResult

from src.runtime.broker import Broker

MAX_WAIT_SECONDS = 600.0
KEEPALIVE_SECONDS = 20.0
POLL_SECONDS = 0.5
MAX_FIELDS = 10
MAX_OPTIONS = 20
LABEL_MAX = 80
DESCRIPTION_MAX = 200
TEXT_MAX = 2_000
MESSAGE_MAX = 2_000
URL_MAX = 2_048
DECLINED_NOTE = "The user declined the server's question."
_UNSUPPORTED_NOTE = "Citadel declined the server's question: {reason}."

OnEvent = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class Policy:
    """Whether this turn can show a server's question, to whom, and under which request id it is answered."""

    enabled: bool = False
    uid: str = ""
    request_id: str = ""


_policy: ContextVar[Policy] = ContextVar("elicitation_policy", default=Policy())
# The current tool step's event stream and the loop it lives on.
_channel: ContextVar[tuple[OnEvent, asyncio.AbstractEventLoop] | None] = ContextVar("elicitation_channel", default=None)


def bind(policy: Policy) -> Token:
    return _policy.set(policy)


def reset(token: Token) -> None:
    _policy.reset(token)


def current() -> Policy:
    return _policy.get()


def bind_channel(on_event: OnEvent, loop: asyncio.AbstractEventLoop) -> Token:
    return _channel.set((on_event, loop))


def reset_channel(token: Token) -> None:
    _channel.reset(token)


class ElicitationStopped(Exception):
    """The user pressed Stop while a server waited; the tool call is not retried."""


# --- what the server asks ----------------------------------------------------------------


class _Unsupported(Exception):
    pass


def parse_request(params: ElicitRequestParams) -> tuple[dict[str, Any] | None, str]:
    """({mode, message, fields | url}, "") for a question Citadel can show, else (None, why not)."""
    message = str(params.message or "")[:MESSAGE_MAX]
    try:
        if isinstance(params, ElicitRequestURLParams):
            return {"mode": "url", "message": message, "url": _url(params.url)}, ""
        return {"mode": "form", "message": message, "fields": _fields(params.requested_schema)}, ""
    except _Unsupported as problem:
        return None, str(problem)


def _url(url: str) -> str:
    if len(url) > URL_MAX:
        raise _Unsupported("the link is too long")
    # Browsers read a backslash as a slash, so it could change which site is opened.
    if "\\" in url or any(char.isspace() or not char.isprintable() for char in url):
        raise _Unsupported("the link has characters that are not allowed")
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises for a port that is not a number
    except ValueError:
        raise _Unsupported("the link is not valid") from None
    if parts.scheme != "https" or not parts.hostname:
        raise _Unsupported("only https links are shown")
    if "@" in parts.netloc:
        raise _Unsupported("the link carries a user name or password")
    return url


def _text(value: Any, limit: int, what: str) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise _Unsupported(f"{what} is not text of at most {limit} characters")
    return value


def _bound(rule: dict, key: str) -> int | float | None:
    value = rule.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (
        isinstance(value, float) and not math.isfinite(value)
    ):
        raise _Unsupported("a field limit is not a number")
    return value


def _fields(schema: Any) -> list[dict[str, Any]]:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise _Unsupported("the form is not a flat object")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or len(properties) > MAX_FIELDS:
        raise _Unsupported(f"the form needs at most {MAX_FIELDS} fields")
    required = schema.get("required") or []
    if not isinstance(required, list) or not all(isinstance(n, str) and n in properties for n in required):
        raise _Unsupported("the form requires a field it does not define")
    return [_field(name, rule, name in required) for name, rule in properties.items()]


def _field(name: str, rule: Any, required: bool) -> dict[str, Any]:
    _text(name, LABEL_MAX, "a field name")
    if not isinstance(rule, dict):
        raise _Unsupported("a field is not described")
    field: dict[str, Any] = {
        "name": name, "label": _text(rule.get("title") or name, LABEL_MAX, "a field label"), "required": required,
    }
    if rule.get("description"):
        field["description"] = _text(rule["description"], DESCRIPTION_MAX, "a field description")
    kind = rule.get("type")
    if "enum" in rule or "oneOf" in rule:
        if kind not in (None, "string"):
            raise _Unsupported("only text can be chosen from a list")
        return {**field, "kind": "choice", "options": _options(rule, "oneOf")}
    if kind == "string":
        # shortcut: format and pattern are left to the server, add them when a real form needs it
        longest, shortest = _bound(rule, "maxLength"), _bound(rule, "minLength")
        field.update(kind="text", max_length=TEXT_MAX if longest is None else min(int(longest), TEXT_MAX))
        if shortest:
            field["min_length"] = int(shortest)
        return field
    if kind in ("number", "integer", "boolean"):
        field["kind"] = kind
        if kind != "boolean":
            for key, source in (("min", "minimum"), ("max", "maximum")):
                if (value := _bound(rule, source)) is not None:
                    field[key] = value
        return field
    if kind == "array":
        items = rule.get("items")
        if not isinstance(items, dict) or items.get("type") not in (None, "string"):
            raise _Unsupported("only text can be chosen from a list")
        field.update(kind="multi_choice", options=_options(items, "anyOf"))
        for key, source in (("min", "minItems"), ("max", "maxItems")):
            if (value := _bound(rule, source)) is not None:
                field[key] = value
        return field
    raise _Unsupported("the form has a field type Citadel cannot show")


def _options(rule: dict, union_key: str) -> list[dict[str, str]]:
    if union_key in rule:
        raw = rule[union_key]
        if not isinstance(raw, list) or not all(isinstance(option, dict) for option in raw):
            raise _Unsupported("the options are not readable")
        pairs = [(o.get("const"), o.get("title") or o.get("const")) for o in raw]
    else:
        values = rule.get("enum")
        names = rule.get("enumNames") or values
        if not isinstance(values, list) or not isinstance(names, list) or len(values) != len(names):
            raise _Unsupported("the options are not readable")
        pairs = list(zip(values, names))
    if not 0 < len(pairs) <= MAX_OPTIONS:
        raise _Unsupported(f"a choice needs 1 to {MAX_OPTIONS} options")
    return [
        {"value": _text(value, LABEL_MAX, "an option"), "label": _text(label, LABEL_MAX, "an option label")}
        for value, label in pairs
    ]


def _shown(request: dict[str, Any]) -> dict[str, Any]:
    """The request as events carry it: without the limits only Legion checks."""
    if request["mode"] == "url":
        return request
    return {**request, "fields": [{k: v for k, v in f.items() if k != "min_length"} for f in request["fields"]]}


# --- what the user answers ---------------------------------------------------------------


def check_content(fields: list[dict[str, Any]], content: Any) -> tuple[dict[str, Any] | None, str | None]:
    """(the content to send, None), or (None, what is wrong), naming the field first."""
    given = content or {}
    if not isinstance(given, dict) or set(given) - {field["name"] for field in fields}:
        return None, "The answer has a field the form does not ask for."
    clean: dict[str, Any] = {}
    for field in fields:
        value = given.get(field["name"])
        if value is None or value == "" or value == []:
            if field["required"]:
                return None, f"{field['label']}: this field is required."
            continue
        if problem := _value_problem(field, value):
            return None, f"{field['label']}: {problem}"
        clean[field["name"]] = value
    return clean, None


def _value_problem(field: dict[str, Any], value: Any) -> str | None:
    kind = field["kind"]
    if kind == "boolean":
        return None if isinstance(value, bool) else "choose yes or no."
    if kind in ("number", "integer"):
        wanted = int if kind == "integer" else (int, float)
        if isinstance(value, bool) or not isinstance(value, wanted) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            return "enter a whole number." if kind == "integer" else "enter a number."
        return _range_problem(field, value, "")
    if kind == "text":
        if not isinstance(value, str):
            return "enter text."
        if len(value) > field["max_length"]:
            return f"use at most {field['max_length']} characters."
        if len(value) < field.get("min_length", 0):
            return f"use at least {field['min_length']} characters."
        return None
    allowed = {option["value"] for option in field["options"]}
    if kind == "choice":
        return None if isinstance(value, str) and value in allowed else "choose one of the options."
    if not isinstance(value, list) or not all(isinstance(item, str) and item in allowed for item in value) \
            or len(set(value)) != len(value):
        return "choose from the options."
    return _range_problem(field, len(value), " options")


def _range_problem(field: dict[str, Any], amount: float, unit: str) -> str | None:
    if "min" in field and amount < field["min"]:
        return f"must be at least {field['min']}{unit}."
    if "max" in field and amount > field["max"]:
        return f"must be at most {field['max']}{unit}."
    return None


# --- waiting -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Reply:
    action: str  # accept | decline | cancel
    outcome: str  # accepted | declined | cancelled | timeout
    content: dict[str, Any] | None = None
    stopped: bool = False


_OUTCOMES = {"accept": "accepted", "decline": "declined", "cancel": "cancelled"}


def _answered(done: bool, problem: str | None = None) -> dict[str, Any]:
    return {"answered": done, "problem": problem}


class ElicitationBroker(Broker[Reply]):
    """The server questions waiting on a user, keyed by (request_id, elicitation id).

    `answer()` and `wait()` both run on the server's event loop."""

    def __init__(self, timeout: float = MAX_WAIT_SECONDS, poll: float = POLL_SECONDS,
                 keepalive: float = KEEPALIVE_SECONDS) -> None:
        super().__init__(timeout, poll)
        self._keepalive = keepalive
        self._waiting: dict[tuple[str, str], tuple[str, list[dict[str, Any]] | None]] = {}

    async def wait(self, request_id: str, elicitation_id: str, uid: str, fields: list[dict[str, Any]] | None,
                   request_event: dict[str, Any], on_event: OnEvent) -> Reply:
        """Sends `request_event` once the wait is registered, so an early answer is never lost."""
        key = (request_id, elicitation_id)
        self._waiting[key] = (uid, fields)
        announced = False
        next_keepalive = 0.0

        async def tick(now: float) -> None:
            nonlocal announced, next_keepalive
            if announced and now < next_keepalive:
                return
            event = {"type": "keepalive"} if announced else request_event
            announced, next_keepalive = True, now + self._keepalive
            await on_event(event)

        try:
            return await self._wait(
                request_id, elicitation_id,
                replaced=Reply("cancel", "cancelled"),
                cancelled=Reply("cancel", "cancelled", stopped=True),
                timed_out=Reply("cancel", "timeout"),
                tick=tick,
            )
        finally:
            self._waiting.pop(key, None)

    def answer(self, request_id: str, elicitation_id: str, uid: str, action: str,
               content: Any) -> dict[str, Any] | None:
        """None when nothing waits here under that id, so the caller may look for a specialist."""
        waiting = self._waiting.get((request_id, elicitation_id))
        if waiting is None:
            return None
        owner, fields = waiting
        if uid != owner:
            return _answered(False)
        if action not in _OUTCOMES:
            return _answered(False, "The action must be accept, decline or cancel.")
        clean = None
        if action == "accept" and fields is not None:
            clean, problem = check_content(fields, content)
            if problem:
                return _answered(False, problem)
        return _answered(self._resolve(request_id, elicitation_id, Reply(action, _OUTCOMES[action], clean)))


BROKER = ElicitationBroker()


def asker(notes: list[str]) -> Callable[[str, str, ElicitRequestParams], Awaitable[ElicitResult]] | None:
    """The callback that puts a server's question to this turn's user, or None when the turn cannot
    show one. Call it on the tool's worker thread; await its result on any event loop. What Legion
    must tell the model about a question is appended to `notes`."""
    policy, channel = _policy.get(), _channel.get()
    if not policy.enabled or channel is None:
        return None
    on_event, loop = channel

    async def ask(server: str, tool: str, params: ElicitRequestParams) -> ElicitResult:
        future = asyncio.run_coroutine_threadsafe(_ask(policy, on_event, server, tool, params, notes), loop)
        return await asyncio.wrap_future(future)

    return ask


async def _ask(policy: Policy, on_event: OnEvent, server: str, tool: str, params: ElicitRequestParams,
               notes: list[str]) -> ElicitResult:
    request, reason = parse_request(params)
    if request is None:
        notes.append(_UNSUPPORTED_NOTE.format(reason=reason))
        return ElicitResult(action="decline")
    elicitation_id = uuid4().hex
    event = {"type": "elicitation_request", "id": elicitation_id, "server": server[:LABEL_MAX], "tool": tool,
             **_shown(request)}
    reply = await BROKER.wait(policy.request_id, elicitation_id, policy.uid, request.get("fields"), event, on_event)
    await on_event({"type": "elicitation_resolved", "id": elicitation_id, "outcome": reply.outcome})
    if reply.stopped:
        raise ElicitationStopped("Stopped before the server's question was answered.")
    if reply.outcome == "declined":
        notes.append(DECLINED_NOTE)
    return ElicitResult(action=reply.action, content=reply.content)


# --- relay through delegation ------------------------------------------------------------


@dataclass(frozen=True)
class Relay:
    """Where the answer to a specialist's question goes."""

    url: str
    request_id: str  # the specialist's
    uid: str


_relays: dict[tuple[str, str], Relay] = {}
_relays_lock = threading.Lock()


def note_relayed(policy: Policy, event: dict[str, Any], url: str, child_request_id: str) -> None:
    """Record or forget a question a specialist's stream carries. Called before the event is shown."""
    kind, elicitation_id = event.get("type"), str(event.get("id") or "")
    if not elicitation_id:
        return
    key = (policy.request_id, elicitation_id)
    with _relays_lock:
        if kind == "elicitation_request":
            _relays[key] = Relay(url, child_request_id, policy.uid)
        elif kind == "elicitation_resolved":
            _relays.pop(key, None)


def drop_relays(request_id: str, child_request_id: str) -> list[str]:
    """Forget one finished specialist's open questions and return their ids."""
    with _relays_lock:
        keys = [key for key, relay in _relays.items()
                if key[0] == request_id and relay.request_id == child_request_id]
        for key in keys:
            del _relays[key]
    return [elicitation_id for _, elicitation_id in keys]


def relay_for(request_id: str, elicitation_id: str, uid: str) -> Relay | None:
    with _relays_lock:
        relay = _relays.get((request_id, elicitation_id))
    return relay if relay is not None and relay.uid == uid else None
```

- [ ] **Step 3: Wire `dispatch_with_progress` in `base_provider.py`**

Change the import lines to:

```python
from src.tools.mcp_client import tool_progress
from src.providers import cancellation, cooldown, deadlines
from src.runtime import elicitations
```

In `dispatch_with_progress`, replace everything from `closed = False` to the end of the function with:

```python
    closed = False
    # Time limits pause while a question from this step, or from a specialist under it, is open.
    waits = deadlines.UserWaits()

    async def deliver(event: dict[str, Any]) -> None:
        waits.note(event)
        await on_event(event)

    def sink(message: str) -> None:
        event_sink(step_event("step_progress", id=step_id, message=message))

    def event_sink(event: dict[str, Any]) -> None:
        with pending_lock:
            if not closed:
                pending.append(asyncio.run_coroutine_threadsafe(deliver(event), loop))

    token = tool_progress.bind(sink)
    events_token = agent_events.bind(event_sink, step_id)
    channel_token = elicitations.bind_channel(deliver, loop)
    try:
        # shortcut: a waiting question holds one worker thread (anyio allows 40); raise the limiter if many users wait at once
        return await anyio.to_thread.run_sync(dispatch, *args)
    finally:
        # A deadline may leave a worker finishing cooperatively; its late events
        # must not reopen a finished turn or target a closed event loop.
        with pending_lock:
            closed = True
        elicitations.reset_channel(channel_token)
        agent_events.reset(events_token)
        tool_progress.reset(token)
        # Deliver every queued progress event before the caller's step_end.
        await asyncio.gather(*(asyncio.wrap_future(f) for f in pending), return_exceptions=True)
        waits.close()
```

- [ ] **Step 4: Use pausable limits**

`turn_guard.py`: remove `import asyncio`; add `from contextlib import AbstractAsyncContextManager` and `from src.providers import deadlines`; replace `timeout`:

```python
    def timeout(self) -> AbstractAsyncContextManager[deadlines.Deadline]:
        """Apply the turn deadline to the entire provider loop. Waiting on a server's question does not count."""
        return deadlines.deadline(self.max_seconds)
```

`executor.py`: `from src.providers import cancellation` becomes `from src.providers import cancellation, deadlines`, and `async with asyncio.timeout(self.limits.unit_timeout_seconds):` becomes `async with deadlines.deadline(self.limits.unit_timeout_seconds):`.

- [ ] **Step 5: Create `tests/test_elicitation.py`**

```python
"""Server questions in the middle of a tool call: checking them, waiting, and who may answer."""

import asyncio

import pytest
from mcp_types import ElicitRequestFormParams, ElicitRequestURLParams

from src.providers import cancellation, deadlines
from src.providers.base_provider import dispatch_with_progress
from src.runtime import elicitations

REQUEST, UID = "req-e", "u-1"
SCHEMA = {"type": "object", "properties": {"name": {"type": "string", "title": "Name", "maxLength": 20}},
          "required": ["name"]}


@pytest.fixture(autouse=True)
def broker(monkeypatch):
    cancellation.clear(REQUEST)
    monkeypatch.setattr(elicitations, "BROKER", elicitations.ElicitationBroker(timeout=3.0, poll=0.02, keepalive=0.05))
    yield
    cancellation.clear(REQUEST)


def form(schema=SCHEMA):
    return ElicitRequestFormParams(message="Your name?", requested_schema=schema)


def reply(action, content=None, delay=0.0):
    def answer(elicitation_id):
        asyncio.get_running_loop().call_later(
            delay, elicitations.BROKER.answer, REQUEST, elicitation_id, UID, action, content)
    return answer


def ask_through_a_step(params, on_request=None, enabled=True, limit=None):
    """One tool step whose worker thread asks the user from another event loop, as an MCP connection does."""
    events, notes = [], []

    async def go():
        async def on_event(event):
            events.append(event)
            if event["type"] == "elicitation_request" and on_request:
                on_request(event["id"])

        def dispatch():
            elicit = elicitations.asker(notes)
            if elicit is None:
                return "no cards"
            return asyncio.run(elicit("Fake", "greet", params)).action

        token = elicitations.bind(elicitations.Policy(enabled, UID, REQUEST))
        try:
            if limit is None:
                return await dispatch_with_progress(dispatch, on_event, "s1")
            async with deadlines.deadline(limit):
                return await dispatch_with_progress(dispatch, on_event, "s1")
        finally:
            elicitations.reset(token)

    result = asyncio.run(go())
    return result, [e for e in events if e["type"] != "keepalive"], notes


def test_an_accepted_form_goes_through():
    result, events, notes = ask_through_a_step(form(), reply("accept", {"name": "Ana"}))
    assert result == "accept" and notes == []
    assert [e["type"] for e in events] == ["elicitation_request", "elicitation_resolved"]
    assert (events[0]["server"], events[0]["tool"], events[0]["mode"]) == ("Fake", "greet", "form")
    assert events[0]["fields"] == [
        {"name": "name", "label": "Name", "required": True, "kind": "text", "max_length": 20}]
    assert events[1]["outcome"] == "accepted"


def test_a_decline_is_noted_for_the_model():
    result, _, notes = ask_through_a_step(form(), reply("decline"))
    assert result == "decline" and notes == [elicitations.DECLINED_NOTE]


def test_only_the_asking_account_answers_and_a_bad_answer_keeps_the_card():
    replies = []

    def on_request(elicitation_id):
        for uid, content in (("other", {"name": "Eve"}), (UID, {}), (UID, {"name": "Ana"})):
            replies.append(elicitations.BROKER.answer(REQUEST, elicitation_id, uid, "accept", content))

    assert ask_through_a_step(form(), on_request)[0] == "accept"
    assert replies == [
        {"answered": False, "problem": None},
        {"answered": False, "problem": "Name: this field is required."},
        {"answered": True, "problem": None},
    ]


def test_no_answer_in_time_cancels(monkeypatch):
    monkeypatch.setattr(elicitations, "BROKER", elicitations.ElicitationBroker(timeout=0.2, poll=0.02))
    result, events, _ = ask_through_a_step(form())
    assert result == "cancel" and events[-1]["outcome"] == "timeout"


def test_waiting_for_the_user_does_not_use_up_the_turn_limit():
    assert ask_through_a_step(form(), reply("accept", {"name": "Ana"}, delay=0.5), limit=0.2)[0] == "accept"


def test_stop_ends_the_wait():
    with pytest.raises(elicitations.ElicitationStopped):
        ask_through_a_step(form(), lambda _id: cancellation.cancel(REQUEST))


def test_a_turn_that_cannot_show_cards_has_no_asker():
    assert ask_through_a_step(form(), enabled=False)[:2] == ("no cards", [])


@pytest.mark.parametrize("params", [
    form({"type": "object", "properties": {"a": {"type": "object"}}}),
    form({"type": "object", "properties": {f"f{i}": {"type": "string"} for i in range(11)}}),
    form({"type": "object", "properties": {"a": {"type": "string", "title": "x" * 81}}}),
    form({"type": "object", "properties": {"a": {"type": "string", "enum": [str(i) for i in range(21)]}}}),
    ElicitRequestURLParams(message="m", url="http://example.com/x"),
    ElicitRequestURLParams(message="m", url="https://user:pass@example.com/"),
    ElicitRequestURLParams(message="m", url="https://example.com\\@evil.test/"),
    ElicitRequestURLParams(message="m", url="https://example.com/" + "a" * 2048),
])
def test_an_unsupported_question_is_declined_with_a_reason(params):
    result, events, notes = ask_through_a_step(params)
    assert result == "decline" and events == []
    assert notes[0].startswith("Citadel declined the server's question:")


def test_every_field_kind_is_read_and_checked():
    request, reason = elicitations.parse_request(form({"type": "object", "required": ["count"], "properties": {
        "count": {"type": "integer", "minimum": 1, "maximum": 5},
        "ratio": {"type": "number"},
        "yes": {"type": "boolean"},
        "one": {"type": "string", "oneOf": [{"const": "a", "title": "A"}]},
        "many": {"type": "array", "items": {"type": "string", "enum": ["x", "y"]}, "maxItems": 1},
    }}))
    assert reason == ""
    fields = request["fields"]
    assert [f["kind"] for f in fields] == ["integer", "number", "boolean", "choice", "multi_choice"]
    good = {"count": 2, "ratio": 0.5, "yes": False, "one": "a", "many": ["x"]}
    assert elicitations.check_content(fields, good) == (good, None)
    for bad in ({}, {"count": 6}, {"count": True}, {"count": 1, "one": "z"},
                {"count": 1, "many": ["x", "y"]}, {"count": 1, "extra": 1}):
        assert elicitations.check_content(fields, bad)[1], bad
```

- [ ] **Step 6: Run** (from `apps/legion/`)

```bash
uv run pytest tests/test_elicitation.py tests/test_base_provider.py tests/test_turn_guard.py tests/test_dag_executor.py tests/test_plan_step_timeout.py -q
```

Expected: PASS.

---

### Task 2: Legion connections: the input rounds

**Files:**
- Create: `apps/legion/src/tools/mcp_client/input_loop.py`
- Modify: `apps/legion/src/tools/mcp_client/transports.py`, `registry.py`, `sync_wrapper.py`, `mcp_upstream.py`; `apps/legion/src/tools/private_extensions/pool.py`
- Test: `apps/legion/tests/test_elicitation.py`, `test_mcp_session_negotiation.py`, `test_private_pool.py`

**Interfaces:**
- Consumes: `elicitations.asker(notes)` from Task 1.
- Produces: `input_loop.speaks_input(session) -> bool`, `input_loop.call_with_input(send, ask)`; `McpClientRegistry.call_tool(name, arguments, on_progress=None, meta=None, elicit=None)`; `PrivateSessionPool.call(account, spec, tool, arguments, elicit=None)`; `elicit` is `async (server_label, tool, params) -> ElicitResult`.

- [ ] **Step 1: Create `input_loop.py`**

```python
"""The rounds of one tool call on a 2026-07-28 connection, where a server may ask for input first."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp_types import ElicitRequest, ElicitRequestParams, ElicitResult, InputRequiredResult
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

MAX_INPUT_ROUNDS = 5

# (server label from our configuration, tool name, the question) -> the user's answer
Elicit = Callable[[str, str, ElicitRequestParams], Awaitable[ElicitResult]]
Ask = Callable[[ElicitRequestParams], Awaitable[ElicitResult]]


def speaks_input(session: Any) -> bool:
    return getattr(session, "protocol_version", None) in MODERN_PROTOCOL_VERSIONS


async def call_with_input(send: Callable[..., Awaitable[Any]], ask: Ask | None) -> Any:
    """`send(**round_arguments)` sends one round on one session. Every retry uses that session, so a
    failed round is never replayed elsewhere. With no `ask`, every question is declined."""
    result = await send(allow_input_required=True)
    for _ in range(MAX_INPUT_ROUNDS):
        if not isinstance(result, InputRequiredResult):
            return result
        responses = {}
        for key, request in (result.input_requests or {}).items():
            if not isinstance(request, ElicitRequest):  # sampling and roots are not offered
                raise RuntimeError("The server asked for something Citadel does not provide")
            responses[key] = await ask(request.params) if ask else ElicitResult(action="decline")
        again: dict[str, Any] = {"allow_input_required": True}
        if responses:
            again["input_responses"] = responses
        if result.request_state is not None:
            again["request_state"] = result.request_state
        result = await send(**again)
    if isinstance(result, InputRequiredResult):
        raise RuntimeError(f"The server asked for input more than {MAX_INPUT_ROUNDS} times")
    return result
```

- [ ] **Step 2: Declare elicitation on probed sessions only (`transports.py`)**

Add `from mcp_types import ElicitResult`. Add above `_open`, and replace `_open`:

```python
async def _decline_input(_context, _params) -> ElicitResult:
    """Declares elicitation on a 2026 session. The real answers go through input_loop.py."""
    return ElicitResult(action="decline")


async def _open(stack: AsyncExitStack, open_streams, timeout_seconds: float, **options) -> ClientSession:
    read_stream, write_stream = await stack.enter_async_context(open_streams())
    return await stack.enter_async_context(
        ClientSession(read_stream, write_stream, read_timeout_seconds=timeout_seconds, **options)
    )
```

In `open_negotiated`, the probe line becomes:

```python
            session = await _open(attempt, open_streams, timeout_seconds, elicitation_callback=_decline_input)
```

The later `_open` call for the handshake session stays without it, so older servers are not offered elicitation.

- [ ] **Step 3: Run the rounds in `registry.py`**

Add `from functools import partial` and `from src.tools.mcp_client import input_loop`. Add the parameter `elicit: input_loop.Elicit | None = None,` after `meta` in `call_tool`, add one docstring sentence (`elicit` puts a server's question to the user; without it a question is declined), and replace the inner `call`:

```python
        async def call(on: Any) -> types.CallToolResult:
            async def send(**round_arguments: Any):
                return await on.call_tool(
                    upstream_name, arguments, read_timeout_seconds=CALL_TIMEOUT_SECONDS, **extra, **round_arguments
                )

            if not input_loop.speaks_input(on):
                return await send()
            # The name comes from this installation's settings, never from the server.
            label = config.label if config else server_id
            return await input_loop.call_with_input(send, partial(elicit, label, upstream_name) if elicit else None)
```

- [ ] **Step 4: `sync_wrapper.py`**

```python
    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        on_progress: Callable[[str], None] | None = None,
        meta: dict[str, Any] | None = None,
        elicit: Any = None,
    ) -> types.CallToolResult:
        extra = {"elicit": elicit} if elicit else {}
        return self._run(self._registry.call_tool(name, arguments, on_progress, meta, **extra))
```

- [ ] **Step 5: `pool.py`**

Add `from functools import partial` and `from src.tools.mcp_client import input_loop`. Add `busy: int = 0` as the last field of `_Entry`. In `session`, the reuse condition becomes:

```python
            if entry is not None and (entry.busy or self._clock() - entry.last_used <= self._idle):
```

Replace `_make_room`:

```python
    async def _make_room(self, account: str) -> None:
        """Close idle and oldest sessions. A session in the middle of a call is never closed here."""
        now = self._clock()
        for key, entry in list(self._entries.items()):
            if not entry.busy and now - entry.last_used > self._idle:
                await self._close(key)
        mine = [k for k, e in self._entries.items() if e.account == account]
        spare = sorted((k for k in mine if not self._entries[k].busy), key=lambda k: self._entries[k].last_used)
        for key in spare[: max(0, len(mine) - self._per_account + 1)]:
            await self._close(key)
        while len(self._entries) >= self._total:
            spare = [k for k, e in self._entries.items() if not e.busy]
            if not spare:
                break
            await self._close(min(spare, key=lambda k: self._entries[k].last_used))
```

Replace `call`:

```python
    async def call(
        self, account: str, spec: PrivateSpec, tool: str, arguments: dict[str, Any],
        elicit: input_loop.Elicit | None = None,
    ) -> types.CallToolResult:
        async def run(session: ClientSession) -> Any:
            entry = self._entries.get((account, spec.key()))
            if entry is not None:
                entry.busy += 1  # a user may take minutes to answer; the session must stay open
            try:
                async def send(**round_arguments: Any):
                    return await session.call_tool(
                        tool, arguments, read_timeout_seconds=self._call_timeout, **round_arguments)

                if not input_loop.speaks_input(session):
                    return await send()
                return await input_loop.call_with_input(send, partial(elicit, spec.label, tool) if elicit else None)
            finally:
                if entry is not None:
                    entry.busy -= 1
                    entry.last_used = self._clock()

        return await self._use(account, spec, run)
```

- [ ] **Step 6: `mcp_upstream.py`**

Add `elicitations` to the `from src.runtime import ...` line. Rename the existing `def call_tool(name: str, arguments: dict[str, Any]) -> str:` to `def _dispatch_tool(name: str, arguments: dict[str, Any], elicit: Any) -> str:` and add above it:

```python
def call_tool(name: str, arguments: dict[str, Any]) -> str:
    """Run one tool and return the text the model gets."""
    notes: list[str] = []
    text = _dispatch_tool(name, arguments, elicitations.asker(notes))
    if notes:
        # Citadel's own words, so they are added after screening. A numbered failure stays one.
        text = type(text)("\n\n".join((text, *dict.fromkeys(notes))))
    return text
```

In `_dispatch_tool`: the private branch becomes `return _call_private(name, arguments, elicit)`, and after `if meta: extra["meta"] = meta` add:

```python
    if elicit:
        extra["elicit"] = elicit
```

`_call_private` becomes `def _call_private(name: str, arguments: dict[str, Any], elicit: Any = None) -> str:` and its call becomes:

```python
        result = client.run_coroutine(private_pool.call(
            turn.account, spec, upstream, arguments, **({"elicit": elicit} if elicit else {})))
```

- [ ] **Step 7: Tests**

Append to `tests/test_elicitation.py`, with these imports added at the top (`threading`, `time`, `uvicorn`, and):

```python
from mcp.server.mcpserver import Context, MCPServer
from mcp_types import ElicitRequest, ElicitResult, InputRequiredResult

from src.tools.mcp_client.config import ServerConfig
from src.tools.mcp_client.registry import McpClientRegistry
from tests.test_private_integration import free_port
```

```python
# --- against a real 2026 server ----------------------------------------------------------


@pytest.fixture(scope="module")
def url():
    mcp = MCPServer("asking")

    @mcp.tool()
    async def greet(ctx: Context) -> str | InputRequiredResult:
        answer = (ctx.input_responses or {}).get("name")
        if answer is None:
            return InputRequiredResult(
                input_requests={"name": ElicitRequest(params=form())}, request_state="asked")
        return f"{answer.action}:{(answer.content or {}).get('name', '')}"

    @mcp.tool()
    async def forever() -> InputRequiredResult:
        return InputRequiredResult(request_state="again")

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(
        mcp.streamable_http_app(host="127.0.0.1"), host="127.0.0.1", port=port, log_level="warning",
        timeout_graceful_shutdown=1))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(.02)
    assert server.started
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    worker.join(10)


def call(url, tool, elicit=None):
    async def go():
        registry = McpClientRegistry()
        registry._configs["asking"] = ServerConfig("asking", "Asking server", "", "http", url=url)
        status = await registry._connect_one("asking", registry._configs["asking"])
        assert status.status == "connected", status.error
        try:
            return (await registry.call_tool(f"asking__{tool}", {}, elicit=elicit)).content[0].text
        finally:
            await registry.aclose()

    return asyncio.run(asyncio.wait_for(go(), 20))


def test_the_answer_goes_back_to_the_server(url):
    asked = []

    async def elicit(label, tool, params):
        asked.append((label, tool, params.message))
        return ElicitResult(action="accept", content={"name": "Ana"})

    assert call(url, "greet", elicit) == "accept:Ana"
    assert asked == [("Asking server", "greet", "Your name?")]


def test_a_call_without_cards_declines(url):
    assert call(url, "greet") == "decline:"


def test_endless_input_rounds_fail_the_call(url):
    with pytest.raises(RuntimeError, match="more than 5"):
        call(url, "forever")
```

In `tests/test_mcp_session_negotiation.py`, give `run` a fourth parameter `built=None`, make the fake `Session.__init__` do:

```python
        def __init__(self, *args, **kwargs):
            if built is not None:
                built.append("elicitation_callback" in kwargs)
```

and add:

```python
def test_only_the_probed_session_declares_elicitation(monkeypatch):
    built = []
    run(monkeypatch, MCPError(METHOD_NOT_FOUND, "Method not found"), True, built)
    assert built == [True, False]
```

In `tests/test_private_pool.py` add:

```python
def test_a_session_in_the_middle_of_a_call_is_not_closed_to_make_room():
    h = Harness(per_account=1)

    async def go():
        release = asyncio.Event()
        first = await h.pool.session("a@x", spec())

        async def slow(tool, arguments, read_timeout_seconds):
            await release.wait()
            return "done"

        first.call_tool = slow
        running = asyncio.create_task(h.pool.call("a@x", spec(), "echo", {}))
        await asyncio.sleep(0)
        h.now += 10_000
        await h.pool.session("a@x", spec("other"))
        assert h.closed == []
        release.set()
        assert await running == "done"

    run(go())
```

- [ ] **Step 8: Run** (from `apps/legion/`)

```bash
uv run pytest tests/test_elicitation.py tests/test_mcp_session_negotiation.py tests/test_private_pool.py tests/test_private_upstream.py tests/test_registry.py tests/test_registry_origins.py tests/test_mcp_upstream_servers.py tests/test_mcp_output_screening.py -q
```

Expected: PASS.

---

### Task 3: Legion turn wiring and relay

**Files:**
- Modify: `apps/legion/src/agents/agent_config.py`, `agent_events.py`; `agents/roles/orchestrator/delegation.py`; `server.py`
- Test: `apps/legion/tests/test_elicitation.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: MCP tool `ask(..., elicit: bool = False)`; MCP tool `answer_elicitation(request_id, id, action, content=None) -> {"answered": bool, "problem": str | null}`; `status()["user_elicitations"] == True`; events `elicitation_request`, `elicitation_resolved`.

- [ ] **Step 1: `agent_config.py`**

Add `elicitations` to the `from src.runtime import ...` line. Add `elicit: bool = False,` after `confidential: bool = False,` in `run_chat`, and this docstring paragraph:

```
    elicit: the caller can show a server's own questions and send answers back through
    answer_elicitation(); needs a verified account and a request_id.
```

After the `question_token = ...` line add:

```python
    elicit_token = elicitations.bind(elicitations.Policy(
        bool(elicit and requester.uid and request_id), requester.uid, request_id or ""))
```

and in the `finally`, beside `questions.reset(question_token)`:

```python
        elicitations.reset(elicit_token)
```

- [ ] **Step 2: `agent_events.py`**

```python
_PASS_THROUGH = {"step_start", "step_progress", "step_end", "agent_start", "agent_end", "agent_token", "plan_update",
                 "elicitation_request", "elicitation_resolved", "keepalive"}
```

- [ ] **Step 3: `delegation.py`**

Add `elicitations` to the `from src.runtime import approvals, ...` line. Add after `_ask_linked`:

```python
async def answer_elicitation(
    url: str, request_id: str, elicitation_id: str, action: str, content: dict[str, Any] | None,
) -> dict[str, Any]:
    """Carry the user's answer one hop down, to the specialist that is waiting."""
    arguments: dict[str, Any] = {"request_id": request_id, "id": elicitation_id, "action": action}
    if content is not None:
        arguments["content"] = content
    return await _call_tool(url, "answer_elicitation", arguments)
```

Change `_progress_forwarder`:

```python
def _progress_forwarder(
    sink: agent_events.Sink | None, step_id: str | None, url: str = "", child_id: str | None = None,
) -> Any:
```

Keep its docstring. Before `async def on_progress` add `policy = elicitations.current()`, and replace the last three lines of `on_progress`:

```python
            if out is not None:
                if policy.enabled and child_id:
                    # Recorded before it is shown, so an answer always finds its way back.
                    elicitations.note_relayed(policy, out, url, child_id)
                sink(out)
```

In `call`: beside the `caveman` argument block add

```python
        if elicitations.current().enabled:
            arguments["elicit"] = True
```

the forwarder becomes `on_progress=_progress_forwarder(sink, step_id, agent["url"], child_id),` and the `finally` starts with:

```python
        if child_id:
            # A specialist that ended while a question was open takes its card with it.
            for elicitation_id in elicitations.drop_relays(elicitations.current().request_id, child_id):
                agent_events.emit({"type": "elicitation_resolved", "id": elicitation_id, "outcome": "cancelled"})
```

- [ ] **Step 4: `server.py`**

Imports (inside the config `try` block): add `elicitations` to `from src.runtime import ...`, and add `from src.agents.roles.orchestrator import delegation`.

`ask`: add `elicit: bool = False,` after `confidential: bool = False,`; add to the docstring:

```
    elicit: the caller can show a server's own questions (`elicitation_request` events) and send
    answers back through answer_elicitation(); a delegating agent passes it to its specialists.
```

and in the `agent_config.run_chat(...)` call, after the `confidential` expansion add `**({"elicit": True} if elicit else {}),`.

After `answer_question` add:

```python
@mcp.tool()
async def answer_elicitation(
    request_id: str,
    id: str,
    action: str,
    content: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Answers a server's question an ask() call raised with an `elicitation_request` event:
    action is "accept", "decline" or "cancel"; content holds a form's values. Only the account
    that asked can answer. {"answered": false, "problem": "..."} means the content was refused
    and the question stays open; without a problem, nothing is waiting under that id."""
    uid = internal_auth.current_requester().uid
    answered = elicitations.BROKER.answer(request_id, id, uid, action, content)
    if answered is not None:
        return answered
    relay = elicitations.relay_for(request_id, id, uid)
    if relay is None:
        return {"answered": False, "problem": None}
    return await delegation.answer_elicitation(relay.url, relay.request_id, id, action, content)
```

In `status`, add `"user_elicitations": True,` after `"user_questions": True,` and the docstring sentence `` `user_elicitations` says ask() understands elicit. `` If a test compares the whole status dictionary, add the key there.

- [ ] **Step 5: Relay test**

Append to `tests/test_elicitation.py`, adding `from src import server`, `from src.agents.roles.orchestrator import delegation` and `from src.runtime import internal_auth` to its imports:

```python
def test_an_answer_travels_two_levels_down(monkeypatch):
    async def go():
        events = []

        async def on_event(event):
            events.append(event)

        waiter = asyncio.create_task(elicitations.BROKER.wait(
            "c", "e1", UID, None, {"type": "elicitation_request", "id": "e1"}, on_event))
        await asyncio.sleep(0.05)
        # What each parent records as it forwards the specialist's event.
        elicitations.note_relayed(elicitations.Policy(True, UID, "b"), events[0], "http://c/mcp", "c")
        elicitations.note_relayed(elicitations.Policy(True, UID, "a"), events[0], "http://b/mcp", "b")
        hops = []

        async def next_hop(url, name, arguments, on_progress=None):
            hops.append(url)
            return await server.answer_elicitation(**arguments)

        monkeypatch.setattr(delegation, "_call_tool", next_hop)
        outsider = internal_auth.bind_requester(internal_auth.Requester(uid="other"))
        try:
            assert (await server.answer_elicitation("a", "e1", "accept"))["answered"] is False
        finally:
            internal_auth.reset_requester(outsider)
        token = internal_auth.bind_requester(internal_auth.Requester(uid=UID))
        try:
            answered = await server.answer_elicitation("a", "e1", "accept")
        finally:
            internal_auth.reset_requester(token)
        assert (await waiter).outcome == "accepted"
        assert elicitations.drop_relays("a", "b") == ["e1"] and elicitations.drop_relays("b", "c") == ["e1"]
        return answered, hops

    assert asyncio.run(go()) == ({"answered": True, "problem": None}, ["http://b/mcp", "http://c/mcp"])
```

- [ ] **Step 6: Run** (from `apps/legion/`)

```bash
uv run pytest tests/test_elicitation.py tests/test_delegation.py tests/test_delegation_cancellation.py tests/test_delegation_event_loop.py tests/test_agent_events.py tests/test_agent_config.py tests/test_server.py tests/test_questions.py -m "" -q
```

Expected: PASS.

---

### Task 4: Stronghold

**Files:**
- Create: `apps/stronghold/src/turns/elicitation_events.py`, `apps/stronghold/tests/test_turn_elicitations.py`
- Modify: `apps/stronghold/src/agents/gateway.py`, `src/turns/engine.py`, `src/turns/routes.py`
- Test: `apps/stronghold/tests/turn_agent.py`, `test_agent_gateway.py`

**Interfaces:**
- Consumes: Legion `answer_elicitation`, `status.user_elicitations`.
- Produces: turn body field `can_elicit`; snapshot key `elicitations`; `POST /turns/{chat_id}/elicitations` `{id, action, content}` answering `{"answered": true}`, 404, 409, 422 or 502.

- [ ] **Step 1: Create `elicitation_events.py`**

```python
"""A server's question that Legion relays, cut to sizes a browser should show. Legion checks the form
and the answer; this only keeps a misbehaving agent from sending the browser anything large or odd."""

from __future__ import annotations

from typing import Any

MAX_FIELDS = 10
MAX_OPTIONS = 20
ID_MAX = 64
LABEL_MAX = 80
DESCRIPTION_MAX = 200
TOOL_MAX = 120
MESSAGE_MAX = 2_000
TEXT_MAX = 2_000
URL_MAX = 2_048
_KINDS = ("text", "number", "integer", "boolean", "choice", "multi_choice")


def _cut(value: Any, limit: int) -> str:
    return value[:limit] if isinstance(value, str) else ""


def clamp_request(event: dict[str, Any]) -> dict[str, Any]:
    """An `elicitation_request` event with only the known keys, bounded."""
    out: dict[str, Any] = {
        "type": "elicitation_request",
        "id": _cut(event.get("id"), ID_MAX),
        "server": _cut(event.get("server"), LABEL_MAX),
        "tool": _cut(event.get("tool"), TOOL_MAX),
        "mode": "url" if event.get("mode") == "url" else "form",
        "message": _cut(event.get("message"), MESSAGE_MAX),
    }
    for key in ("agent_id", "agent_label"):
        if event.get(key):
            out[key] = _cut(event[key], TOOL_MAX)
    if out["mode"] == "url":
        url = event.get("url")
        safe = isinstance(url, str) and len(url) <= URL_MAX and url.lower().startswith("https://")
        out["url"] = url if safe else ""
    else:
        out["fields"] = _fields(event.get("fields"))
    return out


def _fields(raw: Any) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for item in raw[:MAX_FIELDS] if isinstance(raw, list) else []:
        if not isinstance(item, dict) or item.get("kind") not in _KINDS or not _cut(item.get("name"), LABEL_MAX):
            continue
        name = _cut(item["name"], LABEL_MAX)
        field: dict[str, Any] = {
            "name": name, "label": _cut(item.get("label"), LABEL_MAX) or name,
            "kind": item["kind"], "required": item.get("required") is True,
        }
        if description := _cut(item.get("description"), DESCRIPTION_MAX):
            field["description"] = description
        for key in ("min", "max", "max_length"):
            value = item.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                field[key] = value
        if item["kind"] in ("choice", "multi_choice"):
            options = item.get("options") if isinstance(item.get("options"), list) else []
            field["options"] = [
                {"value": o["value"][:LABEL_MAX], "label": _cut(o.get("label"), LABEL_MAX) or o["value"][:LABEL_MAX]}
                for o in options[:MAX_OPTIONS] if isinstance(o, dict) and isinstance(o.get("value"), str)
            ]
        fields.append(field)
    return fields
```

- [ ] **Step 2: `agents/gateway.py`**

In both `ask` signatures (Protocol and `McpAgentGateway`) add `elicit: bool = False,` after `limits`. Add to the Protocol:

```python
    async def answer_elicitation(
        self, url: str, caller: Caller, request_id: str, elicitation_id: str, action: str,
        content: dict[str, Any] | None,
    ) -> dict[str, Any]: ...
```

In `McpAgentGateway.ask`, after the `if ask_user:` block:

```python
        if elicit:
            # Not fail-closed: an older agent never asks, and the turn still runs.
            status = await self._call(url, caller, "status", {})
            if status.get("user_elicitations"):
                arguments["elicit"] = True
```

After `answer_question`:

```python
    async def answer_elicitation(self, url, caller, request_id, elicitation_id, action, content):
        """Sends the user's answer to a server's question. `problem` says why the content was refused
        (the question stays open); without one, `answered` False means nothing was waiting."""
        arguments: dict[str, Any] = {"request_id": request_id, "id": elicitation_id, "action": action}
        if content is not None:
            arguments["content"] = content
        result = await self._call(url, caller, "answer_elicitation", arguments)
        problem = result.get("problem")
        return {"answered": bool(result.get("answered")),
                "problem": problem[:300] if isinstance(problem, str) else None}
```

- [ ] **Step 3: `turns/engine.py`**

- Import: `from src.turns import elicitation_events, question_answers, summarization`.
- `TurnOptions`, after `can_ask`:

```python
    # The browser can show an outside server's own questions and send answers back.
    can_elicit: bool = False
```

- `Turn`, after `pending_questions`:

```python
    # Outside servers' questions waiting for the user, by elicitation id.
    pending_elicitations: dict[str, dict[str, Any]] = field(default_factory=dict)
```

- `snapshot`, after `"questions"`: `"elicitations": [dict(e) for e in self.pending_elicitations.values()],`
- After `record_question`:

```python
    def record_elicitation(self, event: dict[str, Any]) -> None:
        """Remembers a server's question that waits for the user, for a browser that joins late."""
        if event.get("id"):
            self.pending_elicitations[event["id"]] = {k: v for k, v in event.items() if k != "type"}
```

- `_publish`, after the `question_resolved` branch:

```python
            elif kind == "elicitation_request":
                turn.activity = "waiting for your answer"
                turn.record_elicitation(event)
            elif kind == "elicitation_resolved":
                turn.activity = ""
                turn.pending_elicitations.pop(str(event.get("id") or ""), None)
```

  and in the terminal block add `turn.pending_elicitations.clear()`.
- In `_answer.on_event`, add `"elicitation_request", "elicitation_resolved",` to the allowed types.
- In the `self._gateway.ask(...)` call add `elicit=turn.options.can_elicit,`.
- In `_clamped`, before the `question_request` branch:

```python
    if kind == "elicitation_request":
        return elicitation_events.clamp_request(event)
```

- After `answer`:

```python
    def pending_elicitation(self, owner: str, chat_id: str, elicitation_id: str) -> dict[str, Any] | None:
        """The server question with this id that is waiting for an answer, if any."""
        turn = self.get(owner, chat_id)
        if turn is None or turn.status != "running":
            return None
        return turn.pending_elicitations.get(elicitation_id)

    async def answer_elicitation(
        self, owner: str, chat_id: str, elicitation_id: str, action: str, content: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Sends the user's answer to the agent. None when it is not waiting. The agent then reports an
        `elicitation_resolved` event, which clears it for every watcher. Nothing of it is kept here."""
        turn = self.get(owner, chat_id)
        if turn is None or turn.status != "running" or elicitation_id not in turn.pending_elicitations:
            return None
        return await self._gateway.answer_elicitation(
            turn.agent.url, turn.caller, turn.request_id, elicitation_id, action, content)
```

- [ ] **Step 4: `turns/routes.py`**

Import `elicitation_events` beside `question_answers`; import `Annotated` from `typing` if absent. `TurnRequest`, after `can_ask`: `can_elicit: bool = False`. In `TurnOptions(...)`: `can_elicit=body.can_elicit,`. After `QuestionRequest`:

```python
ElicitationValue = (
    bool | int | float
    | Annotated[str, Field(max_length=elicitation_events.TEXT_MAX)]
    | Annotated[list[Annotated[str, Field(max_length=elicitation_events.LABEL_MAX)]],
                Field(max_length=elicitation_events.MAX_OPTIONS)]
)


class ElicitationRequest(BaseModel):
    id: str = Field(min_length=1, max_length=elicitation_events.ID_MAX)
    action: Literal["accept", "decline", "cancel"]
    content: dict[Annotated[str, Field(max_length=elicitation_events.LABEL_MAX)], ElicitationValue] | None = Field(
        default=None, max_length=elicitation_events.MAX_FIELDS)
```

After the `answer_questions` route:

```python
@router.post("/{chat_id}/elicitations")
async def answer_elicitation(body: ElicitationRequest, chat_id: str = ChatId,
                             who: Requester = Depends(current_requester),
                             turns: TurnRegistry = Depends(get_turns)) -> dict[str, bool]:
    """Answers a question an outside server asked during the running answer. The content is not logged or saved."""
    if not turns.is_running(who.uid, chat_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer is being written for this chat")
    if turns.pending_elicitation(who.uid, chat_id, body.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    content = body.content if body.action == "accept" else None
    try:
        reply = await turns.answer_elicitation(who.uid, chat_id, body.id, body.action, content)
    except AgentCallError:
        # The agent's error text could repeat what the user typed.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The agent could not take the answer") from None
    if reply and reply["problem"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, reply["problem"])
    if not reply or not reply["answered"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    return {"answered": True}
```

- [ ] **Step 5: `tests/turn_agent.py`**

Fields, after `answer_error`:

```python
    # A server question this fake relays during a turn (the event without type and id).
    elicitation: dict | None = None
    elicitation_answers: list[tuple] = field(default_factory=list)  # (id, action, content)
    elicitation_error: str | None = None
    _eliciting: dict = field(default_factory=dict)
```

`ask`: add `elicit=False,` after `limits=None,`; add `"elicit": elicit,` to the recorded dict; after the `if self.questions:` block add `if self.elicitation:` / `await self._elicit(request_id, on_event)`. Add methods:

```python
    async def _elicit(self, request_id, on_event):
        self.loop = asyncio.get_running_loop()
        waiting = self.loop.create_future()
        self._eliciting[(request_id, "e1")] = waiting
        await on_event({"type": "elicitation_request", "id": "e1", **self.elicitation})
        outcome = await waiting
        del self._eliciting[(request_id, "e1")]
        await on_event({"type": "elicitation_resolved", "id": "e1", "outcome": outcome})

    async def answer_elicitation(self, url, caller, request_id, elicitation_id, action, content):
        if self.elicitation_error:
            raise AgentCallError(self.elicitation_error)
        self.elicitation_answers.append((elicitation_id, action, content))
        waiting = self._eliciting.get((request_id, elicitation_id))
        if waiting is None or waiting.done():
            return {"answered": False, "problem": None}
        if content == {"name": ""}:
            return {"answered": False, "problem": "Name: this field is required."}
        waiting.set_result({"accept": "accepted", "decline": "declined", "cancel": "cancelled"}[action])
        return {"answered": True, "problem": None}
```

In `cancel`, before `return True`:

```python
        for (waiting_request, _id), waiting in list(self._eliciting.items()):
            if waiting_request == request_id and not waiting.done():
                waiting.set_result("cancelled")
```

- [ ] **Step 6: Create `tests/test_turn_elicitations.py`**

```python
"""An outside server's question during a turn: the flag, the snapshot, the answer route and what is kept."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.turns import elicitation_events
from tests.turn_agent import TurnAgent
from tests.test_turns import agent  # noqa: F401  (the Legion stand-in fixture)
from tests.test_turns import chat, events, new_id, start, wait_until

FORM = {"server": "Notes", "tool": "save", "mode": "form", "message": "Which folder?",
        "fields": [{"name": "name", "label": "Name", "kind": "text", "required": True, "max_length": 20}]}


def answer(client: TestClient, chat_id: str, **body):
    payload = {"id": "e1", "action": "accept", "content": {"name": "Secret-Ana"}, **body}
    return client.post(f"/turns/{chat_id}/elicitations", json=payload)


def begin(client: TestClient, agent: TurnAgent) -> str:
    agent.elicitation = dict(FORM)
    chat_id = new_id()
    assert start(client, chat_id, can_elicit=True).status_code == 202
    wait_until(lambda: client.app.state.turns.pending_elicitation("u-1", chat_id, "e1") is not None)
    return chat_id


def test_elicit_is_off_unless_the_browser_can_show_cards(client: TestClient, agent: TurnAgent) -> None:
    chat_id = new_id()
    start(client, chat_id)
    events(client, chat_id)
    assert agent.asks[0]["elicit"] is False


def test_a_question_waits_in_the_snapshot_until_it_is_answered(client: TestClient, agent: TurnAgent) -> None:
    chat_id = begin(client, agent)
    turn = client.app.state.turns.get("u-1", chat_id)
    assert agent.asks[0]["elicit"] is True
    assert turn.snapshot()["elicitations"] == [{"id": "e1", **FORM}]
    refused = answer(client, chat_id, content={"name": ""})
    assert (refused.status_code, refused.json()["detail"]) == (422, "Name: this field is required.")
    assert turn.snapshot()["elicitations"]
    assert answer(client, chat_id).json() == {"answered": True}
    assert events(client, chat_id)[-1]["type"] == "final"
    assert turn.snapshot()["elicitations"] == []
    assert "Secret-Ana" not in json.dumps(chat(client, chat_id))


def test_an_answer_that_cannot_be_taken_is_refused(client: TestClient, agent: TurnAgent) -> None:
    assert answer(client, new_id()).status_code == 404
    chat_id = begin(client, agent)
    assert answer(client, chat_id, id="other").status_code == 409
    assert answer(client, chat_id, content={"name": {"nested": 1}}).status_code == 422
    agent.elicitation_error = "boom Secret-Ana"
    failed = answer(client, chat_id)
    assert failed.status_code == 502 and "Secret-Ana" not in failed.text
    agent.elicitation_error = None
    assert answer(client, chat_id, action="decline").json() == {"answered": True}
    assert agent.elicitation_answers[-1] == ("e1", "decline", None)
    events(client, chat_id)


def test_a_question_is_cut_to_size() -> None:
    cut = elicitation_events.clamp_request({
        "type": "elicitation_request", "id": "e1", "server": "s" * 200, "mode": "url",
        "url": "javascript:alert(1)", "message": "m" * 5000, "surprise": 1,
    })
    assert len(cut["server"]) == 80 and len(cut["message"]) == 2000
    assert cut["url"] == "" and "surprise" not in cut
```

- [ ] **Step 7: `tests/test_agent_gateway.py`**

In `_build_agent`'s `ask`: add `elicit: bool = False,` and `"elicit": elicit,` to the returned dict. In its `status` flags add `"user_elicitations": True`. Add the tool:

```python
    @mcp.tool()
    def answer_elicitation(request_id: str, id: str, action: str, content: dict | None = None) -> dict[str, Any]:
        if (request_id, id) != ("r1", "e1"):
            return {"answered": False, "problem": None}
        if action == "accept" and not content:
            return {"answered": False, "problem": "Name: this field is required."}
        return {"answered": True, "problem": None}
```

Add the tests:

```python
def test_ask_sends_elicit_only_when_asked_and_understood(agent_url: str, old_agent_url: str) -> None:
    gateway = McpAgentGateway(None)
    assert _ask(gateway, agent_url)["elicit"] is False
    assert _ask(gateway, agent_url, elicit=True)["elicit"] is True
    assert _ask(gateway, old_agent_url, elicit=True)["elicit"] is False


def test_answering_an_elicitation_passes_the_problem_on(agent_url: str) -> None:
    def send(*arguments):
        return asyncio.run(McpAgentGateway(None).answer_elicitation(agent_url, CALLER, *arguments))

    assert send("r1", "e1", "accept", {"name": "Ana"}) == {"answered": True, "problem": None}
    assert send("r1", "e1", "accept", None) == {"answered": False, "problem": "Name: this field is required."}
    assert send("r1", "nope", "decline", None) == {"answered": False, "problem": None}
```

- [ ] **Step 8: Run** (from `apps/stronghold/`)

```bash
uv run pytest tests/test_turn_elicitations.py tests/test_agent_gateway.py tests/test_turns.py tests/test_turn_approvals.py tests/test_turn_agent_events.py -q
```

Expected: PASS.

---

### Task 5: Portcullis pass-through

**Files:**
- Modify: `apps/portcullis/src/routes/chats.py`
- Test: `apps/portcullis/tests/fake_turns.py`, `test_turn_passthrough.py`

**Interfaces:**
- Consumes: Stronghold route from Task 4.
- Produces: `POST /api/chats/{chat_id}/elicitations`; turn body field `can_elicit`.

- [ ] **Step 1: `routes/chats.py`**

In `TurnRequest`, after `can_ask`:

```python
    # The browser can show an outside server's own questions (answers go to
    # POST /api/chats/{id}/elicitations).
    can_elicit: bool = False
```

After `QuestionRequest`:

```python
class ElicitationRequest(BaseModel):
    # The question being answered: the `id` of an elicitation_request event.
    id: str = Field(min_length=1, max_length=64)
    action: Literal["accept", "decline", "cancel"]
    # A form's values by field name; Stronghold and Legion check them.
    content: dict[str, Any] | None = Field(default=None, max_length=10)
```

After the `answer_questions` route:

```python
@router.post("/{chat_id}/elicitations")
async def answer_elicitation(
    body: ElicitationRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Answers a question an outside server asked during the running answer. The content is not logged."""
    return as_response(await stronghold.forward("POST", f"/turns/{chat_id}/elicitations", account, json=body.model_dump()))
```

- [ ] **Step 2: Tests**

`fake_turns.py`, beside `/questions`:

```python
        if action == "/elicitations":
            return httpx.Response(200, json={"answered": True})
```

`test_turn_passthrough.py`:

```python
def test_an_elicitation_answer_is_passed_on(client: TestClient, upstream) -> None:
    chat_id = new_id()
    body = {"id": "e1", "action": "accept", "content": {"count": 2, "yes": False, "many": ["a"]}}
    assert client.post(f"/api/chats/{chat_id}/elicitations", json=body).status_code == 401
    as_admin(client)
    response = client.post(f"/api/chats/{chat_id}/elicitations", json=body)
    assert (response.status_code, response.json()) == (200, {"answered": True})
    assert upstream.turns.bodies("POST", "/elicitations")[-1] == body
    assert client.post(f"/api/chats/{chat_id}/elicitations", json={"id": "e1", "action": "maybe"}).status_code == 422


def test_can_elicit_reaches_stronghold(client: TestClient, upstream) -> None:
    as_admin(client)
    start(client, new_id(), can_elicit=True)
    assert last_start(upstream)["can_elicit"] is True
```

- [ ] **Step 3: Run** (from `apps/portcullis/`)

```bash
uv run pytest tests/test_turn_passthrough.py -q
```

Expected: PASS.

---

### Task 6: Ember types, client and store

**Files:**
- Modify: `apps/ember/src/api/types.ts`, `src/features/chat/api/ChatsClient.ts`, `src/features/chat/stores/chat.ts`
- Create: `apps/ember/src/features/chat/stores/chat.elicitations.test.ts`

**Interfaces:**
- Consumes: Portcullis route from Task 5; Stronghold events.
- Produces: types `ElicitationField`, `ElicitationValue`, `ElicitationAction`, `PendingElicitation`; store `pendingElicitations`, `answeringElicitations`, `elicitationProblems`, `answerElicitation(id, action, content?)`.

- [ ] **Step 1: `api/types.ts`**

After `QuestionAnswer`:

```ts
/** One field of a form an outside server asks the user to fill in. */
export interface ElicitationField {
  name: string;
  label: string;
  kind: "text" | "number" | "integer" | "boolean" | "choice" | "multi_choice";
  required: boolean;
  description?: string;
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
  max_length?: number;
}

export type ElicitationValue = string | number | boolean | string[];

export type ElicitationAction = "accept" | "decline" | "cancel";

/** An outside server's question that waits for the user's answer. */
export interface PendingElicitation {
  id: string;
  server: string;
  tool: string;
  mode: "form" | "url";
  message: string;
  agent_label?: string;
  fields?: ElicitationField[];
  url?: string;
}
```

In `TurnEvent`: add `elicitations?: PendingElicitation[];` to the snapshot, and after `question_resolved`:

```ts
  | ({ type: "elicitation_request" } & PendingElicitation)
  | { type: "elicitation_resolved"; id: string; outcome: string }
```

- [ ] **Step 2: `ChatsClient.ts`**

Import `ElicitationAction, ElicitationValue`. In `TurnStart` after `can_ask`:

```ts
  /** This page can show an outside server's own questions and send answers back. */
  can_elicit?: boolean;
```

After `answerQuestion`:

```ts
  /** Answers a question an outside server asked during the answer (an elicitation_request's id). */
  answerElicitation: (id: string, elicitationId: string, action: ElicitationAction, content?: Record<string, ElicitationValue>) =>
    apiRequest<{ answered: boolean }>("POST", `${path(id)}/elicitations`, { id: elicitationId, action, ...(content ? { content } : {}) }),
```

- [ ] **Step 3: `stores/chat.ts`**

Import types `ElicitationAction`, `ElicitationValue`, `PendingElicitation`. After `answeringQuestions`:

```ts
  // Outside servers' questions that wait for the user, the ones whose answer is
  // on its way, and why an answer was refused (by elicitation id).
  const pendingElicitations = ref<PendingElicitation[]>([]);
  const answeringElicitations = ref<string[]>([]);
  const elicitationProblems = ref<Record<string, string>>({});
```

In the snapshot case: `pendingElicitations.value = event.elicitations ?? [];`. After the `question_resolved` case:

```ts
      case "elicitation_request": {
        activity.value = "waiting for your answer ...";
        if (!pendingElicitations.value.some((e) => e.id === event.id)) {
          const { type: _type, sequence: _sequence, ...pending } = event;
          pendingElicitations.value.push(pending);
        }
        break;
      }
      case "elicitation_resolved":
        activity.value = "";
        dropElicitation(event.id);
        break;
```

After `dropQuestion`:

```ts
  function dropElicitation(id: string): void {
    pendingElicitations.value = pendingElicitations.value.filter((e) => e.id !== id);
    answeringElicitations.value = answeringElicitations.value.filter((a) => a !== id);
    delete elicitationProblems.value[id];
  }
```

In `unfollow`:

```ts
    pendingElicitations.value = [];
    answeringElicitations.value = [];
    elicitationProblems.value = {};
```

In `send`, after `can_ask: true,`: `can_elicit: true,`. After `skipQuestion`:

```ts
  /** Answers an outside server's question. The card stays (its buttons off) until the agent confirms
   * with an elicitation_resolved event; a refused answer keeps the card and shows why. */
  async function answerElicitation(id: string, action: ElicitationAction, content?: Record<string, ElicitationValue>): Promise<void> {
    const conversation = active.value;
    if (!conversation || !pendingElicitations.value.some((e) => e.id === id) || answeringElicitations.value.includes(id)) return;
    const started = generation;
    answeringElicitations.value = [...answeringElicitations.value, id];
    delete elicitationProblems.value[id];
    try {
      await chatsClient.answerElicitation(conversation.id, id, action, content);
    } catch (err) {
      if (started !== generation) return;
      if (isApiStatus(err, 404, 409)) return dropElicitation(id);
      answeringElicitations.value = answeringElicitations.value.filter((a) => a !== id);
      elicitationProblems.value[id] = errorMessage(err);
    }
  }
```

Return `pendingElicitations, answeringElicitations, elicitationProblems, answerElicitation` from the store. In existing store tests that compare the whole `startTurn` payload, add `can_elicit: true` beside `can_ask: true`.

- [ ] **Step 4: Create `chat.elicitations.test.ts`**

Copy the head of `chat.questions.test.ts` (imports, the four `vi.mock` blocks, `client`, `watch`, `ACCOUNT`, `summary`, `TWO`, `emit`, `fire`, `storeWith`, `running`, `beforeEach`), replace `answerQuestion: vi.fn()` with `answerElicitation: vi.fn()` in the mock, then:

```ts
const CARD = { id: "e1", server: "Notes", tool: "save", mode: "form", message: "Folder?", fields: [] };
const ask = () => fire({ type: "elicitation_request", ...CARD });

describe("an outside server's question", () => {
  it("is asked for with every turn", async () => {
    await running();

    expect(client.startTurn.mock.calls[0]![1]).toMatchObject({ can_elicit: true });
  });

  it("appears once and comes back from a snapshot", async () => {
    const chat = await running();
    ask();
    ask();
    expect(chat.pendingElicitations).toEqual([CARD]);

    fire({ type: "snapshot", text: "", activity: "", elicitations: [CARD] });

    expect(chat.pendingElicitations).toEqual([CARD]);
  });

  it("stays with its buttons off until the agent confirms", async () => {
    const chat = await running();
    ask();
    client.answerElicitation.mockResolvedValue({ answered: true });

    await chat.answerElicitation("e1", "accept", { folder: "Work" });
    await chat.answerElicitation("e1", "decline");

    expect(client.answerElicitation).toHaveBeenCalledOnce();
    expect(client.answerElicitation).toHaveBeenCalledWith("c1", "e1", "accept", { folder: "Work" });
    expect(chat.answeringElicitations).toEqual(["e1"]);
    fire({ type: "elicitation_resolved", id: "e1", outcome: "accepted" });
    expect(chat.pendingElicitations).toEqual([]);
    expect(chat.answeringElicitations).toEqual([]);
  });

  it("keeps the card and says why an answer was refused", async () => {
    const chat = await running();
    ask();
    client.answerElicitation.mockRejectedValue(new ApiError(422, "Folder: this field is required."));

    await chat.answerElicitation("e1", "accept", {});

    expect(chat.pendingElicitations).toHaveLength(1);
    expect(chat.answeringElicitations).toEqual([]);
    expect(chat.elicitationProblems).toEqual({ e1: "Folder: this field is required." });
    expect(chat.sendError).toBe("");
  });

  it("is dropped quietly when nothing is waiting any more", async () => {
    const chat = await running();
    ask();
    client.answerElicitation.mockRejectedValue(new ApiError(409, "Nothing is waiting for that answer"));

    await chat.answerElicitation("e1", "cancel");

    expect(chat.pendingElicitations).toEqual([]);
  });
});
```

- [ ] **Step 5: Run** (from `apps/ember/`)

```bash
pnpm exec vitest run src/features/chat/stores/chat.elicitations.test.ts src/features/chat/stores/chat.questions.test.ts src/features/chat/stores/chat.test.ts src/features/chat/api/ChatsClient.test.ts
```

Expected: PASS.

---

### Task 7: Ember card, wiring and commit

**Files:**
- Create: `apps/ember/src/features/chat/components/ElicitationCard.vue`, `ElicitationCard.test.ts`
- Modify: `apps/ember/src/features/chat/components/MessageList.vue`, `src/features/chat/views/ChatView.vue`
- Modify: `docs/superpowers/specs/2026-11-26-legion-sdk-v2-elicitation-design.md`

- [ ] **Step 1: Read the UI rules**

Read `.agents/skills/ember-frontend-design/SKILL.md`, `.agents/skills/ember-design-system/SKILL.md`, and the global `ux-checks` and `mobile-ui` skills. They win over the code below on conflict.

- [ ] **Step 2: Create `ElicitationCard.vue`**

```vue
<script setup lang="ts">
import { computed, nextTick, reactive, ref, useId } from "vue";
import { ToggleSwitch, copyText } from "@citadel/ui";
import type { ElicitationAction, ElicitationField, ElicitationValue, PendingElicitation } from "../../../api/types";

/** A question an outside server asks mid-answer: a short form, or a link to
 * open. The server's text is shown as plain text. The agent confirms with an
 * elicitation_resolved event, which removes the card. */

const props = defineProps<{ pending: PendingElicitation; answering: boolean; problem?: string }>();
const emit = defineEmits<{
  answer: [id: string, action: ElicitationAction, content?: Record<string, ElicitationValue>];
}>();

const uid = useId();
const form = ref<HTMLFormElement | null>(null);
const fields = computed(() => props.pending.fields ?? []);
// Typed text stays text until Send; switches and ticks keep their own type.
const values = reactive<Record<string, string | boolean | string[]>>(
  Object.fromEntries(
    (props.pending.fields ?? []).map((f) => [f.name, f.kind === "boolean" ? false : f.kind === "multi_choice" ? [] : ""]),
  ),
);
const errors = reactive<Record<string, string>>({});
const sent = ref<ElicitationAction | "">("");

// Legion names the field first ("Name: this field is required."), so it is shown there.
const problemField = computed(() => fields.value.find((f) => props.problem?.startsWith(`${f.label}: `)));
const formProblem = computed(() => (problemField.value ? "" : (props.problem ?? "")));
function errorFor(field: ElicitationField): string {
  if (errors[field.name]) return errors[field.name]!;
  return problemField.value === field ? props.problem!.slice(field.label.length + 2) : "";
}
function describedBy(field: ElicitationField, index: number): string | undefined {
  const ids = [field.description ? `${uid}-${index}-help` : "", errorFor(field) ? `${uid}-${index}-error` : ""];
  return ids.filter(Boolean).join(" ") || undefined;
}

function read(field: ElicitationField): { value?: ElicitationValue; error?: string } {
  const raw = values[field.name]!;
  if (typeof raw === "boolean") return { value: raw };
  if (Array.isArray(raw)) {
    if (!raw.length) return field.required ? { error: "Choose at least one." } : {};
    if (field.min !== undefined && raw.length < field.min) return { error: `Choose at least ${field.min}.` };
    if (field.max !== undefined && raw.length > field.max) return { error: `Choose at most ${field.max}.` };
    return { value: [...raw] };
  }
  if (raw === "") return field.required ? { error: "This field is required." } : {};
  if (field.kind !== "number" && field.kind !== "integer") return { value: raw };
  const number = Number(raw);
  if (!raw.trim() || !Number.isFinite(number) || (field.kind === "integer" && !Number.isInteger(number))) {
    return { error: field.kind === "integer" ? "Enter a whole number." : "Enter a number." };
  }
  if (field.min !== undefined && number < field.min) return { error: `Enter at least ${field.min}.` };
  if (field.max !== undefined && number > field.max) return { error: `Enter at most ${field.max}.` };
  return { value: number };
}

function answer(action: ElicitationAction, content?: Record<string, ElicitationValue>): void {
  if (props.answering) return;
  sent.value = action;
  emit("answer", props.pending.id, action, content);
}

async function submit(): Promise<void> {
  if (props.pending.mode !== "form") return;
  const content: Record<string, ElicitationValue> = {};
  let invalid = false;
  for (const field of fields.value) {
    const { value, error } = read(field);
    errors[field.name] = error ?? "";
    if (error) invalid = true;
    else if (value !== undefined) content[field.name] = value;
  }
  if (invalid) {
    await nextTick();
    form.value?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    return;
  }
  answer("accept", content);
}

// URL mode: only an https link is offered, with its site in punycode so a look-alike name shows.
const link = computed(() => {
  try {
    const parsed = new URL(props.pending.url ?? "");
    return parsed.protocol === "https:" ? { href: props.pending.url!, site: parsed.hostname } : null;
  } catch {
    return null;
  }
});
const followed = ref(false);
const copyLabel = ref("Copy link");
async function copy(): Promise<void> {
  const copied = await copyText(link.value!.href);
  copyLabel.value = copied ? "Copied" : "Copy failed";
  if (copied) followed.value = true;
}
</script>

<template>
  <form ref="form" class="elicitation-card" :aria-label="`${pending.server} has a question`" novalidate @submit.prevent="submit">
    <header>
      <strong>{{ pending.server }} asks</strong>
      <span class="note">{{ [pending.agent_label, pending.tool].filter(Boolean).join(" · ") }}</span>
    </header>
    <p class="message">{{ pending.message }}</p>

    <template v-if="pending.mode === 'url'">
      <template v-if="link">
        <p class="site">Site: <strong>{{ link.site }}</strong></p>
        <p class="url" @copy="followed = true">{{ link.href }}</p>
        <div class="buttons">
          <a class="open" :href="link.href" target="_blank" rel="noopener noreferrer" @click="followed = true" @auxclick="followed = true">Open link</a>
          <button type="button" class="copy-link" @click="copy">{{ copyLabel }}</button>
        </div>
        <p class="note">Open the link, finish there, then press Continue.</p>
      </template>
      <p v-else class="error" role="alert">This link cannot be opened safely.</p>
    </template>

    <template v-else>
      <div v-for="(field, i) in fields" :key="field.name" class="field">
        <ToggleSwitch
          v-if="field.kind === 'boolean'"
          small
          :checked="values[field.name] === true"
          :disabled="answering"
          :aria-describedby="describedBy(field, i)"
          :aria-invalid="!!errorFor(field)"
          @change="values[field.name] = ($event.target as HTMLInputElement).checked"
        >{{ field.label }}</ToggleSwitch>
        <fieldset v-else-if="field.kind === 'multi_choice'" :aria-describedby="describedBy(field, i)">
          <legend>{{ field.label }}<span v-if="field.required"><span aria-hidden="true"> *</span><span class="sr-only"> required</span></span></legend>
          <label v-for="o in field.options" :key="o.value" class="tick">
            <input v-model="values[field.name]" type="checkbox" :value="o.value" :disabled="answering" :aria-invalid="!!errorFor(field)" />
            {{ o.label }}
          </label>
        </fieldset>
        <template v-else>
          <label :for="`${uid}-${i}`">{{ field.label }}<span v-if="field.required" aria-hidden="true"> *</span></label>
          <select v-if="field.kind === 'choice'" :id="`${uid}-${i}`" v-model="values[field.name]" :disabled="answering" :aria-required="field.required" :aria-invalid="!!errorFor(field)" :aria-describedby="describedBy(field, i)">
            <option value="">Choose…</option>
            <option v-for="o in field.options" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <textarea v-else-if="field.kind === 'text' && (field.max_length ?? 0) > 200" :id="`${uid}-${i}`" v-model="values[field.name]" rows="3" :maxlength="field.max_length" :disabled="answering" :aria-required="field.required" :aria-invalid="!!errorFor(field)" :aria-describedby="describedBy(field, i)" />
          <input v-else :id="`${uid}-${i}`" v-model="values[field.name]" type="text" :inputmode="field.kind === 'integer' ? 'numeric' : field.kind === 'number' ? 'decimal' : 'text'" :maxlength="field.max_length" autocomplete="off" :disabled="answering" :aria-required="field.required" :aria-invalid="!!errorFor(field)" :aria-describedby="describedBy(field, i)" />
        </template>
        <p v-if="field.description" :id="`${uid}-${i}-help`" class="note">{{ field.description }}</p>
        <p v-if="errorFor(field)" :id="`${uid}-${i}-error`" class="error" role="alert">{{ errorFor(field) }}</p>
      </div>
      <p class="warning">Do not enter passwords or keys here.</p>
    </template>

    <p v-if="formProblem" class="error" role="alert">{{ formProblem }}</p>
    <div class="buttons">
      <button v-if="pending.mode === 'url'" type="button" class="submit" :aria-busy="answering && sent === 'accept'" :disabled="!followed || answering" @click="answer('accept')">Continue</button>
      <button v-else type="submit" class="submit" :aria-busy="answering && sent === 'accept'" :disabled="answering">Send</button>
      <button type="button" class="decline" :aria-busy="answering && sent === 'decline'" :disabled="answering" @click="answer('decline')">Decline</button>
      <button type="button" class="cancel" :aria-busy="answering && sent === 'cancel'" :disabled="answering" @click="answer('cancel')">Cancel</button>
    </div>
  </form>
</template>

<style scoped src="./chatShared.css"></style>
<style scoped>
.elicitation-card {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--accent) 6%, var(--surface));
}
header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
}
p {
  margin: 0;
  overflow-wrap: anywhere;
}
.message {
  white-space: pre-wrap;
}
.url {
  user-select: all;
  font-family: var(--font-mono, monospace);
  font-size: 0.8em;
}
.field {
  display: grid;
  gap: 4px;
  min-width: 0;
}
fieldset {
  display: grid;
  gap: 4px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
.tick {
  display: flex;
  align-items: center;
  gap: 8px;
}
input[type="text"],
textarea,
select {
  min-width: 0;
  max-width: 100%;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font: inherit;
  font-size: 0.9em;
  color: var(--text);
  background: var(--bg);
}
[aria-invalid="true"] {
  border-color: var(--danger);
}
input:focus-visible,
textarea:focus-visible,
select:focus-visible,
.open:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.note {
  font-size: 0.75em;
  color: var(--muted);
}
.warning {
  font-size: 0.8em;
}
.error {
  font-size: 0.8em;
  color: var(--danger);
}
.open {
  display: inline-flex;
  align-items: center;
  padding: 5px 14px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-full);
  font-size: 0.85em;
  color: var(--text);
  text-decoration: none;
}
.buttons .submit {
  border-color: var(--accent);
  color: var(--accent-contrast);
  background: var(--accent);
}
.buttons button:disabled {
  cursor: default;
  opacity: 0.45;
}
@media (pointer: coarse), (max-width: 767px) {
  .open,
  .buttons button,
  .tick,
  select,
  input[type="text"] {
    min-height: 44px;
  }
}
</style>
```

- [ ] **Step 3: Create `ElicitationCard.test.ts`**

```ts
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { PendingElicitation } from "../../../api/types";
import ElicitationCard from "./ElicitationCard.vue";

const FORM: PendingElicitation = {
  id: "e1", server: "Notes", tool: "save", mode: "form", message: "<b>Which folder?</b>", agent_label: "Writer",
  fields: [
    { name: "folder", label: "Folder", kind: "text", required: true, max_length: 20 },
    { name: "count", label: "Count", kind: "integer", required: false, min: 1 },
    { name: "tags", label: "Tags", kind: "multi_choice", required: false, options: [{ value: "a", label: "A" }] },
    { name: "pin", label: "Pin", kind: "boolean", required: false },
  ],
};
const LINK: PendingElicitation = {
  id: "e2", server: "Notes", tool: "login", mode: "url", message: "Sign in", url: "https://bücher.example/login",
};

function mountCard(pending: PendingElicitation = FORM, props: Record<string, unknown> = {}) {
  return mount(ElicitationCard, { props: { pending, answering: false, ...props } });
}

describe("ElicitationCard", () => {
  it("names the asker, shows the message as plain text and warns about secrets", () => {
    const w = mountCard();

    expect(w.text()).toContain("Notes asks");
    expect(w.text()).toContain("Writer · save");
    expect(w.get(".message").text()).toBe("<b>Which folder?</b>");
    expect(w.find(".message b").exists()).toBe(false);
    expect(w.text()).toContain("Do not enter passwords or keys here.");
  });

  it("puts an error beside the field and keeps what was typed", async () => {
    const w = mountCard();
    const inputs = w.findAll('input[type="text"]');
    await inputs[1]!.setValue("many");

    await w.get("form").trigger("submit");

    expect(w.findAll(".field")[0]!.get(".error").text()).toBe("This field is required.");
    expect(w.findAll(".field")[1]!.get(".error").text()).toBe("Enter a whole number.");
    expect((inputs[1]!.element as HTMLInputElement).value).toBe("many");
    expect(w.emitted("answer")).toBeUndefined();
  });

  it("sends typed values", async () => {
    const w = mountCard();
    const inputs = w.findAll('input[type="text"]');
    await inputs[0]!.setValue("Work");
    await inputs[1]!.setValue("2");
    await w.get(".tick input").setValue(true);
    await w.get('input[role="switch"]').setValue(true);

    await w.get("form").trigger("submit");

    expect(w.emitted("answer")).toEqual([["e1", "accept", { folder: "Work", count: 2, tags: ["a"], pin: true }]]);
  });

  it("shows the server's refusal beside the field it names", () => {
    const w = mountCard(FORM, { problem: "Folder: use at most 20 characters." });

    expect(w.findAll(".field")[0]!.get(".error").text()).toBe("use at most 20 characters.");
  });

  it("declines and cancels without values", async () => {
    const w = mountCard();

    await w.get("button.decline").trigger("click");
    await w.get("button.cancel").trigger("click");

    expect(w.emitted("answer")).toEqual([["e1", "decline", undefined], ["e1", "cancel", undefined]]);
  });

  it("offers a link safely and continues only after it was opened", async () => {
    const w = mountCard(LINK);
    const anchor = w.get("a.open");

    expect(w.get(".site").text()).toContain("xn--bcher-kva.example");
    expect(anchor.attributes("rel")).toBe("noopener noreferrer");
    expect(anchor.attributes("target")).toBe("_blank");
    expect((w.get("button.submit").element as HTMLButtonElement).disabled).toBe(true);
    await anchor.trigger("click");
    expect(w.emitted("answer")).toBeUndefined();
    await w.get("button.submit").trigger("click");

    expect(w.emitted("answer")).toEqual([["e2", "accept", undefined]]);
  });

  it("offers no link that is not https", () => {
    const w = mountCard({ ...LINK, url: "javascript:alert(1)" });

    expect(w.find("a.open").exists()).toBe(false);
  });
});
```

- [ ] **Step 4: Wire `MessageList.vue` and `ChatView.vue`**

`MessageList.vue`: import `ElicitationCard from "./ElicitationCard.vue"` and the types `ElicitationAction`, `ElicitationValue`, `PendingElicitation`. Props, after `answeringQuestions`:

```ts
  /** Outside servers' questions waiting for the user, the ones already answered, and refusals by id. */
  elicitations?: PendingElicitation[];
  answeringElicitations?: string[];
  elicitationProblems?: Record<string, string>;
```

Emit, after `"skip-question"`:

```ts
  "answer-elicitation": [id: string, action: ElicitationAction, content?: Record<string, ElicitationValue>];
```

Template, after the `QuestionCard` element:

```vue
        <ElicitationCard
          v-for="e in elicitations ?? []"
          :key="e.id"
          :pending="e"
          :answering="answeringElicitations?.includes(e.id) ?? false"
          :problem="elicitationProblems?.[e.id]"
          @answer="(id, action, content) => emit('answer-elicitation', id, action, content)"
        />
```

`ChatView.vue`: take `pendingElicitations`, `answeringElicitations`, `elicitationProblems` from the store the same way as `pendingQuestions`, and add to `MessageList`:

```vue
        :elicitations="pendingElicitations"
        :answering-elicitations="answeringElicitations"
        :elicitation-problems="elicitationProblems"
        @answer-elicitation="chat.answerElicitation"
```

- [ ] **Step 5: Update the spec**

In the spec, set `Status:` to `built, not shipped`, and add under "Waiting":

```
- The turn time limit and the architect unit limit pause while a question is open.
```

- [ ] **Step 6: Run** (from `apps/ember/`)

```bash
pnpm exec vitest run src/features/chat/components/ElicitationCard.test.ts src/features/chat/components/MessageList.test.ts src/radiusScale.test.ts
```

```bash
pnpm exec vue-tsc -b
```

Expected: PASS, no type errors.

- [ ] **Step 7: Look at the card**

With the Ember dev server and sample data (no production sign-in), check the form card and the link card at 375 px and desktop width, in light and dark. Say in the report what could not be viewed.

- [ ] **Step 8: Commit** (from `Applications/Citadel/`)

```bash
git status --short
git add apps/legion apps/stronghold apps/portcullis apps/ember docs/superpowers
git commit -m "feat: outside MCP servers can ask the user during a tool call (elicitation)"
```

## Report at the end

State what changed, which commands ran, and what was not run: no Docker build, no live services together, no real outside 2026 server, desktop "Open link" not checked, no full suites.

Shipping is not part of this plan. It needs the user's go-ahead, in this order: Legion, Stronghold, Portcullis, then Ember (installer rebuild and web publish). If the desktop "Open link" does nothing, "Copy link" is the fallback; adding the Tauri opener plugin is a follow-up decision.
