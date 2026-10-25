"""The default Laya strategy (admin) and each account's own, forwarded to Garrison's /agents/triage-strategy."""

from __future__ import annotations

import json

import httpx

from tests.conftest import FakeAgent, FakeEmailSender, FakeUpstream
from tests.test_admin import login, make_member
from tests.test_registration import as_admin
from tests.test_triage import ASK, YES_NO, laya_answers, run_agents

NAMES = ["english-only", "typed-only", "auto"]
URL = "http://agent-a.internal/agents/triage-strategy"


class Garrison:
    """Garrison's /agents/triage-strategy: the stored default, and a service that offers NAMES."""

    def __init__(self, default: str | None = None, down: bool = False) -> None:
        self.default, self.down = default, down

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/agents/triage-strategy":
            return httpx.Response(404, json={"error": "no route"})
        if self.down:
            return httpx.Response(503, json={"error": "down"})
        if request.method == "PUT":
            value = json.loads(request.content)["strategy"]
            if value is not None and value not in NAMES:
                return httpx.Response(400, json={"error": f"unknown strategy {value!r}"})
            self.default = value
        return httpx.Response(200, json={"default": self.default, "strategies": NAMES})


# -- admin default ------------------------------------------------------------------------------------------
def test_admin_reads_and_sets_the_default(client, upstream: FakeUpstream) -> None:
    upstream.handler = Garrison()
    as_admin(client)

    assert client.get("/api/admin/triage-strategy").json() == {"default": None, "strategies": NAMES}
    saved = client.put("/api/admin/triage-strategy", json={"value": "typed-only"})
    assert (saved.status_code, saved.json()["default"]) == (200, "typed-only")
    assert str(upstream.requests[-1].url) == URL
    assert json.loads(upstream.requests[-1].content) == {"strategy": "typed-only"}
    assert client.put("/api/admin/triage-strategy", json={"value": None}).json()["default"] is None


def test_admin_default_errors_pass_through(client, upstream: FakeUpstream) -> None:
    upstream.handler = Garrison()
    as_admin(client)

    assert client.put("/api/admin/triage-strategy", json={"value": "nope"}).status_code == 400
    assert client.put("/api/admin/triage-strategy", json={}).status_code == 422
    upstream.handler = Garrison(down=True)
    assert client.get("/api/admin/triage-strategy").status_code == 502


def test_only_settings_managers_touch_the_admin_default(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = Garrison()
    assert client.get("/api/admin/triage-strategy").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")
    assert client.get("/api/admin/triage-strategy").status_code == 403
    assert client.put("/api/admin/triage-strategy", json={"value": "auto"}).status_code == 403


# -- an account's own ---------------------------------------------------------------------------------------
def test_an_account_starts_on_the_default_and_picks_its_own(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = Garrison(default="auto")
    assert client.get("/api/account/triage-strategy").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")

    assert client.get("/api/account/triage-strategy").json() == {"value": None, "default": "auto", "strategies": NAMES}
    assert client.put("/api/account/triage-strategy", json={"value": "typed-only"}).json()["value"] == "typed-only"
    assert client.get("/api/account/triage-strategy").json()["value"] == "typed-only"
    assert client.put("/api/account/triage-strategy", json={"value": None}).json()["value"] is None


def test_an_account_cannot_pick_an_unknown_strategy(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = Garrison()
    make_member(client, email, "alice")
    login(client, "alice")

    refused = client.put("/api/account/triage-strategy", json={"value": "nope"})
    assert refused.status_code == 422 and "english-only" in refused.json()["detail"]
    assert client.get("/api/account/triage-strategy").json()["value"] is None


def test_while_garrison_is_down_the_account_can_read_and_clear_but_not_pick(
    client, upstream: FakeUpstream, email: FakeEmailSender
) -> None:
    upstream.handler = Garrison()
    make_member(client, email, "alice")
    login(client, "alice")
    client.put("/api/account/triage-strategy", json={"value": "typed-only"})

    upstream.handler = Garrison(down=True)
    assert client.get("/api/account/triage-strategy").json() == {"value": "typed-only", "default": None, "strategies": []}
    assert client.put("/api/account/triage-strategy", json={"value": "auto"}).status_code == 503
    assert client.put("/api/account/triage-strategy", json={"value": None}).json()["value"] is None


# -- the Laya request ---------------------------------------------------------------------------------------
def test_ask_sends_the_account_strategy_only_when_it_has_one(
    client, upstream: FakeUpstream, agent: FakeAgent, monkeypatch, tmp_path, email: FakeEmailSender
) -> None:
    upstream.handler = Garrison()
    run_agents(tmp_path)
    calls: list[dict] = []
    laya_answers(agent, monkeypatch, {"type": "noul", "noul": 0.9, "answer_confidence": 0.9, "uncertain": False}, calls)
    make_member(client, email, "alice")
    login(client, "alice")

    assert client.post(ASK, json=YES_NO).status_code == 200
    assert "strategy" not in calls[-1]["request"]
    client.put("/api/account/triage-strategy", json={"value": "typed-only"})
    assert client.post(ASK, json=YES_NO).status_code == 200
    assert calls[-1]["request"]["strategy"] == "typed-only"


def test_default_changes_log_before_and_after(client, upstream):
    upstream.handler = Garrison()
    as_admin(client)
    actor = client.get("/api/auth/me").json()["id"]
    assert client.put("/api/admin/triage-strategy", json={"value": "typed-only"}).status_code == 200
    assert client.put("/api/admin/triage-strategy", json={"value": None}).status_code == 200
    entries = client.get("/api/logs/action", params={"actor": actor}).json()
    assert [entry["message"] for entry in entries if entry["source"] == "triage_strategy.default"] == [
        "Default triage strategy: typed-only -> not set",
        "Default triage strategy: not set -> typed-only",
    ]


def test_an_empty_service_list_refuses_picks_with_503_but_allows_clearing(client, upstream):
    upstream.handler = lambda request: httpx.Response(200, json={"default": "auto", "strategies": []})
    as_admin(client)
    assert client.put("/api/account/triage-strategy", json={"value": "typed-only"}).status_code == 503
    assert client.put("/api/account/triage-strategy", json={"value": None}).status_code == 200


def test_a_stale_account_choice_is_reported_as_422_without_silent_fallback(client, upstream, agent, tmp_path):
    upstream.handler = Garrison()
    as_admin(client)
    run_agents(tmp_path)
    assert client.put("/api/account/triage-strategy", json={"value": "typed-only"}).status_code == 200
    agent.fail = "Invalid Laya request: unknown strategy 'typed-only'; choose one of: auto"
    response = client.post(ASK, json=YES_NO)
    assert response.status_code == 422
    assert response.json()["detail"] == agent.fail
    assert client.get("/api/account/triage-strategy").json()["value"] == "typed-only"
