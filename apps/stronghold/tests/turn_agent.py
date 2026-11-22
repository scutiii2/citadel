"""A Legion stand-in for the turn tests: streams events, waits on approvals and questions, and can be held."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.agents.gateway import AgentCallError, Caller


@dataclass
class TurnAgent:
    """Stands in for ai_agent behind Stronghold's own MCP client (the
    AgentGateway). By default ask() streams two tokens and answers "Hello!";
    tests change `answer`, `events`, `fail`, or set `hold` to keep a turn
    running until release() (or a cancel) lets it finish."""

    answer: str = "Hello!"
    events: list[dict] = field(
        default_factory=lambda: [{"type": "token", "text": "Hel"}, {"type": "token", "text": "lo!"}]
    )
    result_extra: dict = field(default_factory=dict)
    fail: str | None = None
    hold: bool = False
    summary: str = "SUMMARY"
    asks: list[dict] = field(default_factory=list)
    interprets: list[str] = field(default_factory=list)
    cancels: list[str] = field(default_factory=list)
    gate: Any = None
    # Tools this fake "wants to run" during a turn. With approval_mode "ask"
    # it raises an approval_request for each (unless allowed already), waits
    # for decide(), and runs or refuses it, like the real agent.
    tool_calls: list[str] = field(default_factory=list)
    decisions: list[tuple[str, str, str]] = field(default_factory=list)
    decide_result: bool | None = None  # force decide()'s answer
    decide_error: str | None = None
    # A question this fake "asks" during a turn (the questions list of an ask_user call).
    questions: list[dict] = field(default_factory=list)
    answers: list[tuple] = field(default_factory=list)  # (request_id, step_id, answers, skipped)
    answer_result: bool | None = None  # force answer_question()'s result
    answer_error: str | None = None
    _asking: dict = field(default_factory=dict)
    ran: list[str] = field(default_factory=list)  # tools that actually ran
    # Private extensions: what probe_extension() was asked, what it answers per URL
    # (default: connected with two tools), and a forced failure.
    probes: list = field(default_factory=list)
    probe_results: dict = field(default_factory=dict)
    probe_fail: str | None = None
    _waiting: dict = field(default_factory=dict)

    loop: Any = None

    def release(self) -> None:
        """Safe from the test thread: the gate lives on the app's loop."""
        if self.gate is not None:
            self.loop.call_soon_threadsafe(self.gate.set)

    async def ask(
        self,
        url,
        caller: Caller,
        *,
        question,
        history,
        request_id,
        caveman,
        on_event,
        approval_mode="off",
        allowed_tools=None,
        disabled_tools=None,
        ask_user=False,
        plan=True,
        plan_lean=True,
        private_extensions=None,
        allow_read_only=False,
        exact_context=False,
        limits=None,
    ):
        self.asks.append(
            {
                "url": url,
                "caller": caller,
                "question": question,
                "history": history,
                "request_id": request_id,
                "caveman": caveman,
                "approval_mode": approval_mode,
                "allowed_tools": allowed_tools,
                "disabled_tools": disabled_tools,
                "limits": limits,
                "ask_user": ask_user,
                "plan": plan,
                "plan_lean": plan_lean,
                "exact_context": exact_context,
                "private_extensions": private_extensions,
                "allow_read_only": allow_read_only,
            }
        )
        for event in self.events:
            await on_event(event)
        for index, tool in enumerate(self.tool_calls):
            await self._run_tool(f"step{index}", tool, request_id, approval_mode, allowed_tools or [], on_event)
        if self.questions:
            await self._ask_user("q1", request_id, on_event)
        if self.hold:
            self.loop = asyncio.get_running_loop()
            self.gate = asyncio.Event()
            await self.gate.wait()
        if self.fail:
            raise AgentCallError(self.fail)
        cancelled = request_id in self.cancels
        return {
            "response": "Cancelled." if cancelled else self.answer,
            "cancelled": cancelled,
            "provider_id": "claude",
            "model": "claude-test",
            "total_tokens": 100,
            "input_tokens": 70,
            "output_tokens": 30,
            "context_tokens": 1000,
            "context_window": 200000,
            "agent_usage": [
                {"provider_id": "claude", "model": "claude-test", "input_tokens": 70, "output_tokens": 30, "total_tokens": 100}
            ],
            **self.result_extra,
        }

    async def _run_tool(self, step_id, tool, request_id, approval_mode, allowed_tools, on_event):
        await on_event({"type": "step_start", "id": step_id, "tool": tool, "label": tool.upper(), "arguments": {"a": 1}})
        approved = True
        # Like the real agent: a private tool (u_...) asks even when approvals are off.
        if (approval_mode == "ask" or tool.startswith("u_")) and tool not in allowed_tools:
            waiting = asyncio.get_running_loop().create_future()
            self._waiting[(request_id, step_id)] = waiting
            await on_event(
                {"type": "approval_request", "id": step_id, "tool": tool, "label": tool.upper(), "arguments": {"a": 1}}
            )
            decision = await waiting
            del self._waiting[(request_id, step_id)]
            await on_event({"type": "approval_resolved", "id": step_id, "outcome": decision})
            approved = decision in ("allow", "always")
        if approved:
            self.ran.append(tool)
        await on_event(
            {"type": "step_end", "id": step_id, "ok": approved, "result": "done" if approved else "The user declined."}
        )

    async def decide(self, url, caller, request_id, step_id, decision):
        if self.decide_error:
            raise AgentCallError(self.decide_error)
        self.decisions.append((request_id, step_id, decision))
        waiting = self._waiting.get((request_id, step_id))
        if self.decide_result is not None:
            answered = self.decide_result
        else:
            answered = waiting is not None and not waiting.done()
        if answered and waiting is not None and not waiting.done():
            waiting.set_result(decision)
        return answered

    async def _ask_user(self, step_id, request_id, on_event):
        self.loop = asyncio.get_running_loop()
        await on_event(
            {"type": "step_start", "id": step_id, "tool": "ask_user", "label": None, "arguments": {"questions": self.questions}}
        )
        waiting = asyncio.get_running_loop().create_future()
        self._asking[(request_id, step_id)] = waiting
        await on_event({"type": "question_request", "id": step_id, "questions": self.questions})
        outcome = await waiting
        del self._asking[(request_id, step_id)]
        await on_event({"type": "question_resolved", "id": step_id, "outcome": outcome})
        await on_event({"type": "step_end", "id": step_id, "ok": outcome != "cancelled", "result": f"outcome: {outcome}"})

    async def answer_question(self, url, caller, request_id, step_id, answers, skipped):
        if self.answer_error:
            raise AgentCallError(self.answer_error)
        self.answers.append((request_id, step_id, answers, skipped))
        waiting = self._asking.get((request_id, step_id))
        known = waiting is not None and not waiting.done()
        if self.answer_result is not None:
            known = self.answer_result
        if known and waiting is not None and not waiting.done():
            waiting.set_result("skipped" if skipped else "answered")
        return known

    async def probe_extension(self, url, caller, *, extension_url, headers):
        self.probes.append({"url": url, "caller": caller, "extension_url": extension_url, "headers": headers})
        if self.probe_fail:
            raise AgentCallError(self.probe_fail)
        return self.probe_results.get(
            extension_url, {"status": "connected", "error": None, "tools": ["add", "search"]}
        )

    async def interpret(self, url, caller, text):
        self.interprets.append(text)
        if self.fail:
            raise AgentCallError(self.fail)
        return {"response": self.summary, "provider_id": "claude", "model": "claude-test", "total_tokens": 10}

    async def cancel(self, url, caller, request_id):
        self.cancels.append(request_id)
        self.release()
        # A tool waiting for the user's answer ends as it does in the real agent.
        for (waiting_request, _step), waiting in list(self._waiting.items()):
            if waiting_request == request_id and not waiting.done():
                waiting.set_result("cancelled")
        for (waiting_request, _step), waiting in list(self._asking.items()):
            if waiting_request == request_id and not waiting.done():
                waiting.set_result("cancelled")
        return True
