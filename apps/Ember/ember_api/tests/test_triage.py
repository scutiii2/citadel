"""/api/triage: titles from the title-writer agent, and typed questions asked straight to Laya (FakeAgent here)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.config import UsageSettings
from src.services.agent_gateway import AgentCallError
from src.services.triage_questions import parse_titles, read_answer, unique_titles
from tests.conftest import AGENTS, FakeAgent, FakeEmailSender
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

TITLES = "/api/triage/titles"
ASK = "/api/triage/ask"
LAYA_URL = "http://laya.internal/mcp"
TITLE_URL = "http://titles.internal/mcp"


def run_agents(tmp_path: Path, *, laya: bool = True, titles: bool = True) -> None:
    """Registers the Triage Assistant and the title writer, as ai_agent's registry and definitions files would."""
    extra, defined = [], []
    if laya:
        extra.append({"id": "triage-assistant", "label": "Triage Assistant", "url": LAYA_URL})
        defined.append({"id": "triage-assistant", "label": "Triage Assistant", "llm": {"provider": "laya"}})
    if titles:
        extra.append({"id": "title-writer", "label": "Title Writer", "url": TITLE_URL})
        defined.append({"id": "title-writer", "label": "Title Writer", "llm": {"provider": "anthropic"}})
    (tmp_path / "config_agents.json").write_text(json.dumps({"agents": [*AGENTS, *extra]}), encoding="utf-8")
    (tmp_path / "agent_definitions.json").write_text(json.dumps({"defined": defined}), encoding="utf-8")


def laya_answers(agent: FakeAgent, monkeypatch, answer: dict, calls: list | None = None) -> None:
    async def ask(url, caller, *, question, **kwargs):
        if calls is not None:
            calls.append({"url": url, "caller": caller, "request": json.loads(question), **kwargs})
        return {
            "response": json.dumps({"answers": {"q": answer}, "uncertain": answer["uncertain"]}),
            "provider_id": "laya", "model": "convaiinnovations/laya", "total_tokens": 370, "input_tokens": 370,
        }

    monkeypatch.setattr(agent, "ask", ask)


CHOICE = {
    "kind": "choice", "text": "SQLite database is locked", "question": "Which area?",
    "options": [{"title": "database", "description": "SQL and storage"}, {"title": "network", "description": "Connections"}],
}
YES_NO = {"kind": "yes_no", "text": "SQLite database is locked", "question": "Is there a problem?"}
SCORE = {
    "kind": "score", "text": "SQLite database is locked", "question": "How urgent is this?",
    "levels": ["Can wait", "Soon", "Right now"],
}


# -- parsing ---------------------------------------------------------------------------------------------
def test_titles_are_the_first_word_lowercased_and_made_unique() -> None:
    assert unique_titles(["Billing!", "billing now", "", 7]) == ["billing", "billing2", "option3", "7"]


def test_parse_titles_reads_a_code_fenced_array_and_fills_what_is_missing() -> None:
    assert parse_titles('```json\n["Cost", "Speed"]\n```', 3) == ["cost", "speed", "option3"]
    assert parse_titles("sorry, no", 2) == ["option1", "option2"]


def test_read_answer_rejects_something_that_is_not_the_expected_json() -> None:
    import pytest

    from src.services.triage_questions import TriageUnavailable

    with pytest.raises(TriageUnavailable):
        read_answer("choice", "not json")
    with pytest.raises(TriageUnavailable):
        read_answer("yes_no", json.dumps({"answers": {"q": {"type": "noul"}}}))


# -- access ------------------------------------------------------------------------------------------------
def test_needs_login(client: TestClient) -> None:
    assert client.post(TITLES, json={"descriptions": ["a", "b"]}).status_code == 401
    assert client.post(ASK, json=YES_NO).status_code == 401


def test_unverified_account_is_refused(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email, "alice", verify=False)
    login(client, "alice")

    assert client.post(ASK, json=YES_NO).status_code == 403


# -- titles --------------------------------------------------------------------------------------------------
def test_titles_come_from_the_title_writer_and_only_it_sees_the_descriptions(
    client: TestClient, agent: FakeAgent, tmp_path: Path
) -> None:
    as_admin(client)
    run_agents(tmp_path)
    agent.summary = '["Storage", "Network"]'

    response = client.post(TITLES, json={"descriptions": ["SQL and storage", " Connections "]})

    assert response.json() == {"titles": ["storage", "network"]}
    assert len(agent.interprets) == 1
    assert "SQL and storage" in agent.interprets[0] and "Connections" in agent.interprets[0]


def test_titles_fall_back_to_numbered_options_when_the_reply_is_unusable(
    client: TestClient, agent: FakeAgent, tmp_path: Path
) -> None:
    as_admin(client)
    run_agents(tmp_path)
    agent.summary = "I cannot do that"

    assert client.post(TITLES, json={"descriptions": ["a", "b"]}).json() == {"titles": ["option1", "option2"]}


def test_titles_are_unavailable_without_the_agent_or_when_it_fails(
    client: TestClient, agent: FakeAgent, tmp_path: Path
) -> None:
    as_admin(client)
    run_agents(tmp_path, titles=False)
    assert client.post(TITLES, json={"descriptions": ["a", "b"]}).status_code == 503

    run_agents(tmp_path)
    agent.fail = "boom"
    assert client.post(TITLES, json={"descriptions": ["a", "b"]}).status_code == 503


def test_titles_need_two_to_ten_descriptions(client: TestClient, tmp_path: Path) -> None:
    as_admin(client)
    run_agents(tmp_path)

    assert client.post(TITLES, json={"descriptions": ["only one"]}).status_code == 422
    assert client.post(TITLES, json={"descriptions": ["x"] * 11}).status_code == 422
    assert client.post(TITLES, json={"descriptions": ["ok", "  "]}).status_code == 422


# -- ask --------------------------------------------------------------------------------------------------------
def test_a_choice_question_is_sent_to_laya_and_the_answer_comes_back(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_agents(tmp_path)
    calls: list = []
    laya_answers(agent, monkeypatch, {
        "type": "choice", "choice": "database", "probabilities": {"database": 0.91234, "network": 0.08766},
        "answer_confidence": 0.9123, "uncertain": False,
    }, calls)

    found = client.post(ASK, json=CHOICE).json()

    assert found == {
        "kind": "choice", "choice": "database", "probabilities": {"database": 0.9123, "network": 0.0877},
        "confidence": 0.9123, "uncertain": False,
    }
    call = calls[0]
    assert call["url"] == LAYA_URL
    assert call["caller"].username == "root"
    assert call["request"] == {
        "text": "SQLite database is locked",
        "questions": {"q": {"type": "choice", "instructions": "Which area?",
                            "criteria": {"database": "SQL and storage", "network": "Connections"}}},
        "local_only": True,  # Laya answers alone: no fallback to Jev
    }
    assert call["history"] == [] and call["enabled_extensions"] == []


def test_a_yes_no_question_is_a_noul_question(client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch) -> None:
    as_admin(client)
    run_agents(tmp_path)
    calls: list = []
    laya_answers(agent, monkeypatch, {"type": "noul", "noul": 0.82, "answer_confidence": 0.82, "uncertain": True}, calls)

    found = client.post(ASK, json={**YES_NO, "trace": True}).json()

    assert found == {"kind": "yes_no", "answer": "yes", "yes": 0.82, "confidence": 0.82, "uncertain": True}
    spec = calls[0]["request"]["questions"]["q"]
    assert spec["type"] == "noul" and spec["instructions"] == "Is there a problem?"
    assert calls[0]["request"]["trace"] is True


def test_a_score_question_sends_its_levels_lowest_first_and_returns_the_score(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_agents(tmp_path)
    calls: list = []
    laya_answers(agent, monkeypatch, {
        "type": "score", "score": 1.23456, "legend": {"0": "Can wait", "1": "Soon", "2": "Right now"},
        "answer_confidence": 0.7, "uncertain": False,
    }, calls)

    found = client.post(ASK, json=SCORE).json()

    assert found == {
        "kind": "score", "score": 1.2346, "levels": ["Can wait", "Soon", "Right now"],
        "confidence": 0.7, "uncertain": False,
    }
    assert calls[0]["request"]["questions"]["q"] == {
        "type": "score", "instructions": "How urgent is this?", "criteria": ["Can wait", "Soon", "Right now"],
    }


def test_an_unknown_choice_keeps_its_candidates(client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch) -> None:
    as_admin(client)
    run_agents(tmp_path)
    laya_answers(agent, monkeypatch, {
        "type": "choice", "choice": "database", "probabilities": {"database": 0.5, "network": 0.5},
        "answer_confidence": 0.5, "uncertain": True, "unknown": True, "candidates": ["database", "network"],
        "also_check": ["network"], "answered_by": "laya-english+jev",
    })

    found = client.post(ASK, json=CHOICE).json()

    assert found["unknown"] is True and found["candidates"] == ["database", "network"]
    assert found["also_check"] == ["network"] and found["answered_by"] == "laya-english+jev"


def test_ask_is_unavailable_without_laya(client: TestClient, tmp_path: Path) -> None:
    as_admin(client)
    run_agents(tmp_path, laya=False)

    assert client.post(ASK, json=YES_NO).status_code == 503


def test_laya_refusing_the_text_is_a_422_and_other_failures_a_503(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_agents(tmp_path)

    async def too_long(*_args, **_kwargs):
        raise AgentCallError("Laya could not read the complete input")

    monkeypatch.setattr(agent, "ask", too_long)
    assert client.post(ASK, json=YES_NO).status_code == 422

    async def down(*_args, **_kwargs):
        raise AgentCallError("connection refused")

    monkeypatch.setattr(agent, "ask", down)
    assert client.post(ASK, json=YES_NO).status_code == 503


def test_an_answer_that_is_not_json_is_a_503(client: TestClient, agent: FakeAgent, tmp_path: Path) -> None:
    as_admin(client)
    run_agents(tmp_path)
    agent.answer = "Hello!"

    assert client.post(ASK, json=YES_NO).status_code == 503


def test_the_form_is_validated(client: TestClient, tmp_path: Path) -> None:
    as_admin(client)
    run_agents(tmp_path)

    one_option = {**CHOICE, "options": CHOICE["options"][:1]}
    repeated = {**CHOICE, "options": [CHOICE["options"][0], {**CHOICE["options"][1], "title": "Database"}]}
    bad_title = {**CHOICE, "options": [{"title": "two words", "description": "x"}, CHOICE["options"][1]]}
    yes_no_with_options = {**YES_NO, "options": CHOICE["options"]}
    for body in (one_option, repeated, bad_title, yes_no_with_options, {**YES_NO, "text": "  "}, {**YES_NO, "text": "x" * 4001},
                 {**YES_NO, "kind": "rank"}, {**YES_NO, "question": ""},
                 {**YES_NO, "kind": "score"}, {**SCORE, "levels": ["Only one"]}, {**SCORE, "levels": ["x"] * 11},
                 {**SCORE, "options": CHOICE["options"]}, {**YES_NO, "levels": SCORE["levels"]}, {**CHOICE, "levels": SCORE["levels"]}):
        assert client.post(ASK, json=body).status_code == 422, body


# -- accounting ----------------------------------------------------------------------------------------------
def usage_kinds(client: TestClient) -> list[str]:
    return [r["kind"] for r in client.get("/api/usage/records").json()]


def log_lines(client: TestClient, kind: str) -> list[str]:
    me = client.get("/api/auth/me").json()["id"]
    return [e["message"] for e in client.get(f"/api/logs/{kind}", params={"actor": me}).json()]


def test_titles_are_counted_in_usage_and_logged_without_the_descriptions(
    client: TestClient, agent: FakeAgent, tmp_path: Path
) -> None:
    as_admin(client)
    run_agents(tmp_path)
    agent.summary = '["storage", "network"]'

    client.post(TITLES, json={"descriptions": ["SQL and storage secret", "Connections"]})

    assert usage_kinds(client) == ["triage_titles"]
    assert log_lines(client, "action")[0] == "Wrote titles for 2 options"


def test_a_question_is_counted_in_usage_and_logged_without_its_text(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_agents(tmp_path)
    laya_answers(agent, monkeypatch, {"type": "noul", "noul": 0.2, "answer_confidence": 0.6, "uncertain": True})

    client.post(ASK, json=YES_NO)
    client.post(ASK, json={**YES_NO, "question": "Which area?"})

    rows = client.get("/api/usage/records").json()
    assert [r["kind"] for r in rows] == ["triage", "triage"]
    assert rows[0]["total_tokens"] == 370 and rows[0]["provider_id"] == "laya"
    lines = log_lines(client, "action")
    assert lines[:2] == ["Asked the Triage Assistant a yes or no question: no, uncertain"] * 2
    assert not any("SQLite" in line or "Which area" in line for line in lines)


def test_an_unavailable_agent_is_logged_as_an_error_and_costs_nothing(client: TestClient, tmp_path: Path) -> None:
    as_admin(client)
    run_agents(tmp_path, laya=False, titles=False)

    assert client.post(ASK, json=YES_NO).status_code == 503
    assert client.post(TITLES, json={"descriptions": ["a", "b"]}).status_code == 503

    assert usage_kinds(client) == []
    assert log_lines(client, "error") == [
        "the title-writer agent is not running",
        "the Triage Assistant is not running",
    ]


def test_the_usage_limit_blocks_both_routes(client_factory, agent: FakeAgent, tmp_path: Path, monkeypatch) -> None:
    client = as_admin(client_factory(usage=UsageSettings(six_hour_token_limit=100)))
    run_agents(tmp_path)
    laya_answers(agent, monkeypatch, {"type": "noul", "noul": 0.9, "answer_confidence": 0.9, "uncertain": False})
    assert client.post(ASK, json=YES_NO).status_code == 200  # 370 tokens: over the limit now

    asked = client.post(ASK, json=YES_NO)
    titled = client.post(TITLES, json={"descriptions": ["a", "b"]})

    assert asked.status_code == titled.status_code == 429
    assert "6-hour token limit" in asked.json()["detail"]
    assert agent.interprets == []
