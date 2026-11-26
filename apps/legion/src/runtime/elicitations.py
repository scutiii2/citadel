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
