"""/usage: rows, the 6-hour and weekly limits, reports, and the administrators' totals."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from src.document_store import DbGatewayUnavailable
from src.usage import routes as usage_routes
from src.usage import service as usage_service
from src.usage.settings import PricingSettings, UsageSettings
from tests.conftest import AGENTS, IDENTITY, FakeDbGateway
from tests.helpers import login, uid_of

NOW = datetime(2026, 3, 15, 10, 0, 0)


class Clock:
    """What the usage code reads as "now" (naive UTC)."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(usage_service, "utcnow", clock)
    monkeypatch.setattr(usage_routes, "utcnow", clock)
    return clock


def row(tokens: int = 100, **extra) -> dict:
    return {"agent": "claude", "provider_id": "claude", "model": "m", "total_tokens": tokens, **extra}


def record(client: TestClient, rows: list[dict], turn: str = "t1", kind: str = "chat", chat_id: str | None = "c1"):
    return client.post("/usage/records", json={"turn_id": turn, "kind": kind, "chat_id": chat_id, "rows": rows})


def report(client: TestClient, **params) -> dict:
    response = client.get("/usage", params=params)
    assert response.status_code == 200, response.text
    return response.json()["report"]


# --- recording and reporting ---------------------------------------------------


def test_usage_needs_the_requester_identity(client: TestClient) -> None:
    assert client.get("/usage", headers={"X-Requester-Uid": ""}).status_code == 400
    assert record(client, [row()], ).status_code == 201


def test_a_turn_is_recorded_and_reported(client: TestClient, clock: Clock) -> None:
    assert record(client, [row(100, input_tokens=60, output_tokens=40)]).json() == {"total": 100}

    usage = client.get("/usage").json()

    assert usage["six_hour"]["used"] == 100 and usage["weekly"]["limit"] == 5_000_000
    r = usage["report"]
    assert (r["total_tokens"], r["turns"], r["chats"], r["input_tokens"], r["output_tokens"]) == (100, 1, 1, 60, 40)
    assert r["by_agent"] == [{"agent": "claude", "model": "m", "tokens": 100, "cost": None}]
    assert r["daily"] == [{"date": "2026-03-15", "tokens": 100}]
    assert r["unpriced_tokens"] == 100 and r["total_cost"] is None


def test_each_agent_of_a_turn_counts_separately_but_the_turn_counts_once(client: TestClient, clock: Clock) -> None:
    record(client, [row(100), row(50, agent="openai", provider_id="openai")])

    r = report(client)

    assert (r["total_tokens"], r["turns"]) == (150, 1)
    assert {a["agent"] for a in r["by_agent"]} == {"claude", "openai"}


def test_summaries_count_as_tokens_but_not_as_turns(client: TestClient, clock: Clock) -> None:
    record(client, [row(100)])
    record(client, [row(10, agent="context-summarizer")], turn="t2", kind="summary")

    r = report(client)

    assert (r["total_tokens"], r["summary_tokens"], r["turns"]) == (110, 10, 1)


def test_the_account_sees_only_its_own_usage(client: TestClient, clock: Clock) -> None:
    record(client, [row(100)])
    login(client, "bob")

    assert report(client)["total_tokens"] == 0
    assert client.get("/usage/records").json() == []


@pytest.mark.parametrize("body", [
    {"turn_id": "", "rows": []}, {"rows": []}, {"turn_id": "t", "rows": [{"total_tokens": 0}]},
    {"turn_id": "t", "rows": [{"total_tokens": -5}]}, {"turn_id": "t", "rows": [{"total_tokens": 1, "agent": "x" * 121}]},
    {"turn_id": "t" * 65, "rows": []}, {"turn_id": "t", "kind": "k" * 21, "rows": []},
])
def test_bad_rows_are_refused(client: TestClient, db_gateway: FakeDbGateway, body: dict) -> None:
    assert client.post("/usage/records", json=body).status_code == 422
    assert db_gateway.records == {}


def test_an_empty_turn_records_nothing(client: TestClient, db_gateway: FakeDbGateway) -> None:
    assert record(client, []).json() == {"total": 0}
    assert db_gateway.records == {}


# --- limits ----------------------------------------------------------------------


def test_the_six_hour_limit_blocks_until_the_oldest_tokens_age_out(make_client, clock: Clock) -> None:
    client = make_client(usage=UsageSettings(six_hour_token_limit=100, weekly_token_limit=0))
    assert client.post("/usage/check").json() == {"block": None}
    record(client, [row(100)])

    block = client.post("/usage/check").json()["block"]

    assert block["reason"] == "6-hour token limit reached"
    assert datetime.fromisoformat(block["reset_at"]) == NOW + timedelta(hours=6)
    clock.now = NOW + timedelta(hours=6, minutes=1)
    assert client.post("/usage/check").json() == {"block": None}


def test_the_weekly_limit_is_the_backstop(make_client, clock: Clock) -> None:
    client = make_client(usage=UsageSettings(six_hour_token_limit=0, weekly_token_limit=100))
    record(client, [row(100)])
    clock.now = NOW + timedelta(days=2)

    block = client.post("/usage/check").json()["block"]

    assert block["reason"] == "weekly token limit reached"
    assert datetime.fromisoformat(block["reset_at"]) == NOW + timedelta(days=7)


def test_zero_means_unlimited(make_client, clock: Clock) -> None:
    client = make_client(usage=UsageSettings(six_hour_token_limit=0, weekly_token_limit=0))
    record(client, [row(10_000_000)])

    assert client.post("/usage/check").json() == {"block": None}


def test_windows_report_used_limit_and_reset(client: TestClient, clock: Clock) -> None:
    record(client, [row(30)])
    clock.now = NOW + timedelta(hours=7)
    record(client, [row(20)], turn="t2")

    usage = client.get("/usage").json()

    assert (usage["six_hour"]["used"], usage["weekly"]["used"]) == (20, 50)
    assert datetime.fromisoformat(usage["weekly"]["reset_at"]) == NOW + timedelta(days=7)
    assert datetime.fromisoformat(usage["six_hour"]["reset_at"]) == clock.now + timedelta(hours=6)


def test_a_day_with_more_rows_than_one_page_is_read_in_full(client: TestClient, clock: Clock, monkeypatch) -> None:
    monkeypatch.setattr(usage_service, "_PAGE", 3)
    record(client, [row(1) for _ in range(8)])

    assert client.get("/usage").json()["six_hour"]["used"] == 8


# --- reports ---------------------------------------------------------------------


def test_report_covers_the_period_asked_for(client: TestClient, clock: Clock) -> None:
    clock.now = NOW - timedelta(days=10)
    record(client, [row(7)], turn="old")
    clock.now = NOW
    record(client, [row(3)], turn="new")

    assert report(client, days=30)["total_tokens"] == 10
    assert report(client, days=5)["total_tokens"] == 3


def test_since_starts_at_midnight_of_that_utc_day(client: TestClient, clock: Clock) -> None:
    clock.now = datetime(2026, 3, 1, 0, 0, 1)
    record(client, [row(5)], turn="first")
    clock.now = datetime(2026, 2, 28, 23, 59, 59)
    record(client, [row(9)], turn="before")
    clock.now = NOW

    r = report(client, since="2026-03-01")

    assert r["total_tokens"] == 5 and r["days"] == 15
    assert r["since"].startswith("2026-03-01T00:00:00")


@pytest.mark.parametrize("since", ["2026-03-16", "2025-01-01"])
def test_since_must_be_recent_and_not_in_the_future(client: TestClient, clock: Clock, since: str) -> None:
    assert client.get("/usage", params={"since": since}).status_code == 422
    assert client.get("/usage/records", params={"since": since}).status_code == 422
    assert client.get("/usage/all", params={"since": since}).status_code == 422


@pytest.mark.parametrize("params", [{"days": 0}, {"days": 367}, {"group_by": "nope"}, {"limit": 0}])
def test_bad_query_values_are_422(client: TestClient, clock: Clock, params: dict) -> None:
    assert client.get("/usage", params=params).status_code == 422 or client.get("/usage/records", params=params).status_code == 422


def test_hourly_is_24_buckets_of_tokens_by_utc_hour(client: TestClient, clock: Clock) -> None:
    assert report(client)["hourly"] == [0] * 24
    clock.now = datetime(2026, 3, 14, 9, 30)
    record(client, [row(40)], turn="a")
    clock.now = datetime(2026, 3, 15, 9, 5)
    record(client, [row(60)], turn="b")
    clock.now = NOW

    hourly = report(client)["hourly"]

    assert len(hourly) == 24 and hourly[9] == 100 and sum(hourly) == 100


def test_group_by_and_filters(client: TestClient, clock: Clock) -> None:
    record(client, [row(100, gateway="g1", model="a"), row(50, agent="openai", provider_id="openai", gateway="g2", model="b")])

    by_provider = report(client, group_by="provider")
    assert [(g["key"], g["tokens"]) for g in by_provider["groups"]] == [("claude", 100), ("openai", 50)]
    assert [g["key"] for g in report(client, group_by="gateway")["groups"]] == ["g1", "g2"]
    assert [g["key"] for g in report(client, group_by="model")["groups"]] == ["a", "b"]
    assert report(client, agent="openai")["total_tokens"] == 50
    assert report(client, provider="claude")["total_tokens"] == 100
    assert [g["key"] for g in report(client, agent="nobody")["groups"]] == []


def test_a_row_without_names_is_grouped_as_unknown(client: TestClient, clock: Clock) -> None:
    record(client, [{"total_tokens": 5}])

    assert report(client)["groups"][0]["key"] == "unknown"
    assert report(client)["by_agent"][0]["agent"] == "unknown"


def test_cost_comes_from_the_configured_price_at_read_time(make_client, clock: Clock) -> None:
    pricing = PricingSettings.from_config({"models": {"M": {"input": 2.0, "output": 10.0}}})
    client = make_client(pricing=pricing)
    record(client, [row(1_500_000, model="m", input_tokens=1_000_000, output_tokens=500_000), row(5, model="free")])

    r = report(client)

    assert r["total_cost"] == pytest.approx(7.0) and r["currency"] == "USD"
    assert r["unpriced_tokens"] == 5
    assert r["by_agent"][0]["cost"] == pytest.approx(7.0)
    costs = {r["model"]: r["cost"] for r in client.get("/usage/records").json()}
    assert costs == {"m": pytest.approx(7.0), "free": None}


# --- records ---------------------------------------------------------------------


def test_records_are_newest_first_with_the_detail_of_each_call(client: TestClient, clock: Clock) -> None:
    record(client, [row(10, agent_id="a1", gateway="g", started_at="2026-03-15T09:59:00", finished_at="2026-03-15T09:59:30",
                        delegated_by="boss")], turn="old", kind="chat")
    clock.now = NOW + timedelta(minutes=1)
    record(client, [row(20)], turn="new", kind="suggestion", chat_id=None)

    rows = client.get("/usage/records").json()

    assert [r["turn_id"] for r in rows] == ["new", "old"]
    assert rows[0]["kind"] == "suggestion" and rows[0]["chat_id"] is None and isinstance(rows[0]["id"], int)
    old = rows[1]
    assert (old["agent_id"], old["gateway"], old["delegated_by"]) == ("a1", "g", "boss")
    assert (old["started_at"], old["finished_at"]) == ("2026-03-15T09:59:00", "2026-03-15T09:59:30")
    assert old["created_at"] == "2026-03-15T10:00:00"
    assert len({r["id"] for r in rows}) == 2


def test_records_respect_limit_and_filters(client: TestClient, clock: Clock) -> None:
    record(client, [row(1), row(2, agent="openai", provider_id="openai"), row(3)])

    assert len(client.get("/usage/records", params={"limit": 2}).json()) == 2
    assert [r["total_tokens"] for r in client.get("/usage/records", params={"agent": "openai"}).json()] == [2]
    assert len(client.get("/usage/records", params={"provider": "claude"}).json()) == 2


# --- every account ---------------------------------------------------------------


def test_all_totals_list_each_account_with_usage_busiest_first(client: TestClient, clock: Clock) -> None:
    login(client, "alice")
    record(client, [row(10)], turn="a1")
    clock.now = NOW + timedelta(minutes=5)
    record(client, [row(5, agent="context-summarizer")], turn="a2", kind="summary")
    login(client, "bob")
    record(client, [row(40)], turn="b1")
    record(client, [row(40)], turn="b2")

    totals = client.get("/usage/all").json()

    assert [(t["uid"], t["tokens"], t["turns"]) for t in totals] == [(uid_of("bob"), 80, 2), (uid_of("alice"), 15, 1)]
    assert totals[1]["last_used_at"] == "2026-03-15T10:05:00"


# --- account deletion --------------------------------------------------------------


def test_purging_an_account_removes_only_its_rows(client: TestClient, clock: Clock, db_gateway: FakeDbGateway) -> None:
    login(client, "alice")
    record(client, [row(1), row(2)])
    login(client, "bob")
    record(client, [row(4)])

    assert client.delete(f"/usage/accounts/{uid_of('alice')}").status_code == 204

    assert [doc["owner"] for doc in db_gateway.records.values()] == [uid_of("bob")]
    assert client.delete("/usage/accounts/has%20space").status_code == 422


def test_purging_a_large_account_takes_every_page(client: TestClient, clock: Clock, db_gateway: FakeDbGateway, monkeypatch) -> None:
    monkeypatch.setattr(usage_service, "_PAGE", 2)
    record(client, [row(1) for _ in range(7)])

    assert client.delete(f"/usage/accounts/{IDENTITY['X-Requester-Uid']}").status_code == 204

    assert db_gateway.records == {}


def test_storage_down_gives_503(client: TestClient, clock: Clock, db_gateway: FakeDbGateway, monkeypatch) -> None:
    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("db_gateway is not reachable")

    for method in ("get", "put", "create", "delete", "query"):
        monkeypatch.setattr(db_gateway, method, down)

    assert client.post("/usage/check").status_code == 503
    assert client.get("/usage").status_code == 503
    assert record(client, [row()]).status_code == 503
