"""An account's free resets, limit boosts and cleared times: the rules, with no storage.

Every time is naive UTC, and every method that depends on the time takes it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

WINDOWS = ("six_hour", "weekly")
KINDS = {"six_hour": ("six_hour",), "weekly": ("weekly",), "both": WINDOWS}
MAX_RESETS = 100


class AllowanceError(ValueError):
    """A change is refused; the message is safe to show."""


class ResetNotFound(AllowanceError):
    def __init__(self) -> None:
        super().__init__("That reset is not available.")


class NothingToReset(AllowanceError):
    def __init__(self) -> None:
        super().__init__("There is nothing to reset yet.")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _text(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class Reset:
    id: str
    kind: str
    granted_at: datetime
    expires_at: datetime | None

    @property
    def covers(self) -> tuple[str, ...]:
        return KINDS[self.kind]

    def live(self, now: datetime) -> bool:
        return self.expires_at is None or self.expires_at > now


@dataclass(frozen=True)
class Boost:
    id: str
    windows: tuple[str, ...]
    percent: int
    granted_at: datetime
    ends_at: datetime


@dataclass
class Allowance:
    owner: str
    resets: list[Reset] = field(default_factory=list)
    boosts: list[Boost] = field(default_factory=list)
    cleared: dict[str, datetime | None] = field(default_factory=lambda: dict.fromkeys(WINDOWS))
    auto_use: bool = False

    @classmethod
    def from_doc(cls, owner: str, doc: dict[str, Any] | None) -> Allowance:
        if doc is None:
            return cls(owner)
        return cls(
            owner,
            [Reset(r["id"], r["kind"], _time(r["granted_at"]), _time(r["expires_at"])) for r in doc["resets"]],
            [Boost(b["id"], tuple(b["windows"]), b["percent"], _time(b["granted_at"]), _time(b["ends_at"]))
             for b in doc["boosts"]],
            {window: _time(doc["cleared"].get(window)) for window in WINDOWS},
            doc["auto_use"],
        )

    def to_doc(self) -> dict[str, Any]:
        return {
            "key": self.owner, "owner": self.owner, "auto_use": self.auto_use,
            "resets": [{**asdict(r), "granted_at": _text(r.granted_at), "expires_at": _text(r.expires_at)}
                       for r in self.resets],
            "boosts": [{**asdict(b), "windows": list(b.windows), "granted_at": _text(b.granted_at),
                        "ends_at": _text(b.ends_at)} for b in self.boosts],
            "cleared": {window: _text(at) for window, at in self.cleared.items()},
        }

    # --- reading -----------------------------------------------------------

    def live_resets(self, now: datetime) -> list[Reset]:
        """Soonest expiry first; resets without one come last, oldest first."""
        return sorted((r for r in self.resets if r.live(now)),
                      key=lambda r: (r.expires_at or datetime.max, r.granted_at))

    def live_boosts(self, now: datetime) -> list[Boost]:
        return [b for b in self.boosts if b.ends_at > now]

    def find(self, reset_id: str, now: datetime) -> Reset:
        for reset in self.live_resets(now):
            if reset.id == reset_id:
                return reset
        raise ResetNotFound()

    def boost(self, window: str, now: datetime) -> Boost | None:
        """The one that applies: the highest percent, and of equals the one ending last."""
        active = [b for b in self.live_boosts(now) if window in b.windows]
        return max(active, key=lambda b: (b.percent, b.ends_at), default=None)

    def limit(self, window: str, base: int, now: datetime) -> int:
        boost = self.boost(window, now)
        return base * (100 + boost.percent) // 100 if boost and base else base

    def plan(self, blocked: Iterable[str], now: datetime) -> tuple[Reset, ...]:
        """The resets that would unblock exactly these windows; empty when the account cannot be unblocked."""
        blocked = set(blocked)
        if not blocked:
            return ()
        live = self.live_resets(now)

        def first(kind: str) -> Reset | None:
            return next((r for r in live if r.kind == kind), None)

        both = first("both")
        if len(blocked) == 1:
            chosen = first(next(iter(blocked))) or both
            return (chosen,) if chosen else ()
        if both:
            return (both,)
        pair = (first("six_hour"), first("weekly"))
        return pair if all(pair) else ()

    # --- changing ----------------------------------------------------------

    def grant(self, kind: str, count: int, expires_at: datetime | None, now: datetime) -> None:
        if len(self.live_resets(now)) + count > MAX_RESETS:
            raise AllowanceError(f"An account holds at most {MAX_RESETS} unused resets.")
        self.resets += [Reset(_new_id("r"), kind, now, expires_at) for _ in range(count)]

    def add_boost(self, windows: Iterable[str], percent: int, ends_at: datetime, now: datetime) -> None:
        self.boosts.append(Boost(_new_id("b"), tuple(windows), percent, now, ends_at))

    def remove_reset(self, reset_id: str) -> None:
        kept = [r for r in self.resets if r.id != reset_id]
        if len(kept) == len(self.resets):
            raise ResetNotFound()
        self.resets = kept

    def remove_boost(self, boost_id: str) -> None:
        kept = [b for b in self.boosts if b.id != boost_id]
        if len(kept) == len(self.boosts):
            raise AllowanceError("That boost is not available.")
        self.boosts = kept

    def clear(self, windows: Iterable[str], now: datetime) -> None:
        for window in windows:
            self.cleared[window] = now

    def use(self, reset_id: str, now: datetime) -> Reset:
        reset = self.find(reset_id, now)
        self.clear(reset.covers, now)
        self.remove_reset(reset.id)
        return reset

    def prune(self, now: datetime) -> None:
        self.resets = [r for r in self.resets if r.live(now)]
        self.boosts = self.live_boosts(now)
