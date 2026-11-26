"""/turns: chat turns run by Stronghold. Portcullis checks login and permission, then passes the
request on (as /api/chats/{id}/turns, /events, /approvals, /questions, /cancel, /summarize, /clear and
/suggestion) and adds the `trusted` block: what only Portcullis knows (the administrator's forced tool
approval, the account's tools.execute permission, the extension ids Armory lists and which brains may
take auto-saves). A browser can never fill `trusted`; Portcullis overwrites whatever it sent.

Running turns live in this process's memory: run ONE Stronghold replica."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.agents.accounts import AccountAgentService
from src.agents.directory import AgentDirectory
from src.agents.gateway import AgentCallError, AgentGateway, Caller
from src.chats.store import ChatLimitError, ChatNotFound, ChatStore, message_time
from src.document_store import DbGatewayError, DocumentStore
from src.extensions.service import UserExtensionService
from src.requester import Requester, current_requester
from src.tuning.limits import LimitsStore
from src.turns import elicitation_events, question_answers, suggestions, summarization
from src.turns.engine import TooManyTurns, TurnConflict, TurnNotFound, TurnOptions, TurnRegistry
from src.usage.limits import limit_reached
from src.usage.rows import stored_rows
from src.usage.service import UsageService
from src.usage.settings import Pricing, with_cost

router = APIRouter(prefix="/turns", tags=["turns"])

NO_AGENT_RUNNING = "No agent is running"
ChatId = Path(pattern=r"^[A-Za-z0-9-]{8,64}$")
TITLE_MAX = 120
# Room for a question plus a few attached files' text (20k characters each).
QUESTION_MAX = 200_000
MAX_ALLOWED_TOOLS = 200
_TOOL_NAME = re.compile(r"[A-Za-z0-9_.\-]{1,120}")


def get_turns(request: Request) -> TurnRegistry:
    return request.app.state.turns


def get_chats(request: Request) -> ChatStore:
    return request.app.state.chats


def get_directory(request: Request) -> AgentDirectory:
    return request.app.state.agents


def get_gateway(request: Request) -> AgentGateway:
    return request.app.state.agent_gateway


def get_usage(request: Request) -> UsageService:
    return request.app.state.usage


def get_pricing(request: Request) -> Pricing:
    return request.app.state.pricing


class Trusted(BaseModel):
    """What Portcullis alone knows. Defaults are the safe side: every tool asks, no extension, no auto-save."""

    forced_approval: bool = True
    tools_execute: bool = False


class TurnRequest(BaseModel):
    question: str = Field(min_length=1, max_length=QUESTION_MAX)
    caveman: bool = False
    independent: bool = False
    # None uses the chat's saved preference.
    plan: bool = True
    plan_lean: bool = True
    exact_context: bool = False
    ask_before_tools: bool = False
    allowed_tools: list[str] = Field(default_factory=list, max_length=MAX_ALLOWED_TOOLS)
    allow_read_only: bool = False
    can_ask: bool = False
    can_elicit: bool = False
    # Used only when this turn creates the chat.
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    # Regenerate / edit: index of the user question this one replaces; it and everything after it are dropped.
    truncate_to: int | None = Field(default=None, ge=0)
    trusted: Trusted = Field(default_factory=Trusted)

    @field_validator("allowed_tools")
    @classmethod
    def tool_names(cls, names: list[str]) -> list[str]:
        bad = [n for n in names if not _TOOL_NAME.fullmatch(n)]
        if bad:
            raise ValueError(f"not a tool name: {bad[0][:64]!r}")
        return names


class ApprovalRequest(BaseModel):
    step_id: str = Field(min_length=1, max_length=200)
    decision: Literal["allow", "always", "deny"]
    trusted: Trusted = Field(default_factory=Trusted)


class QuestionAnswerIn(BaseModel):
    selected: list[str] = Field(default_factory=list, max_length=question_answers.MAX_OPTIONS)
    other: str | None = Field(default=None, max_length=question_answers.OTHER_MAX)


class QuestionRequest(BaseModel):
    step_id: str = Field(min_length=1, max_length=200)
    skipped: bool = False
    answers: list[QuestionAnswerIn] = Field(default_factory=list, max_length=question_answers.MAX_QUESTIONS)


ElicitationValue = (
    bool | int | float
    | Annotated[str, Field(max_length=elicitation_events.TEXT_MAX)]
    | Annotated[list[Annotated[str, Field(max_length=elicitation_events.LABEL_MAX)]],
                Field(max_length=elicitation_events.MAX_OPTIONS)]
)


class ElicitationRequest(BaseModel):
    id: str = Field(min_length=1, max_length=elicitation_events.ID_MAX)
    action: Literal["accept", "decline", "cancel"]
    content: dict[Annotated[str, Field(max_length=elicitation_events.LABEL_MAX)], ElicitationValue] | None = Field(
        default=None, max_length=elicitation_events.MAX_FIELDS)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")


def _busy() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "An answer is still being written for this chat")


def _clean_title(title: str) -> str:
    return " ".join(title.split()) or "Chat"


def _replaced_from(existing: list[dict[str, Any]], index: int) -> list[dict[str, Any]]:
    """`existing` up to (not including) `index`, which must be a question the user typed."""
    target = existing[index] if index < len(existing) else None
    if target is None or target.get("role") != "user" or target.get("kind"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a question you typed can be regenerated or edited")
    return existing[:index]


def _caller(who: Requester) -> Caller:
    return Caller(username=who.username, email=who.email, uid=who.uid)


def _out(chat: dict[str, Any], pricing: Pricing) -> dict[str, Any]:
    """A chat as the browser reads it: details plus costed messages."""
    return {**chat, "messages": [with_cost(m, pricing) for m in chat["messages"]]}


def _details(chat: dict[str, Any], running: bool = False) -> dict[str, Any]:
    return {**{k: v for k, v in chat.items() if k != "messages"}, "running": running}


async def _own_limits(request: Request, who: Requester) -> dict[str, int]:
    """The account's own response limits. Without them the turn still runs, on the admin's values."""
    try:
        return await LimitsStore(request.app.state.store).get(who.uid)
    except DbGatewayError:
        return {}


async def _switched_off_agents(store: DocumentStore, directory: AgentDirectory, who: Requester) -> list[str]:
    """Closed on failure: an empty list would quietly offer agents the account switched off."""
    try:
        return await AccountAgentService(store, who.uid).disabled(await directory.known_ids())
    except DbGatewayError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Account agents storage is unavailable") from error


async def _private_extensions(request: Request, who: Requester) -> tuple[tuple[dict, ...], tuple[dict, ...]]:
    """(extensions for Legion, notices). On any failure: none, and a notice saying why."""
    try:
        turn = await UserExtensionService(request.app.state.store, who.uid, request.app.state.box).enabled_for_turn()
        return tuple(turn.items), tuple(turn.skipped)
    except DbGatewayError:
        return (), ({"id": "private", "label": "Private extensions", "error": "Private extensions storage is unavailable"},)


# --- state -----------------------------------------------------------------------


@router.get("/running")
async def running(who: Requester = Depends(current_requester), turns: TurnRegistry = Depends(get_turns)) -> dict[str, list[str]]:
    return {"chat_ids": sorted(turns.running_chat_ids(who.uid))}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def discard_all(who: Requester = Depends(current_requester), turns: TurnRegistry = Depends(get_turns)) -> Response:
    """The account's chats are all being deleted: stop their turns."""
    await turns.discard_account(who.uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def discard_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                          turns: TurnRegistry = Depends(get_turns)) -> Response:
    """A deleted account: stop its turns. Portcullis calls it when an administrator deletes the account."""
    await turns.discard_account(uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard(chat_id: str = ChatId, who: Requester = Depends(current_requester),
                  turns: TurnRegistry = Depends(get_turns)) -> Response:
    """The chat is being deleted: stop its turn and forget the replay."""
    await turns.discard(who.uid, chat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- start and watch --------------------------------------------------------------


@router.post("/{chat_id}", status_code=status.HTTP_202_ACCEPTED)
async def start_turn(
    request: Request, body: TurnRequest, chat_id: str = ChatId, who: Requester = Depends(current_requester),
    chats: ChatStore = Depends(get_chats), turns: TurnRegistry = Depends(get_turns),
    directory: AgentDirectory = Depends(get_directory), usage: UsageService = Depends(get_usage),
) -> dict[str, Any]:
    """Saves the question and starts answering it. The answer keeps going (and is saved) even if the
    browser leaves; watch it via /events."""
    agent = await directory.entry()
    if agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_AGENT_RUNNING)
    if turns.is_running(who.uid, chat_id):
        raise _busy()
    try:
        block = await usage.check(who.uid)
    except DbGatewayError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Usage storage is unavailable") from error
    if block is not None:
        raise limit_reached(block)
    trusted = body.trusted

    question = {"role": "user", "content": body.question, "at": message_time()}
    try:
        try:
            existing = (await chats.get(who.uid, chat_id))["messages"]
            if body.truncate_to is not None:
                existing = _replaced_from(existing, body.truncate_to)
            chat = await chats.replace_messages(who.uid, chat_id, [*existing, question], agent_id=agent.id)
        except ChatNotFound:
            if body.truncate_to is not None:
                raise _not_found() from None
            chat = await chats.put(who.uid, chat_id, _clean_title(body.title or body.question[:60]), agent.id, [question])
    except ChatLimitError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error

    forced = trusted.forced_approval
    switched_off = await _switched_off_agents(request.app.state.store, directory, who)
    private_items, private_skipped = await _private_extensions(request, who)
    try:
        options = TurnOptions(
            limits=await _own_limits(request, who),
            caveman=body.caveman,
            independent=body.independent,
            plan=body.plan,
            plan_lean=body.plan_lean,
            exact_context=body.exact_context,
            ask_before_tools=body.ask_before_tools or forced,
            allowed_tools=() if forced else tuple(dict.fromkeys(body.allowed_tools)),
            allow_read_only=body.allow_read_only and body.ask_before_tools and not forced,
            disabled_tools=tuple("agent:" + agent_id for agent_id in switched_off) if trusted.tools_execute else ("*",),
            can_ask=body.can_ask,
            can_elicit=body.can_elicit,
            private_extensions=private_items,
            private_skipped=private_skipped,
        )
        turn = turns.start(who.uid, chat_id, agent, _caller(who), options)
    except TurnConflict as error:
        raise _busy() from error
    except TooManyTurns as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many answers running at once - wait for one to finish") from error
    return {"chat": _details(chat, running=True), "sequence": turn.sequence}


@router.get("/{chat_id}/events")
async def turn_events(request: Request, chat_id: str = ChatId, after: int = Query(default=0, ge=0),
                      who: Requester = Depends(current_requester), turns: TurnRegistry = Depends(get_turns)) -> StreamingResponse:
    """Server-Sent Events for the chat's current (or just finished) turn: a snapshot of the text so far when
    joining late, then live events, and last a "final" or "error" event. 404 when there is no turn to watch."""
    last_event_id = request.headers.get("last-event-id", "")
    if last_event_id.isdigit():
        after = max(after, int(last_event_id))
    try:
        events = await turns.subscribe(who.uid, chat_id, after)
    except TurnNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer is being written for this chat") from error

    async def stream() -> AsyncIterator[bytes]:
        async for event in events:
            if event.get("type") == "ping":
                yield b": ping\n\n"
                continue
            yield f"id: {event['sequence']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{chat_id}/approvals")
async def decide_approval(body: ApprovalRequest, chat_id: str = ChatId, who: Requester = Depends(current_requester),
                          turns: TurnRegistry = Depends(get_turns)) -> dict[str, Any]:
    """Answers a tool the running answer waits to run. Returns the tool's name so Portcullis can log it."""
    if not turns.is_running(who.uid, chat_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer is being written for this chat")
    pending = turns.pending_approval(who.uid, chat_id, body.step_id)
    if pending is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    # "Always" would let the tool skip asking for the rest of the turn; while approval is required it means "this once".
    decision = "allow" if body.decision == "always" and body.trusted.forced_approval else body.decision
    try:
        decided = await turns.decide(who.uid, chat_id, body.step_id, decision)
    except AgentCallError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    if not decided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    return {"decided": True, "decision": decision, "tool": pending["tool"]}


@router.post("/{chat_id}/questions")
async def answer_questions(body: QuestionRequest, chat_id: str = ChatId, who: Requester = Depends(current_requester),
                           turns: TurnRegistry = Depends(get_turns)) -> dict[str, bool]:
    """Answers (or skips) the questions the running answer waits on. The answer text is not logged."""
    if not turns.is_running(who.uid, chat_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer is being written for this chat")
    pending = turns.pending_question(who.uid, chat_id, body.step_id)
    if pending is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    answers = [answer.model_dump() for answer in body.answers] if not body.skipped else []
    if not body.skipped:
        problem = question_answers.check_answers(pending["questions"], answers)
        if problem is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    try:
        answered = await turns.answer(who.uid, chat_id, body.step_id, answers, body.skipped)
    except AgentCallError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    if not answered:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    return {"answered": True}


@router.post("/{chat_id}/elicitations")
async def answer_elicitation(body: ElicitationRequest, chat_id: str = ChatId,
                             who: Requester = Depends(current_requester),
                             turns: TurnRegistry = Depends(get_turns)) -> dict[str, bool]:
    """Answers a question an outside server asked during the running answer. The content is not logged or saved."""
    if not turns.is_running(who.uid, chat_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer is being written for this chat")
    if turns.pending_elicitation(who.uid, chat_id, body.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    content = body.content if body.action == "accept" else None
    try:
        reply = await turns.answer_elicitation(who.uid, chat_id, body.id, body.action, content)
    except AgentCallError:
        # The agent's error text could repeat what the user typed.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The agent could not take the answer") from None
    if reply and reply["problem"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, reply["problem"])
    if not reply or not reply["answered"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for that answer")
    return {"answered": True}


@router.post("/{chat_id}/cancel")
async def cancel_turn(chat_id: str = ChatId, who: Requester = Depends(current_requester),
                      turns: TurnRegistry = Depends(get_turns)) -> dict[str, bool]:
    return {"cancelled": await turns.cancel(who.uid, chat_id)}


# --- suggestion, summarize, clear -------------------------------------------------


@router.get("/{chat_id}/suggestion")
async def chat_suggestion(
    chat_id: str = ChatId, who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats),
    turns: TurnRegistry = Depends(get_turns), directory: AgentDirectory = Depends(get_directory),
    gateway: AgentGateway = Depends(get_gateway), usage: UsageService = Depends(get_usage),
) -> dict[str, str | None]:
    """The message the user will probably type next. Never an error: anything that stops it is `{text: null}`.
    Portcullis asks only for accounts that switched suggestions on."""
    try:
        chat = await chats.get(who.uid, chat_id)
    except ChatNotFound as error:
        raise _not_found() from error
    none: dict[str, str | None] = {"text": None}
    if turns.is_running(who.uid, chat_id):
        return none
    messages = chat["messages"]
    exchange = suggestions.last_exchange(messages)
    if exchange is None:
        return none
    question, answer = exchange
    key = suggestions.cache_key(who.uid, chat_id, len(messages), answer)
    known, cached = suggestions.CACHE.lookup(key)
    if known:
        return {"text": cached}
    agent = await directory.entry()
    if agent is None:
        return none
    try:
        if await usage.check(who.uid) is not None:
            return none
    except DbGatewayError:
        return none
    outcome = await suggestions.suggest(gateway, agent.url, _caller(who), question, answer)
    if outcome is None:
        return none
    rows = stored_rows(outcome.result)
    if rows:
        try:
            await usage.record(who.uid, uuid.uuid4().hex, "suggestion", chat_id, rows)
        except DbGatewayError:
            pass  # Accounting must not lose the suggestion.
    suggestions.CACHE.put(key, outcome.text)
    return {"text": outcome.text}


@router.post("/{chat_id}/summarize")
async def summarize_chat(
    chat_id: str = ChatId, who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats),
    turns: TurnRegistry = Depends(get_turns), directory: AgentDirectory = Depends(get_directory),
    gateway: AgentGateway = Depends(get_gateway), usage: UsageService = Depends(get_usage),
    pricing: Pricing = Depends(get_pricing),
) -> dict[str, Any]:
    """Replaces the history with one summary plus the raw log it replaced. Nothing changes if it fails.
    Counts toward the usage limits like a chat turn."""
    if turns.is_running(who.uid, chat_id):
        raise _busy()
    try:
        chat = await chats.get(who.uid, chat_id)
    except ChatNotFound as error:
        raise _not_found() from error
    agent = await directory.get(summarization.SUMMARIZER_AGENT_ID)
    if agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Context summarizer is not running")
    block = await usage.check(who.uid)
    if block is not None:
        raise limit_reached(block)
    try:
        outcome = await summarization.summarize(gateway, agent.url, _caller(who), chat["messages"])
    except summarization.SummarizeError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't summarize: {error}") from error
    if outcome is None:
        return _out(chat, pricing)  # nothing new since the last summary
    turn_id = uuid.uuid4().hex
    for result in outcome.results:
        rows = stored_rows(result)
        if rows:
            try:
                await usage.record(who.uid, turn_id, "summary", chat_id, rows)
            except DbGatewayError:
                pass
    try:
        chat = await chats.replace_messages(who.uid, chat_id, outcome.messages)
    except ChatNotFound as error:
        raise _not_found() from error
    return _out(chat, pricing)


@router.post("/{chat_id}/clear")
async def clear_chat(chat_id: str = ChatId, who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats),
                     turns: TurnRegistry = Depends(get_turns), pricing: Pricing = Depends(get_pricing)) -> dict[str, Any]:
    """Starts the conversation afresh without asking an agent: the old messages are kept as one raw log."""
    if turns.is_running(who.uid, chat_id):
        raise _busy()
    try:
        chat = await chats.get(who.uid, chat_id)
        messages = summarization.cleared(chat["messages"])
        if messages is not None:
            chat = await chats.replace_messages(who.uid, chat_id, messages)
    except ChatNotFound as error:
        raise _not_found() from error
    except ChatLimitError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error
    return _out(chat, pricing)
