"""OpenAI Responses API provider - pinned by agent_config.py when
AI_AGENT_PROVIDER=openai.

Adapted from chat_app/src/services/llm/openai_provider.py - see
anthropic_provider.py's module docstring for what changed and why.

AI_AGENT_GATEWAY picks which client this instance talks through, same
pattern as anthropic_provider.py: always loaded from
gateways/openai/<gateway>.json. "gpt" (default)
is just another block there, except it has no base_url (the OpenAI SDK
already defaults to api.openai.com) and its api_key points at the plain
GPT_API_KEY var. "azure" is the one exception requiring a different SDK
client class (AzureOpenAI - azure_endpoint/api_version/deployment, not a
base_url swap). Any other value (e.g. "together", "groq", "fireworks",
"deepinfra", "perplexity", "ollama", "vllm") is a plain OpenAI-compatible
base_url swap block.

has_api_key() checks the CURRENTLY SELECTED gateway's own required
secret(s), not a fixed var - a developer running only "groq" with
GROQ_API_KEY set (and no GPT_API_KEY at all) is correctly seen as
configured.

Caveat worth knowing: run_chat/run_interpret below call client.responses.
create - the OpenAI Responses API. Azure OpenAI supports it; most of the
other gateways (Together, Groq, Fireworks, DeepInfra, Perplexity, Ollama,
vLLM) only implement the older Chat Completions API
(client.chat.completions.create), not Responses. Pointing AI_AGENT_GATEWAY
at one of those will build a client fine but run_chat's actual API calls
may 404 - swapping the call site to chat.completions is a separate,
larger change (different message/tool-call shapes) than the client
wiring here.
"""

from __future__ import annotations

import json
import os
from typing import Any, Sequence

import httpx
from openai import APIStatusError, AsyncAzureOpenAI, AsyncOpenAI, AzureOpenAI, BadRequestError, OpenAI

from src.llm.turn_guard import TurnStopped
from src.agents import agent_routing, agent_spec, ask_user, delegation, plan
from src.llm.gateway_failover import GatewayRoute, classify

from src.core import approvals, questions

from src.agents.agent_spec import RosterEntry
from src.llm import cancellation, cooldown, llm_config, llm_options, token_limits
from src.llm.agent_roles import SYSTEM_PROMPT, roster_block, system_prompt_for
from src.llm.context_breakdown import ProviderCounter, breakdown_fields
from src.core.chat_history import validate_history
from src.llm.base_provider import (
    BaseProvider, ChatCancelled, ChatResult, LiveUsage, OnEvent, ToolCallRecord, dispatch_with_progress, step_event,
)
from src.mcp_client.mcp_upstream import call_tool, list_tools, tool_description


PROVIDER_NAME = "openai"

# Read by agent_config.py to decide whether this provider's run_chat() can
# be driven with a live on_event callback (streamed tokens +
# step_start/step_end around tool calls) or only awaited for a final
# ChatResult - see anthropic_provider.py's SUPPORTS_STREAMING for the same
# flag on that provider.
SUPPORTS_STREAMING = True


class _OpenAI(BaseProvider):
    PROVIDER_ID = "openai"
    GATEWAY_ENV = "AI_AGENT_GATEWAY"
    DEFAULT_MODEL_FALLBACK = "gpt-5.6-sol"

    _clients: dict[str, Any] = {}
    _sync_clients: dict[str, Any] = {}

    @classmethod
    def _gateway_name(cls) -> str:
        return os.getenv(cls.GATEWAY_ENV) or "gpt"

    @classmethod
    def has_api_key(cls, gateway: str | None = None) -> bool:
        gateway_name = gateway or cls._gateway_name()
        try:
            cfg = llm_config.gateway(PROVIDER_NAME, gateway_name)
        except KeyError:
            return False
        if gateway_name == "azure":
            return bool(cfg.get("azure_endpoint") and cfg.get("api_key"))
        return bool(cfg.get("api_key") or cfg.get("auth_token"))

    @classmethod
    def is_available(cls) -> bool:
        names = (cls._gateway_name(), *(choice.gateway for choice in agent_spec.current().llm.fallback_gateways))
        return any(cls.has_api_key(name) and not cooldown.is_in_cooldown(cooldown.gateway_key(cls.PROVIDER_ID, name))
                   for name in names)

    @classmethod
    def _build_client(cls, gateway: str | None, cache: dict[str, Any], plain: Any, azure: Any) -> Any:
        """Resolve the gateway and build (once, cached in `cache`) its SDK client from the
        given classes: the Async* ones for get_client(), the sync ones for get_sync_client()."""
        gateway_name = gateway or cls._gateway_name()
        if gateway_name in cache:
            return cache[gateway_name]

        if gateway_name == "azure":
            cfg = llm_config.gateway(PROVIDER_NAME, "azure")
            if not cfg.get("azure_endpoint") or not cfg.get("api_key"):
                raise ValueError(
                    "gateways/openai/azure.json: AZURE_OPENAI_ENDPOINT / "
                    "AZURE_OPENAI_API_KEY not set in .env"
                )
            cache[gateway_name] = azure(
                azure_endpoint=cfg["azure_endpoint"],
                api_version=cfg.get("api_version"),
                api_key=cfg["api_key"],
            )
            return cache[gateway_name]

        # Every other block ("gpt" itself, "together", "groq", "ollama",
        # ...) is a plain OpenAI() build - the gateway file supplies
        # api_key/base_url, "gpt"'s own block just leaves base_url unset
        # (SDK default).
        cfg = llm_config.gateway(PROVIDER_NAME, gateway_name)
        secret = cfg.get("api_key") or cfg.get("auth_token")
        if not secret:
            raise ValueError(
                f"gateways/openai/{gateway_name}.json: its api_key env var is not "
                "set in .env"
            )
        cache[gateway_name] = plain(api_key=secret, base_url=cfg.get("base_url"))
        return cache[gateway_name]

    @classmethod
    def get_client(cls, gateway: str | None = None) -> AsyncOpenAI | AsyncAzureOpenAI:
        return cls._build_client(gateway, cls._clients, AsyncOpenAI, AsyncAzureOpenAI)

    @classmethod
    def get_sync_client(cls, gateway: str | None = None) -> OpenAI | AzureOpenAI:
        """Same as get_client(), but the plain synchronous SDK classes, cached separately.
        Used by run_interpret(), whose client.responses.create(...) calls are never awaited."""
        return cls._build_client(gateway, cls._sync_clients, OpenAI, AzureOpenAI)

    @classmethod
    def resolve_default_model(cls) -> str:
        try:
            cfg = llm_config.gateway(PROVIDER_NAME, cls._gateway_name())
        except KeyError:
            cfg = {}
        if cfg.get("model"):
            return cfg["model"]
        return cls.DEFAULT_MODEL_FALLBACK

    @classmethod
    def resolve_vendor_label(cls) -> str:
        """See anthropic_provider._Anthropic.resolve_vendor_label - same
        reasoning, just the files in gateways/openai/."""
        gateway_name = cls._gateway_name()
        try:
            cfg = llm_config.gateway(PROVIDER_NAME, gateway_name)
        except KeyError:
            cfg = {}
        return cfg.get("label") or gateway_name.capitalize()


PROVIDER_ID = _OpenAI.PROVIDER_ID
DEFAULT_MODEL = _OpenAI.resolve_default_model()
VENDOR_LABEL = _OpenAI.resolve_vendor_label()

_get_client = _OpenAI.get_client
_get_sync_client = _OpenAI.get_sync_client
has_api_key = _OpenAI.has_api_key
is_available = _OpenAI.is_available


def _tool_schemas(
    enabled_extensions: list[str] | None = None, roster: Sequence[RosterEntry] = ()
) -> list[dict[str, Any]]:
    # display_label rides along on every schema dict returned here, same as
    # anthropic_provider._tool_schemas - NOT a real Responses API tools=
    # field, so run_chat pops it back off before sending schemas to the API.
    schemas = [
        {
            "type": "function",
            "name": tool.name,
            "description": tool_description(tool),
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            "display_label": (tool.meta or {}).get("display_label") if hasattr(tool, "meta") else None,
        }
        for tool in list_tools(enabled_extensions)
    ]
    # Only an orchestrator has a roster, so only it can delegate.
    if roster:
        schemas.append(
            {
                "type": "function",
                "name": delegation.TOOL_NAME,
                "description": delegation.tool_description(list(roster)),
                "parameters": delegation.tool_parameters(list(roster)),
                "display_label": None,
            }
        )
    # Only the top-level agent of a turn whose caller can show questions.
    if questions.current().enabled:
        schemas.append(
            {
                "type": "function",
                "name": ask_user.TOOL_NAME,
                "description": ask_user.tool_description(),
                "parameters": ask_user.tool_parameters(),
                "display_label": None,
            }
        )
    policy = plan.current()
    if policy.offered:
        schemas.append({
            "type": "function",
            "name": plan.TOOL_NAME,
            "description": plan.tool_description(policy.lean),
            "parameters": plan.tool_parameters(),
            "display_label": "Plan",
        })
    return schemas


# Fields the SDK adds to the parsed output items that stream.get_final_response()
# returns (ParsedResponseFunctionToolCall.parsed_arguments,
# ParsedResponseOutputText.parsed) - the Responses API rejects them when the
# items are sent back as input ("Unknown parameter: input[3].parsed_arguments").
_SDK_ONLY_FIELDS = {"parsed_arguments", "parsed"}

class _OpenAIRequestCounter:
    """The Responses API's input-token count, for a minimal request (see
    context_breakdown.ProviderCounter). A client or gateway without it raises,
    and the caller settles for the estimate."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    async def count(self, *, system: str = "", tools: Sequence[dict[str, Any]] = ()) -> int:
        extra: dict[str, Any] = {}
        if system:
            extra["instructions"] = system
        if tools:
            extra["tools"] = list(tools)
        counted = await self._client.responses.input_tokens.count(
            model=self._model, input=[{"role": "user", "content": "x"}], **extra
        )
        return int(counted.input_tokens)


# Stream events that carry tokens the user never sees as text (reasoning and
# tool-call arguments); they only feed the live token meter.
_REASONING_DELTAS = frozenset({
    "response.reasoning_summary_text.delta",
    "response.reasoning_text.delta",
    "response.function_call_arguments.delta",
})


def _strip_sdk_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_sdk_fields(v) for k, v in value.items() if k not in _SDK_ONLY_FIELDS}
    if isinstance(value, list):
        return [_strip_sdk_fields(v) for v in value]
    return value


def _output_as_input_items(output: list[Any]) -> list[Any]:
    """Response output items, as plain dicts safe to resend as input."""
    return [
        _strip_sdk_fields(item.model_dump(exclude_none=True)) if hasattr(item, "model_dump") else item
        for item in output
    ]


def _dispatch(name: str, arguments: dict[str, Any], depth: int) -> str:
    if name == delegation.TOOL_NAME:
        return delegation.dispatch(arguments, depth)
    return call_tool(name, arguments)


def _route_for_turn() -> GatewayRoute:
    return GatewayRoute.for_turn(PROVIDER_ID, _OpenAI._gateway_name(),
                                 (choice.gateway for choice in agent_spec.current().llm.fallback_gateways),
                                 lambda gateway: has_api_key(gateway))


def _model_for_route(route: GatewayRoute, requested: str | None) -> str:
    primary = _OpenAI._gateway_name()
    if route.current == primary:
        return requested or DEFAULT_MODEL
    explicit = next((choice.model for choice in agent_spec.current().llm.fallback_gateways
                     if choice.gateway == route.current), None)
    return llm_config.model_for_gateway(PROVIDER_ID, primary, route.current, requested or DEFAULT_MODEL, explicit)


def _strip_reasoning(messages: list[Any]) -> list[Any]:
    """Reasoning item ids and encrypted payloads cannot cross gateway boundaries."""
    return [message for message in messages
            if (message.get("type") if isinstance(message, dict) else getattr(message, "type", None)) != "reasoning"]


async def run_chat(
    question: str,
    history: list[dict[str, Any]],
    model: str | None = None,
    enabled_extensions: list[str] | None = None,
    request_id: str | None = None,
    depth: int = 0,
    on_event: OnEvent | None = None,
    caveman: bool = False,
) -> ChatResult:
    history = validate_history(history)
    route = _route_for_turn()
    client = _get_client() if route.current == _OpenAI._gateway_name() else _get_client(route.current)
    model_name = _model_for_route(route, model)
    history = token_limits.trim_history_to_fit(history, PROVIDER_ID, route.current)
    roster = await agent_routing.roster_for()
    system_prompt = system_prompt_for(caveman, roster)
    messages: list[Any] = [{"role": "system", "content": system_prompt}, *history]
    messages.append({"role": "user", "content": question})
    tools_used: list[str] = []
    tool_calls: list[ToolCallRecord] = []
    schemas = _tool_schemas(enabled_extensions, roster)
    # display_label isn't a real Responses API tools= field (see
    # _tool_schemas) - pop it into this name->label lookup here, once,
    # rather than sending it to the API or re-deriving it per call below.
    labels = {s["name"]: s.pop("display_label") for s in schemas}
    # Stays None (rather than 0) until a round actually reports usage -
    # some SDK versions leave response.usage unset, and a provider that
    # never reported usage should say "unknown" (see ChatResult.total_tokens),
    # not "zero tokens".
    total_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    meter = LiveUsage(on_event)
    options = llm_options.for_provider(PROVIDER_ID)
    guard = options.turn_guard()
    checklist = plan.Checklist()
    stop_message = 'Reached maximum tool-call rounds without a final answer.'
    # The full prompt just sent (all resent history), not a sum across
    # rounds like total_tokens - overwritten each round rather than
    # accumulated, same reasoning as anthropic_provider.run_chat.
    context_tokens: int | None = None
    roster_text = roster_block(roster)

    async def breakdown() -> dict[str, Any]:
        return await breakdown_fields(
            context_tokens, system_prompt, roster_text, schemas,
            lambda: ProviderCounter(_OpenAIRequestCounter(client, model_name), model_name),
        )

    async def result(response: str) -> ChatResult:
        return ChatResult(
            response=response,
            tools_used=tools_used,
            tool_calls=tool_calls,
            provider_id=PROVIDER_ID,
            gateway=route.current,
            gateway_switches=[switch.as_dict() for switch in route.switches],
            model=model_name,
            total_tokens=total_tokens,
            context_tokens=context_tokens,
            **await breakdown(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    try:
        async with guard.timeout():
            for _ in range(options.max_tool_rounds(token_limits.max_tool_rounds(PROVIDER_ID, route.current))):
                if cancellation.is_cancelled(request_id):
                    raise ChatCancelled()
                # Every round is streamed, so text appears as the model writes
                # it. A round that ends in function calls may still have streamed
                # some text first; "token_reset" tells the client to drop it,
                # since the real answer is the text of the final (no-tool) round.
                while True:
                    token_limits.enforce_context_limit(PROVIDER_ID, messages, route.current)
                    text_parts: list[str] = []
                    try:
                        async with client.responses.stream(
                            model=model_name,
                            input=messages,
                            tools=schemas if schemas else None,
                            max_output_tokens=options.max_tokens(token_limits.max_output_tokens(PROVIDER_ID, route.current)),
                            **options.extra_kwargs(model_name),
                        ) as stream:
                            async for event in stream:
                                if event.type == "response.output_text.delta":
                                    text_parts.append(event.delta)
                                    if on_event:
                                        await on_event(step_event("token", text=event.delta))
                                    await meter.chars(len(event.delta))
                                elif event.type in _REASONING_DELTAS:
                                    # Not shown as the answer, but the model is
                                    # spending tokens: keep the live meter moving.
                                    await meter.chars(len(event.delta))
                                elif event.type == "response.failed":
                                    failure = getattr(event.response, "error", None)
                                    status = {"server_error": 503, "rate_limit_exceeded": 429}.get(
                                        getattr(failure, "code", None))
                                    if status is not None:
                                        # Responses can fail after HTTP 200. Adapt known SDK
                                        # failure codes to the shared HTTP classifier before
                                        # get_final_response loses them behind a RuntimeError.
                                        # These transport objects perform no network I/O.
                                        response_error = httpx.Response(status, request=httpx.Request(
                                            "POST", "https://gateway.invalid"))
                                        raise APIStatusError(failure.message, response=response_error, body=None)
                            response = await stream.get_final_response()
                        break
                    except Exception as error:
                        if isinstance(error, BadRequestError) and classify(error) is None:
                            if not text_parts and options.drop_rejected(str(error), model_name):
                                continue
                        switch = route.advance(error)
                        if switch is None:
                            raise
                        if on_event:
                            if text_parts:
                                await on_event(step_event("token_reset"))
                            await on_event(step_event("gateway_switch", **switch.as_dict()))
                        messages = _strip_reasoning(messages)
                        client = _get_client(route.current)
                        model_name = _model_for_route(route, model)
                usage = getattr(response, "usage", None)
                round_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
                if round_tokens is not None:
                    total_tokens = (total_tokens or 0) + round_tokens
                round_input = getattr(usage, "input_tokens", None) if usage is not None else None
                if round_input is not None:
                    input_tokens = (input_tokens or 0) + round_input
                round_output = getattr(usage, "output_tokens", None) if usage is not None else None
                if round_output is not None:
                    output_tokens = (output_tokens or 0) + round_output
                await meter.round_done(round_tokens)
                context_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
                guard.check_tokens(total_tokens)

                function_calls = [item for item in response.output if getattr(item, "type", "") == "function_call"]
                if not function_calls:
                    return await result("".join(text_parts) or response.output_text)

                if text_parts and on_event:
                    await on_event(step_event("token_reset"))

                messages.extend(_output_as_input_items(response.output))
                for call in function_calls:
                    try:
                        arguments = json.loads(call.arguments or "{}")
                    except Exception:
                        arguments = {}
                    guard.check_call(call.name, arguments)
                    tools_used.append(call.name)
                    step_id = call.call_id
                    if on_event:
                        await on_event(step_event(
                            "step_start", id=step_id, tool=call.name, label=labels.get(call.name), arguments=arguments,
                        ))
                    # Local planning and questions do not run external tools or need approval.
                    asked = await checklist.handle(call.name, arguments, on_event)
                    if asked is None:
                        asked = await questions.handle(call.name, request_id, step_id, arguments, on_event)
                    if asked is not None:
                        result_text, ok = asked
                    else:
                        # With approvals on, the user answers before anything runs; a
                        # refusal is handed to the model as this step's result.
                        declined = await approvals.review(
                            request_id, step_id, call.name, labels.get(call.name), arguments, on_event
                        )
                        if declined is not None:
                            result_text, ok = declined, False
                        else:
                            try:
                                result_text = await dispatch_with_progress(_dispatch, on_event, step_id, call.name, arguments, depth)
                                ok = True
                            except Exception as error:
                                result_text = f"Tool '{call.name}' failed: {error}"
                                ok = False
                    if on_event:
                        await on_event(step_event("step_end", id=step_id, ok=ok, result=result_text))
                    tool_calls.append(ToolCallRecord(name=call.name, arguments=arguments, result=result_text))
                    messages.append({"type": "function_call_output", "call_id": call.call_id, "output": result_text})
    except TurnStopped as error:
        stop_message = str(error)
    except TimeoutError:
        cancellation.cancel(request_id)
        stop_message = guard.time_message()

    if on_event:
        await on_event(step_event("token_reset"))
        await on_event(step_event("token", text=stop_message))
    return await result(stop_message)


def run_interpret(text: str, model: str | None = None) -> ChatResult:
    """One non-agentic completion, no tools offered - see
    claude_provider.run_interpret's docstring, same reasoning. Uses
    _get_sync_client(), not _get_client() - this call is a plain,
    non-`await`ed client.responses.create(...), same reasoning as
    anthropic_provider.run_interpret."""
    route = _route_for_turn()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    while True:
        client = _get_sync_client() if route.current == _OpenAI._gateway_name() else _get_sync_client(route.current)
        model_name = _model_for_route(route, model)
        token_limits.enforce_context_limit(PROVIDER_ID, messages, route.current)
        try:
            response = client.responses.create(
                model=model_name,
                input=messages,
                max_output_tokens=llm_options.for_provider(PROVIDER_ID).max_tokens(
                    token_limits.max_output_tokens(PROVIDER_ID, route.current)),
            )
        except Exception as error:
            if route.advance(error) is None:
                raise
            continue
        usage = getattr(response, "usage", None)
        total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
        context_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
        return ChatResult(
            response=response.output_text, provider_id=PROVIDER_ID, model=model_name,
            gateway=route.current, gateway_switches=[switch.as_dict() for switch in route.switches],
            total_tokens=total_tokens, context_tokens=context_tokens,
            input_tokens=context_tokens,
            output_tokens=getattr(usage, "output_tokens", None) if usage is not None else None,
        )
