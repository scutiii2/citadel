"""Token usage: recording, the rolling 6-hour and weekly limits, and the reports of the Usage page.

One document per agent call in the "usage_records" collection (key `<uid>:<random>`). Treasury
filters on equality only, so each row carries its UTC `day` and a read fetches the days it needs.
Times are naive UTC; the browser shows local time.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from src.clock import utcnow
from src.document_store import DocumentStore
from src.schema.models import UsageRecordDoc, checked
from src.usage.allowance import Allowance, NothingToReset, Reset, ResetNotFound
from src.usage.allowances import AllowanceStore
from src.usage.settings import Pricing, UsageSettings

COLLECTION = "usage_records"
SIX_HOURS = timedelta(hours=6)
WEEK = timedelta(days=7)
MAX_REPORT_DAYS = 366
_PAGE = 500
_DAYS_AT_ONCE = 16
_PURGE_MAX_PAGES = 200


LABELS = {"six_hour": "6-hour", "weekly": "weekly"}


@dataclass(frozen=True)
class LimitBlock:
    reason: str
    reset_at: datetime
    resettable: bool = False  # an unused free reset could unblock the account


@dataclass(frozen=True)
class Window:
    used: int  # counted tokens
    limit: int  # effective; 0 = unlimited
    reset_at: datetime | None
    base_limit: int = 0
    boost: dict[str, Any] | None = None


@dataclass(frozen=True)
class Admission:
    block: LimitBlock | None  # None: the question may go on
    spend: tuple[Reset, ...] = ()  # automatic use is on and these would unblock it


@dataclass(frozen=True)
class Admitted:
    block: LimitBlock | None
    notice: str | None = None  # what was spent, to tell the user


def counted_tokens(row: dict[str, Any], weight: float) -> int:
    """A row's tokens as the limits count them: cached input only at `weight`."""
    total = row["total_tokens"]
    cached = min(row.get("cached_input_tokens") or 0, total)
    return total - math.floor(cached * (1 - weight))


def spent_notice(resets: tuple[Reset, ...]) -> str:
    if len(resets) == 2:
        return "Free 6-hour and weekly resets were used so this question could run."
    word = "6-hour and weekly" if resets[0].kind == "both" else LABELS[resets[0].kind]
    return f"A free {word} reset was used so this question could run."


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
        self.allowances = AllowanceStore(store)
        self._admitting: dict[str, asyncio.Lock] = {}

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
            await self._store.put(COLLECTION, key, checked(UsageRecordDoc, doc))
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

    def _window(self, rows: list[dict[str, Any]], name: str, span: timedelta, base: int,
                allowance: Allowance, now: datetime) -> Window:
        since, cleared = now - span, allowance.cleared[name]
        inside = [(datetime.fromisoformat(r["created_at"]), r) for r in rows]
        inside = [(at, r) for at, r in inside if at >= since and (cleared is None or at > cleared)]
        boost = allowance.boost(name, now) if base else None
        return Window(
            used=sum(counted_tokens(r, self._settings.cached_token_weight) for _, r in inside),
            limit=allowance.limit(name, base, now),
            reset_at=min(at for at, _ in inside) + span if inside else None,
            base_limit=base,
            boost={"percent": boost.percent, "ends_at": boost.ends_at} if boost else None,
        )

    async def windows(self, owner: str, allowance: Allowance | None = None) -> dict[str, Window]:
        now = utcnow()
        rows = await self._rows(owner, now - WEEK)
        allowance = allowance or await self.allowances.read(owner)
        s = self._settings
        return {
            "six_hour": self._window(rows, "six_hour", SIX_HOURS, s.six_hour_token_limit, allowance, now),
            "weekly": self._window(rows, "weekly", WEEK, s.weekly_token_limit, allowance, now),
        }

    async def overview(self, owner: str) -> dict[str, Any]:
        """The windows, unused resets and switch, as the account's own page shows them."""
        allowance = await self.allowances.read(owner)
        windows = await self.windows(owner, allowance)
        return {
            **{name: asdict(window) for name, window in windows.items()},
            "resets": [asdict(reset) for reset in allowance.live_resets(utcnow())],
            "auto_use": allowance.auto_use,
            "cached_token_weight": self._settings.cached_token_weight,
        }

    async def admission(self, owner: str) -> Admission:
        """Whether a question may go on. The tighter 6-hour window is named first. Changes nothing."""
        allowance = await self.allowances.read(owner)
        windows = await self.windows(owner, allowance)
        blocked = [name for name, w in windows.items() if w.limit and w.used >= w.limit and w.reset_at]
        if not blocked:
            return Admission(None)
        plan = allowance.plan(blocked, utcnow())
        block = LimitBlock(f"{LABELS[blocked[0]]} token limit reached", windows[blocked[0]].reset_at, bool(plan))
        return Admission(block, plan if allowance.auto_use else ())

    async def check(self, owner: str) -> LimitBlock | None:
        return (await self.admission(owner)).block

    async def admit(self, owner: str) -> Admitted:
        """`admission`, spending the account's resets when it asked for that. Saved before the question goes on."""
        async with self._admitting.setdefault(owner, asyncio.Lock()):
            admission = await self.admission(owner)
            if admission.block is None or not admission.spend:
                return Admitted(admission.block)
            now = utcnow()
            try:
                async with self.allowances.change(owner, now) as allowance:
                    for reset in admission.spend:
                        allowance.use(reset.id, now)
            except ResetNotFound:  # removed or expired just now: nothing was saved
                return Admitted((await self.admission(owner)).block)
            return Admitted((await self.admission(owner)).block, spent_notice(admission.spend))

    async def use_reset(self, owner: str, reset_id: str) -> None:
        async with self._admitting.setdefault(owner, asyncio.Lock()):
            now = utcnow()
            async with self.allowances.change(owner, now) as allowance:
                reset = allowance.find(reset_id, now)
                windows = await self.windows(owner, allowance)
                if not any(windows[name].used for name in reset.covers):
                    raise NothingToReset()
                allowance.use(reset_id, now)

    async def set_auto_use(self, owner: str, enabled: bool) -> None:
        async with self.allowances.change(owner, utcnow()) as allowance:
            allowance.auto_use = enabled

    async def grant(self, owner: str, kind: str, count: int, expires_at: datetime | None) -> None:
        now = utcnow()
        async with self.allowances.change(owner, now) as allowance:
            allowance.grant(kind, count, expires_at, now)

    async def clear(self, owner: str, windows: tuple[str, ...]) -> None:
        now = utcnow()
        async with self.allowances.change(owner, now) as allowance:
            allowance.clear(windows, now)

    async def boost(self, owner: str, windows: tuple[str, ...], percent: int, ends_at: datetime) -> None:
        now = utcnow()
        async with self.allowances.change(owner, now) as allowance:
            allowance.add_boost(windows, percent, ends_at, now)

    async def remove_reset(self, owner: str, reset_id: str) -> None:
        async with self.allowances.change(owner, utcnow()) as allowance:
            allowance.remove_reset(reset_id)

    async def remove_boost(self, owner: str, boost_id: str) -> None:
        async with self.allowances.change(owner, utcnow()) as allowance:
            allowance.remove_boost(boost_id)

    async def allowance_list(self) -> list[dict[str, Any]]:
        now = utcnow()
        return [{"uid": a.owner, "auto_use": a.auto_use,
                 "resets": [asdict(r) for r in a.live_resets(now)], "boosts": [asdict(b) for b in a.live_boosts(now)]}
                for a in await self.allowances.all()]

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
        await self.allowances.delete(owner)
        removed = 0
        for _ in range(_PURGE_MAX_PAGES):
            docs = await self._store.query(COLLECTION, {"owner": owner}, limit=_PAGE)
            if not docs:
                break
            for doc in docs:
                removed += await self._store.delete(COLLECTION, doc["key"])
        return removed
