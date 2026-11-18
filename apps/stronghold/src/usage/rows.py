"""One usage row per agent from an ask()/interpret() result.

A copy of Portcullis's services/usage_rows.py (kept there for chat turns until chats move here).
All times are naive UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and value >= 0 else None


def _time(value: Any) -> datetime | None:
    """An ISO-8601 time from ai_agent ("...Z") as naive UTC; None when absent or unreadable."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _text(value: Any, limit: int) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def usage_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per agent from an ask()/interpret() result: ask's
    `agent_usage` (own + delegated agents) when present, else its totals."""
    rows = []
    for entry in result.get("agent_usage") or []:
        if isinstance(entry, dict) and _int(entry.get("total_tokens")):
            agent_id = _text(entry.get("agent_id"), 120)
            provider_id = _text(entry.get("provider_id"), 60)
            rows.append(
                {
                    "agent": agent_id or provider_id,
                    "agent_id": agent_id,
                    "agent_label": _text(entry.get("agent_label"), 120),
                    "provider_id": provider_id,
                    "gateway": _text(entry.get("gateway"), 60),
                    "model": entry.get("model"),
                    "input_tokens": _int(entry.get("input_tokens")),
                    "output_tokens": _int(entry.get("output_tokens")),
                    "total_tokens": _int(entry.get("total_tokens")),
                    "started_at": _time(entry.get("started_at")),
                    "finished_at": _time(entry.get("finished_at")),
                    "delegated_by": _text(entry.get("delegated_by"), 120),
                    **{key: entry[key] for key in ("context_breakdown", "context_breakdown_exact") if key in entry},
                }
            )
    if not rows and _int(result.get("total_tokens")):
        rows.append(
            {
                "agent": result.get("provider_id"),
                "agent_id": None,
                "agent_label": None,
                "provider_id": result.get("provider_id"),
                "gateway": None,
                "model": result.get("model"),
                "input_tokens": _int(result.get("input_tokens")),
                "output_tokens": _int(result.get("output_tokens")),
                "total_tokens": _int(result.get("total_tokens")),
                "started_at": None,
                "finished_at": None,
                "delegated_by": None,
            }
        )
    return rows


# Shown on a message but not stored as usage.
_DISPLAY_ONLY = {"agent_label", "context_breakdown", "context_breakdown_exact"}


def stored_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The rows Stronghold keeps: no display-only keys, times as ISO text, ready for JSON."""
    return [
        {key: value.isoformat() if isinstance(value, datetime) else value for key, value in row.items() if key not in _DISPLAY_ONLY}
        for row in usage_rows(result)
    ]
