import pytest

from src.mcp_tools.scope import Account
from src.mcp_tools.usage_tools import UsageTools
from src.usage.service import UsageService
from src.usage.settings import Pricing, PricingSettings, UsageSettings

ANA = Account("u-1", "ana", "ana@example.com")
BOB = Account("u-2", "bob", "bob@example.com")


def row(agent, model, total, input_tokens=None, output_tokens=None):
    return {"agent": agent, "agent_id": agent, "model": model, "total_tokens": total,
            "input_tokens": input_tokens if input_tokens is not None else total // 2,
            "output_tokens": output_tokens if output_tokens is not None else total - total // 2}


@pytest.fixture
async def world(db_gateway):
    usage = UsageService(db_gateway, UsageSettings(), Pricing(PricingSettings()))
    await usage.record("u-1", "t1", "chat", "c1", [row("ember", "m1", 100), row("researcher", "m2", 300)])
    await usage.record("u-1", "t2", "chat", "c1", [row("ember", "m1", 50)])
    await usage.record("u-2", "t3", "chat", "c2", [row("ember", "m1", 7000)])
    return UsageTools(usage)


async def test_the_summary_is_the_requesters_own_usage_largest_first(world):
    answer = await world.summary(ANA, 7, "agent")
    assert answer["ok"] is True and answer["total_tokens"] == 450 and answer["requests"] == 2
    assert [(r["key"], r["total_tokens"]) for r in answer["rows"]] == [("researcher", 300), ("ember", 150)]
    assert "your" in answer["message"].lower() and "7" in answer["message"]


async def test_another_account_never_sees_these_rows(world):
    answer = await world.summary(BOB, 7, "agent")
    assert answer["total_tokens"] == 7000 and [r["key"] for r in answer["rows"]] == ["ember"]


async def test_group_by_model_and_day(world):
    by_model = await world.summary(ANA, 7, "model")
    assert [(r["key"], r["total_tokens"]) for r in by_model["rows"]] == [("m2", 300), ("m1", 150)]
    by_day = await world.summary(ANA, 7, "day")
    assert len(by_day["rows"]) == 1 and by_day["rows"][0]["total_tokens"] == 450 and "key" in by_day["rows"][0]


async def test_a_bad_period_or_grouping_is_a_refusal_result(world):
    for days, group in ((0, "agent"), (91, "agent"), (7, "colour")):
        refused = await world.summary(ANA, days, group)
        assert refused["ok"] is False and refused["message"]
