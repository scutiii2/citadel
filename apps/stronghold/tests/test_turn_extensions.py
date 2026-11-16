"""Private extensions on a turn: the account's list goes to the agent, the browser cannot name one,
notices reach the watcher, and a private tool asks."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.turns.engine import TurnOptions
from tests.test_turns import agent  # noqa: F401  (the Legion stand-in fixture)
from tests.test_turns import events, new_id, start, wait_until
from tests.turn_agent import TurnAgent

NOTES = {"label": "Notes", "url": "https://notes.example.com/mcp", "headers": {"X-Key": "s3cret"}}


def add_notes(client: TestClient) -> None:
    assert client.post("/user-extensions", json=NOTES).status_code == 201


def test_a_turn_without_private_extensions_sends_none(client: TestClient, agent: TurnAgent) -> None:
    chat_id = new_id()
    start(client, chat_id)
    events(client, chat_id)
    assert not agent.asks[-1]["private_extensions"]


def test_the_browser_cannot_name_an_extension_for_a_turn(client: TestClient, agent: TurnAgent) -> None:
    chat_id = new_id()
    start(client, chat_id, private_extensions=[{"id": "evil", "label": "x", "url": "http://10.0.0.5/mcp", "headers": {}}])
    events(client, chat_id)
    assert not agent.asks[-1]["private_extensions"]


def test_what_the_agent_could_not_connect_to_reaches_the_watcher_as_a_notice(client: TestClient, agent: TurnAgent) -> None:
    add_notes(client)
    notices = [{"id": "notes", "label": "Notes", "error": "Timed out"}]
    agent.result_extra = {"private_extension_errors": notices}
    chat_id = new_id()
    start(client, chat_id)
    assert [e["notices"] for e in events(client, chat_id) if e["type"] == "notice"] == [notices]


def test_no_notice_when_everything_connected(client: TestClient, agent: TurnAgent) -> None:
    add_notes(client)
    chat_id = new_id()
    start(client, chat_id)
    assert not [e for e in events(client, chat_id) if e["type"] == "notice"]


def test_a_private_tool_asks_even_when_ask_before_tools_is_off(client: TestClient, agent: TurnAgent) -> None:
    add_notes(client)
    agent.tool_calls = ["u_notes__search"]
    chat_id = new_id()
    start(client, chat_id)  # no ask_before_tools
    wait_until(lambda: agent._waiting)
    assert agent.ran == []
    decided = client.post(f"/turns/{chat_id}/approvals",
                          json={"step_id": "step0", "decision": "allow", "trusted": {"forced_approval": False}})
    assert decided.status_code == 200
    events(client, chat_id)
    assert agent.ran == ["u_notes__search"]


def test_turn_options_never_show_header_values_in_repr() -> None:
    options = TurnOptions(private_extensions=({"id": "notes", "label": "N", "url": "u", "headers": {"X-Key": "s3cret"}},))
    assert "s3cret" not in repr(options)


def test_storage_unavailable_still_runs_the_turn_without_private_extensions(client: TestClient, agent: TurnAgent, db_gateway) -> None:
    from src.document_store import DbGatewayError

    real = db_gateway.query

    async def broken(collection, *args, **kwargs):
        if collection == "user_extensions":
            raise DbGatewayError("down")
        return await real(collection, *args, **kwargs)

    db_gateway.query = broken
    chat_id = new_id()
    start(client, chat_id)
    stream = events(client, chat_id)
    assert not agent.asks[-1]["private_extensions"]
    assert "unavailable" in next(e for e in stream if e["type"] == "notice")["notices"][0]["error"]
