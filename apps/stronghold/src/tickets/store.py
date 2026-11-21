"""Support ticket storage in Treasury documents."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from src.document_store import DbGatewayError, Document, DocumentStore
from src.tickets import rules

TICKETS = "tickets"
GROUPS = "ticket_groups"
COUNTERS = "ticket_counters"
MAX_COMMENTS = 100
_PAGE = 500
_CLOSED = {"resolved", "closed"}
_UPDATABLE = {"status", "priority", "assignee", "tags"}


class AutoLimit(Exception):
    """The owner reached the cap for automatic tickets."""


class CommentLimit(Exception):
    """The ticket cannot hold another comment."""


def _ticket(doc: Document, group: Document) -> Document:
    result = {k: v for k, v in doc.items() if k not in {"fingerprint", "comments"}}
    return dict(result, group_priority=group["priority"], group_pinned=group["priority_pinned"],
                effective_priority=rules.higher_priority(doc["priority"], group["priority"]))


def _staff(doc: Document, now: str) -> str:
    return max(doc["last_staff_activity_at"] or now, now)


# shortcut: one lock per process; add a version field and a retry if Stronghold ever runs more than one replica.
class TicketStore:
    def __init__(self, docs: DocumentStore) -> None:
        self._docs = docs
        self._lock = asyncio.Lock()

    async def _scan(self, collection: str, **filters: Any) -> AsyncIterator[Document]:
        offset = 0
        while True:
            page = await self._docs.query(collection, filters, limit=_PAGE, offset=offset)
            for doc in page:
                yield doc
            if len(page) < _PAGE:
                return
            offset += len(page)

    async def _allocate(self, collection: str, doc: Document) -> int:
        counter = await self._docs.get(COUNTERS, collection)
        last = counter["last"] if counter else 0
        for number in range(last + 1, last + 51):
            if await self._docs.create(collection, str(number), dict(doc, id=number)):
                await self._docs.put(COUNTERS, collection, {"key": collection, "last": number})
                return number
        raise DbGatewayError(f"Could not allocate an id in {collection}")

    async def _new_group(self, title: str, now: str) -> int:
        return await self._allocate(GROUPS, {"title": title[:120], "priority": "normal",
                                            "priority_pinned": False, "created_at": now, "updated_at": now})

    async def _open_auto(self, owner: str, fingerprint: str) -> Document | None:
        return max(
            [doc async for doc in self._scan(TICKETS, owner=owner, fingerprint=fingerprint)
             if doc["status"] not in _CLOSED],
            key=lambda doc: doc["id"], default=None,
        )

    async def insert_ticket(
        self, *, owner: str, reporter: str, type: str, title: str, description: str, source: str, tags: list[str],
        context: dict[str, Any], fingerprint: str | None, group_id: int | None,
        possible_group_id: int | None, now: str, auto_cap: int | None = None, auto_since: str | None = None,
    ) -> tuple[int, bool, int]:
        async with self._lock:
            if source == "ai_auto":
                existing = await self._open_auto(owner, fingerprint) if fingerprint else None
                if existing is not None:
                    return existing["id"], False, existing["group_id"]
                if auto_cap is not None:
                    count = 0
                    async for doc in self._scan(TICKETS, owner=owner, source=source):
                        count += doc["created_at"] >= (auto_since or "")
                    if count >= auto_cap:
                        raise AutoLimit()
            if group_id is None:
                group_id = await self._new_group(title, now)
            else:
                group = await self.get_group(group_id)
                if group is None:
                    raise DbGatewayError("Ticket group is missing")
                await self._docs.put(GROUPS, str(group_id), dict(group, updated_at=now))
            doc = dict(group_id=group_id, type=type, title=title, description=description, owner=owner,
                       reporter=reporter, source=source, tags=tags, context=context, fingerprint=fingerprint,
                       possible_group_id=possible_group_id, created_at=now, updated_at=now, status="open",
                       priority="normal", assignee=None, closed_at=None, last_staff_activity_at=None, comments=[])
            return await self._allocate(TICKETS, doc), True, group_id

    @staticmethod
    def _append(doc: Document, author: str, role: str, body: str, now: str) -> int:
        comments = doc["comments"]
        if len(comments) >= MAX_COMMENTS:
            raise CommentLimit()
        number = len(comments) + 1
        comments.append(dict(id=number, ticket_id=doc["id"], author=author, author_role=role, body=body, created_at=now))
        doc["updated_at"] = now
        if role == "staff":
            doc["last_staff_activity_at"] = _staff(doc, now)
        return number

    async def add_comment(self, ticket_id: int, author: str, role: str, body: str, now: str) -> int | None:
        async with self._lock:
            doc = await self._docs.get(TICKETS, str(ticket_id))
            if doc is None:
                return None
            number = self._append(doc, author, role, body, now)
            await self._docs.put(TICKETS, str(ticket_id), doc)
            return number

    async def update_ticket(self, ticket_id: int, changes: Document, now: str, *, staff_activity: bool = False) -> bool:
        unknown = changes.keys() - _UPDATABLE
        if unknown:
            raise ValueError(f"Cannot change: {', '.join(sorted(unknown))}")
        async with self._lock:
            doc = await self._docs.get(TICKETS, str(ticket_id))
            if doc is None:
                return False
            doc.update(changes, updated_at=now)
            if "status" in changes:
                doc["closed_at"] = now if doc["status"] in _CLOSED else None
            if staff_activity:
                doc["last_staff_activity_at"] = _staff(doc, now)
            await self._docs.put(TICKETS, str(ticket_id), doc)
            return True

    async def reopen_own(self, ticket_id: int, owner: str, now: str) -> bool | None:
        async with self._lock:
            doc = await self._docs.get(TICKETS, str(ticket_id))
            if doc is None or doc["owner"] != owner:
                return None
            if doc["status"] not in _CLOSED:
                return False
            self._append(doc, "System", "system", "Ticket reopened by the reporter.", now)
            doc.update(status="open", closed_at=None)
            await self._docs.put(TICKETS, str(ticket_id), doc)
            return True

    async def move_ticket(self, ticket_id: int, group_id: int | None, now: str) -> int | None:
        async with self._lock:
            doc = await self._docs.get(TICKETS, str(ticket_id))
            if doc is None:
                return None
            if group_id is None:
                group_id = await self._new_group(doc["title"], now)
            else:
                group = await self.get_group(group_id)
                if group is None:
                    return None
                await self._docs.put(GROUPS, str(group_id), dict(group, updated_at=now))
            await self._docs.put(TICKETS, str(ticket_id), dict(doc, group_id=group_id, possible_group_id=None,
                                 updated_at=now, last_staff_activity_at=_staff(doc, now)))
            return group_id

    async def update_group(self, group_id: int, *, priority: str | None = None,
                           pinned: bool | None = None, now: str) -> bool:
        async with self._lock:
            group = await self.get_group(group_id)
            if group is None:
                return False
            if priority is not None:
                group["priority"] = priority
            if pinned is not None:
                group["priority_pinned"] = pinned
            await self._docs.put(GROUPS, str(group_id), dict(group, updated_at=now))
            return True

    async def elevate_group(self, group_id: int, priority: str, now: str) -> bool:
        async with self._lock:
            group = await self.get_group(group_id)
            if (group is None or group["priority_pinned"]
                    or rules.priority_rank(priority) <= rules.priority_rank(group["priority"])):
                return False
            await self._docs.put(GROUPS, str(group_id), dict(group, priority=priority, updated_at=now))
            return True

    async def owner_tags(self, owner: str) -> list[str]:
        return sorted({tag async for doc in self._scan(TICKETS, owner=owner) for tag in doc["tags"]})

    async def find_open_auto(self, owner: str, fingerprint: str) -> int | None:
        doc = await self._open_auto(owner, fingerprint)
        return doc["id"] if doc is not None else None

    async def get_ticket(self, ticket_id: int) -> Document | None:
        doc = await self._docs.get(TICKETS, str(ticket_id))
        if doc is None:
            return None
        group = await self.get_group(doc["group_id"])
        return _ticket(doc, group) if group is not None else None

    async def _project(self, docs: list[Document], limit: int | None, priority: str | None = None) -> list[Document]:
        if limit == 0:
            return []
        groups: dict[int, Document | None] = {}
        tickets = []
        for doc in sorted(docs, key=lambda item: item["id"], reverse=True):
            group_id = doc["group_id"]
            if group_id not in groups:
                groups[group_id] = await self.get_group(group_id)
            if groups[group_id] is not None:
                ticket = _ticket(doc, groups[group_id])
                if not priority or ticket["effective_priority"] == priority:
                    tickets.append(ticket)
                    if limit is not None and 0 < limit <= len(tickets):
                        break
        return tickets

    async def list_tickets(
        self, *, owner: str | None = None, status: str | None = None, type: str | None = None,
        tag: str | None = None, priority: str | None = None, assignee: str | None = None,
        group_id: int | None = None, possible_only: bool = False, limit: int | None = 100,
    ) -> list[Document]:
        if limit is None and not owner:
            raise ValueError("An owner is required for an unbounded ticket list.")
        filters = {key: val for key, val in dict(owner=owner, status=status, type=type,
                   assignee=assignee, group_id=group_id).items() if val}
        docs = [doc async for doc in self._scan(TICKETS, **filters)
                if (not tag or tag in doc["tags"]) and (not possible_only or doc["possible_group_id"] is not None)]
        return await self._project(docs, limit, priority)

    async def candidates(self, type: str, tags: list[str], limit: int) -> list[Document]:
        latest: dict[int, Document] = {}
        async for doc in self._scan(TICKETS, type=type):
            prior = latest.get(doc["group_id"])
            if doc["status"] not in _CLOSED and (prior is None or doc["id"] > prior["id"]):
                latest[doc["group_id"]] = doc
        wanted = set(tags)
        return await self._project([doc for doc in latest.values() if not wanted or wanted.intersection(doc["tags"])], limit)

    async def list_comments(self, ticket_id: int) -> list[Document]:
        doc = await self._docs.get(TICKETS, str(ticket_id))
        return doc["comments"] if doc is not None else []

    async def get_group(self, group_id: int) -> Document | None:
        return await self._docs.get(GROUPS, str(group_id))

    async def group_counts(self, group_id: int, since: str) -> tuple[int, int]:
        total = recent = 0
        async for doc in self._scan(TICKETS, group_id=group_id):
            total += 1
            recent += doc["created_at"] >= since
        return total, recent

    # shortcut: staff-only reads scan every ticket; add per-status counters if there are ever tens of thousands.
    async def list_groups(
        self, *, since: str, status: str | None = None, tag: str | None = None,
        priority: str | None = None, limit: int = 100,
    ) -> list[Document]:
        by_group: dict[int, list[Document]] = defaultdict(list)
        async for doc in self._scan(TICKETS):
            by_group[doc["group_id"]].append(doc)
        groups = []
        async for group in self._scan(GROUPS, **({"priority": priority} if priority else {})):
            docs = by_group.get(group["id"])
            if not docs or (status and not any(doc["status"] == status for doc in docs)):
                continue
            tags = sorted({value for doc in docs for value in doc["tags"]})
            if tag and tag not in tags:
                continue
            groups.append(dict(group, ticket_count=len(docs), recent_count=sum(doc["created_at"] >= since for doc in docs),
                               open_count=sum(doc["status"] not in _CLOSED for doc in docs),
                               last_activity=max(doc["updated_at"] for doc in docs), tags=tags))
        return sorted(groups, key=lambda group: (group["last_activity"], group["id"]), reverse=True)[:None if limit < 0 else limit]

    async def stats(self) -> dict[str, int]:
        opened = urgent = 0
        groups = set()
        urgent_groups = {g["id"] async for g in self._scan(GROUPS, priority="urgent")}
        async for doc in self._scan(TICKETS):
            if doc["status"] not in _CLOSED:
                opened += 1
                urgent += doc["priority"] == "urgent" or doc["group_id"] in urgent_groups
                groups.add(doc["group_id"])
        return {"open": opened, "urgent": urgent, "groups": len(groups)}

    async def purge_owner(self, owner: str) -> int:
        async with self._lock:
            removed = 0
            while page := await self._docs.query(TICKETS, {"owner": owner}, limit=_PAGE):
                for doc in page:
                    removed += await self._docs.delete(TICKETS, str(doc["id"]))
            return removed
