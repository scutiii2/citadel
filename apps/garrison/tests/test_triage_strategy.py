"""The admin default strategy: what the /agents/triage-strategy routes do (llm/triage_strategy.py)."""

from __future__ import annotations

import pytest

from src import server
from src.core import tuning_overrides
from src.llm import triage_strategy
from src.llm.laya_agent import LayaServiceError
from tests.fake_laya import STRATEGIES, FakeService


@pytest.fixture(autouse=True)
def overlay(tmp_path, monkeypatch):
    path = tmp_path / "overrides.json"
    monkeypatch.setattr(tuning_overrides, "OVERRIDES_PATH", path)
    return path


def test_describe_reports_nothing_set_and_the_service_names():
    assert triage_strategy.describe(FakeService()) == {"default": None, "strategies": list(STRATEGIES)}


def test_update_saves_a_known_strategy_and_clearing_removes_it():
    service = FakeService()
    assert triage_strategy.update("typed-only", service)["default"] == "typed-only"
    assert tuning_overrides.triage_strategy() == "typed-only"
    assert triage_strategy.update(None, service)["default"] is None
    assert tuning_overrides.triage_strategy() is None


def test_update_refuses_an_unknown_name_and_keeps_the_old_one():
    service = FakeService()
    triage_strategy.update("average", service)
    with pytest.raises(triage_strategy.StrategyError) as refused:
        triage_strategy.update("nope", service)
    assert refused.value.status == 400 and "unknown strategy 'nope'" in str(refused.value)
    assert tuning_overrides.triage_strategy() == "average"


def test_describe_still_answers_when_the_service_is_down():
    service = FakeService()
    service.strategies = lambda: (_ for _ in ()).throw(LayaServiceError("down"))
    assert triage_strategy.describe(service) == {"default": None, "strategies": []}


def test_update_to_a_name_needs_the_service_but_clearing_does_not():
    service = FakeService()
    service.strategies = lambda: (_ for _ in ()).throw(LayaServiceError("down"))
    with pytest.raises(triage_strategy.StrategyError) as down:
        triage_strategy.update("average", service)
    assert down.value.status == 502
    assert triage_strategy.update(None, service)["default"] is None


@pytest.mark.parametrize("body, status", [(None, 400), ({}, 400), ({"strategy": 3}, 400),
                                        ({"strategy": "nope"}, 400), ({"strategy": "typed-only"}, 200),
                                        ({"strategy": None}, 200)])
def test_put_route_checks_the_body_and_returns_the_result(monkeypatch, body, status):
    import asyncio
    import json
    from unittest.mock import AsyncMock

    monkeypatch.setattr(triage_strategy.laya_agent, "agent", lambda: FakeService())
    response = asyncio.run(server.triage_strategy_put(AsyncMock(json=AsyncMock(return_value=body))))
    assert response.status_code == status
    result = json.loads(response.body)
    if status == 200:
        assert result == {"default": body["strategy"], "strategies": list(STRATEGIES)}
    else:
        assert "error" in result


def test_get_route_reports_the_default(monkeypatch):
    import asyncio
    import json

    monkeypatch.setattr(triage_strategy.laya_agent, "agent", lambda: FakeService())
    response = asyncio.run(server.triage_strategy_get(None))
    assert response.status_code == 200
    assert json.loads(response.body) == {"default": None, "strategies": list(STRATEGIES)}
