"""Which reported subscription plans may be invited into a group.

The allowlists are not guessed: an administrator types the plan strings the
workers report (the Forge page shows them) into app_settings. Empty means
nothing is eligible. This is a guard in Ember's UI and API only; the provider
enforces the real limit."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from src.db import utcnow
from src.models import AppSetting, ForgeWorker

MAX_PLANS = 12
PLAN_MAX = 40
_SETTING_MAX = 200  # app_settings.value is a String(200)


class InvalidPlanList(ValueError):
    """The allowlist is not acceptable; the message is safe to show."""


def normalize_plan(plan: str) -> str:
    return " ".join(plan.split()).lower()


class PlanPolicy(ABC):
    """The plans one provider's workers may be invited with."""

    provider: str

    @abstractmethod
    async def allowed(self) -> list[str]:
        """Normalized plan strings."""

    async def is_allowed(self, reported_plan: str | None) -> bool:
        if not reported_plan:
            return False
        return normalize_plan(reported_plan) in await self.allowed()


class StoredPlanPolicy(PlanPolicy):
    """The allowlist is a JSON list in app_settings under `forge_plans_<provider>`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def _name(self) -> str:
        return f"forge_plans_{self.provider}"

    async def allowed(self) -> list[str]:
        row = await self._session.get(AppSetting, self._name)
        if row is None:
            return []
        try:
            value = json.loads(row.value)
        except ValueError:
            return []
        if not isinstance(value, list):
            return []
        return [normalize_plan(p) for p in value if isinstance(p, str)]

    async def set_allowed(self, plans: list[str]) -> list[str]:
        """Saves the list (cleaned: lower case, no blanks, no repeats) and returns it."""
        cleaned = list(dict.fromkeys(n for n in (normalize_plan(p) for p in plans) if n))
        if len(cleaned) > MAX_PLANS:
            raise InvalidPlanList(f"At most {MAX_PLANS} plans")
        if any(len(p) > PLAN_MAX for p in cleaned):
            raise InvalidPlanList(f"A plan name is at most {PLAN_MAX} characters")
        text = json.dumps(cleaned)
        if len(text) > _SETTING_MAX:
            raise InvalidPlanList("The plan list is too long")
        row = await self._session.get(AppSetting, self._name)
        if row is None:
            self._session.add(AppSetting(name=self._name, value=text))
        else:
            row.value = text
            row.updated_at = utcnow()
        await self._session.commit()
        return cleaned


class ClaudePlanPolicy(StoredPlanPolicy):
    provider = "claude"


class CodexPlanPolicy(StoredPlanPolicy):
    provider = "codex"


class PlanPolicyRegistry:
    """Maps a provider to its policy. A new provider is one new policy subclass listed here."""

    def __init__(self, session: AsyncSession) -> None:
        self._policies: dict[str, StoredPlanPolicy] = {
            policy.provider: policy for policy in (ClaudePlanPolicy(session), CodexPlanPolicy(session))
        }

    def for_provider(self, provider: str) -> StoredPlanPolicy:
        try:
            return self._policies[provider]
        except KeyError:
            raise ValueError(f"Unknown provider: {provider}") from None

    async def allowed(self) -> dict[str, list[str]]:
        return {provider: await policy.allowed() for provider, policy in self._policies.items()}

    async def problem(self, worker: ForgeWorker) -> str | None:
        """Why the worker cannot be used, or None when it can."""
        policy = self._policies.get(worker.provider)
        if policy is None:
            return f"Unknown provider: {worker.provider}"
        if await policy.is_allowed(worker.reported_plan):
            return None
        return f"Plan not eligible: {worker.reported_plan or 'not reported yet'}"
