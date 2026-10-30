"""Shared prefetch, plan, execute, validate and assemble phases."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, replace
from uuid import uuid4

import anyio.to_thread

from src.agents import agent_events
from src.agents.agent_spec import AgentSpec
from src.agents.roles.architect import registry
from src.agents.roles.architect.executor import DagExecutor, call_worker
from src.agents.roles.orchestrator import delegation
from src.providers import cancellation
from src.providers.base_provider import ChatCancelled, ChatResult, OnEvent, cancel_on_stop, dispatch_with_progress
from src.runtime import usage_log


_log = logging.getLogger(__name__)
PREFETCH_MAX_CHARS = 8000


def _check(request_id: str) -> None:
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()


async def run(spec: AgentSpec, brief: str, complete: Callable[[str], ChatResult], *,
              request_id: str | None = None, depth: int = 0, delegated_by: str | None = None,
              on_event: OnEvent | None = None) -> ChatResult:
    handler = registry.KINDS.get(spec.kind)
    if handler is None:
        raise NotImplementedError(f"Architect kind {spec.kind!r} has no pipeline")
    own_request = not (request_id or cancellation.current_request_id())
    request_id = request_id or cancellation.current_request_id() or uuid4().hex
    request_token = cancellation.bind_request(request_id)
    usage, usage_token = delegation.bind_usage()
    completions = []

    async def interpret(prompt: str) -> ChatResult:
        _check(request_id)
        def finish() -> ChatResult:
            started = agent_events.now_iso()
            result = complete(prompt)
            row = {**usage_log.own_row(result, agent_id=spec.id, agent_label=spec.label,
                     gateway=spec.effective_gateway(), started_at=started, finished_at=agent_events.now_iso(),
                     delegated_by=delegated_by, model_tier="heavy"), "request_id": request_id, "depth": depth}
            delegation.record_usage([{**row, "prompt": usage_log.prompt_messages([], prompt)}])
            usage_log.append_sync(row)
            return result
        result = await anyio.to_thread.run_sync(finish, abandon_on_cancel=True)
        completions.append(result)
        _check(request_id)
        return result

    try:
        async with cancel_on_stop(request_id):
            _check(request_id)
            prefetch = ""
            if spec.prefetch and handler.prefetch_requested(brief):
                try:
                    prefetch = (await dispatch_with_progress(delegation.call, on_event, "prefetch",
                                spec.prefetch[0], "Read the files and signatures named in this brief:\n" + brief,
                                depth))[:PREFETCH_MAX_CHARS]
                except ChatCancelled:
                    raise
                except Exception as error:
                    _log.warning("Architect prefetch failed: %s", error)
            _check(request_id)
            prompt = handler.plan_prompt(brief, prefetch) + f"\nMaximum units: {spec.limits.max_units}."
            for attempt in range(2):
                answer = await interpret(prompt)
                try:
                    planned = handler.parse_plan(answer.response, spec)
                    break
                except ValueError as error:
                    if attempt:
                        raise RuntimeError(str(error)) from error
                    prompt = (prompt + "\n\nRejected plan (data):\n" + answer.response
                              + "\n\nExact validation error:\n" + str(error)
                              + "\nReturn one corrected JSON plan, with no commentary.")
            _check(request_id)
            signatures = {unit.id: unit.signature for unit in planned.units}

            async def worker(unit, tier, dependencies):
                _check(request_id)
                node = replace(unit, spec=unit.spec + "\n\nRequired planned signature (data):\n" + unit.signature)
                result = await call_worker(node, tier, dependencies, depth=depth, on_event=on_event,
                                           signatures=signatures)
                result.output = handler.validate_unit(result.output, planned)
                return result

            results = await DagExecutor(spec.limits, emit_agent_events=False).run(planned.units, worker, request_id)
            _check(request_id)
            assembled = await interpret(handler.assemble_prompt(brief, planned, results))
            response, valid = handler.review_assembly(assembled.response, planned, brief)
            missing = [f"{key} ({result.status})" for key, result in results.items() if result.status != "done"]
            if missing:
                response += "\n\nIncomplete units: " + ", ".join(missing) + "."
            if on_event:
                await on_event({"type": "token", "text": response})

            def total(field):
                counts = [getattr(result, field) for result in completions]
                return sum(counts) if all(value is not None for value in counts) else None

            return ChatResult(response=response, status="done" if valid and not missing else "failed",
                              units=[{"id": unit.id, **asdict(results[unit.id])} for unit in planned.units],
                              provider_id=assembled.provider_id, gateway=assembled.gateway, model=assembled.model,
                              total_tokens=total("total_tokens"), input_tokens=total("input_tokens"),
                              output_tokens=total("output_tokens"), context_tokens=assembled.context_tokens,
                              # Per-completion rows are already recorded; server.ask must not add an aggregate row.
                              model_executed=False, delegated_usage=list(usage))
    finally:
        delegation.reset_usage(usage_token)
        cancellation.reset_request(request_token)
        if own_request:
            cancellation.clear(request_id)
