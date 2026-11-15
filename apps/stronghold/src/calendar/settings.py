"""The "calendar" block of Stronghold's config, and the clock the stored times use."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC, the form every stored time has."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class CalendarSettings:
    """config_app.json's "calendar" block: ICS schedule feeds and the alerts before events."""

    enabled: bool = True
    tick_seconds: int = 30
    feed_refresh_minutes: int = 10
    lookahead_hours: int = 48
    late_grace_minutes: int = 5
    max_feeds_per_account: int = 10
    max_alarm_rules: int = 10
    max_ics_bytes: int = 5 * 1024 * 1024
    fetch_timeout_s: int = 15
    allow_private_urls: bool = False
    # The "sub" claim of web push messages; push services may contact it.
    push_contact: str = "mailto:admin@example.com"

    @classmethod
    def from_config(cls, raw: dict) -> CalendarSettings:
        positive = (
            "tick_seconds", "feed_refresh_minutes", "lookahead_hours", "late_grace_minutes",
            "max_feeds_per_account", "max_alarm_rules", "max_ics_bytes", "fetch_timeout_s",
        )
        numbers = {name: int(raw.get(name, getattr(cls, name))) for name in positive}
        for name, value in numbers.items():
            if value < 1:
                raise ValueError(f"calendar.{name} must be at least 1")
        contact = str(raw.get("push_contact") or cls.push_contact)
        if not contact.startswith(("mailto:", "https://")):
            raise ValueError("calendar.push_contact must start with mailto: or https://")
        return cls(
            enabled=bool(raw.get("enabled", True)),
            allow_private_urls=bool(raw.get("allow_private_urls", False)),
            push_contact=contact,
            **numbers,
        )
