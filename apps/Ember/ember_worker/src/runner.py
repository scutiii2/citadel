"""Runs turns. Each turn is a task that feeds a provider's events to the server as frames,
and exactly one terminal frame (turn_done or turn_error) closes it."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport
from src.protocol import (
    delta_frames,
    permission_request_frame,
    tool_frame,
    turn_done_frame,
    turn_error_frame,
    usage_frame,
)
from src.providers.base import Provider

logger = logging.getLogger(__name__)

CANCEL_GRACE_SECONDS = 5.0
CANCELLED = "cancelled"

Send = Callable[[dict], Awaitable[None]]


class _Gate:
    """What a provider calls to ask the user; bound to one turn."""

    def __init__(self, runner: TurnRunner, turn_id: str) -> None:
        self._runner = runner
        self._turn_id = turn_id

    async def ask(self, tool: str, summary: str) -> bool:
        return await self._runner._ask(self._turn_id, tool, summary)


class TurnRunner:
    def __init__(self, provider: Provider, send: Send, cancel_grace: float = CANCEL_GRACE_SECONDS) -> None:
        self._provider = provider
        self._send = send
        self._cancel_grace = cancel_grace
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancelled: set[str] = set()
        self._questions: dict[str, asyncio.Future[bool]] = {}
        self._question_turn: dict[str, str] = {}

    def active_turns(self) -> set[str]:
        return set(self._tasks)

    def start(self, request: TurnRequest) -> None:
        if request.turn_id in self._tasks:
            return
        task = asyncio.create_task(self._run(request))
        self._tasks[request.turn_id] = task
        task.add_done_callback(lambda _task, turn_id=request.turn_id: self._tasks.pop(turn_id, None))

    def permission_reply(self, request_id: str, allow: bool) -> None:
        question = self._questions.get(request_id)
        if question is not None and not question.done():
            question.set_result(allow)

    async def cancel(self, turn_id: str) -> None:
        task = self._tasks.get(turn_id)
        if task is None:
            return
        self._cancelled.add(turn_id)
        self._deny_questions(turn_id)
        try:
            await self._provider.cancel(turn_id)
        except Exception:
            logger.warning("the provider could not cancel turn %s", turn_id, exc_info=True)
        asyncio.get_running_loop().call_later(self._cancel_grace, task.cancel)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, request: TurnRequest) -> None:
        turn_id = request.turn_id
        finished = False
        try:
            async for event in self._provider.run_turn(request, _Gate(self, turn_id)):
                if finished:
                    continue
                if isinstance(event, TextDelta):
                    for frame in delta_frames(turn_id, event.text):
                        await self._send(frame)
                elif isinstance(event, ToolCall):
                    await self._send(tool_frame(turn_id, event.name, event.summary))
                elif isinstance(event, UsageReport):
                    await self._send(usage_frame(turn_id, event.input_tokens, event.output_tokens))
                elif isinstance(event, Finished):
                    finished = True
                    await self._send(turn_done_frame(turn_id, event.text))
                elif isinstance(event, Failed):
                    finished = True
                    await self._send(turn_error_frame(turn_id, CANCELLED if turn_id in self._cancelled else event.message))
            if not finished:
                finished = True
                await self._send(turn_error_frame(turn_id, CANCELLED if turn_id in self._cancelled else "The CLI ended without an answer."))
        except asyncio.CancelledError:
            if not finished:
                try:
                    await self._send(turn_error_frame(turn_id, CANCELLED))
                except Exception:
                    pass
            raise
        except Exception as error:
            logger.exception("turn %s failed", turn_id)
            if not finished:
                try:
                    await self._send(turn_error_frame(turn_id, str(error) or type(error).__name__))
                except Exception:
                    pass
        finally:
            self._cancelled.discard(turn_id)
            self._deny_questions(turn_id)

    async def _ask(self, turn_id: str, tool: str, summary: str) -> bool:
        request_id = uuid.uuid4().hex
        question: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._questions[request_id] = question
        self._question_turn[request_id] = turn_id
        try:
            await self._send(permission_request_frame(turn_id, request_id, tool, summary))
            return await question
        finally:
            self._questions.pop(request_id, None)
            self._question_turn.pop(request_id, None)

    def _deny_questions(self, turn_id: str) -> None:
        for request_id, owner in list(self._question_turn.items()):
            question = self._questions.get(request_id)
            if owner == turn_id and question is not None and not question.done():
                question.set_result(False)
