"""Run the tool calls of one model round: the part the Anthropic and OpenAI loops share.

A provider turns the model's reply into `Call`s and gets one `Outcome` per call, in the same order.
Each call passes the same checks it always did (turn guard, local tools, approvals, error numbers).

Calls that the model emitted together run at the same time only when that is safe: a run of
consecutive calls that each need no approval and belong to a built-in tool that declares
itself read-only. Any other call (a write, a delegation, a local tool, a private tool, one that needs
approval) runs alone, in order, so a write never overlaps a neighbour and approvals are asked one by one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from src.providers.base_provider import OnEvent, ToolCallRecord, dispatch_with_progress, step_event
from src.providers.turn_guard import TurnGuard
from src.runtime import approvals, counters, questions, run_tools, tool_batch_settings
from src.tools.mcp_client.mcp_upstream import NumberedFailureText, is_read_only_builtin


@dataclass(frozen=True)
class Call:
    id: str
    name: str
    arguments: Any


@dataclass
class Outcome:
    text: str
    ok: bool
    # What the step card shows when it differs from what the model receives.
    shown: str | None = None


class ToolRound:
    """One provider turn's way of running a round of calls. Build it once per turn, call `run` each round."""

    def __init__(
        self, *, guard: TurnGuard, dispatch: Callable[..., str], labels: dict[str, Any], depth: int,
        request_id: str | None, on_event: OnEvent | None, planning: Any, checklist: Any,
        tools_used: list[str], tool_calls: list[ToolCallRecord], batch_tools: frozenset[str] = frozenset(),
    ) -> None:
        self.guard = guard
        self.dispatch = dispatch
        self.labels = labels
        self.depth = depth
        self.request_id = request_id
        self.on_event = on_event
        self.planning = planning
        self.checklist = checklist
        self.tools_used = tools_used
        self.tool_calls = tool_calls
        # What `run_tools` may call; empty keeps that tool out. `results` keeps the finished steps of this turn's batches.
        self.batch_tools = batch_tools
        self.results: dict[str, str] = {}
        self.settings = tool_batch_settings.Settings()

    async def run(self, calls: Sequence[Call]) -> list[Outcome]:
        self.settings = tool_batch_settings.current()  # an edit on the Tuning page applies from the next round
        # The guard sees the calls in order before anything runs, so a stopped turn starts no tool.
        for call in calls:
            self.guard.check_call(call.name, call.arguments)
        outcomes: list[Outcome] = []
        index = 0
        while index < len(calls):
            end = index
            while end < len(calls) and self._can_overlap(calls[end]):
                end += 1
            if end - index >= 2:
                counters.add("batch.parallel_groups")
                counters.add("batch.parallel_calls", end - index)
                outcomes += await self._run_group(calls[index:end])
                index = end
            else:
                outcomes.append(await self._run_one(calls[index]))
                index += 1
        return outcomes

    def _can_overlap(self, call: Call) -> bool:
        return (self.settings.parallel and not approvals.current().needs_approval(call.name)
                and is_read_only_builtin(call.name))

    async def _emit(self, kind: str, **fields: Any) -> None:
        if self.on_event:
            await self.on_event(step_event(kind, **fields))

    async def _start(self, call: Call) -> None:
        self.tools_used.append(call.name)
        await self._emit("step_start", id=call.id, tool=call.name, label=self.labels.get(call.name), arguments=call.arguments)

    async def _run_tool(self, call: Call) -> Outcome:
        try:
            text = await dispatch_with_progress(self.dispatch, self.on_event, call.id, call.name, call.arguments, self.depth)
            return Outcome(text, True)
        except Exception as error:
            return Outcome(f"Tool '{call.name}' failed: {error}", False)

    async def _finish(self, call: Call, outcome: Outcome) -> Outcome:
        if isinstance(outcome.text, NumberedFailureText):
            self.guard.note_result(call.name, call.arguments, outcome.text)
            outcome.ok = False
        await self._emit("step_end", id=call.id, ok=outcome.ok, result=outcome.shown or outcome.text)
        return outcome

    def _record(self, call: Call, outcome: Outcome) -> None:
        self.tool_calls.append(ToolCallRecord(name=call.name, arguments=call.arguments, result=outcome.text))

    async def _run_one(self, call: Call) -> Outcome:
        await self._start(call)
        # Local planning and questions do not run external tools or need approval.
        asked = (await self.planning.handle(call.name, call.arguments, self.depth, self.request_id, self.on_event)
                 if self.planning else await self.checklist.handle(call.name, call.arguments, self.on_event))
        if asked is None:
            asked = await questions.handle(call.name, self.request_id, call.id, call.arguments, self.on_event)
        if asked is None and call.name == run_tools.TOOL_NAME and self.batch_tools:
            outcome = await self._run_batch(call)
        elif asked is not None:
            outcome = Outcome(*asked)
        else:
            # With approvals on, the user answers before anything runs; a
            # refusal is handed to the model as this step's result.
            declined = await approvals.review(
                self.request_id, call.id, call.name, self.labels.get(call.name), call.arguments, self.on_event)
            outcome = Outcome(declined, False) if declined is not None else await self._run_tool(call)
        outcome = await self._finish(call, outcome)
        self._record(call, outcome)
        return outcome

    async def _run_group(self, calls: Sequence[Call]) -> list[Outcome]:
        for call in calls:
            await self._start(call)
        limit = asyncio.Semaphore(self.settings.max_parallel)

        async def one(call: Call) -> Outcome:
            async with limit:
                outcome = await self._run_tool(call)
            return await self._finish(call, outcome)

        outcomes = list(await asyncio.gather(*(one(call) for call in calls)))
        for call, outcome in zip(calls, outcomes):
            self._record(call, outcome)
        return outcomes

    async def _run_batch(self, call: Call) -> Outcome:
        """`run_tools`: the steps wave by wave, each wave through `run`, so a step is an ordinary call."""
        steps, waves, error = run_tools.validate(call.arguments, self.batch_tools, self.results)
        if error:
            return Outcome(error, False)
        status: dict[str, str] = {}
        texts: dict[str, str] = {}
        for wave in waves:
            ready: list[tuple[run_tools.Step, Call]] = []
            for step in wave:
                blocked = next((d for d in step.depends_on if status.get(d) != "done"), None)
                if blocked:
                    status[step.id], texts[step.id] = "skipped", f"Skipped: step {blocked!r} did not finish."
                    continue
                try:
                    arguments = run_tools.resolve(step.arguments, {**self.results, **texts})
                except ValueError as problem:
                    status[step.id], texts[step.id] = "failed", str(problem)
                    continue
                ready.append((step, Call(f"{call.id}:{step.id}", step.tool, arguments)))
            if not ready:
                continue
            for (step, _), outcome in zip(ready, await self.run([item for _, item in ready])):
                status[step.id] = "done" if outcome.ok else "failed"
                texts[step.id] = outcome.text
        self.results.update({step.id: texts[step.id] for step in steps if status[step.id] == "done"})
        counters.add("batch.run_tools")
        counters.add("batch.run_tools_steps", len(steps))
        counters.add("batch.run_tools_failed_steps", sum(1 for step in steps if status[step.id] != "done"))
        return Outcome(run_tools.reply(steps, status, texts), all(status[step.id] == "done" for step in steps),
                       run_tools.summary(steps, status))
