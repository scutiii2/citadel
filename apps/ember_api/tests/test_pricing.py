import json

import pytest

from src import config
from src.config import PricingSettings
from src.services.pricing import Pricing, with_cost


@pytest.fixture
def pricing():
    return Pricing(PricingSettings.from_config({"models": {"Model": {"input": 2, "output": 8}}}))


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
    pricing = Pricing(PricingSettings.from_config({"models": {
        "Model": {"input": 1, "output": 2}, "MODEL": {"input": 3, "output": 4},
    }}))
    assert pricing.cost("MODEL", 1_000_000, 0) == 3


@pytest.mark.parametrize("key,value", [
    ("input", -1), ("output", "2"), ("input", True),
    ("output", float("nan")), ("input", float("inf")),
])
def test_invalid_prices_name_the_key(key, value):
    price = {"input": 2, "output": 8, key: value}
    with pytest.raises(ValueError, match=f"models.Model.{key}"):
        PricingSettings.from_config({"models": {"Model": price}})


@pytest.mark.parametrize("models", [{" ": {"input": 0, "output": 0}}, {4: {}}, {"Model": []}, []])
def test_invalid_models(models):
    with pytest.raises(ValueError, match="models"):
        PricingSettings.from_config({"models": models})


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


def test_settings_load_pricing_from_example(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "config_app.json.example").write_text("{}")
    (configs / "config_pricing.json.example").write_text(json.dumps({
        "currency": "USD", "models": {"example-model": {"input": 0, "output": 0}},
    }))
    monkeypatch.setattr(config, "CONFIGS_DIR", configs)
    # Environment setup is unrelated to pricing; do not touch real local secrets.
    monkeypatch.setattr(config, "ensure_env_file", lambda *args: None)
    settings = config.load_settings()
    assert settings.pricing.models["example-model"].input == 0
    assert (configs / "config_pricing.json").exists()
