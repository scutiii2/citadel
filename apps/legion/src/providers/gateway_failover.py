"""Same-provider routing; only gateway failures may advance a turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Callable, Iterable

from src.runtime import tuning_overrides
from src.runtime.config_files import TUNING_PATH, read_section
from src.providers import cooldown
from src.providers.gateway_client import GatewayCallError

class NoTrustedGateway(Exception):
    """A request holds confidential data and none of the agent's trusted gateways can take it. Never retried
    on an untrusted gateway; the message is safe to show."""

    def __init__(self) -> None:
        super().__init__("This request holds confidential data, and none of this agent's trusted gateways is available, "
                         "so it was not sent. Try again later or mark a gateway as trusted.")


class FailureKind(StrEnum):
    rate_limit = "rate_limit"
    quota = "quota"
    auth = "auth"
    unavailable = "unavailable"


_KINDS = {kind.value: kind for kind in FailureKind}


def classify(error: Exception) -> FailureKind | None:
    """A gateway failure's kind, or None when the round must not be retried.
    ConversationGateway classifies its own failures; anything else is Legion's
    own error and never a reason to switch gateway."""
    if isinstance(error, GatewayCallError):
        # No kind means the request itself was refused: never retry that.
        return _KINDS.get(error.kind or "")
    return None


@lru_cache(maxsize=1)
def _cooldown_settings() -> tuple[float, float, float]:
    """Load once during provider startup so routing never reads disk on a failure."""
    section = read_section(TUNING_PATH, "gateway_failover", default={})
    return tuple(float(section.get(f"{kind}_cooldown_seconds", default)) for kind, default in (
        ("quota", 3600.0), ("auth", 3600.0), ("unavailable", 30.0)))


# Providers import this module before serving requests, outside the event loop.
_cooldown_settings()


def reset_cache() -> None:
    """Reload cooldowns so later failures do not read disk."""
    _cooldown_settings.cache_clear()
    _cooldown_settings()


tuning_overrides.on_change(reset_cache)


def cooldown_seconds(kind: FailureKind, error: Exception) -> float:
    """Honor a gateway's rate-limit delay; use configured delays for outages."""
    if kind == FailureKind.rate_limit:
        delay = cooldown.extract_retry_after_seconds(error)
        return delay if delay is not None else cooldown.DEFAULT_COOLDOWN_SECONDS
    index = {FailureKind.quota: 0, FailureKind.auth: 1, FailureKind.unavailable: 2}[kind]
    return _cooldown_settings()[index]


@dataclass(frozen=True)
class SwitchInfo:
    """Public switch metadata contains no gateway error text."""

    from_gateway: str
    to_gateway: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"from": self.from_gateway, "to": self.to_gateway, "reason": self.reason}


@dataclass
class GatewayRoute:
    """Move forward through one credentialed candidate list for a whole turn."""

    provider: str
    candidates: tuple[str, ...]
    current: str
    has_credentials: Callable[[str], bool]
    switches: list[SwitchInfo] = field(default_factory=list)
    _index: int = 0
    # Set once the turn holds confidential data: only a gateway this says is trusted may be used.
    trusted_only: Callable[[str], bool] | None = None

    @classmethod
    def for_turn(cls, provider: str, primary: str, fallbacks: Iterable[str],
                 has_credentials: Callable[[str], bool]) -> GatewayRoute:
        candidates = tuple(dict.fromkeys((primary, *fallbacks)))
        index = next((i for i, name in enumerate(candidates)
                      if has_credentials(name) and not cooldown.is_in_cooldown(cooldown.gateway_key(provider, name))), 0)
        return cls(provider, candidates, candidates[index], has_credentials, _index=index)

    def _usable(self, name: str) -> bool:
        return (self.has_credentials(name) and not cooldown.is_in_cooldown(cooldown.gateway_key(self.provider, name))
                and (self.trusted_only is None or self.trusted_only(name)))

    def require_trusted(self, is_trusted: Callable[[str], bool]) -> SwitchInfo | None:
        """From now on use only trusted gateways. Moves to the first usable trusted candidate when the current one
        is not trusted (the switch to report, else None); raises NoTrustedGateway when there is none."""
        self.trusted_only = is_trusted
        if self._usable(self.current):
            return None
        for index, name in enumerate(self.candidates):
            if self._usable(name):
                switch = SwitchInfo(self.current, name, "confidential")
                self.current, self._index = name, index
                self.switches.append(switch)
                return switch
        raise NoTrustedGateway()

    def advance(self, error: Exception) -> SwitchInfo | None:
        kind = classify(error)
        if kind is None:
            return None
        cooldown.start_cooldown(cooldown.gateway_key(self.provider, self.current), cooldown_seconds(kind, error), kind.value)
        for index in range(self._index + 1, len(self.candidates)):
            name = self.candidates[index]
            if not self._usable(name):
                continue
            switch = SwitchInfo(self.current, name, kind.value)
            self.current, self._index = name, index
            self.switches.append(switch)
            return switch
        return None
