import json
import sqlite3

import pytest

from src.config import PricingSettings
from tests.test_chats import put
from tests.test_registration import as_admin
from tests.test_turns import events, new_id, start


@pytest.fixture
def priced(client_factory):
    client = client_factory(pricing=PricingSettings.from_config({
        "models": {"m1": {"input": 2, "output": 8}},
    }))
    as_admin(client)
    return client


def test_chat_costs_are_read_time_and_branch_is_priced(priced):
    chat_id = new_id()
    answer = {"role": "assistant", "content": "answer", "model": "m1",
              "input_tokens": 1000, "output_tokens": 250, "cost": 99,
              "agent_usage": [{"agent": "a", "model": "m1", "total_tokens": 1250,
                               "input_tokens": 1000, "output_tokens": 250, "cost": 99}]}
    assert put(priced, chat_id, messages=[{"role": "user", "content": "hi"}, answer]).status_code == 200
    message = priced.get(f"/api/chats/{chat_id}").json()["messages"][1]
    assert message["cost"] == 0.004
    assert message["agent_usage"][0]["cost"] == 0.004
    branch = priced.post(f"/api/chats/{chat_id}/branch", json={"upto": 1})
    assert branch.status_code == 201
    assert branch.json()["messages"][1]["cost"] == 0.004
    with sqlite3.connect(priced.app.state.settings.database_path) as db:
        stored = db.execute("select messages from chats").fetchall()
    assert stored and all('"cost"' not in row[0] for row in stored)


def test_report_records_and_stream_cost(client_factory, agent):
    # The shared Pricing must be constructed from the configured settings at startup.
    pricing = PricingSettings.from_config({"models": {"m1": {"input": 2, "output": 8}}})
    client = client_factory(pricing=pricing)
    as_admin(client)
    agent.result_extra = {"model": "m1", "input_tokens": 1000, "output_tokens": 250,
                          "total_tokens": 1350, "agent_usage": [
        {"agent_id": "a", "model": "m1", "input_tokens": 1000, "output_tokens": 250, "total_tokens": 1250},
        {"agent_id": "b", "model": "unknown", "input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
    ]}
    chat_id = new_id()
    assert start(client, chat_id).status_code == 202
    final = events(client, chat_id)[-1]
    assert final["type"] == "final"
    assert final["message"]["cost"] == 0.004
    assert final["message"]["agent_usage"][0]["cost"] == 0.004
    assert "cost" not in final["message"]["agent_usage"][1]
    report = client.get("/api/usage").json()["report"]
    assert report["total_cost"] == 0.004
    assert report["currency"] == "USD"
    assert report["unpriced_tokens"] == 100
    assert {r["key"]: r["cost"] for r in report["groups"]} == {"a": 0.004, "b": None}
    assert {r["agent"]: r["cost"] for r in report["by_agent"]} == {"a": 0.004, "b": None}
    rows = client.get("/api/usage/records").json()
    assert {r["model"]: r["cost"] for r in rows} == {"m1": 0.004, "unknown": None}
    assert client.get(f"/api/admin/usage/{client.get('/api/auth/me').json()['id']}/records").json() == rows
    with sqlite3.connect(client.app.state.settings.database_path) as db:
        raw = db.execute("select messages from chats where chat_id = ?", (chat_id,)).fetchone()[0]
    assert "cost" not in json.loads(raw)[1]
    assert '"cost"' not in raw


def test_all_unknown_and_empty_reports_have_no_cost(client, agent):
    as_admin(client)
    report = client.get("/api/usage").json()["report"]
    assert report["total_cost"] is None
    assert report["unpriced_tokens"] == 0
    chat_id = new_id()
    agent.result_extra = {"model": "unknown", "total_tokens": 10, "agent_usage": []}
    assert start(client, chat_id).status_code == 202
    assert "cost" not in events(client, chat_id)[-1]["message"]
    report = client.get("/api/usage").json()["report"]
    assert report["total_cost"] is None
    assert report["unpriced_tokens"] == 10
