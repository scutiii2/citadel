"""Detect requests for independent review and enforce a separate reviewer call."""
from __future__ import annotations

import re
from uuid import uuid4

import anyio.to_thread

from src.agents import agent_routing
from src.agents.roles.orchestrator import auto_route, delegation
from src.providers import cancellation
from src.providers.base_provider import ChatCancelled, dispatch_with_progress, step_event
from src.providers.decision import router_list, settings, strategy
from src.runtime import approvals


async def requested(question: str, history: list[dict]) -> bool | None:
    """Return None when the decision service cannot decide; never log the subject."""
    config = settings.settings()
    question = re.sub(r"\[\[ATTACHMENT\b[^\]]*\]\].*?\[\[/ATTACHMENT\]\]", "", question, flags=re.DOTALL)
    previous = re.sub(r"\[\[ATTACHMENT\b[^\]]*\]\].*?\[\[/ATTACHMENT\]\]", "", auto_route._last_assistant(history), flags=re.DOTALL)
    prefix = f"Previous assistant message: {previous[-300:]}\n" if previous else ""
    prefix += "User message: "
    limit = max(0, config.max_input_chars - len(prefix))
    if len(question) > limit:
        start = (limit + 1) // 2
        question = question[:start] + (question[-(limit - start):] if limit > start else "")
    subject = (prefix + question)[-config.max_input_chars:]
    try:
        choice = await anyio.to_thread.run_sync(lambda: strategy.ask_choice(
            subject,
            {"review": "The user requests an independent review or check by another agent or person.",
             "ordinary": "The user does not request an independent reviewer or second agent."},
            "Does the latest user message request independent review by another agent?",
            models=router_list.router_models(), min_confidence=config.auto_route.min_confidence,
            timeout=config.timeout_seconds,
        ))
    except Exception:
        return None
    if choice.confidence < config.auto_route.min_confidence or choice.choice not in {"review", "ordinary"}:
        return None
    return choice.choice == "review"


async def finish(question: str, history: list[dict], draft: str, on_event, request_id: str | None, depth: int) -> str:
    """Run the reviewer after the draft, or explicitly report why it could not run."""
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    roster = await agent_routing.roster_for()
    if not any(entry.id == "reviewer" for entry in roster):
        return draft + "\n\nIndependent review was not completed: Reviewer is unavailable."
    arguments = {"agent_id": "reviewer", "question": (
        "Independently review the draft against the original request and available evidence. "
        "Identify errors and missing evidence; do not assume the draft is correct.\n\n"
        + auto_route._handoff(question, history) + "\n\nDraft answer:\n" + draft)}
    step_id = f"review-{uuid4().hex[:8]}"
    if on_event:
        await on_event(step_event("step_start", id=step_id, tool=delegation.TOOL_NAME,
                                  label="Asking Reviewer", arguments=arguments))
    declined = await approvals.review(request_id, step_id, delegation.TOOL_NAME, "Asking Reviewer", arguments, on_event)
    if declined is not None:
        if on_event:
            await on_event(step_event("step_end", id=step_id, ok=False, result=declined))
        return draft + "\n\nIndependent review was not completed: approval was not granted."
    try:
        review = await dispatch_with_progress(delegation.dispatch, on_event, step_id, arguments, depth)
        if not review.strip():
            raise ValueError("empty review")
    except ChatCancelled:
        raise
    except Exception:
        if on_event:
            await on_event(step_event("step_end", id=step_id, ok=False, result="Reviewer could not complete the review."))
        return draft + "\n\nIndependent review was not completed: Reviewer failed."
    if on_event:
        await on_event(step_event("step_end", id=step_id, ok=True, result=review))
    return draft + "\n\nIndependent review:\n" + review
