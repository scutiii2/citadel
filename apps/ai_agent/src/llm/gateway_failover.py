"""Same-provider routing; only SDK gateway failures may advance a turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Iterable

import anthropic
import openai

from src.core.catalog import catalog
from src.core.config_files import TUNING_PATH, read_section
from src.llm import cooldown

QUOTA_WORDS = ("credit", "quota", "billing", "insufficient", "balance", "exceeded your current")
_SDK_ERRORS = (anthropic.APIError, openai.APIError)
_TRANSPORT_ERRORS = (anthropic.APIConnectionError, openai.APIConnectionError)


class FailureKind(StrEnum):
    rate_limit = "rate_limit"
    quota = "quota"
    auth = "auth"
    unavailable = "unavailable"


@catalog
def classify(error: Exception) -> FailureKind | None:
    """Inspect SDK identity before status/wording so local failures never retry."""
    if not isinstance(error, _SDK_ERRORS):
        return None
    status = getattr(error, "status_code", None)
    if status == 402:
        return FailureKind.quota
    if status in (401, 403):
        return FailureKind.auth
    if status in (400, 429) and any(word in str(error).lower() for word in QUOTA_WORDS):
        return FailureKind.quota
    if status == 429 or isinstance(error, (anthropic.RateLimitError, openai.RateLimitError)):
        return FailureKind.rate_limit
    if (isinstance(status, int) and 500 <= status < 600) or isinstance(error, _TRANSPORT_ERRORS):
        return FailureKind.unavailable
    if isinstance(error, (anthropic.AuthenticationError, openai.AuthenticationError,
                          anthropic.PermissionDeniedError, openai.PermissionDeniedError)):
        return FailureKind.auth
    if isinstance(error, (anthropic.InternalServerError, openai.InternalServerError)):
        return FailureKind.unavailable
    return None


@catalog
def cooldown_seconds(kind: FailureKind, error: Exception) -> float:
    """Honor a gateway's rate-limit delay; use configured delays for outages."""
    if kind == FailureKind.rate_limit:
        delay = cooldown.extract_retry_after_seconds(error)
        return delay if delay is not None else cooldown.DEFAULT_COOLDOWN_SECONDS
    defaults = {FailureKind.quota: 3600.0, FailureKind.auth: 3600.0, FailureKind.unavailable: 30.0}
    section = read_section(TUNING_PATH, "gateway_failover", default={})
    return float(section.get(f"{kind.value}_cooldown_seconds", defaults[kind]))


@dataclass(frozen=True)
@catalog
class SwitchInfo:
    """Public switch metadata contains no gateway error text."""

    from_gateway: str
    to_gateway: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"from": self.from_gateway, "to": self.to_gateway, "reason": self.reason}


@dataclass
@catalog
class GatewayRoute:
    """Move forward through one credentialed candidate list for a whole turn."""

    provider: str
    candidates: tuple[str, ...]
    current: str
    has_credentials: Callable[[str], bool]
    switches: list[SwitchInfo] = field(default_factory=list)
    _index: int = 0

    @classmethod
    def for_turn(cls, provider: str, primary: str, fallbacks: Iterable[str],
                 has_credentials: Callable[[str], bool]) -> GatewayRoute:
        candidates = tuple(dict.fromkeys((primary, *fallbacks)))
        index = next((i for i, name in enumerate(candidates)
                      if has_credentials(name) and not cooldown.is_in_cooldown(cooldown.gateway_key(provider, name))), 0)
        return cls(provider, candidates, candidates[index], has_credentials, _index=index)

    def advance(self, error: Exception) -> SwitchInfo | None:
        kind = classify(error)
        if kind is None:
            return None
        cooldown.start_cooldown(cooldown.gateway_key(self.provider, self.current), cooldown_seconds(kind, error))
        for index in range(self._index + 1, len(self.candidates)):
            name = self.candidates[index]
            if not self.has_credentials(name) or cooldown.is_in_cooldown(cooldown.gateway_key(self.provider, name)):
                continue
            switch = SwitchInfo(self.current, name, kind.value)
            self.current, self._index = name, index
            self.switches.append(switch)
            return switch
        return None
