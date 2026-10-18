"""Runs Forge turns. A user message is routed to a worker as a `turn` frame; the worker's
frames become stored messages (and live browser events); with relay on, a reply that ends
with an @mention hands the turn to another worker. One turn runs per group at a time.

Long-lived and single-process: it opens its own short database sessions."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.db import Database
from src.models import ForgeMessage
from src.services.forge.approvals import PendingPermission, PermissionBroker
from src.services.forge.connections import WorkerRegistry
from src.services.forge.events import GroupEventBus
from src.services.forge.groups import GroupService, MemberRow, NotAMember
from src.services.forge.messages import MessageStore, message_event
from src.services.forge.plans import PlanPolicyRegistry
from src.services.forge.protocol import (
    Delta,
    PermissionRequested,
    ToolUsed,
    TurnDone,
    TurnError,
    Usage,
    WorkerFrame,
    cancel_frame,
    permission_reply_frame,
    turn_frame,
)
from src.services.forge.routing import Member, TurnRouter

logger = logging.getLogger(__name__)

CANCEL_GRACE_SECONDS = 10.0
HISTORY_CHARS = 20_000


class GroupBusy(Exception):
    """A turn is already running in the group (maps to 409)."""


@dataclass(frozen=True)
class TurnOutcome:
    text: str | None = None
    error: str | None = None
    cancelled: bool = False
    usage: dict | None = None


@dataclass
class _ActiveTurn:
    turn_id: str
    group_id: int
    worker_id: int
    label: str
    done: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())
    usage: dict | None = None
    cancelled: bool = False


class TurnCoordinator:
    def __init__(
        self,
        database: Database,
        registry: WorkerRegistry,
        bus: GroupEventBus,
        store: MessageStore,
        router: TurnRouter,
        *,
        permission_timeout: float = 600.0,
        cancel_grace: float = CANCEL_GRACE_SECONDS,
    ) -> None:
        self._database = database
        self._registry = registry
        self._bus = bus
        self._store = store
        self._router = router
        self._cancel_grace = cancel_grace
        self._broker = PermissionBroker(self._deny_expired, permission_timeout)
        # group id -> the task running its chain (None while the claim is being made)
        self._running: dict[int, asyncio.Task | None] = {}
        self._stopping: set[int] = set()
        self._turns: dict[str, _ActiveTurn] = {}
        self._by_worker: dict[int, str] = {}

    # --- what the routes call ------------------------------------------------------

    def is_running(self, group_id: int) -> bool:
        return group_id in self._running

    async def post_user_message(self, account_id: int, group_id: int, text: str) -> ForgeMessage:
        if group_id in self._running:
            raise GroupBusy(group_id)
        self._running[group_id] = None  # claimed before the first await, so two messages cannot both start
        started = False
        try:
            async with self._database.sessions() as session:
                groups = self._groups(session, account_id)
                group = await groups.get(group_id)
                members = [Member(row.worker.id, row.worker.label) for row in await groups.members(group_id)]
            target = self._router.target_for_user(text, members, group.last_worker_id)
            message = await self._post(group_id, "user", "text", {"text": text})
            if target is None:
                await self.post_system(group_id, "No worker was addressed. Start your message with @label.")
                return message
            task = asyncio.create_task(self._run_chain(account_id, group_id, target, text, message.seq))
            self._running[group_id] = task
            task.add_done_callback(lambda finished: self._finished(group_id, finished))
            started = True
            self._publish_turn(group_id, True)
            return message
        finally:
            if not started:
                self._running.pop(group_id, None)

    async def post_system(self, group_id: int, text: str) -> None:
        await self._post(group_id, "system", "system", {"text": text})

    async def resolve_permission(self, account_id: int, group_id: int, request_id: str, allow: bool) -> bool:
        await self._owned_group(account_id, group_id)
        pending = self._broker.resolve(group_id, request_id)
        if pending is None:
            return False
        await self._answer_permission(pending, allow, by="user")
        return True

    async def cancel(self, account_id: int, group_id: int) -> bool:
        """Asks the running worker to stop. False when nothing is running."""
        await self._owned_group(account_id, group_id)
        if group_id not in self._running:
            return False
        self._stopping.add(group_id)  # no further hand-off after this turn
        turn = next((t for t in self._turns.values() if t.group_id == group_id), None)
        if turn is None:
            return True
        turn.cancelled = True
        connection = self._registry.get(turn.worker_id)
        if connection is not None:
            try:
                await connection.send(cancel_frame(turn.turn_id))
            except Exception:
                logger.warning("could not send cancel to worker %s", turn.worker_id)
        # If the worker does not acknowledge in time, the turn is ended here.
        asyncio.get_running_loop().call_later(self._cancel_grace, self._complete, turn, TurnOutcome(cancelled=True))
        return True

    async def shutdown(self) -> None:
        self._broker.close()
        tasks = [task for task in self._running.values() if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- what the worker socket calls ----------------------------------------------

    async def on_worker_frame(self, worker_id: int, frame: WorkerFrame) -> None:
        turn_id = getattr(frame, "turn_id", None)
        turn = self._turns.get(turn_id) if turn_id else None
        if turn is None or turn.worker_id != worker_id:
            return  # late, or not this worker's turn
        sender = str(worker_id)
        if isinstance(frame, Delta):
            self._bus.publish(
                turn.group_id,
                {"type": "delta", "turn_id": turn.turn_id, "sender": sender, "label": turn.label, "text": frame.text},
            )
        elif isinstance(frame, ToolUsed):
            body = {"turn_id": turn.turn_id, "label": turn.label, "name": frame.name, "summary": frame.summary}
            await self._post(turn.group_id, sender, "tool", body)
        elif isinstance(frame, PermissionRequested):
            self._broker.open(PendingPermission(frame.request_id, turn.group_id, worker_id, turn.turn_id))
            body = {
                "turn_id": turn.turn_id,
                "label": turn.label,
                "request_id": frame.request_id,
                "tool": frame.tool,
                "summary": frame.summary,
            }
            await self._post(turn.group_id, sender, "permission_request", body)
        elif isinstance(frame, Usage):
            turn.usage = {"input_tokens": frame.input_tokens, "output_tokens": frame.output_tokens}
        elif isinstance(frame, TurnDone):
            self._complete(turn, TurnOutcome(text=frame.text, usage=turn.usage))
        elif isinstance(frame, TurnError):
            self._complete(turn, TurnOutcome(cancelled=True) if turn.cancelled else TurnOutcome(error=frame.message))

    async def on_worker_disconnected(self, worker_id: int) -> None:
        turn = self._turns.get(self._by_worker.get(worker_id, ""))
        if turn is not None:
            self._complete(turn, TurnOutcome(error="worker disconnected"))

    # --- the chain of turns ---------------------------------------------------------

    def _finished(self, group_id: int, task: asyncio.Task) -> None:
        self._running.pop(group_id, None)
        self._stopping.discard(group_id)
        if not task.cancelled() and task.exception() is not None:
            logger.error("forge chain failed", exc_info=task.exception())
        self._publish_turn(group_id, False)

    async def _run_chain(
        self, account_id: int, group_id: int, target: Member, prompt: str, prompt_seq: int | None
    ) -> None:
        depth = 0
        try:
            while True:
                outcome = await self._run_turn(account_id, group_id, target, prompt, prompt_seq)
                if outcome is None or outcome.error or outcome.cancelled or not outcome.text:
                    return
                if group_id in self._stopping:
                    return
                async with self._database.sessions() as session:
                    groups = self._groups(session, account_id)
                    group = await groups.get(group_id)
                    rows = await groups.members(group_id)
                if not group.relay or depth >= self._router.max_relay_depth:
                    return
                handoff = self._router.handoff(
                    outcome.text, [Member(row.worker.id, row.worker.label) for row in rows], target.worker_id
                )
                if handoff is None:
                    return
                (target, prompt), prompt_seq, depth = handoff, None, depth + 1
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("forge turn failed")
            try:
                await self.post_system(group_id, f"Forge error: {error}")
            except Exception:
                logger.exception("could not record the failure")

    async def _run_turn(
        self, account_id: int, group_id: int, target: Member, prompt: str, prompt_seq: int | None
    ) -> TurnOutcome | None:
        async with self._database.sessions() as session:
            groups = self._groups(session, account_id)
            group = await groups.get(group_id)
            try:
                member = await groups.member(group_id, target.worker_id)
            except NotAMember:
                await self.post_system(group_id, f"@{target.label} is no longer in this group.")
                return None
            problem = await groups.problem(member.worker)
        label = member.worker.label
        if problem is not None:
            await self.post_system(group_id, f"@{label}: {problem}")
            return None
        connection = self._registry.get(target.worker_id)
        if connection is None:
            await self.post_system(group_id, f"@{label} is offline. Start ember-worker on its computer.")
            return None

        history = await self._history(group_id, member, prompt_seq)
        turn = _ActiveTurn(uuid.uuid4().hex, group_id, target.worker_id, label)
        self._turns[turn.turn_id] = turn
        self._by_worker[turn.worker_id] = turn.turn_id
        try:
            await connection.send(
                turn_frame(
                    turn_id=turn.turn_id,
                    group_id=group_id,
                    folder=member.folder,
                    mode=group.mode,
                    prompt=prompt,
                    history=history,
                )
            )
            outcome = await turn.done
        except Exception as error:  # the socket failed while sending
            outcome = TurnOutcome(error=f"could not reach the worker ({error})")
        finally:
            self._turns.pop(turn.turn_id, None)
            if self._by_worker.get(turn.worker_id) == turn.turn_id:
                del self._by_worker[turn.worker_id]
            self._broker.discard_turn(turn.turn_id)
        await self._finish(account_id, group_id, member, turn, outcome)
        return outcome

    async def _finish(
        self, account_id: int, group_id: int, member: MemberRow, turn: _ActiveTurn, outcome: TurnOutcome
    ) -> None:
        worker, label = member.worker, member.worker.label
        if outcome.error is not None:
            await self.post_system(group_id, f"@{label} failed: {outcome.error}")
            return
        if outcome.cancelled:
            await self.post_system(group_id, f"@{label} stopped.")
            return
        body = {"text": outcome.text, "label": label, "provider": worker.provider, "turn_id": turn.turn_id}
        if outcome.usage:
            body["usage"] = outcome.usage
        await self._post(group_id, str(worker.id), "text", body)
        newest = await self._store.last_seq(group_id)
        async with self._database.sessions() as session:
            await self._groups(session, account_id).mark_seen(group_id, worker.id, newest)

    async def _history(self, group_id: int, member: MemberRow, prompt_seq: int | None) -> list[dict]:
        messages = await self._store.history(group_id, member.last_seq, exclude_seq=prompt_seq)
        lines: list[dict] = []
        total = 0
        for message in reversed(messages):  # newest first, so the budget keeps the latest
            text = message.body.get("text", "")
            total += len(text)
            if total > HISTORY_CHARS:
                break
            sender = "user" if message.sender == "user" else message.body.get("label", message.sender)
            lines.append({"sender": sender, "text": text})
        lines.reverse()
        return lines

    # --- helpers --------------------------------------------------------------------

    def _complete(self, turn: _ActiveTurn, outcome: TurnOutcome) -> None:
        if not turn.done.done():
            turn.done.set_result(outcome)

    async def _answer_permission(self, pending: PendingPermission, allow: bool, by: str) -> None:
        connection = self._registry.get(pending.worker_id)
        if connection is not None:
            try:
                await connection.send(permission_reply_frame(pending.request_id, allow))
            except Exception:
                logger.warning("could not send a permission reply to worker %s", pending.worker_id)
        sender = "user" if by == "user" else "system"
        await self._post(
            pending.group_id, sender, "permission_result", {"request_id": pending.request_id, "allow": allow, "by": by}
        )

    async def _deny_expired(self, pending: PendingPermission) -> None:
        await self._answer_permission(pending, False, by="timeout")

    async def _post(self, group_id: int, sender: str, kind: str, body: dict) -> ForgeMessage:
        message = await self._store.append(group_id, sender, kind, body)
        self._bus.publish(group_id, message_event(message))
        return message

    def _publish_turn(self, group_id: int, running: bool) -> None:
        self._bus.publish(group_id, {"type": "turn", "running": running})

    def _groups(self, session: AsyncSession, account_id: int) -> GroupService:
        return GroupService(session, account_id, PlanPolicyRegistry(session))

    async def _owned_group(self, account_id: int, group_id: int) -> None:
        async with self._database.sessions() as session:
            await self._groups(session, account_id).get(group_id)
