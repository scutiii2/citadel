"""Ticket settings: the document kept in the settings store under "tickets" (every key optional)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_TAGS: dict[str, str] = {
    "config": "A setting, config file or environment variable is missing or wrong.",
    "tool-failure": "A tool or capability failed or returned an error.",
    "auth": "Login, permissions or access problems.",
    "ui": "Something looks or behaves wrong in the web interface.",
    "chat": "Chat answers, history, attachments or agents misbehave.",
    "performance": "Slowness, timeouts or high resource use.",
    "email": "Sending or receiving email, invitations or verification.",
    "feature-request": "A new feature or an improvement is being suggested.",
}
DEFAULT_ELEVATION: dict[str, dict[str, int]] = {
    "high": {"tickets": 3, "recent": 2},
    "urgent": {"tickets": 6, "recent": 4},
}
MIN_TAGS = 2
MAX_TAGS = 10  # Laya's `choice` question allows at most ten options.


@dataclass(frozen=True)
class TicketConfig:
    tags: dict[str, str]
    auto_hourly_cap: int
    recent_hours: int
    elevation: dict[str, dict[str, int]]
    laya_min_confidence: float
    laya_candidates: int
    laya_timeout_seconds: float

    def document(self) -> dict[str, Any]:
        """The settings as one document: what the admin page shows and what the store keeps."""
        return {
            "tags": dict(self.tags), "auto_hourly_cap": self.auto_hourly_cap, "recent_hours": self.recent_hours,
            "elevation": {level: dict(rule) for level, rule in self.elevation.items()},
            "laya": {"min_confidence": self.laya_min_confidence, "candidates": self.laya_candidates,
                     "timeout_seconds": self.laya_timeout_seconds},
        }


def _positive_int(raw: dict[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"ticket settings: {key} must be a whole number of at least 1.")
    return value


def _tags(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict) or not MIN_TAGS <= len(raw) <= MAX_TAGS:
        raise ValueError(f"ticket settings: tags must be an object of {MIN_TAGS} to {MAX_TAGS} tag: description pairs.")
    for tag, description in raw.items():
        if not isinstance(tag, str) or not tag.strip() or not isinstance(description, str) or not description.strip():
            raise ValueError("ticket settings: every tag needs a non-empty name and description.")
    return {tag.strip().lower(): description.strip() for tag, description in raw.items()}


def _elevation(raw: Any) -> dict[str, dict[str, int]]:
    if not isinstance(raw, dict) or not set(raw) <= set(DEFAULT_ELEVATION):
        raise ValueError("ticket settings: elevation may only define 'high' and 'urgent'.")
    result: dict[str, dict[str, int]] = {}
    for level, rule in raw.items():
        if not isinstance(rule, dict):
            raise ValueError(f"ticket settings: elevation.{level} must be an object.")
        result[level] = {key: _positive_int(rule, key, 0) for key in ("tickets", "recent")}
    return result


def load_ticket_config(raw: Any = None) -> TicketConfig:
    """Validate a settings document into a TicketConfig; None or {} gives the defaults."""
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise ValueError("Ticket settings must be an object.")
    laya = raw.get("laya", {})
    if not isinstance(laya, dict):
        raise ValueError("ticket settings: laya must be an object.")
    confidence = laya.get("min_confidence", 0.7)
    timeout = laya.get("timeout_seconds", 20.0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 < confidence <= 1:
        raise ValueError("ticket settings: laya.min_confidence must be above 0 and at most 1.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("ticket settings: laya.timeout_seconds must be above 0.")
    candidates = _positive_int(laya, "candidates", 5)
    if candidates > 10:
        raise ValueError("ticket settings: laya.candidates must be at most 10.")
    return TicketConfig(
        tags=_tags(raw.get("tags", DEFAULT_TAGS)),
        auto_hourly_cap=_positive_int(raw, "auto_hourly_cap", 5),
        recent_hours=_positive_int(raw, "recent_hours", 24),
        elevation=_elevation(raw["elevation"]) if "elevation" in raw else dict(DEFAULT_ELEVATION),
        laya_min_confidence=float(confidence),
        laya_candidates=candidates,
        laya_timeout_seconds=float(timeout),
    )
