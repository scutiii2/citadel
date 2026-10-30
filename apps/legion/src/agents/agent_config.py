"""Resolves this ai_agent instance's pinned LLM provider+model, once, at
import time - fails loudly if AI_AGENT_PROVIDER is missing, unknown, or
its API key isn't configured, rather than discovering that on the first
real request.
"""

from __future__ import annotations

import dataclasses
import inspect
import importlib
import logging
import os
from pathlib import Path
from typing import Any

import anyio
from dotenv import dotenv_values

from src.agents import agent_spec
from src.agents.roles.orchestrator import auto_route, delegation, memory_recall, skill_recall, skill_reflection
from src.agents.roles.router import router_routing
from src.agents.roles.orchestrator import plan as plan_policy

from src.runtime import approvals, internal_auth, questions, tool_filter, tuning_overrides
from src.tools.private_extensions import turn as private_turn
from src.agents import auto_tier
from src.providers import context_breakdown, llm_config, llm_options, model_tiers, token_limits
from src.providers import reasoning_effort as effort_limits
from src.runtime.seed import seed_from_example
from src.runtime.chat_history import validate_history

_SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
_log = logging.getLogger(__name__)


def _load_secrets_into_environ() -> None:
    seed_from_example(_SECRETS_PATH)
    for key, value in dotenv_values(_SECRETS_PATH).items():
        if value:
            os.environ.setdefault(key, value)


# Must run BEFORE importing anthropic_provider/openai_provider below: each
# resolves its own DEFAULT_MODEL/VENDOR_LABEL from AI_AGENT_GATEWAY (see
# their resolve_default_model/resolve_vendor_label) once, at ITS OWN import
# time. server.py sets AI_AGENT_GATEWAY from the agent file before this
# module is imported; .env only fills in what is still unset (setdefault).
_load_secrets_into_environ()

from src.providers import cancellation, cooldown
from src.providers.base_provider import ChatCancelled, ChatResult  # noqa: E402
from src.providers.model_limits import context_window_for  # noqa: E402

_PROVIDERS = {
    "anthropic": "src.providers.language.anthropic_provider",
    "openai": "src.providers.language.openai_provider",
    "decision": "src.providers.decision.provider",
}


class AgentConfigError(Exception):
    """Raised at import time for a missing/unknown AI_AGENT_PROVIDER, or
    a missing API key for the selected provider."""


def _resolve() -> tuple[str, Any]:
    _load_secrets_into_environ()
    provider_id = os.getenv("AI_AGENT_PROVIDER")
    if not provider_id:
        raise AgentConfigError(
            f"AI_AGENT_PROVIDER is not set in {_SECRETS_PATH} - must be one of: {', '.join(sorted(_PROVIDERS))}"
        )
    module_name = _PROVIDERS.get(provider_id)
    if module_name is None:
        raise AgentConfigError(
            f"Unknown AI_AGENT_PROVIDER {provider_id!r} - must be one of: {', '.join(sorted(_PROVIDERS))}"
        )
    # Import only the selected provider: a local Laya agent must not depend on
    # a cloud gateway, persona configuration or cloud SDK initialization.
    module = importlib.import_module(module_name)
    if not module.has_api_key():
        raise AgentConfigError(
            f"AI_AGENT_PROVIDER is {provider_id!r} but its API key is not configured in {_SECRETS_PATH}"
        )
    spec = agent_spec.current()
    for index, choice in enumerate(spec.llm.fallback_gateways):
        where = f"{spec.source or spec.id}: llm.fallback_gateways[{index}].gateway"
        try:
            llm_config.gateway(provider_id, choice.gateway)
        except KeyError:
            raise AgentConfigError(f"{where}: gateway {choice.gateway!r} has no file") from None
        if not module.has_api_key(choice.gateway):
            _log.warning("%s: gateway %s has no credentials; skipping fallback", where, choice.gateway)
    return provider_id, module


PROVIDER_ID, _PROVIDER_MODULE = _resolve()
MODEL = os.getenv("AI_AGENT_MODEL") or None


def _read_only_check():
    """The check "Auto" approval uses, or None for an agent that lists no mcp_server tools (laya)."""
    if PROVIDER_ID == "decision":
        return None
    # Imported here: laya agents never load mcp_upstream.
    from src.tools.mcp_client import mcp_upstream

    return mcp_upstream.is_read_only_builtin


async def run_chat(
    question: str,
    history: list[dict[str, Any]],
    enabled_extensions: list[str],
    request_id: str | None = None,
    depth: int = 0,
    on_event: Any = None,
    caveman: bool = False,
    approval_mode: str = "off",
    allowed_tools: list[str] | None = None,
    disabled_tools: list[str] | None = None,
    ask_user: bool = False,
    private_extensions: list[dict[str, Any]] | None = None,
    model_tier: str | None = None,
    reasoning_effort: str | None = None,
    plan: bool = True,
    plan_lean: bool = True,
    allow_read_only: bool = False,
    exact_context: bool = False,
    limits: dict[str, int] | None = None,
    delegated_by: str | None = None,
) -> ChatResult:
    """Run a chat completion request through the configured provider.

    reasoning_effort: the effort ("off"/"low"/"medium"/"high") the caller asks
    for (delegation.py). It is capped at this agent's llm.max_effort
    (llm/reasoning_effort.py) and applies to this turn only; the result notes
    a change. None keeps the agent's own reasoning_effort.

    model_tier: a strength tier ("light"/"standard"/"heavy"/"extreme") the caller asks
    for (delegation.py). It is resolved against this agent's own tiers and
    cap (llm/model_tiers.py); a request outside the cap is clamped, with a
    note on the result. None keeps the pinned model.

    ask_user: the caller can show the user clickable questions (core/questions.py);
    only a top-level turn (depth 0) is offered the tool.

    disabled_tools: tools the asking user switched off for their own chats
    (see core/tool_filter.py); they are not offered and not run.

    plan / plan_lean: the chat's checklist toggles (agents/plan.py). The
    update_plan tool is offered only when `plan` is on and this agent's file
    has plan_tool on; `plan_lean` asks for an update only on a status change.

    exact_context: count the parts of the context window with the provider's own
    token counter (llm/context_breakdown.py) instead of estimating them; any failure
    falls back to the estimate.

    limits: the user's own output-token and tool-round caps for this turn; lower only.

    private_extensions: the user's own MCP servers for this turn, as ember_api
    sent them (see private_extensions/turn.py). Their tools are offered after
    the user approves each one; a server that cannot be reached is reported
    in `result.private_extension_errors` and the turn goes on without it.

    approval_mode / allowed_tools: see approvals.py - with "ask" a tool runs
    only after the user allows it (tools in allowed_tools were allowed
    already); "deny" refuses any tool that would need asking.
    allow_read_only: with "ask", built-in tools that declare readOnlyHint run
    without asking ("Auto" in ember); ignored with any other mode.

    Both anthropic_provider and openai_provider's run_chat are async
    (support streaming, forwarding on_event for live step_start/step_end/
    token events) - awaited directly here. The iscoroutinefunction check
    stays as a safety net for any future provider module that hasn't been
    converted yet: a sync run_chat would run in a worker thread via
    anyio.to_thread.run_sync so a slow completion doesn't block other
    requests this process is serving, with on_event dropped since a sync
    provider has nowhere to await it from.
    """
    history = validate_history(history)
    spec = agent_spec.current()
    plan_mode = getattr(spec, "mode", "legacy") == "plan" and spec.orchestrator
    requester = internal_auth.current_requester()
    private = private_turn.PrivateTurn.from_raw(private_extensions, requester.email or requester.username)
    # Validated before anything is registered: a bad mode must not start a turn.
    policy = approvals.ApprovalPolicy(
        approval_mode, set(allowed_tools or ()), ask_prefixes=(private_turn.TOOL_PREFIX,) if private else (),
        read_only_check=_read_only_check() if allow_read_only and approval_mode == "ask" else None,
    )
    effort = effort_limits.resolve(reasoning_effort, agent_spec.current().llm.max_effort, agent_spec.current().id)
    cancellation.register(request_id)
    tuning_overrides.poll()
    request_token = cancellation.bind_request(request_id)
    delegated_usage, usage_token = delegation.bind_usage()
    attachment_token = delegation.bind_attachments(question, history)
    caveman_token = delegation.bind_caveman(caveman)
    extensions_token = delegation.bind_enabled_extensions(enabled_extensions)
    approval_token = approvals.bind(policy)
    question_token = questions.bind(questions.QuestionPolicy(ask_user and depth == 0))
    filter_token = tool_filter.bind(disabled_tools or ())
    plan_token = plan_policy.bind(plan_policy.PlanPolicy(plan, agent_spec.current().plan_tool, plan_lean))
    private_token = private_turn.bind(private)
    exact_token = context_breakdown.bind_exact(exact_context)
    effort_token = llm_options.bind_effort(effort.effort)
    limits_token = token_limits.bind_user_limits(limits)
    try:
        if cancellation.is_cancelled(request_id):
            raise ChatCancelled()
        if getattr(spec, "role", None) == "architect":
            from src.agents.roles.architect import pipeline

            model = model_tiers.resolve("heavy", model_tiers.own_tiers(), MODEL, spec.id).model
            result = await pipeline.run(spec, question, lambda text: _PROVIDER_MODULE.run_interpret(text, model),
                                        request_id=request_id, depth=depth, delegated_by=delegated_by, on_event=on_event)
            delegation.record_usage(result.delegated_usage)
            result.delegated_usage = delegated_usage
            return result
        if private and not plan_mode:
            # Imported here: laya agents never load mcp_upstream.
            from src.tools.mcp_client import mcp_upstream

            await mcp_upstream.prefetch_private(private)
        # A confident classifier pick sends the question straight to a specialist, and this
        # agent's own model never runs (agents/auto_route.py; off unless configured).
        routed, routed_tier, auto_note = (None, None, "") if plan_mode else await router_routing.route_turn(
            question, history, on_event, request_id, depth, model_tier)
        if routed is not None:
            routed.delegated_usage = delegated_usage
            return routed
        # A top-level turn that asked for no tier may get one from how hard its question looks (llm/auto_tier.py).
        if not model_tier and routed_tier:
            model_tier = routed_tier
        resolution = (
            model_tiers.resolve(model_tier, model_tiers.own_tiers(), MODEL, agent_spec.current().id)
            if model_tier else model_tiers.clamp_default(
                MODEL, getattr(_PROVIDER_MODULE, "DEFAULT_MODEL", None), agent_spec.current().id
            )
        )
        if auto_note:
            resolution = dataclasses.replace(resolution, note="; ".join(n for n in (auto_note, resolution.note) if n))
        provider_question = question
        if depth == 0 and agent_spec.current().memory_recall:
            if cancellation.is_cancelled(request_id):
                raise ChatCancelled()
            # Only the question the model sees changes; attachments and the stored chat keep the original.
            provider_question = await memory_recall.with_recall(question, on_event)
        if depth == 0 and agent_spec.current().skill_recall:
            if cancellation.is_cancelled(request_id):
                raise ChatCancelled()
            provider_question = await skill_recall.with_skills(question, provider_question, on_event)
        if inspect.iscoroutinefunction(_PROVIDER_MODULE.run_chat):
            result = await _PROVIDER_MODULE.run_chat(
                provider_question, history, resolution.model, enabled_extensions, request_id, depth,
                on_event=on_event, caveman=caveman,
            )
            result.delegated_usage = delegated_usage
        else:
            # Phase 1: openai_provider is still sync - run it off the event
            # loop thread so a slow completion doesn't block other requests
            # this ai_agent process is serving. on_event is dropped here on
            # purpose: a sync provider has nowhere to await it from (Phase 3
            # converts openai_provider the same way Task 3 did anthropic_provider).
            result = await anyio.to_thread.run_sync(
                lambda: _PROVIDER_MODULE.run_chat(
                    provider_question, history, resolution.model, enabled_extensions, request_id, depth,
                    caveman=caveman,
                )
            )
        result.model_tier = resolution.tier
        result.model_note = resolution.note
        result.reasoning_effort = effort.effort
        result.effort_note = effort.note
        result.private_extension_errors = list(private.errors)
        if depth == 0 and agent_spec.current().skill_learning:
            # In the background and after the answer exists: learning never delays or changes the turn.
            skill_reflection.schedule(question, result, request_id)
        return result
    finally:
        token_limits.reset_user_limits(limits_token)
        llm_options.reset_effort(effort_token)
        context_breakdown.reset_exact(exact_token)
        private_turn.reset(private_token)
        plan_policy.reset(plan_token)
        tool_filter.reset(filter_token)
        questions.reset(question_token)
        approvals.reset(approval_token)
        delegation.reset_enabled_extensions(extensions_token)
        delegation.reset_caveman(caveman_token)
        delegation.reset_attachments(attachment_token)
        delegation.reset_usage(usage_token)
        cancellation.clear(request_id)
        cancellation.reset_request(request_token)


def run_interpret(text: str) -> ChatResult:
    """A single non-agentic completion - see llm/anthropic_provider.py's
    run_interpret. Unlike run_chat, this never registers/clears
    cancellation: it's always one call, not a multi-round loop a user
    could need to interrupt mid-way."""
    model = model_tiers.clamp_default(MODEL, getattr(_PROVIDER_MODULE, "DEFAULT_MODEL", None), agent_spec.current().id).model
    return _PROVIDER_MODULE.run_interpret(text, model)


def cancel(request_id: str) -> bool:
    return cancellation.cancel(request_id)


def status() -> dict[str, Any]:
    spec = agent_spec.current()
    primary = spec.llm.gateway or agent_spec.default_gateway(PROVIDER_ID)
    gateways = []
    for name in (primary, *(choice.gateway for choice in spec.llm.fallback_gateways)):
        key = cooldown.gateway_key(PROVIDER_ID, name)
        remaining = cooldown.seconds_remaining(key)
        credentials = _PROVIDER_MODULE.has_api_key() if name == primary else _PROVIDER_MODULE.has_api_key(name)
        gateways.append({"gateway": name, "available": credentials and remaining <= 0,
                         "cooldown_seconds_remaining": int(remaining)})
    available = _PROVIDER_MODULE.is_available()
    reason = None
    if not available and not _PROVIDER_MODULE.has_api_key():
        reason = "missing_key"
    elif not available and any(gateway["cooldown_seconds_remaining"] for gateway in gateways):
        reason = "rate_limited"
    elif not available:
        reason = "unavailable"
    model = MODEL or _PROVIDER_MODULE.DEFAULT_MODEL
    return {
        "provider_id": PROVIDER_ID,
        "vendor_label": _PROVIDER_MODULE.VENDOR_LABEL,
        "model": model,
        "available": available,
        "reason": reason,
        "cooldown_seconds_remaining": gateways[0]["cooldown_seconds_remaining"],
        "gateways": gateways,
        "context_window": context_window_for(model),
    }
