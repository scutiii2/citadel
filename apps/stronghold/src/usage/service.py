"""Token usage: recording, the rolling 6-hour and weekly limits, and the reports of the Usage page.

One document per agent call in the "usage_records" collection (key `<uid>:<random>`). Treasury
filters on equality only, so each row carries its UTC `day` and a read fetches the days it needs.
Times are naive UTC; the browser shows local time.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from src.calendar.settings import utcnow
from src.document_store import DocumentStore
from src.usage.settings import Pricing, UsageSettings

COLLECTION = "usage_records"
SIX_HOURS = timedelta(hours=6)
WEEK = timedelta(days=7)
MAX_REPORT_DAYS = 366
_PAGE = 500
_DAYS_AT_ONCE = 16
_PURGE_MAX_PAGES = 200


@dataclass(frozen=True)
class LimitBlock:
    reason: str
    reset_at: datetime


@dataclass(frozen=True)
class Window:
    used: int
    limit: int  # 0 = unlimited
    reset_at: datetime | None


def period_start(days: int, since_date: date | None = None) -> tuple[datetime, int]:
    """Where a report begins, and how many days it spans. A `since_date` (a UTC day, from its
    midnight: "this month" is the 1st) replaces `days`."""
    now = utcnow()
    if since_date is not None:
        start = datetime.combine(since_date, time.min)
        return start, max(1, min(math.ceil((now - start) / timedelta(days=1)), MAX_REPORT_DAYS))
    days = max(1, min(days, MAX_REPORT_DAYS))
    return now - timedelta(days=days), days


def _when(doc: dict[str, Any], field: str) -> datetime | None:
    return datetime.fromisoformat(doc[field]) if doc.get(field) else None


class UsageService:
    # shortcut: every read fetches whole days of rows (a limit check reads 8 days); add per-hour
    # sums if an account's rows per week grow into the tens of thousands.
    def __init__(self, store: DocumentStore, settings: UsageSettings, pricing: Pricing) -> None:
        self._store = store
        self._settings = settings
        self._pricing = pricing

    async def record(self, owner: str, turn_id: str, kind: str, chat_id: str | None, rows: list[dict[str, Any]]) -> int:
        """Stores one row per agent call; returns the tokens recorded."""
        now = utcnow()
        for row in rows:
            key = f"{owner}:{uuid.uuid4().hex}"
            doc = {
                **row, "id": uuid.uuid4().int >> 76,  # 52 bits: safe as a JSON number
                "key": key, "owner": owner, "turn_id": turn_id, "kind": kind, "chat_id": chat_id,
                "day": now.date().isoformat(), "created_at": now.isoformat(),
            }
            await self._store.put(COLLECTION, key, doc)
        return sum(row["total_tokens"] for row in rows)

    async def _day(self, owner: str | None, day: date) -> list[dict[str, Any]]:
        filters = {"day": day.isoformat(), **({"owner": owner} if owner else {})}
        docs: list[dict[str, Any]] = []
        while True:
            page = await self._store.query(COLLECTION, filters, limit=_PAGE, offset=len(docs))
            docs += page
            if len(page) < _PAGE:
                return docs

    async def _rows(self, owner: str | None, since: datetime) -> list[dict[str, Any]]:
        """Rows created at or after `since`, oldest first."""
        days = [since.date() + timedelta(days=n) for n in range((utcnow().date() - since.date()).days + 1)]
        docs: list[dict[str, Any]] = []
        for start in range(0, len(days), _DAYS_AT_ONCE):
            for found in await asyncio.gather(*(self._day(owner, day) for day in days[start:start + _DAYS_AT_ONCE])):
                docs += found
        kept = [doc for doc in docs if datetime.fromisoformat(doc["created_at"]) >= since]
        return sorted(kept, key=lambda doc: (doc["created_at"], doc["id"]))

    @staticmethod
    def _window(rows: list[dict[str, Any]], span: timedelta, limit: int) -> Window:
        since = utcnow() - span
        inside = [(datetime.fromisoformat(r["created_at"]), r["total_tokens"]) for r in rows]
        inside = [(at, tokens) for at, tokens in inside if at >= since]
        reset_at = min(at for at, _ in inside) + span if inside else None
        return Window(used=sum(tokens for _, tokens in inside), limit=limit, reset_at=reset_at)

    async def windows(self, owner: str) -> dict[str, Window]:
        rows = await self._rows(owner, utcnow() - WEEK)
        s = self._settings
        return {
            "six_hour": self._window(rows, SIX_HOURS, s.six_hour_token_limit),
            "weekly": self._window(rows, WEEK, s.weekly_token_limit),
        }

    async def check(self, owner: str) -> LimitBlock | None:
        """The tighter 6-hour window first, then the weekly backstop."""
        windows = await self.windows(owner)
        for key, label in (("six_hour", "6-hour"), ("weekly", "weekly")):
            window = windows[key]
            if window.limit and window.used >= window.limit and window.reset_at:
                return LimitBlock(reason=f"{label} token limit reached", reset_at=window.reset_at)
        return None

    @staticmethod
    def _filtered(rows: list[dict[str, Any]], agent: str | None, provider: str | None) -> list[dict[str, Any]]:
        return [r for r in rows if (not agent or r.get("agent") == agent) and (not provider or r.get("provider_id") == provider)]

    async def report(
        self, owner: str, days: int, since_date: date | None = None, *,
        group_by: str = "agent", agent: str | None = None, provider: str | None = None,
    ) -> dict[str, Any]:
        since, days = period_start(days, since_date)
        rows = self._filtered(await self._rows(owner, since), agent, provider)

        daily: dict[str, int] = {}
        hourly = [0] * 24  # tokens by UTC hour of day, for the busiest hour
        agents: dict[tuple[str, str], int] = {}
        agent_costs: dict[tuple[str, str], float] = {}
        total_cost: float | None = None
        unpriced_tokens = 0
        groups: dict[str, dict[str, Any]] = {}
        turns: set[str] = set()
        chats: set[str] = set()
        total = input_total = output_total = summary_total = 0
        for row in rows:
            created_at = datetime.fromisoformat(row["created_at"])
            tokens, model = row["total_tokens"], row.get("model")
            input_tokens, output_tokens = row.get("input_tokens"), row.get("output_tokens")
            day = created_at.date().isoformat()
            daily[day] = daily.get(day, 0) + tokens
            hourly[created_at.hour] += tokens
            key = (row.get("agent") or "unknown", model or "")
            agents[key] = agents.get(key, 0) + tokens
            cost = self._pricing.cost(model, input_tokens, output_tokens)
            if cost is None:
                unpriced_tokens += tokens
            else:
                total_cost = (total_cost or 0) + cost
                agent_costs[key] = agent_costs.get(key, 0) + cost
            group_key = {
                "agent": row.get("agent"), "provider": row.get("provider_id"),
                "gateway": row.get("gateway"), "model": model,
            }[group_by] or "unknown"
            group = groups.setdefault(
                group_key, {"key": group_key, "tokens": 0, "input_tokens": 0, "output_tokens": 0, "turns": set(), "cost": None}
            )
            if cost is not None:
                group["cost"] = (group["cost"] or 0) + cost
            group["tokens"] += tokens
            group["input_tokens"] += input_tokens or 0
            group["output_tokens"] += output_tokens or 0
            group["turns"].add(row["turn_id"])
            if row["kind"] == "summary":
                summary_total += tokens
            else:
                turns.add(row["turn_id"])
            if row.get("chat_id"):
                chats.add(row["chat_id"])
            total += tokens
            input_total += input_tokens or 0
            output_total += output_tokens or 0

        return {
            "days": days, "since": since, "total_tokens": total, "total_cost": total_cost,
            "currency": self._pricing.currency, "unpriced_tokens": unpriced_tokens,
            "input_tokens": input_total, "output_tokens": output_total, "summary_tokens": summary_total,
            "turns": len(turns), "chats": len(chats),
            "by_agent": [
                {"agent": name, "model": model, "tokens": tokens, "cost": agent_costs.get((name, model))}
                for (name, model), tokens in sorted(agents.items(), key=lambda item: -item[1])
            ],
            "group_by": group_by,
            "groups": [{**g, "turns": len(g["turns"])} for g in sorted(groups.values(), key=lambda g: -g["tokens"])],
            "daily": [{"date": day, "tokens": tokens} for day, tokens in sorted(daily.items())],
            "hourly": hourly,
        }

    async def records(
        self, owner: str, days: int, since_date: date | None = None, *,
        agent: str | None = None, provider: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """This account's usage rows, newest first, with when each agent's call ran."""
        since, _ = period_start(days, since_date)
        rows = self._filtered(await self._rows(owner, since), agent, provider)
        return [
            {
                "id": r["id"], "turn_id": r["turn_id"], "kind": r["kind"], "chat_id": r.get("chat_id"),
                "agent": r.get("agent"), "agent_id": r.get("agent_id"), "provider_id": r.get("provider_id"),
                "gateway": r.get("gateway"), "model": r.get("model"), "input_tokens": r.get("input_tokens"),
                "output_tokens": r.get("output_tokens"), "total_tokens": r["total_tokens"],
                "started_at": _when(r, "started_at"), "finished_at": _when(r, "finished_at"),
                "delegated_by": r.get("delegated_by"), "created_at": _when(r, "created_at"),
                "cost": self._pricing.cost(r.get("model"), r.get("input_tokens"), r.get("output_tokens")),
            }
            for r in reversed(rows)
        ][:limit]

    async def all_accounts(self, days: int, since_date: date | None = None) -> list[dict[str, Any]]:
        """Totals of every account that used tokens in the period, busiest first."""
        since, _ = period_start(days, since_date)
        totals: dict[str, dict[str, Any]] = {}
        for row in await self._rows(None, since):
            entry = totals.setdefault(row["owner"], {"uid": row["owner"], "tokens": 0, "turn_ids": set(), "last_used_at": None})
            entry["tokens"] += row["total_tokens"]
            if row["kind"] != "summary":
                entry["turn_ids"].add(row["turn_id"])
            entry["last_used_at"] = _when(row, "created_at")  # rows come oldest first
        return sorted(
            ({"uid": e["uid"], "tokens": e["tokens"], "turns": len(e["turn_ids"]), "last_used_at": e["last_used_at"]}
             for e in totals.values()),
            key=lambda e: -e["tokens"],
        )

    async def purge_owner(self, owner: str) -> int:
        """Delete every row of one account (used when the account is deleted). Returns the count."""
        removed = 0
        for _ in range(_PURGE_MAX_PAGES):
            docs = await self._store.query(COLLECTION, {"owner": owner}, limit=_PAGE)
            if not docs:
                break
            for doc in docs:
                removed += await self._store.delete(COLLECTION, doc["key"])
        return removed
