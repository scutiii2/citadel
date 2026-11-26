"""Server questions in the middle of a tool call: checking them, waiting, and who may answer."""

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
import uvicorn
from mcp.server.mcpserver import Context, MCPServer
from mcp_types import (
    ElicitRequest, ElicitRequestFormParams, ElicitRequestURLParams, ElicitResult, InputRequiredResult,
)

from src import server
from src.agents.roles.orchestrator import delegation
from src.providers import cancellation, deadlines
from src.providers.base_provider import dispatch_with_progress
from src.runtime import elicitations, internal_auth
from src.tools.mcp_client.config import ServerConfig
from src.tools.mcp_client.registry import McpClientRegistry
from tests.test_private_integration import free_port

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


def test_the_answer_tool_works_through_the_mcp_server():
    async def go():
        async def on_event(_event):
            pass

        fields = elicitations.parse_request(form())[0]["fields"]
        waiter = asyncio.create_task(elicitations.BROKER.wait(
            REQUEST, "e1", UID, fields, {"type": "elicitation_request", "id": "e1"}, on_event))
        await asyncio.sleep(0.05)
        token = internal_auth.bind_requester(internal_auth.Requester(uid=UID))
        try:
            await server.mcp.call_tool("answer_elicitation", {
                "request_id": REQUEST, "id": "e1", "action": "accept", "content": {"name": "Ana"}})
        finally:
            internal_auth.reset_requester(token)
        return await asyncio.wait_for(waiter, 2)

    reply = asyncio.run(go())
    assert (reply.outcome, reply.content) == ("accepted", {"name": "Ana"})


@pytest.mark.parametrize("action, expected", [
    ("accept", "accept:Ana"),
    ("decline", "decline:\n\n" + elicitations.DECLINED_NOTE),
])
def test_a_tool_step_asks_the_user_through_the_real_connection(url, monkeypatch, action, expected):
    """The whole production path: tool step, worker thread, connection loop, server, and back."""
    from src.tools.mcp_client import mcp_upstream
    from src.tools.mcp_client.sync_wrapper import SyncMcpClient

    client = SyncMcpClient()
    config = ServerConfig("asking", "Asking server", "", "http", url=url)
    client._registry._configs["asking"] = config
    client.run_coroutine(client._registry._connect_one("asking", config))
    everything = SimpleNamespace(allows=lambda name: True, allows_explicitly=lambda name: True)
    monkeypatch.setattr(mcp_upstream, "client", client)
    monkeypatch.setattr(mcp_upstream, "agent_spec", SimpleNamespace(current=lambda: SimpleNamespace(tools=everything)))
    monkeypatch.setattr(mcp_upstream, "_injection_detected", lambda *args: False)
    shown = []

    async def go():
        async def on_event(event):
            shown.append(event)
            if event["type"] == "elicitation_request":
                elicitations.BROKER.answer(REQUEST, event["id"], UID, action, {"name": "Ana"})

        token = elicitations.bind(elicitations.Policy(True, UID, REQUEST))
        try:
            return await dispatch_with_progress(
                lambda: mcp_upstream.call_tool("asking__greet", {}), on_event, "s1")
        finally:
            elicitations.reset(token)

    try:
        assert asyncio.run(asyncio.wait_for(go(), 20)) == expected
    finally:
        client.close()
    assert shown[0]["server"] == "Asking server" and shown[0]["tool"] == "greet"
