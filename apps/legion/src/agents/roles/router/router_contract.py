"""Validated internal routing messages and deployment policy; no model imports."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Tier = Literal["light", "standard", "heavy", "extreme"]
DEFAULT_SIZE_TIERS = {"tiny": "light", "everyday": "light", "large": "standard", "hardest": "heavy"}


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RouterPolicy(Message):
    choose_agent: bool = True
    choose_tier: bool = True
    strategy: Literal["laya-only", "jev-only", "both"] = "both"
    min_confidence: float | None = Field(default=None, gt=0, le=1)
    deadline_seconds: float = Field(default=10, ge=1, le=30)
    remote_timeout_seconds: float = Field(default=3, gt=0, le=30)
    size_tiers: dict[str, Tier] = Field(default_factory=lambda: dict(DEFAULT_SIZE_TIERS))
    trace: bool = False

    @model_validator(mode="after")
    def valid_policy(self):
        if set(self.size_tiers) != set(DEFAULT_SIZE_TIERS):
            raise ValueError("size_tiers must name tiny, everyday, large and hardest")
        return self

    def revision(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:16]

    def summary(self) -> dict:
        return {"choose_agent": self.choose_agent, "choose_tier": self.choose_tier,
                "strategy": self.strategy,
                "deadline_seconds": self.deadline_seconds}


class RouteTier(Message):
    tier: Tier
    id: str = ""
    use_for: str = ""


class RouteCandidate(Message):
    id: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str = Field(max_length=240)
    focus: str = Field(default="", max_length=240)
    tiers: list[RouteTier] = Field(default_factory=list, max_length=4)


class RouteRequest(Message):
    subject: str = Field(min_length=1, max_length=100_000)
    candidates: list[RouteCandidate] = Field(default_factory=list, max_length=100)
    entry: RouteCandidate | None = None
    explicit_tier: Tier | None = None
    choose_agent: bool = True
    choose_tier: bool = True
    request_id: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_candidates(self):
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)) or "none" in ids:
            raise ValueError("candidate IDs must be unique and cannot be none")
        return self


class DecisionOutcome(Message):
    choice: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    uncertain: bool = True
    answered_by: str = ""
    reason: str = "not_requested"


class VoterUsage(Message):
    provider_id: str
    model: str
    started_at: str
    duration_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    ok: bool
    reason: str = ""


class RouteResponse(Message):
    agent: DecisionOutcome = Field(default_factory=DecisionOutcome)
    size: DecisionOutcome = Field(default_factory=DecisionOutcome)
    model_tier: Tier | None = None
    policy_revision: str
    usage: list[VoterUsage] = Field(default_factory=list)
    trace: list[dict] | None = None
