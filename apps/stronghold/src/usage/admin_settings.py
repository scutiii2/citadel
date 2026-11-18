"""The usage limits and the price table, kept in Stronghold's settings database (table `limits_and_prices`).

An administrator edits them on the Usage settings page of Stronghold Admin; nothing is read from a file. A stored
document only holds what was changed; every other value is the default of `UsageSettings` and `PricingSettings`.
A change is used by the next question and the next cost estimate, with no restart.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from src.citadel_auth import settings_store
from src.usage.settings import Pricing, PricingSettings, UsageSettings

TABLE = "limits_and_prices"
USAGE_KEY = "usage"
PRICING_KEY = "pricing"


class UsageSettingsError(ValueError):
    """A change is refused; the message names the setting and is safe to show."""


def _usage_document(settings: UsageSettings) -> dict[str, Any]:
    return dataclasses.asdict(settings)


def _pricing_document(settings: PricingSettings) -> dict[str, Any]:
    return {"currency": settings.currency,
            "models": {name: {"input": price.input, "output": price.output} for name, price in settings.models.items()}}


def load(path: Path) -> tuple[UsageSettings, PricingSettings]:
    """The defaults with what was saved on top. A saved value that no longer validates is an error: it is never ignored."""
    saved = settings_store.read_all(path, TABLE)
    usage = UsageSettings.from_config({**_usage_document(UsageSettings()), **(saved.get(USAGE_KEY) or {})})
    pricing = PricingSettings.from_config(saved.get(PRICING_KEY) or {})
    return usage, pricing


def view(usage: UsageSettings, pricing: PricingSettings | Pricing, path: Path) -> dict[str, Any]:
    saved = settings_store.read_all(path, TABLE)
    price_document = pricing.document() if isinstance(pricing, Pricing) else _pricing_document(pricing)
    return {"usage": _usage_document(usage), "pricing": price_document,
            "stored": {"usage": USAGE_KEY in saved, "pricing": PRICING_KEY in saved}}


def update(usage: UsageSettings, pricing: Pricing, path: Path, changes: Any) -> None:
    """Save `{"usage": {...changed values}, "pricing": {"models": {...the whole table}}}` and use it now.

    `usage` is merged into the current values; `pricing.models` replaces the table. Nothing is saved if one change is refused."""
    if not isinstance(changes, dict) or not changes or not set(changes) <= {"usage", "pricing"}:
        raise UsageSettingsError("Send usage and/or pricing.")
    new_usage = usage
    new_pricing: PricingSettings | None = None
    if "usage" in changes:
        part = changes["usage"]
        if not isinstance(part, dict) or not part:
            raise UsageSettingsError("usage must be an object with at least one value.")
        unknown = set(part) - set(_usage_document(usage))
        if unknown:
            raise UsageSettingsError(f"Unknown usage setting: {', '.join(sorted(unknown))}.")
        try:
            new_usage = UsageSettings.from_config({**_usage_document(usage), **part})
        except ValueError as error:
            raise UsageSettingsError(str(error)) from error
    if "pricing" in changes:
        part = changes["pricing"]
        if not isinstance(part, dict) or set(part) - {"currency", "models"}:
            raise UsageSettingsError("pricing takes currency and models only.")
        try:
            new_pricing = PricingSettings.from_config(part)
        except (ValueError, AttributeError) as error:
            raise UsageSettingsError(str(error)) from error
    if "usage" in changes:
        settings_store.put(path, TABLE, USAGE_KEY, _usage_document(new_usage))
        for field, value in _usage_document(new_usage).items():
            object.__setattr__(usage, field, value)  # UsageSettings is frozen; the services all share this one object.
    if new_pricing is not None:
        settings_store.put(path, TABLE, PRICING_KEY, _pricing_document(new_pricing))
        pricing.replace(new_pricing)
