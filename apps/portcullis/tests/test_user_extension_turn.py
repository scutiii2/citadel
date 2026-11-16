"""Private extensions on a turn: Stronghold's list goes to the agent, the browser cannot name one,
notices reach the watcher, and a private tool asks."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.services.turns import TurnOptions
from tests.conftest import FakeAgent
from tests.test_registration import as_admin
from tests.test_turns import chat, events, new_id, start, wait_until

NOTES = {"id": "notes", "label": "Notes", "url": "https://notes.example.com/mcp", "headers": {"X-Key": "s3cret"}}


def finished(client: TestClient, chat_id: str) -> list[dict]:
    wait_until(lambda: chat(client, chat_id)["running"] is False)
    return events(client, chat_id)


def test_what_stronghold_hands_over_is_sent_to_the_agent(client: TestClient, agent: FakeAgent, upstream) -> None:
    as_admin(client)
    upstream.private = {"items": [NOTES], "skipped": []}
    chat_id = new_id()

    assert start(client, chat_id).status_code == 202
    finished(client, chat_id)

    assert agent.asks[-1]["private_extensions"] == [NOTES]


def test_a_turn_without_private_extensions_sends_none(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    chat_id = new_id()

    start(client, chat_id)
    finished(client, chat_id)

    assert not agent.asks[-1]["private_extensions"]


def test_the_browser_cannot_name_an_extension_for_a_turn(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    chat_id = new_id()

    start(client, chat_id, private_extensions=[{"id": "evil", "label": "x", "url": "http://10.0.0.5/mcp", "headers": {}}])
    finished(client, chat_id)

    assert not agent.asks[-1]["private_extensions"]


def test_what_the_agent_could_not_connect_to_reaches_the_watcher_as_a_notice(
    client: TestClient, agent: FakeAgent, upstream
) -> None:
    as_admin(client)
    upstream.private = {"items": [NOTES], "skipped": []}
    notices = [{"id": "notes", "label": "Notes", "error": "Timed out"}]
    agent.result_extra = {"private_extension_errors": notices}
    chat_id = new_id()

    start(client, chat_id)
    stream = finished(client, chat_id)

    assert [e["notices"] for e in stream if e["type"] == "notice"] == [notices]


def test_no_notice_when_everything_connected(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.private = {"items": [NOTES], "skipped": []}
    chat_id = new_id()

    start(client, chat_id)

    assert not [e for e in finished(client, chat_id) if e["type"] == "notice"]


def test_an_extension_stronghold_skipped_reaches_the_watcher_as_a_notice(client: TestClient, agent: FakeAgent, upstream) -> None:
    as_admin(client)
    skipped = {"id": "notes", "label": "Notes", "error": "Its headers can't be read (the secrets key changed). Edit it to set them again."}
    upstream.private = {"items": [{**NOTES, "id": "wiki"}], "skipped": [skipped]}
    chat_id = new_id()

    start(client, chat_id)
    stream = finished(client, chat_id)

    assert [e["id"] for e in agent.asks[-1]["private_extensions"]] == ["wiki"]
    notice = next(e for e in stream if e["type"] == "notice")
    assert notice["notices"][0]["id"] == "notes"
    assert "can't be read" in notice["notices"][0]["error"]


def test_a_private_tool_asks_even_when_ask_before_tools_is_off(client: TestClient, agent: FakeAgent, upstream) -> None:
    as_admin(client)
    upstream.private = {"items": [NOTES], "skipped": []}
    agent.tool_calls = ["u_notes__search"]
    chat_id = new_id()

    start(client, chat_id)  # no ask_before_tools
    wait_until(lambda: agent._waiting)
    assert agent.ran == []

    decided = client.post(f"/api/chats/{chat_id}/approvals", json={"step_id": "step0", "decision": "allow"})
    assert decided.status_code == 200
    finished(client, chat_id)

    assert agent.ran == ["u_notes__search"]


def test_turn_options_never_show_header_values_in_repr() -> None:
    options = TurnOptions(private_extensions=({"id": "notes", "label": "N", "url": "u", "headers": {"X-Key": "s3cret"}},))

    assert "s3cret" not in repr(options)


def test_stronghold_unable_to_answer_still_runs_the_turn_without_private_extensions(
    client: TestClient, agent: FakeAgent, upstream
) -> None:
    as_admin(client)
    upstream.private_status = 503
    chat_id = new_id()

    start(client, chat_id)
    stream = finished(client, chat_id)

    assert not agent.asks[-1]["private_extensions"]
    notice = next(e for e in stream if e["type"] == "notice")
    assert "unavailable" in notice["notices"][0]["error"]
