"""Anthropic Messages API provider - pinned by agent_config.py when
AI_AGENT_PROVIDER=anthropic. (Renamed from claude_provider.py - the
AI_AGENT_PROVIDER value and PROVIDER_ID/cooldown key are "anthropic".)

Adapted from chat_app/src/services/llm/claude_provider.py: tool calls go
through src.mcp_client.mcp_upstream instead of src.services.mcp_client; no MODELS
list or ProviderSpec registration (this project pins one provider per
instance - see agent_config.py); DEFAULT_MODEL replaces chat_app's
shared Settings object. The tool-calling loop itself, including the
cancellation checkpoint between rounds, is unchanged.

AI_AGENT_GATEWAY picks which client this instance talks through, always
by loading gateways/anthropic/<gateway>.json - "claude" (default) is just another block there,
same as "openrouter"/"litellm"/"portkey"/etc, except it has no base_url
(the Anthropic SDK already defaults to api.anthropic.com), needs no
auth_token (Anthropic's own API takes a plain api_key), and its api_key
points at the plain CLAUDE_API_KEY var. "bedrock" and "vertex" are the
two exceptions requiring a different SDK client class (AnthropicBedrock/
AnthropicVertex, different auth shape entirely) rather than a base_url
swap. Whichever block is picked, the actual secret values it points at
("{CLAUDE_API_KEY}" etc) still only ever come from .env,
resolved by llm_config.py - never written in the JSON file itself.
has_api_key() checks the CURRENTLY SELECTED gateway's own required
secret(s), not a fixed var - a developer running only "openrouter" with
OPENROUTER_API_KEY set (and no CLAUDE_API_KEY at all) is correctly seen
as configured.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from typing import Any, AsyncIterator, Sequence

from anthropic import (
    Anthropic,
    AnthropicBedrock,
    AnthropicVertex,
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AsyncAnthropicVertex,
    BadRequestError,
)
from anthropic.lib.streaming import AsyncMessageStream

from src.llm.turn_guard import TurnStopped
from src.agents import agent_routing, agent_spec, ask_user, delegation, plan
from src.core.catalog import catalog
from src.llm.gateway_failover import GatewayRoute, classify

from src.core import approvals, questions
from src.core.chat_history import validate_history

from src.agents.agent_spec import RosterEntry
from src.llm import cancellation, cooldown, llm_config, llm_options, token_limits
from src.llm.agent_roles import SYSTEM_PROMPT, roster_block, system_prompt_for
from src.llm.context_breakdown import ProviderCounter, breakdown_fields
from src.llm.base_provider import (
    BaseProvider, ChatCancelled, ChatResult, LiveUsage, OnEvent, ToolCallRecord, dispatch_with_progress, step_event,
)
from src.mcp_client.mcp_upstream import call_tool, list_tools, tool_description


PROVIDER_NAME = "anthropic"
_log = logging.getLogger(__name__)

_CACHE_CONTROL = {"type": "ephemeral"}

# Read by Task 4's agent_config.py to decide whether this provider's
# run_chat() can be driven with a live on_event callback (streamed tokens +
# step_start/step_end around tool calls) or only awaited for a final
# ChatResult - every provider module gets this flag, not just the ones
# that support it, so agent_config.py can check it without a try/except.
SUPPORTS_STREAMING = True


class _Anthropic(BaseProvider):
    PROVIDER_ID = "anthropic"
    GATEWAY_ENV = "AI_AGENT_GATEWAY"
    DEFAULT_MODEL_FALLBACK = "claude-sonnet-5"

    _clients: dict[str, Any] = {}
    _sync_clients: dict[str, Any] = {}

    @classmethod
    def _gateway_name(cls) -> str:
        return os.getenv(cls.GATEWAY_ENV) or "claude"

    @classmethod
    def has_api_key(cls, gateway: str | None = None) -> bool:
        gateway_name = gateway or cls._gateway_name()
        try:
            cfg = llm_config.gateway(PROVIDER_NAME, gateway_name)
        except KeyError:
            return False
        if gateway_name == "bedrock":
            return bool(cfg.get("aws_access_key_id") and cfg.get("aws_secret_access_key"))
        if gateway_name == "vertex":
            return bool(cfg.get("project_id"))
        return bool(cfg.get("api_key") or cfg.get("auth_token"))

    @classmethod
    def is_available(cls) -> bool:
        names = (cls._gateway_name(), *(choice.gateway for choice in agent_spec.current().llm.fallback_gateways))
        return any(cls.has_api_key(name) and not cooldown.is_in_cooldown(cooldown.gateway_key(cls.PROVIDER_ID, name))
                   for name in names)

    @classmethod
    def _build_client(cls, gateway: str | None, cache: dict[str, Any], plain: Any, bedrock: Any, vertex: Any) -> Any:
        """Resolve the gateway and build (once, cached in `cache`) its SDK client from the
        given classes: the Async* ones for get_client(), the sync ones for get_sync_client()."""
        gateway_name = gateway or cls._gateway_name()
        if gateway_name in cache:
            return cache[gateway_name]

        if gateway_name == "bedrock":
            cfg = llm_config.gateway(PROVIDER_NAME, "bedrock")
            cache[gateway_name] = bedrock(
                aws_access_key=cfg.get("aws_access_key_id"),
                aws_secret_key=cfg.get("aws_secret_access_key"),
                aws_region=cfg.get("aws_region"),
            )
            return cache[gateway_name]

        if gateway_name == "vertex":
            cfg = llm_config.gateway(PROVIDER_NAME, "vertex")
            if not cfg.get("project_id"):
                raise ValueError("gateways/anthropic/vertex.json project_id env var not set")
            cache[gateway_name] = vertex(project_id=cfg["project_id"], region=cfg.get("region"))
            return cache[gateway_name]

        # Every other block ("claude" itself, "openrouter", "litellm",
        # "helicone", "portkey", ...) is a plain Anthropic() build -
        # The gateway file supplies api_key/auth_token/base_url, "claude"'s
        # own block just leaves base_url unset (SDK default).
        cfg = llm_config.gateway(PROVIDER_NAME, gateway_name)
        api_key = cfg.get("api_key")
        auth_token = cfg.get("auth_token")
        if not api_key and not auth_token:
            raise ValueError(
                f"gateways/anthropic/{gateway_name}.json: neither its api_key nor "
                "auth_token env var is set in .env"
            )
        cache[gateway_name] = plain(api_key=api_key, auth_token=auth_token, base_url=cfg.get("base_url"))
        return cache[gateway_name]

    @classmethod
    def get_client(cls, gateway: str | None = None) -> AsyncAnthropic | AsyncAnthropicBedrock | AsyncAnthropicVertex:
        return cls._build_client(gateway, cls._clients, AsyncAnthropic, AsyncAnthropicBedrock, AsyncAnthropicVertex)

    @classmethod
    def get_sync_client(cls, gateway: str | None = None) -> Anthropic | AnthropicBedrock | AnthropicVertex:
        """Same as get_client(), but the plain synchronous SDK classes, cached separately.
        Exists solely for run_interpret(), whose single non-streaming
        `client.messages.create(...)` call is never awaited."""
        return cls._build_client(gateway, cls._sync_clients, Anthropic, AnthropicBedrock, AnthropicVertex)

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
        """Human-readable name of the CURRENTLY SELECTED gateway (its
        "label" field in gateways/anthropic/<gateway>.json), for chat_app's
        provider dropdown to show the actual vendor in use - e.g.
        "OpenRouter" rather than a static "Claude Agent" - when
        AI_AGENT_GATEWAY points this instance somewhere other than
        "claude". Falls back to the gateway's own name, capitalized, if
        its block has no "label" (or the gateway name is unknown)."""
        gateway_name = cls._gateway_name()
        try:
            cfg = llm_config.gateway(PROVIDER_NAME, gateway_name)
        except KeyError:
            cfg = {}
        return cfg.get("label") or gateway_name.capitalize()


PROVIDER_ID = _Anthropic.PROVIDER_ID
DEFAULT_MODEL = _Anthropic.resolve_default_model()
VENDOR_LABEL = _Anthropic.resolve_vendor_label()

_get_client = _Anthropic.get_client
_get_sync_client = _Anthropic.get_sync_client
has_api_key = _Anthropic.has_api_key
is_available = _Anthropic.is_available


def _dispatch(name: str, arguments: dict[str, Any], depth: int) -> str:
    if name == delegation.TOOL_NAME:
        return delegation.dispatch(arguments, depth)
    return call_tool(name, arguments)


def _tool_schemas(
    enabled_extensions: list[str] | None = None, roster: Sequence[RosterEntry] = ()
) -> list[dict[str, Any]]:
    # display_label rides along on every schema dict returned here so
    # run_chat can build its step_start "label" lookup from the same
    # list it already has - it is NOT a real Anthropic tools= schema
    # field, so run_chat pops it back off before sending schemas to the
    # API (see the `labels = {...pop...}` line below).
    schemas = [
        {
            "name": tool.name,
            "description": tool_description(tool),
            "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
            "display_label": (tool.meta or {}).get("display_label") if hasattr(tool, "meta") else None,
        }
        for tool in list_tools(enabled_extensions)
    ]
    # Only an orchestrator has a roster, so only it can delegate.
    if roster:
        schemas.append(
            {
                "name": delegation.TOOL_NAME,
                "description": delegation.tool_description(list(roster)),
                "input_schema": delegation.tool_parameters(list(roster)),
                "display_label": None,
            }
        )
    # Only the top-level agent of a turn whose caller can show questions.
    if questions.current().enabled:
        schemas.append(
            {
                "name": ask_user.TOOL_NAME,
                "description": ask_user.tool_description(),
                "input_schema": ask_user.tool_parameters(),
                "display_label": None,
            }
        )
    policy = plan.current()
    if policy.offered:
        schemas.append({
            "name": plan.TOOL_NAME,
            "description": plan.tool_description(policy.lean),
            "input_schema": plan.tool_parameters(),
            "display_label": "Plan",
        })
    return schemas


def _prompt_cache_enabled(gateway: str | None = None) -> bool:
    """True when this gateway's block in gateways/anthropic/ sets "prompt_cache".
    Opt-in: a gateway that routes to non-Claude models may reject cache_control."""
    try:
        return bool(llm_config.gateway(PROVIDER_NAME, gateway or _Anthropic._gateway_name()).get("prompt_cache"))
    except KeyError:
        return False


def _cached_request(system_prompt: str, schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`system` and `tools` with cache breakpoints on the system block and the
    last tool. Requests render tools, then system, then messages, so the tool
    breakpoint survives a system prompt change (caveman, roster) and the system
    breakpoint covers both."""
    system = [{"type": "text", "text": system_prompt, "cache_control": _CACHE_CONTROL}]
    tools = list(schemas)
    if tools:
        tools[-1] = {**tools[-1], "cache_control": _CACHE_CONTROL}
    return system, tools


def _with_history_breakpoint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`messages` for one request, with a cache breakpoint on the last message's last
    block, so the next round of a tool loop (or the next turn, within the cache's life)
    reads everything up to here from cache. A copy: `messages` itself never carries
    the marker, or each round would add one and pass the API's limit of four. The last
    message of a request is always the user's question or its tool results, built here
    as a string or dicts; any other shape is sent as it is."""
    if not messages:
        return messages
    last = messages[-1]
    content = last.get("content")
    if isinstance(content, str) and content:
        marked: Any = [{"type": "text", "text": content, "cache_control": _CACHE_CONTROL}]
    elif isinstance(content, list) and content and isinstance(content[-1], dict):
        marked = [*content[:-1], {**content[-1], "cache_control": _CACHE_CONTROL}]
    else:
        return messages
    return [*messages[:-1], {**last, "content": marked}]


class _AnthropicRequestCounter:
    """Anthropic's count_tokens endpoint, for a minimal request (see context_breakdown.ProviderCounter).
    A client or gateway without it raises, and the caller settles for the estimate."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    async def count(self, *, system: str = "", tools: Sequence[dict[str, Any]] = ()) -> int:
        extra: dict[str, Any] = {}
        if system:
            extra["system"] = system
        if tools:
            extra["tools"] = list(tools)
        counted = await self._client.messages.count_tokens(
            model=self._model, messages=[{"role": "user", "content": "x"}], **extra
        )
        return int(counted.input_tokens)


async def _stream_pieces(stream: Any) -> AsyncIterator[tuple[bool, str]]:
    """Yield (is_text, chunk) for what a round streams. Only text goes to the
    user; thinking and tool-call JSON are yielded too (is_text False) so the
    live token meter keeps climbing while the model reasons or writes tool
    arguments. A stream without SDK events (a test double) only has text."""
    if not isinstance(stream, AsyncMessageStream):
        async for chunk in stream.text_stream:
            yield True, chunk
        return
    async for event in stream:
        if event.type == "text":
            yield True, event.text
        elif event.type == "thinking":
            yield False, event.thinking
        elif event.type == "input_json":
            yield False, event.partial_json


def _usage_count(usage: Any, name: str) -> int:
    """One usage counter; a gateway may omit it or send null."""
    value = getattr(usage, name, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _prompt_tokens(usage: Any) -> int:
    """The whole prompt of a round. Anthropic's input_tokens leaves out what the
    cache wrote or served, so those are added back."""
    return (
        _usage_count(usage, "input_tokens")
        + _usage_count(usage, "cache_creation_input_tokens")
        + _usage_count(usage, "cache_read_input_tokens")
    )


@catalog
def _route_for_turn() -> GatewayRoute:
    return GatewayRoute.for_turn(PROVIDER_ID, _Anthropic._gateway_name(),
                                 (choice.gateway for choice in agent_spec.current().llm.fallback_gateways),
                                 lambda gateway: has_api_key(gateway))


@catalog
def _model_for_route(route: GatewayRoute, requested: str | None) -> str:
    primary = _Anthropic._gateway_name()
    if route.current == primary:
        return requested or DEFAULT_MODEL
    explicit = next((choice.model for choice in agent_spec.current().llm.fallback_gateways
                     if choice.gateway == route.current), None)
    return llm_config.model_for_gateway(PROVIDER_ID, primary, route.current, requested or DEFAULT_MODEL, explicit)


@catalog
def _strip_thinking(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy assistant content without signatures issued by the previous gateway."""
    stripped = []
    for message in messages:
        content = message.get("content")
        if message.get("role") == "assistant" and isinstance(content, list):
            content = [block for block in content
                       if (block.get("type") if isinstance(block, dict) else getattr(block, "type", None))
                       not in ("thinking", "redacted_thinking")]
            if not content:
                continue
            message = {**message, "content": content}
        stripped.append(message)
    return stripped


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
    client = _get_client() if route.current == _Anthropic._gateway_name() else _get_client(route.current)
    roster = await agent_routing.roster_for()
    system_prompt = system_prompt_for(caveman, roster)
    model_name = _model_for_route(route, model)
    history = token_limits.trim_history_to_fit(history, PROVIDER_ID, route.current)
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": question}]
    tools_used: list[str] = []
    tool_calls: list[ToolCallRecord] = []
    schemas = _tool_schemas(enabled_extensions, roster)
    # display_label isn't a real Anthropic tools= field (see _tool_schemas) -
    # pop it into this name->label lookup here, once, rather than sending it
    # to the API or re-deriving it per tool_use block below.
    labels = {s["name"]: s.pop("display_label") for s in schemas}
    use_cache = _prompt_cache_enabled() if route.current == _Anthropic._gateway_name() else _prompt_cache_enabled(route.current)
    system, tools = _cached_request(system_prompt, schemas) if use_cache else (system_prompt, schemas)
    # Every round of this loop is a real, separately-billed API call, so a
    # multi-tool-call answer's total is the sum across all rounds, not just
    # the final one. Anthropic's usage object has input_tokens/output_tokens
    # but no total_tokens field of its own - always present on this API, so
    # this stays a plain int rather than the optional/"unknown" handling the
    # other providers need.
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0
    cached_input_tokens = 0
    meter = LiveUsage(on_event)
    options = llm_options.for_provider(PROVIDER_ID)
    guard = options.turn_guard()
    checklist = plan.Checklist()
    empty_answer_retried = False
    malformed_stream_retries: set[str] = set()
    failed_stream_tokens = 0
    stop_message = 'Reached maximum tool-call rounds without a final answer.'
    # The full prompt just sent (all resent history + this round's tool
    # results), not a sum across rounds like total_tokens - this is what
    # the usage bar and the phase-5 auto-trigger need to know how close
    # the *next* call is to the model's context window, so it's
    # overwritten each round rather than accumulated.
    context_tokens = 0
    roster_text = roster_block(roster)

    async def breakdown() -> dict[str, Any]:
        return await breakdown_fields(
            context_tokens, system_prompt, roster_text, schemas,
            lambda: ProviderCounter(_AnthropicRequestCounter(client, model_name), model_name),
        )

    try:
        async with guard.timeout():
            for _ in range(options.max_tool_rounds(token_limits.max_tool_rounds(PROVIDER_ID, route.current))):
                if cancellation.is_cancelled(request_id):
                    raise ChatCancelled()
                # Every round is streamed, so text appears as the model writes
                # it. A round that ends in tool_use may still have streamed some
                # text first; "token_reset" tells the client to drop it, since
                # the real answer is the text of the final (non-tool) round.
                while True:
                    if cancellation.is_cancelled(request_id):
                        raise ChatCancelled()
                    token_limits.enforce_context_limit(PROVIDER_ID, [system_prompt, *messages], route.current)
                    text_parts: list[str] = []
                    stream_chars = 0
                    stream_stage = "opening_stream"
                    try:
                        async with client.messages.stream(
                            model=model_name,
                            max_tokens=options.max_tokens(token_limits.max_output_tokens(PROVIDER_ID, route.current)),
                            system=system,
                            messages=_with_history_breakpoint(messages) if use_cache else messages,
                            tools=tools,
                            **options.extra_kwargs(model_name),
                        ) as stream:
                            stream_stage = "stream_events"
                            async for is_text, chunk in _stream_pieces(stream):
                                stream_chars += len(chunk)
                                if is_text:
                                    text_parts.append(chunk)
                                    if on_event:
                                        await on_event(step_event("token", text=chunk))
                                await meter.chars(len(chunk))
                            stream_stage = "final_message"
                            response = await stream.get_final_message()
                        break
                    except Exception as error:
                        if isinstance(error, json.JSONDecodeError):
                            # Omit exception text, chained exceptions and locals that
                            # may contain gateway payloads; retain parser stack frames.
                            _log.error(
                                "Anthropic response JSONDecodeError: gateway=%s model=%s request_id=%s "
                                "stage=%s line=%s column=%s position=%s\n%s",
                                route.current, model_name, request_id, stream_stage,
                                error.lineno, error.colno, error.pos,
                                "".join(traceback.format_tb(error.__traceback__)),
                            )
                            if classify(error) is None:
                                raise
                            # Failed streams lack final usage. Charge an estimate to
                            # the guard without labelling it as reported token usage.
                            failed_stream_tokens += token_limits.estimate_context_tokens(
                                [system_prompt, *messages, schemas]
                            ) + (stream_chars + len(error.doc) + 3) // 4
                            guard.check_tokens(total_tokens + failed_stream_tokens)
                            await meter.round_done(None)
                            if route.current not in malformed_stream_retries:
                                malformed_stream_retries.add(route.current)
                                _log.warning("Retrying malformed response stream: gateway=%s request_id=%s",
                                             route.current, request_id)
                                if text_parts and on_event:
                                    await on_event(step_event("token_reset"))
                                continue
                        elif isinstance(error, BadRequestError) and classify(error) is None:
                            if not text_parts and options.drop_rejected(str(error), model_name):
                                continue
                        switch = route.advance(error)
                        if switch is None:
                            if isinstance(error, json.JSONDecodeError):
                                raise TurnStopped(
                                    "The model gateway returned an invalid response stream after retrying. "
                                    "Please try again or choose another gateway."
                                ) from None
                            raise
                        if on_event:
                            if text_parts:
                                await on_event(step_event("token_reset"))
                            await on_event(step_event("gateway_switch", **switch.as_dict()))
                        messages = _strip_thinking(messages)
                        client = _get_client(route.current)
                        model_name = _model_for_route(route, model)
                        use_cache = _prompt_cache_enabled(route.current)
                        system, tools = _cached_request(system_prompt, schemas) if use_cache else (system_prompt, schemas)
                prompt_tokens = _prompt_tokens(response.usage)
                total_tokens += prompt_tokens + response.usage.output_tokens
                input_tokens += prompt_tokens
                output_tokens += response.usage.output_tokens
                cached_input_tokens += _usage_count(response.usage, "cache_read_input_tokens")
                await meter.round_done(prompt_tokens + response.usage.output_tokens)
                context_tokens = prompt_tokens
                guard.check_tokens(total_tokens + failed_stream_tokens)

                if response.stop_reason != "tool_use":
                    answer = "".join(block.text for block in response.content if block.type == "text")
                    streamed_answer = "".join(text_parts)
                    if not answer.strip():
                        answer = streamed_answer
                    if not answer.strip():
                        _log.warning(
                            "Anthropic returned no visible answer: gateway=%s model=%s request_id=%s "
                            "stop_reason=%s content_types=%s input_tokens=%s output_tokens=%s retried=%s",
                            route.current, model_name, request_id, response.stop_reason,
                            [block.type for block in response.content], prompt_tokens,
                            _usage_count(response.usage, "output_tokens"), empty_answer_retried,
                        )
                        stop_message = "The model returned no visible answer. Please try again or choose another model."
                        if response.stop_reason == "max_tokens":
                            stop_message = (
                                "The model reached its output limit without producing a visible answer. "
                                "Try a higher output limit or lower reasoning effort."
                            )
                        elif response.stop_reason == "refusal":
                            stop_message = "The model declined this request without providing an explanation."
                        if empty_answer_retried or response.stop_reason not in ("end_turn", "max_tokens"):
                            break
                        empty_answer_retried = True
                        # Keep completed tool results in history; only repeat the model round.
                        # Do not resend an empty assistant message or private thinking blocks.
                        messages.append({"role": "user", "content": (
                            "Your previous response contained no visible answer or tool call. "
                            "Continue the request using the available tools if needed, "
                            "or provide a visible answer explaining what you can do."
                        )})
                        if text_parts and on_event:
                            await on_event(step_event("token_reset"))
                        continue
                    if answer != streamed_answer and on_event:
                        if text_parts:
                            await on_event(step_event("token_reset"))
                        await on_event(step_event("token", text=answer))
                    return ChatResult(
                        response=answer,
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
                        cached_input_tokens=cached_input_tokens,
                    )

                if text_parts and on_event:
                    await on_event(step_event("token_reset"))
                messages.append({"role": "assistant", "content": response.content})

                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    guard.check_call(block.name, block.input)
                    tools_used.append(block.name)
                    step_id = block.id
                    if on_event:
                        await on_event(step_event(
                            "step_start", id=step_id, tool=block.name, label=labels.get(block.name), arguments=block.input,
                        ))
                    # Local planning and questions do not run external tools or need approval.
                    asked = await checklist.handle(block.name, block.input, on_event)
                    if asked is None:
                        asked = await questions.handle(block.name, request_id, step_id, block.input, on_event)
                    if asked is not None:
                        result_text, ok = asked
                    else:
                        # With approvals on, the user answers before anything runs; a
                        # refusal is handed to the model as this step's result.
                        declined = await approvals.review(
                            request_id, step_id, block.name, labels.get(block.name), block.input, on_event
                        )
                        if declined is not None:
                            result_text, ok = declined, False
                        else:
                            try:
                                result_text = await dispatch_with_progress(_dispatch, on_event, step_id, block.name, block.input, depth)
                                ok = True
                            except Exception as error:
                                result_text = f"Tool '{block.name}' failed: {error}"
                                ok = False
                    if on_event:
                        await on_event(step_event("step_end", id=step_id, ok=ok, result=result_text))
                    tool_calls.append(ToolCallRecord(name=block.name, arguments=block.input, result=result_text))
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result_text})

                messages.append({"role": "user", "content": tool_results})
    except TurnStopped as error:
        stop_message = str(error)
    except TimeoutError:
        cancellation.cancel(request_id)
        stop_message = guard.time_message()

    if on_event:
        await on_event(step_event("token_reset"))
        await on_event(step_event("token", text=stop_message))
    return ChatResult(
        response=stop_message,
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
        cached_input_tokens=cached_input_tokens,
    )


def run_interpret(text: str, model: str | None = None) -> ChatResult:
    """One non-agentic completion, no tools offered (see server.py's
    `interpret` tool) - without letting the model wander into calling
    tools, which run_chat's full loop would allow. No cancellation/depth handling - unlike run_chat, this is
    always a single call, never a multi-round loop.

    Uses _get_sync_client(), not _get_client() - this call is a plain,
    non-`await`ed `client.messages.create(...)`, so it needs the
    synchronous Anthropic/AnthropicBedrock/AnthropicVertex client, not
    run_chat's AsyncAnthropic/etc. (calling an async client's
    .messages.create(...) without awaiting it returns an unawaited
    coroutine, not a response)."""
    route = _route_for_turn()
    messages = [{"role": "user", "content": text}]
    while True:
        token_limits.enforce_context_limit(PROVIDER_ID, [SYSTEM_PROMPT, *messages], route.current)
        client = _get_sync_client() if route.current == _Anthropic._gateway_name() else _get_sync_client(route.current)
        model_name = _model_for_route(route, model)
        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=llm_options.for_provider(PROVIDER_ID).max_tokens(
                    token_limits.max_output_tokens(PROVIDER_ID, route.current)),
                system=SYSTEM_PROMPT,
                messages=messages,
            )
        except Exception as error:
            if route.advance(error) is None:
                raise
            continue
        response_text = "".join(block.text for block in response.content if block.type == "text")
        total_tokens = response.usage.input_tokens + response.usage.output_tokens
        return ChatResult(
            response=response_text, provider_id=PROVIDER_ID, model=model_name,
            gateway=route.current, gateway_switches=[switch.as_dict() for switch in route.switches],
            total_tokens=total_tokens, context_tokens=response.usage.input_tokens,
            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
        )
