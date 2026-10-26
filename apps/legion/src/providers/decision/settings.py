"""Settings for decision strategies used by automatic routing and tier selection."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.runtime import tuning_overrides
from src.runtime.config_files import TUNING_PATH, read_section
from src.providers.decision.questions import DEFAULT_SIZE_TIERS, SIZE_CRITERIA
from src.providers.decision import strategy

_log = logging.getLogger(__name__)
_SECTION = "classifier"
FEATURES = ("auto_tier", "auto_route")
_KNOWN = {"timeout_seconds", "max_input_chars", *FEATURES}
_AUTO_TIER_KNOWN = {"enabled", "strategy", "min_confidence", "tiers"}
_AUTO_ROUTE_KNOWN = {"enabled", "strategy", "min_confidence"}


@dataclass(frozen=True)
class AutoTierSettings:
    enabled: bool = False
    strategy: str = "both"
    min_confidence: int = 60
    tiers: tuple[tuple[str, str], ...] = DEFAULT_SIZE_TIERS


@dataclass(frozen=True)
class AutoRouteSettings:
    enabled: bool = False
    strategy: str = "both"
    min_confidence: int = 60


@dataclass(frozen=True)
class ClassifierSettings:
    timeout_seconds: float = 3.0
    max_input_chars: int = 16000
    auto_tier: AutoTierSettings = AutoTierSettings()
    auto_route: AutoRouteSettings = AutoRouteSettings()


def settings() -> ClassifierSettings:
    return _load_settings()


@lru_cache(maxsize=1)
def _load_settings() -> ClassifierSettings:
    raw = read_section(TUNING_PATH, _SECTION, {})
    if not isinstance(raw, dict):
        raise ValueError("config_tuning.json classifier must be an object")
    unknown = set(raw) - _KNOWN
    if unknown:
        _log.warning("Ignoring retired or unknown classifier keys: %s", ", ".join(sorted(unknown)))
    base = ClassifierSettings()
    timeout = raw.get("timeout_seconds", base.timeout_seconds)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
        raise ValueError("config_tuning.json classifier.timeout_seconds must be a number above 0 and at most 60")
    cap = raw.get("max_input_chars", base.max_input_chars)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError("config_tuning.json classifier.max_input_chars must be a positive integer")
    return ClassifierSettings(timeout_seconds=float(timeout), max_input_chars=cap,
                              auto_tier=_auto_tier_settings(raw.get("auto_tier", {})),
                              auto_route=_auto_route_settings(raw.get("auto_route", {})))


def _feature_strategy(raw: dict[str, Any], where: str) -> str:
    if "strategy" not in raw:
        return "both"
    value = raw["strategy"]
    if value not in strategy.STRATEGIES:
        _log.warning("Invalid %s.strategy; using both", where)
        return "both"
    return value


def _auto_route_settings(raw: Any) -> AutoRouteSettings:
    where = f"config_tuning.json {_SECTION}.auto_route"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object")
    unknown = set(raw) - _AUTO_ROUTE_KNOWN
    if unknown:
        raise ValueError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    if not isinstance(raw.get("enabled", False), bool):
        raise ValueError(f"{where}.enabled must be true or false")
    confidence = raw.get("min_confidence", AutoRouteSettings.min_confidence)
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError(f"{where}.min_confidence must be an integer from 0 to 100")
    return AutoRouteSettings(enabled=raw.get("enabled", False), strategy=_feature_strategy(raw, where), min_confidence=confidence)


def _auto_tier_settings(raw: Any) -> AutoTierSettings:
    from src.providers.llm_config import TIERS

    where = f"config_tuning.json {_SECTION}.auto_tier"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object")
    unknown = set(raw) - _AUTO_TIER_KNOWN
    if unknown:
        raise ValueError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    if not isinstance(raw.get("enabled", False), bool):
        raise ValueError(f"{where}.enabled must be true or false")
    confidence = raw.get("min_confidence", AutoTierSettings.min_confidence)
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError(f"{where}.min_confidence must be an integer from 0 to 100")
    mapping = dict(DEFAULT_SIZE_TIERS)
    given = raw.get("tiers", {})
    if not isinstance(given, dict):
        raise ValueError(f"{where}.tiers must be an object of size: tier")
    for size, tier in given.items():
        if size not in SIZE_CRITERIA or tier not in TIERS:
            raise ValueError(f"{where}.tiers maps a size ({', '.join(SIZE_CRITERIA)}) to a tier ({', '.join(TIERS)})")
        mapping[size] = tier
    return AutoTierSettings(enabled=raw.get("enabled", False), strategy=_feature_strategy(raw, where), min_confidence=confidence, tiers=tuple(mapping.items()))

def available(feature: str) -> bool:
    chosen = getattr(settings(), feature).strategy
    gateways = strategy.default_gateways()
    return any(gateways[name].available() for name in strategy._ORDER[chosen])


def reset_cache() -> None:
    _load_settings.cache_clear()


tuning_overrides.on_change(reset_cache)
