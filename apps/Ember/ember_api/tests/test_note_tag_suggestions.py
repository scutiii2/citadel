"""POST /api/notes/suggest-tags: Laya checks which existing tags fit a note (FakeAgent here)."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.services.agent_gateway import AgentCallError
from src.services.tag_suggestions import BATCH, MAX_CANDIDATES
from tests.conftest import AGENTS, FakeAgent, FakeEmailSender
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/notes/suggest-tags"
LAYA_URL = "http://laya.internal/mcp"


def run_laya(tmp_path: Path) -> None:
    """Registers a running Laya agent, as ai_agent's registry and definitions files would."""
    laya = {"id": "triage-assistant", "label": "Triage Assistant", "url": LAYA_URL}
    (tmp_path / "config_agents.json").write_text(json.dumps({"agents": [*AGENTS, laya]}), encoding="utf-8")
    defined = [{"id": "triage-assistant", "label": "Triage Assistant", "llm": {"provider": "laya"}}]
    (tmp_path / "agent_definitions.json").write_text(json.dumps({"defined": defined}), encoding="utf-8")


def laya_says(agent: FakeAgent, monkeypatch, verdicts: dict[str, tuple[float, bool]], calls: list | None = None) -> None:
    """Laya answers each tag from `verdicts` (tag -> (yes probability, uncertain)); unknown tags: no, sure."""

    async def ask(url, caller, *, question, **kwargs):
        request = json.loads(question)
        if calls is not None:
            calls.append({"url": url, "caller": caller, "request": request, **kwargs})
        answers = {}
        for qid, spec in request["questions"].items():
            tag = re.search(r'"(.+)"', spec["instructions"]).group(1)
            yes, uncertain = verdicts.get(tag, (0.05, False))
            answers[qid] = {"type": "noul", "noul": yes, "answer_confidence": 0.5 if uncertain else 0.9, "uncertain": uncertain}
        return {"response": json.dumps({"answers": answers, "uncertain": False})}

    monkeypatch.setattr(agent, "ask", ask)


def tag_notes(client: TestClient, *tag_lists: list[str]) -> None:
    for i, tags in enumerate(tag_lists):
        assert client.post("/api/notes", json={"title": f"n{i}", "tags": tags}).status_code == 201


def test_needs_login(client: TestClient) -> None:
    assert client.post(URL, json={"title": "x"}).status_code == 401


def test_unverified_account_is_refused(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email, "alice", verify=False)
    login(client, "alice")

    assert client.post(URL, json={"title": "x"}).status_code == 403


def test_suggests_only_confident_yes_answers_best_first(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work", "home", "money", "travel"], ["work"], ["home"], ["work"])
    laya_says(agent, monkeypatch, {"work": (0.8, False), "home": (0.95, False), "money": (0.9, True), "travel": (0.3, False)})

    found = client.post(URL, json={"title": "Fix the roof", "body": "call the builder"}).json()

    # "money" is a yes but uncertain, "travel" is a no: both left out.
    assert found == {"suggested": ["home", "work"], "checked": 4, "skipped": 0}


def test_asks_laya_about_tags_not_yet_on_the_note_and_sends_the_text_and_identity(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work", "home", "money"])
    calls: list = []
    laya_says(agent, monkeypatch, {}, calls)

    client.post(URL, json={"title": "Budget", "body": "rent", "tags": [" Work "]})

    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == LAYA_URL
    assert call["caller"].username == "root"
    assert call["history"] == [] and call["enabled_extensions"] == [] and call["caveman"] is False
    assert call["request"]["text"] == "Budget\nrent"
    asked = [re.search(r'"(.+)"', q["instructions"]).group(1) for q in call["request"]["questions"].values()]
    assert sorted(asked) == ["home", "money"]
    assert {q["type"] for q in call["request"]["questions"].values()} == {"noul"}
    assert call["request"]["local_only"] is True  # Laya answers alone: no fallback to Jev


def test_no_existing_tags_means_no_call(client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch) -> None:
    as_admin(client)
    run_laya(tmp_path)
    calls: list = []
    laya_says(agent, monkeypatch, {}, calls)

    found = client.post(URL, json={"title": "Budget"})

    assert found.json() == {"suggested": [], "checked": 0, "skipped": 0}
    assert calls == []


def test_an_empty_note_means_no_call(client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work"])
    calls: list = []
    laya_says(agent, monkeypatch, {}, calls)

    assert client.post(URL, json={"title": "  ", "body": ""}).json() == {"suggested": [], "checked": 0, "skipped": 0}
    assert calls == []


def test_only_the_most_used_tags_are_checked_in_small_batches(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tags = [f"t{i:02d}" for i in range(12)]
    # t00 is used most, then t01 ...: usage counts 12, 11, ... 1.
    tag_notes(client, *[[tag] for i, tag in enumerate(tags) for _ in range(12 - i)])
    calls: list = []
    laya_says(agent, monkeypatch, {"t00": (0.9, False), "t11": (0.9, False)}, calls)

    found = client.post(URL, json={"title": "x"}).json()

    assert len(calls) == MAX_CANDIDATES // BATCH
    assert all(len(c["request"]["questions"]) <= BATCH for c in calls)
    assert found == {"suggested": ["t00"], "checked": MAX_CANDIDATES, "skipped": 4}  # t11 is past the cap


def test_text_is_cut_to_a_short_excerpt(client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work"])
    calls: list = []
    laya_says(agent, monkeypatch, {}, calls)

    client.post(URL, json={"title": "T", "body": "x" * 5000})

    assert len(calls[0]["request"]["text"]) == 700


def test_a_batch_laya_finds_too_long_is_asked_one_tag_at_a_time(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["a", "b", "c"])
    seen: list[int] = []

    async def ask(url, caller, *, question, **kwargs):
        request = json.loads(question)
        seen.append(len(request["questions"]))
        if len(request["questions"]) > 1:
            raise AgentCallError("Invalid ... Laya could not read the complete input. Send a shorter text")
        qid = next(iter(request["questions"]))
        answer = {"type": "noul", "noul": 0.9, "answer_confidence": 0.9, "uncertain": False}
        return {"response": json.dumps({"answers": {qid: answer}})}

    monkeypatch.setattr(agent, "ask", ask)

    found = client.post(URL, json={"title": "x"}).json()

    assert seen == [3, 1, 1, 1]
    assert sorted(found["suggested"]) == ["a", "b", "c"] and found["checked"] == 3 and found["skipped"] == 0


def test_one_tag_that_is_still_too_long_is_skipped_not_fatal(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["a"])

    async def ask(url, caller, *, question, **kwargs):
        raise AgentCallError("Laya could not read the complete input")

    monkeypatch.setattr(agent, "ask", ask)

    assert client.post(URL, json={"title": "x"}).json() == {"suggested": [], "checked": 0, "skipped": 1}


def test_laya_agent_not_running_is_503(client: TestClient, tmp_path: Path) -> None:
    as_admin(client)
    tag_notes(client, ["work"])

    response = client.post(URL, json={"title": "x"})

    assert response.status_code == 503
    assert "Laya agent is not running" in response.json()["detail"]


def test_a_defined_but_stopped_laya_agent_is_not_running(client: TestClient, tmp_path: Path) -> None:
    as_admin(client)
    tag_notes(client, ["work"])
    run_laya(tmp_path)
    (tmp_path / "config_agents.json").write_text(json.dumps({"agents": AGENTS}), encoding="utf-8")  # not registered

    assert client.post(URL, json={"title": "x"}).status_code == 503


def test_an_agent_error_is_503_and_nothing_else_breaks(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work"])

    async def ask(*args, **kwargs):
        raise AgentCallError("Could not reach the agent: refused")

    monkeypatch.setattr(agent, "ask", ask)

    response = client.post(URL, json={"title": "x"})

    assert response.status_code == 503
    assert "Laya did not answer" in response.json()["detail"]
    assert client.get("/api/notes").status_code == 200


def test_a_laya_that_takes_too_long_is_503(
    client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch
) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work"])
    monkeypatch.setattr("src.services.tag_suggestions.TIME_LIMIT", 0.05)

    async def ask(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(agent, "ask", ask)

    response = client.post(URL, json={"title": "x"})

    assert response.status_code == 503
    assert "Laya took too long" in response.json()["detail"]


@pytest.mark.parametrize("reply", ["not json", "{}", '{"answers": {"q0": {"noul": "yes"}}}', '{"answers": {"q0": {"noul": 0.9}}}'])
def test_an_unreadable_answer_is_503(client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch, reply: str) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work"])

    async def ask(*args, **kwargs):
        return {"response": reply}

    monkeypatch.setattr(agent, "ask", ask)

    assert client.post(URL, json={"title": "x"}).status_code == 503


def test_suggestions_use_only_the_accounts_own_tags(
    client: TestClient, agent: FakeAgent, tmp_path: Path, email: FakeEmailSender, monkeypatch
) -> None:
    make_member(client, email, "alice")
    make_member(client, email, "bob")
    run_laya(tmp_path)
    login(client, "alice")
    tag_notes(client, ["alice-tag"])
    client.post("/api/auth/logout", json={})
    login(client, "bob")
    calls: list = []
    laya_says(agent, monkeypatch, {}, calls)

    found = client.post(URL, json={"title": "x"}).json()

    assert found == {"suggested": [], "checked": 0, "skipped": 0}
    assert calls == []  # bob has no tags, and alice's are not his to see


def test_the_text_is_not_logged_or_stored(client: TestClient, agent: FakeAgent, tmp_path: Path, monkeypatch) -> None:
    as_admin(client)
    run_laya(tmp_path)
    tag_notes(client, ["work"])
    laya_says(agent, monkeypatch, {"work": (0.9, False)})

    client.post(URL, json={"title": "very private title", "body": "very private body"})

    root = client.get("/api/auth/me").json()["id"]
    assert "very private" not in str(client.get("/api/logs/action", params={"actor": str(root)}).json())
