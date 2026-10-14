"""Rows as immutable values, so services never touch SQL or JSON text."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.ascension.models import BattleSetup, BattleState, PersonalityInstance


@dataclass(frozen=True)
class ActivityContext:
    kind: str = 'legacy'
    difficulty_id: str | None = None
    trial_type: str | None = None
    trial_stage: int | None = None
    overall: int | None = None
    reward_multiplier: float = 1.0
    recommended_min: int | None = None
    recommended_max: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ActivityContext:
        return cls(**raw)


@dataclass(frozen=True)
class ExpeditionRecord:
    id: str
    owner: str
    ascended_id: str
    started_at: float
    ends_at: float
    duration_hours: int
    xp_reward: int
    insignia_reward: int
    claimed_at: float | None = None
    receipt: dict[str, Any] | None = None


@dataclass(frozen=True)
class PlayerRecord:
    owner: str
    insignia: int
    last_roll_at: float | None
    created_at: float


@dataclass(frozen=True)
class AscendedRecord:
    owner: str
    ascended_id: str
    copies: int  # spare duplicates, spent one per star or sold
    level: int
    xp: int
    faint_until: float | None = None
    tier_id: str | None = None  # None = the Ascended's start tier; Forbidden ignores it
    stars: int = 0  # earned at this tier; reset when it moves up
    default_preset_slot: int = 1


@dataclass(frozen=True)
class PersonalityRecord:
    id: str
    owner: str
    ascended_id: str
    type_id: str
    tier: int
    created_at: float
    seq: int = 0  # assigned by the database

    def instance(self) -> PersonalityInstance:
        return PersonalityInstance(self.id, self.type_id, self.tier)


@dataclass(frozen=True)
class PresetRecord:
    owner: str
    ascended_id: str
    slot: int
    instance_ids: tuple[str, ...]


@dataclass(frozen=True)
class EncounterRecord:
    id: str
    owner: str
    ascended_id: str
    tier_id: str
    level: int
    status: str  # pending, declined, started or expired
    wild_personalities: tuple[PersonalityInstance, ...]  # hidden until a capture
    created_at: float
    activity: ActivityContext = field(default_factory=ActivityContext)


@dataclass(frozen=True)
class BattleRecord:
    id: str
    owner: str
    encounter_id: str
    status: str  # active or terminal
    phase: str  # choosing, awaiting_emblem or terminal
    mode: str  # manual or autonomous
    revision: int
    setup: BattleSetup
    state: BattleState
    player_personalities: tuple[PersonalityInstance, ...]  # frozen from the preset at start
    wild_personalities: tuple[PersonalityInstance, ...]
    emblem_limit: str | None
    rng_seed: int
    rng_counter: int
    created_at: float
    updated_at: float
    pending: dict[str, Any] | None = None  # private: wild action and EMBLEM prompt while awaiting_emblem
    result: dict[str, Any] | None = None
    activity: ActivityContext = field(default_factory=ActivityContext)


@dataclass(frozen=True)
class IdempotencyRecord:
    request_hash: str
    response: dict[str, Any] = field(default_factory=dict)
