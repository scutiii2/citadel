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
