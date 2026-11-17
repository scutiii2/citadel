import json

import pytest

from src import config
from src.services.pricing import Pricing, with_cost


@pytest.fixture
def pricing():
    return Pricing({"models": {"Model": {"input": 2, "output": 8}}})


@pytest.mark.parametrize(("model", "input_tokens", "output_tokens", "expected"), [
    ("Model", 1000, 250, 0.004),
    ("model", 1000, 250, 0.004),
    ("unknown", 1000, 250, None),
    (None, 1000, 250, None),
    ("Model", None, None, None),
    ("Model", 1000, None, 0.002),
    ("Model", None, 250, 0.002),
    ("Model", 0, 0, 0),
])
def test_cost(pricing, model, input_tokens, output_tokens, expected):
    assert pricing.cost(model, input_tokens, output_tokens) == expected
    assert pricing.currency == "USD"


def test_exact_model_match_wins():
    pricing = Pricing({"models": {
        "Model": {"input": 1, "output": 2}, "MODEL": {"input": 3, "output": 4},
    }})
    assert pricing.cost("MODEL", 1_000_000, 0) == 3


def test_with_cost_does_not_mutate_and_removes_stale_cost(pricing):
    message = {"model": "Model", "input_tokens": 1000, "output_tokens": 250,
               "agent_usage": [{"model": "unknown", "cost": 99},
                               {"model": "model", "input_tokens": 1000}]}
    result = with_cost(message, pricing)
    assert result["cost"] == 0.004
    assert "cost" not in result["agent_usage"][0]
    assert result["agent_usage"][1]["cost"] == 0.002
    assert "cost" not in message
    assert message["agent_usage"][0]["cost"] == 99


def test_update_replaces_the_table_and_skips_unusable_prices():
    pricing = Pricing({"models": {"Old": {"input": 1, "output": 1}}})

    pricing.update({"currency": "USD", "models": {"New": {"input": 2, "output": 4}, "Bad": {"input": -1, "output": 1}, "Worse": "x"}})

    assert pricing.cost("Old", 1_000_000, 0) is None
    assert pricing.cost("new", 1_000_000, 1_000_000) == 6
    assert pricing.cost("Bad", 1, 1) is None


def test_refresh_reads_strongholds_table_once_a_minute():
    import asyncio
    import json
    from types import SimpleNamespace

    asked = []

    class Stronghold:
        async def forward(self, method, path, account):
            asked.append((method, path, account))
            return SimpleNamespace(status=200, body=json.dumps({"models": {"M": {"input": 1, "output": 1}}}).encode())

    pricing = Pricing()
    asyncio.run(pricing.refresh(Stronghold()))
    asyncio.run(pricing.refresh(Stronghold()))

    assert asked == [("GET", "/usage/pricing", None)]
    assert pricing.cost("M", 1_000_000, 0) == 1


def test_refresh_keeps_the_last_table_when_stronghold_is_down():
    import asyncio

    class Down:
        async def forward(self, *args, **kwargs):
            raise RuntimeError("down")

    pricing = Pricing({"models": {"M": {"input": 1, "output": 1}}})

    asyncio.run(pricing.refresh(Down()))

    assert pricing.cost("M", 1_000_000, 0) == 1
