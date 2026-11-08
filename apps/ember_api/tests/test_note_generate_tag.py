"""POST /api/notes/generate-tag: the tag-writer agent proposes up to three new tags (FakeAgent here)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.services.tag_writer import MAX_NEW, parse_tags
from tests.conftest import AGENTS, FakeAgent, FakeEmailSender
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/notes/generate-tag"
WRITER_URL = "http://tags.internal/mcp"


def run_writer(tmp_path: Path) -> None:
    """Registers a running tag-writer agent, as ai_agent's registry and definitions files would."""
    writer = {"id": "tag-writer", "label": "Tag Writer", "url": WRITER_URL}
    (tmp_path / "config_agents.json").write_text(json.dumps({"agents": [*AGENTS, writer]}), encoding="utf-8")
    defined = [{"id": "tag-writer", "label": "Tag Writer", "llm": {"provider": "anthropic"}}]
    (tmp_path / "agent_definitions.json").write_text(json.dumps({"defined": defined}), encoding="utf-8")


def tag_notes(client: TestClient, *tag_lists: list[str]) -> None:
    for i, tags in enumerate(tag_lists):
        assert client.post("/api/notes", json={"title": f"n{i}", "tags": tags}).status_code == 201


# -- parsing ---------------------------------------------------------------------------------------------
def test_parse_cleans_tags_and_drops_repeats_and_excluded_ones() -> None:
    reply = '```json\n["Home Repair", "work", "home-repair", "  ", 7, "Roof!"]\n```'

    assert parse_tags(reply, {"work"}) == ["home-repair", "roof"]


def test_parse_keeps_at_most_three() -> None:
    assert parse_tags('["a", "b", "c", "d", "e"]', set()) == ["a", "b", "c"] and MAX_NEW == 3


@pytest.mark.parametrize("reply", ["sorry, no", "", "{}", "[1, 2]", "[]"])
def test_parse_gives_no_tags_for_an_unusable_reply(reply: str) -> None:
    assert parse_tags(reply, set()) == []


# -- route -----------------------------------------------------------------------------------------------
def test_needs_login(client: TestClient) -> None:
    assert client.post(URL, json={"title": "x"}).status_code == 401


def test_unverified_account_is_refused(client: TestClient, email: FakeEmailSender) -> None:
    make_member(client, email, "alice", verify=False)
    login(client, "alice")

    assert client.post(URL, json={"title": "x"}).status_code == 403


def test_returns_up_to_three_new_tags_without_existing_ones(client: TestClient, agent: FakeAgent, tmp_path: Path) -> None:
    as_admin(client)
    run_writer(tmp_path)
    tag_notes(client, ["work", "home"])
    agent.summary = '["Work", "roofing", "budget", "quotes", "extra"]'

    response = client.post(URL, json={"title": "Fix the roof", "body": "call the builder", "tags": ["quotes"]})

    assert response.json() == {"tags": ["roofing", "budget", "extra"]}


def test_the_agent_sees_the_note_and_the_existing_tags(client: TestClient, agent: FakeAgent, tmp_path: Path) -> None:
    as_admin(client)
    run_writer(tmp_path)
    tag_notes(client, ["work"], ["work"], ["home"])
    agent.summary = "[]"

    client.post(URL, json={"title": "Budget", "body": "rent due"})

    assert len(agent.interprets) == 1
    sent = agent.interprets[0]
    assert "Existing tags: work, home" in sent and "Budget\nrent due" in sent


def test_the_text_is_cut_to_an_excerpt(client: TestClient, agent: FakeAgent, tmp_path: Path) -> None:
    as_admin(client)
    run_writer(tmp_path)
    agent.summary = "[]"

    client.post(URL, json={"title": "T", "body": "x" * 5000})

    assert "x" * 1500 not in agent.interprets[0] and "x" * 1400 in agent.interprets[0]


def test_an_empty_note_means_no_call(client: TestClient, agent: FakeAgent, tmp_path: Path) -> None:
    as_admin(client)
    run_writer(tmp_path)

    assert client.post(URL, json={"title": "  ", "body": ""}).json() == {"tags": []}
    assert agent.interprets == []


def test_an_unusable_reply_gives_no_tags(client: TestClient, agent: FakeAgent, tmp_path: Path) -> None:
    as_admin(client)
    run_writer(tmp_path)
    agent.summary = "I cannot help with that"

    assert client.post(URL, json={"title": "x"}).json() == {"tags": []}


def test_agent_not_running_is_503(client: TestClient) -> None:
    as_admin(client)

    response = client.post(URL, json={"title": "x"})

    assert response.status_code == 503
    assert "tag-writer agent is not running" in response.json()["detail"]


def test_an_agent_error_is_503(client: TestClient, agent: FakeAgent, tmp_path: Path) -> None:
    as_admin(client)
    run_writer(tmp_path)
    agent.fail = "Could not reach the agent: refused"

    response = client.post(URL, json={"title": "x"})

    assert response.status_code == 503
    assert "tag-writer agent did not answer" in response.json()["detail"]
    assert client.get("/api/notes").status_code == 200


def test_the_account_sees_only_its_own_tags(client: TestClient, agent: FakeAgent, tmp_path: Path, email: FakeEmailSender) -> None:
    make_member(client, email, "alice")
    make_member(client, email, "bob")
    run_writer(tmp_path)
    login(client, "alice")
    tag_notes(client, ["alice-tag"])
    client.post("/api/auth/logout", json={})
    login(client, "bob")
    agent.summary = "[]"

    client.post(URL, json={"title": "x"})

    assert "alice-tag" not in agent.interprets[0]
