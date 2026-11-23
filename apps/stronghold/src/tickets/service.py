"""Support tickets: validation, automatic-report guards, tagging, Triage grouping and priority elevation.
Keeps filing when Triage is down (skips grouping and tagging); ticket text is never logged."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from weakref import WeakValueDictionary

from pathlib import Path

from src.agents.gateway import Caller
from src.redact import redact
from src.tickets import rules, settings
from src.tickets.classifier import ClassifierUnavailable, TicketClassifier
from src.tickets.config import TicketConfig, load_ticket_config
from src.tickets.store import AutoLimit, CommentLimit, TicketStore

logger = logging.getLogger(__name__)

TITLE_MAX = 120
DESCRIPTION_MAX = 4000
COMMENT_MAX = 2000
_CONTEXT_LIMITS = {"chat_id": 200, "agent": 100, "tool_name": 100, "error_text": 2000}
_VERIFIED_MAX_CHARS = 200


class TicketError(ValueError):
    """A request tickets cannot honour; the message is safe to show a user or model."""


class TicketNotFound(LookupError):
    """No such ticket or group, or not visible to the requester."""


@dataclass(frozen=True)
class CreateOutcome:
    ticket: dict[str, Any]
    duplicate: bool
    group_size: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any, name: str, limit: int) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise TicketError(f"The {name} is required.")
    if len(clean) > limit:
        raise TicketError(f"The {name} is {len(clean)} characters; the limit is {limit}.")
    return clean


def _reported_context(context: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, limit in _CONTEXT_LIMITS.items():
        value = (context or {}).get(key)
        if value:
            result[key] = redact(str(value))[0][:limit]
    return result


def _verified_context(context: dict[str, Any] | None) -> dict[str, str]:
    return {str(key)[:50]: str(value)[:_VERIFIED_MAX_CHARS] for key, value in list((context or {}).items())[:10]}


class TicketService:
    def __init__(self, store: TicketStore, config: TicketConfig, classifier: TicketClassifier | None = None,
                 *, clock: Callable[[], datetime] | None = None, settings_path: Path | None = None) -> None:
        self._store = store
        self._config = config
        self._settings_path = settings_path
        self._classifier = classifier
        self._settings_lock = asyncio.Lock()
        self._owner_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._clock = clock or _utc_now

    async def tag_options(self, owner: str) -> list[dict[str, str]]:
        """Configured vocabulary and tags used on this owner's own tickets."""
        options = [{"value": tag, "label": tag, "description": description} for tag, description in self._config.tags.items()]
        custom = await self._store.owner_tags(owner)
        options.extend({"value": tag, "label": tag, "description": "A tag from your tickets."} for tag in custom if tag not in self._config.tags)
        return options

    def settings_document(self) -> dict[str, Any]:
        return self._config.document()

    async def update_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Change ticket settings: top-level keys in `changes` replace the current ones, `laya` merges key by key.
        Validated as a whole, saved to the settings store, and used by the next ticket."""
        if not isinstance(changes, dict) or not changes:
            raise TicketError("Send at least one setting to change.")
        async with self._settings_lock:
            document = self._config.document()
            unknown = set(changes) - set(document)
            if unknown:
                raise TicketError(f"Unknown setting: {', '.join(sorted(unknown))}.")
            document.update({key: value for key, value in changes.items() if key != "laya"})
            if "laya" in changes:
                if not isinstance(changes["laya"], dict):
                    raise TicketError("laya must be an object.")
                document["laya"] = {**document["laya"], **changes["laya"]}
            try:
                config = load_ticket_config(document)
            except ValueError as error:
                raise TicketError(str(error)) from error
            if self._settings_path is not None:
                await asyncio.to_thread(settings.save, self._settings_path, config)
            self._config = config
            if self._classifier is not None:
                self._classifier.tune(min_confidence=config.laya_min_confidence, timeout=config.laya_timeout_seconds)
            return config.document()

    def _now(self) -> datetime:
        return self._clock()

    # ---- create -------------------------------------------------------

    async def create(
        self, *, owner: str, reporter: str = "", type: str, title: str, description: str, source: str = "user",
        tags: list[str] | None = None, context: dict[str, Any] | None = None,
        verified_context: dict[str, Any] | None = None, caller: Caller | None = None,
    ) -> CreateOutcome:
        """File a ticket. `owner` is the account's stable uid and decides who can see it; `reporter` is
        only the name shown to staff (it falls back to the owner) and may change later."""
        owner = str(owner or "").strip()
        if not owner:
            raise TicketError("No signed-in reporter is known for this request, so a ticket cannot be filed.")
        async with self._owner_lock(owner):
            reporter = str(reporter or "").strip() or owner
            if type not in rules.TYPES:
                raise TicketError(f"The type must be one of: {', '.join(rules.TYPES)}.")
            if source not in rules.SOURCES:
                raise TicketError(f"The source must be one of: {', '.join(rules.SOURCES)}.")
            title = _text(title, "title", TITLE_MAX)
            description = _text(description, "description", DESCRIPTION_MAX)
            reported = _reported_context(context)
            if source != "user":  # written by a model from tool output: never store secrets
                title, description = redact(title)[0], redact(description)[0]

            fingerprint = None
            if source == "ai_auto":
                fingerprint = rules.fingerprint(reported.get("tool_name"), reported.get("error_text") or title)
                existing = await self._store.find_open_auto(owner, fingerprint)
                if existing:
                    return await self._outcome(existing, duplicate=True)
                if self._classifier is not None and caller is not None:
                    tool = reported.get("tool_name")
                    error = reported.get("error_text")
                    if not tool or not error:
                        raise TicketError("Automatic reports need the tool name and error text.")
                    try:
                        reportable = await self._classifier.reportable_failure(caller, tool, error)
                    except ClassifierUnavailable:
                        raise TicketError("Automatic report could not be classified. Report it manually if needed.") from None
                    if not reportable:
                        raise TicketError("Automatic reports require evidence of a tool bug or configuration issue.")

            draft = {"type": type, "title": title, "description": description}
            try:
                tag_list = rules.clean_tags(tags, self._config.tags, allow_custom=source == "user")
            except ValueError as error:
                raise TicketError(str(error)) from None
            group_id = possible = None
            priority = "normal"
            if self._classifier is not None and caller is not None:
                try:
                    priority = await self._classifier.pick_priority(caller, draft)
                except ClassifierUnavailable:
                    pass
                try:
                    tagged = tag_list or await self._classifier_tag(caller, draft)
                    if tagged:
                        group_id, possible = await self._match_group(caller, draft, tagged)
                        if possible is None:
                            tag_list = tagged
                except ClassifierUnavailable:
                    logger.warning("Ticket classification skipped: Triage is unavailable.")

            now = self._now()
            try:
                ticket_id, created, group_id = await self._store.insert_ticket(owner=owner, reporter=reporter, type=type, title=title, description=description,
                    source=source, tags=tag_list, priority=priority,
                    context={"reported": reported, "verified": _verified_context(verified_context)},
                    fingerprint=fingerprint, group_id=group_id, possible_group_id=possible, now=now.isoformat(),
                    auto_cap=self._config.auto_hourly_cap if source == "ai_auto" else None,
                    auto_since=(now - timedelta(hours=1)).isoformat(),
                )
            except AutoLimit:
                raise TicketError(
                    f"Too many automatic reports from this account in the last hour "
                    f"(limit {self._config.auto_hourly_cap}); not filing another one."
                ) from None
            if created:
                await self._reelevate(group_id)
            return await self._outcome(ticket_id, duplicate=not created)

    async def _outcome(self, ticket_id: int, *, duplicate: bool) -> CreateOutcome:
        ticket = await self._store.get_ticket(ticket_id)
        total, _ = await self._store.group_counts(ticket["group_id"], self._since())
        return CreateOutcome(ticket=ticket, duplicate=duplicate, group_size=total)

    def _since(self) -> str:
        return (self._now() - timedelta(hours=self._config.recent_hours)).isoformat()

    async def _classifier_tag(self, caller: Caller, draft: dict[str, Any]) -> list[str]:
        try:
            tag = await self._classifier.pick_tag(caller, draft, self._config.tags)
        except Exception as error:
            raise ClassifierUnavailable("Ticket tag unavailable") from error
        return [tag] if tag else []

    async def _match_group(self, caller: Caller, draft: dict[str, Any], tags: list[str]) -> tuple[int | None, int | None]:
        candidates = await self._store.candidates(draft["type"], tags, self._config.laya_candidates)
        possible: int | None = None
        for candidate in candidates:
            try:
                verdict = await self._classifier.same_issue(caller, draft, candidate)
            except Exception as error:
                raise ClassifierUnavailable("Ticket group unavailable") from error
            if verdict == "yes":
                return candidate["group_id"], None
            if verdict == "uncertain" and possible is None:
                possible = candidate["group_id"]
        return None, possible

    async def _reelevate(self, group_id: int) -> None:
        """Raise the group's priority from its size and recent rate unless an admin pinned it."""
        group = await self._store.get_group(group_id)
        if group is None or group["priority_pinned"]:
            return
        total, recent = await self._store.group_counts(group_id, self._since())
        raised = rules.elevated_priority(group["priority"], total, recent, self._config.elevation)
        if raised != group["priority"]:
            await self._store.elevate_group(group_id, raised, self._now().isoformat())


    # ---- reads --------------------------------------------------------

    async def _visible(self, ticket_id: int, owner: str | None) -> dict[str, Any]:
        ticket = await self._store.get_ticket(ticket_id)
        # Someone else's ticket looks exactly like a missing one.
        if ticket is None or (owner is not None and ticket["owner"] != owner):
            raise TicketNotFound(f"No ticket {ticket_id}.")
        return ticket

    async def _with_comments(self, ticket_id: int, owner: str | None = None) -> dict[str, Any]:
        ticket = await self._visible(ticket_id, owner)
        ticket["comments"] = await self._store.list_comments(ticket_id)
        return ticket

    async def get_ticket(self, ticket_id: int, *, owner: str | None = None) -> dict[str, Any]:
        return await self._with_comments(ticket_id, owner)

    @staticmethod
    def _check(value: str | None, allowed: tuple[str, ...], name: str) -> None:
        if value is not None and value not in allowed:
            raise TicketError(f"The {name} must be one of: {', '.join(allowed)}.")

    async def list_tickets(
        self, *, owner: str | None = None, status: str | None = None, type: str | None = None,
        tag: str | None = None, priority: str | None = None, assignee: str | None = None,
        group_id: int | None = None, possible_only: bool = False, limit: int | None = 100,
    ) -> list[dict[str, Any]]:
        if limit is None and not owner:
            raise TicketError("An owner is required for an unbounded ticket list.")
        self._check(status, rules.STATUSES, "status")
        self._check(type, rules.TYPES, "type")
        self._check(priority, rules.PRIORITIES, "priority")
        return await self._store.list_tickets(owner=owner, status=status, type=type, tag=tag, priority=priority,
            assignee=assignee, group_id=group_id, possible_only=possible_only,
            limit=None if limit is None else max(1, min(limit, 500)),
        )

    async def list_groups(
        self, *, status: str | None = None, tag: str | None = None, priority: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._check(status, rules.STATUSES, "status")
        self._check(priority, rules.PRIORITIES, "priority")
        return await self._store.list_groups(since=self._since(), status=status, tag=tag, priority=priority,
            limit=max(1, min(limit, 500)),
        )

    async def stats(self) -> dict[str, int]:
        return await self._store.stats()

    # ---- changes ------------------------------------------------------

    async def add_comment(
        self, ticket_id: int, *, author: str, role: str, body: str, owner: str | None = None,
    ) -> dict[str, Any]:
        await self._visible(ticket_id, owner)
        self._check(role, ("reporter", "staff", "ai"), "role")
        text = _text(body, "comment", COMMENT_MAX)
        if role == "ai":
            text = redact(text)[0]
        try:
            saved = await self._store.add_comment(ticket_id, author, role, text, self._now().isoformat())
        except CommentLimit:
            raise TicketError("This ticket has the most comments it can hold.") from None
        if saved is None:
            raise TicketNotFound(f"No ticket {ticket_id}.")
        return await self._with_comments(ticket_id)

    async def close_own(self, ticket_id: int, owner: str) -> dict[str, Any]:
        await self._visible(ticket_id, owner)
        await self._store.update_ticket(ticket_id, {"status": "closed"}, self._now().isoformat())
        return await self._with_comments(ticket_id)

    async def reopen_own(self, ticket_id: int, owner: str) -> dict[str, Any]:
        owner = str(owner or "").strip()
        if not owner:
            raise TicketError("No requester id was sent for this request.")
        try:
            reopened = await self._store.reopen_own(ticket_id, owner, self._now().isoformat())
        except CommentLimit:
            raise TicketError("This ticket has the most comments it can hold.") from None
        if reopened is None:
            raise TicketNotFound(f"No ticket {ticket_id}.")
        if not reopened:
            raise TicketError("Only resolved or closed tickets can be reopened.")
        return await self._with_comments(ticket_id)

    async def update_ticket(
        self, ticket_id: int, *, status: str | None = None, priority: str | None = None,
        assignee: str | None = None, tags: list[str] | None = None,
    ) -> dict[str, Any]:
        self._check(status, rules.STATUSES, "status")
        self._check(priority, rules.PRIORITIES, "priority")
        await self._visible(ticket_id, None)
        changes: dict[str, Any] = {}
        if status is not None:
            changes["status"] = status
        if priority is not None:
            changes["priority"] = priority
        if assignee is not None:
            if not isinstance(assignee, str):
                raise TicketError("The assignee must be a username string or null.")
            changes["assignee"] = assignee.strip() or None
        if tags is not None:
            try:
                changes["tags"] = rules.clean_tags(tags, self._config.tags, allow_custom=True)
            except ValueError as error:
                raise TicketError(str(error)) from None
        if changes:
            await self._store.update_ticket(ticket_id, changes, self._now().isoformat(), staff_activity=True)
        return await self._with_comments(ticket_id)

    async def move_ticket(self, ticket_id: int, group_id: int | None) -> dict[str, Any]:
        await self._visible(ticket_id, None)
        target = await self._store.move_ticket(ticket_id, group_id, self._now().isoformat())
        if target is None:
            raise TicketNotFound(f"No group {group_id}.")
        await self._reelevate(target)
        return await self._with_comments(ticket_id)

    async def set_group_priority(
        self, group_id: int, *, priority: str | None = None, pinned: bool | None = None,
    ) -> dict[str, Any]:
        self._check(priority, rules.PRIORITIES, "priority")
        if await self._store.get_group(group_id) is None:
            raise TicketNotFound(f"No group {group_id}.")
        if priority is not None and pinned is None:
            pinned = True  # a hand-set priority is pinned until an admin unpins it
        await self._store.update_group(group_id, priority=priority, pinned=pinned, now=self._now().isoformat())
        if pinned is False:
            await self._reelevate(group_id)
        return await self._store.get_group(group_id)

    def _owner_lock(self, owner: str) -> asyncio.Lock:
        lock = self._owner_locks.get(owner)
        if lock is None:
            lock = asyncio.Lock()
            self._owner_locks[owner] = lock
        return lock

    async def purge_owner(self, owner: str) -> int:
        async with self._owner_lock(owner):
            return await self._store.purge_owner(owner)
