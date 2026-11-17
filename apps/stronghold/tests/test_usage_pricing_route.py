"""GET /usage/pricing: the one price table, for Portcullis."""

import pytest

from src.usage.settings import Pricing, PricingSettings


def test_document_lists_every_price():
    pricing = Pricing(PricingSettings.from_config({"models": {"Model": {"input": 2, "output": 8}}}))

    assert pricing.document() == {"currency": "USD", "models": {"Model": {"input": 2.0, "output": 8.0}}}


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
