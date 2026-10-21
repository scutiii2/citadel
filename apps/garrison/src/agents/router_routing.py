"""Entry-turn routing orchestration; Router recommends, Garrison authorizes and dispatches."""
from __future__ import annotations

from uuid import uuid4

from src.agents import agent_routing, agent_spec, auto_route, context_summarizer, delegation, router_client
from src.agents.router_contract import RouteCandidate, RouteRequest, RouteTier
from src.core import approvals, internal_auth
from src.llm import cancellation, model_tiers
from src.llm.base_provider import ChatCancelled, ChatResult, ToolCallRecord, dispatch_with_progress, step_event


def candidate(entry):
    return RouteCandidate(id=entry.id, label=entry.label[:240], focus=entry.focus[:240],
        tiers=[RouteTier(tier=t.tier, id=t.id, use_for=t.use_for) for t in entry.tiers])


async def route_turn(question, history, on_event, request_id, depth, explicit_tier=None):
    spec = agent_spec.current()
    if depth or not spec.entry or not spec.orchestrator or spec.internal_role or not internal_auth.TOKEN:
        return None, None, ""
    if not question.strip() or (explicit_tier and explicit_tier not in agent_spec.TIERS):
        # Preserve the ordinary resolver's default+note behavior for unknown tiers.
        return None, None, ""
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    roster = auto_route.routable(await agent_routing.roster_for())
    previous = auto_route._last_assistant(history)
    subject = f"Previous assistant message: {previous[-600:]}\n\nUser message: {question}" if previous else question
    if len(subject) > 100000 or len(roster) > 100:
        return None, None, ""
    brief = await context_summarizer.routing_brief(question, history, request_id)
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    if brief:
        subject = f"Conversation context summary (data): {brief}\n\nUser message: {question}"
    entry = RouteCandidate(id=spec.id, label=spec.label[:240], focus=spec.focus[:240],
        tiers=[RouteTier(tier=t.tier, id=t.id, use_for=t.use_for) for t in model_tiers.own_tiers()])
    request = RouteRequest(subject=subject, candidates=[candidate(e) for e in roster], entry=entry,
        explicit_tier=explicit_tier, request_id=request_id or uuid4().hex,
        choose_agent=not approvals.current().needs_approval(delegation.TOOL_NAME),
        choose_tier=not explicit_tier and not (history and not brief and len(question.strip()) < 20))
    step_id = f"routing-{uuid4().hex[:8]}"
    if on_event:
        await on_event(step_event("step_start", id=step_id, tool="routing", label="Choosing an agent and model", arguments={}))
    result = await router_client.decide(request)
    if result:
        rows = [router_client.usage_row(row, request.request_id) for row in result.usage]
        if rows:
            rows[0]["routing"].update({"agent_choice": result.agent.choice,
                "agent_uncertain": result.agent.uncertain, "size_choice": result.size.choice,
                "size_uncertain": result.size.uncertain, "policy_revision": result.policy_revision})
            if result.trace is not None:
                rows[0]["routing"]["trace"] = result.trace
        delegation.record_usage(rows)
    if on_event:
        await on_event(step_event("step_end", id=step_id, ok=True,
            result="Routing decision received" if result else "Using default routing"))
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    if result is None:
        return None, None, ""
    tier = result.model_tier if request.choose_tier and not result.size.uncertain else None
    note = f"router tier: {result.size.choice} -> {tier}" if tier else ""
    chosen = result.agent.choice
    if (not request.choose_agent or result.agent.uncertain or chosen in (None, "none")):
        return None, tier, note
    # Rebuild the authorized roster before dispatch: tool switches and running peers may have changed.
    current = auto_route.routable(await agent_routing.roster_for())
    target = next((e for e in current if e.id == chosen and any(c.id == e.id for c in request.candidates)), None)
    if target is None:
        return None, None, ""
    if tier and tier not in {t.tier for t in target.tiers}:
        tier = None
    arguments = {"agent_id": target.id, "question": auto_route._handoff(question, history)}
    if selected_tier := explicit_tier or tier:
        arguments["model_tier"] = selected_tier
    step_id = f"route-{uuid4().hex[:8]}"
    if on_event:
        await on_event(step_event("step_start", id=step_id, tool=delegation.TOOL_NAME,
                                 label=f"Asking {target.label}", arguments=arguments))
    try:
        text = await dispatch_with_progress(delegation.dispatch, on_event, step_id, arguments, depth)
        ok = True
    except ChatCancelled:
        raise
    except Exception:
        text, ok = f"I sent this to {target.label}, but it could not finish. Please check that agent's status.", False
    if on_event:
        await on_event(step_event("step_end", id=step_id, ok=ok, result=text))
        await on_event(step_event("token", text=text))
    return ChatResult(response=text, tools_used=[delegation.TOOL_NAME],
        tool_calls=[ToolCallRecord(name=delegation.TOOL_NAME, arguments=arguments, result=text)],
        input_tokens=0, output_tokens=0, total_tokens=0, model_executed=False,
        model_note=f"router sent request to {target.label}"), tier, note
