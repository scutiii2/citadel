"""/api/chats: the logged-in account's chat history, and the chat turns
portcullis runs for it (chat.use)."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from src.deps import (
    get_log_writer,
    get_pricing,
    get_stronghold,
    get_settings_service,
    require_permission,
)
from src.models import Account
from src.services import question_answers
from src.services.chat_service import (
    TITLE_MAX,
    ChatLimitError,
    ChatMessage,
    ChatNotFound,
    ChatRecord,
    ChatService,
    FolderNotFound,
    NotABranchPoint,
    decode_messages,
)
from src.services.log_service import LogWriter
from src.services.permissions import CHAT_USE, TOOLS_EXECUTE
from src.services.pricing import Pricing, with_cost
from src.services.settings_service import FORCE_TOOL_APPROVAL, SettingsService
from src.routes.stronghold import as_response, pass_on
from src.services.stronghold_forwarder import ForwardedResponse, StrongholdForwarder, StrongholdUnavailable
from src.services.stronghold_turns import running_chat_ids

router = APIRouter(prefix="/api/chats", tags=["chats"])

require_chat = require_permission(CHAT_USE)

_CHAT_ID_PATTERN = r"^[A-Za-z0-9-]{8,64}$"
# What the agent's tools are called (`tool_<capability>_<command>`, an
# extension's `<id>__<tool>`, `delegate_to_agent`).
_TOOL_NAME = re.compile(r"[A-Za-z0-9_.\-]{1,120}")
MAX_ALLOWED_TOOLS = 200
MAX_DISABLED_TOOLS = 2000
# Browser-made UUIDs; anything else is refused before touching the database.
ChatId = Path(pattern=_CHAT_ID_PATTERN)
# Room for a question plus a few attached files' text (20k characters each).
QUESTION_MAX = 200_000


MIN_QUERY_CHARS = 2
MAX_QUERY_CHARS = 100


def get_chat_service(
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> ChatService:
    return ChatService(stronghold, account)


# --- models ------------------------------------------------------------------


# Limits of a saved answer's steps and per-agent usage rows (as in Stronghold's turn engine).
STEP_RESULT_MAX = 4000
MAX_STEPS = 50
MAX_AGENT_USAGE_ROWS = 20


class StepIn(BaseModel):
    """One tool step of an answer, as portcullis saved it."""

    tool: str = Field(max_length=200)
    label: str = Field(default="", max_length=300)
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool | None = None
    result: str = Field(default="", max_length=STEP_RESULT_MAX)
    # Which agent ran it, when a delegated agent did.
    agent_id: str | None = Field(default=None, max_length=120)
    agent_label: str | None = Field(default=None, max_length=120)


MAX_CONTEXT_PARTS = 12


class ContextPartIn(BaseModel):
    """One part of what filled an answer's context window."""

    id: str = Field(max_length=40)
    label: str = Field(max_length=60)
    tokens: int = Field(ge=0)


class AgentUsageIn(BaseModel):
    """One agent's share of an answer that delegated to others."""

    agent: str = Field(max_length=120)
    agent_label: str | None = Field(default=None, max_length=120)
    provider_id: str | None = Field(default=None, max_length=60)
    gateway: str | None = Field(default=None, max_length=60)
    # ISO-8601 UTC ("...Z"), as ai_agent reported them.
    started_at: str | None = Field(default=None, max_length=40)
    finished_at: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=120)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int = Field(ge=0)
    context_breakdown: list[ContextPartIn] | None = Field(default=None, max_length=MAX_CONTEXT_PARTS)
    context_breakdown_exact: bool | None = None


# What message_time() makes: 2026-10-06T14:03:09.123Z (a fraction is optional).
MESSAGE_TIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"


class MessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    # summary / log_attachment: written by summarize and clear; command: a
    # slash command's call and its result, shown but never asked about; triage:
    # a typed question put to the Triage Assistant from the chat page, and its answer.
    kind: Literal["summary", "log_attachment", "command", "triage"] | None = None
    # When the message was written (UTC, as message_time makes it). Set by the
    # server for questions and answers; a browser sends back what it was given.
    at: str | None = Field(default=None, pattern=MESSAGE_TIME_PATTERN)
    model: str | None = Field(default=None, max_length=120)
    # The ember agent id that wrote an answer (saved by the turn).
    agent: str | None = Field(default=None, max_length=120)
    total_tokens: int | None = Field(default=None, ge=0)
    # The split of total_tokens, and how long the whole turn took (seconds).
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    duration_s: float | None = Field(default=None, ge=0)
    context_tokens: int | None = Field(default=None, ge=0)
    context_window: int | None = Field(default=None, ge=0)
    # What filled context_tokens (system prompt, tools, messages ...), as ai_agent measured it.
    context_breakdown: list[ContextPartIn] | None = Field(default=None, max_length=MAX_CONTEXT_PARTS)
    # True when those parts were counted by the model provider, not estimated.
    context_breakdown_exact: bool | None = None
    # The tool steps of an answer (saved by portcullis's turn; a browser
    # only sends them back when it re-saves or imports a chat).
    steps: list[StepIn] | None = Field(default=None, max_length=MAX_STEPS)
    # Who used the tokens when the answer ran several agents (its own plus
    # delegated ones); absent when only one did.
    agent_usage: list[AgentUsageIn] | None = Field(default=None, max_length=MAX_AGENT_USAGE_ROWS)


def _clean_title(title: str) -> str:
    cleaned = " ".join(title.split())
    if not cleaned:
        raise ValueError("title must not be blank")
    return cleaned


class RenameRequest(BaseModel):
    title: str = Field(max_length=TITLE_MAX)

    @field_validator("title")
    @classmethod
    def clean_title(cls, title: str) -> str:
        return _clean_title(title)


class UpdateChatRequest(BaseModel):
    """Any of: a new title, a folder (null: out of its folder), a pin."""

    title: str | None = Field(default=None, max_length=TITLE_MAX)
    folder_id: int | None = None
    pinned: bool | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, title: str | None) -> str | None:
        return None if title is None else _clean_title(title)

    @model_validator(mode="after")
    def something_to_change(self) -> UpdateChatRequest:
        if self.title is None and self.pinned is None and "folder_id" not in self.model_fields_set:
            raise ValueError("send a title, a folder_id or pinned")
        return self


class PutChatRequest(RenameRequest):
    agent_id: str | None = Field(default=None, max_length=120)
    messages: list[MessageIn]


class TurnRequest(BaseModel):
    question: str = Field(min_length=1, max_length=QUESTION_MAX)
    # Ignored: every question goes to the entry agent. Kept so older browsers still validate.
    agent_id: str | None = Field(default=None, max_length=120)
    caveman: bool = False
    # Send no earlier messages to the agent: this question stands alone. The chat still saves them.
    independent: bool = False
    # None uses the saved preference; older clients never enable it accidentally.
    # The agent may keep a task checklist (update_plan); plan_lean asks it to update the list only on a status change.
    plan: bool = True
    plan_lean: bool = True
    # Count what fills the context window with the provider's own token counter, not an estimate.
    exact_context: bool = False
    # Ask the user before each tool runs (they answer through
    # POST /api/chats/{id}/approvals). allowed_tools: tools they already
    # allowed for this chat, which run without asking.
    ask_before_tools: bool = False
    allowed_tools: list[str] = Field(default_factory=list, max_length=MAX_ALLOWED_TOOLS)
    # "Auto" (needs ask_before_tools): built-in tools that only read run without asking. Ignored while
    # the administrator requires approval for every tool.
    allow_read_only: bool = False
    # The browser can show the agent's clickable questions (answers go to
    # POST /api/chats/{id}/questions). Off for clients that cannot, e.g. chat_cli.
    can_ask: bool = False

    @field_validator("allowed_tools")
    @classmethod
    def tool_names(cls, names: list[str]) -> list[str]:
        bad = [n for n in names if not _TOOL_NAME.fullmatch(n)]
        if bad:
            raise ValueError(f"not a tool name: {bad[0][:64]!r}")
        return names

    # Used only when this turn creates the chat.
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    # Regenerate / edit: index of the user question this one replaces. It and
    # everything after it are dropped before the new question is added.
    truncate_to: int | None = Field(default=None, ge=0)


class ApprovalRequest(BaseModel):
    # The tool run being answered: the `id` of an approval_request event.
    step_id: str = Field(min_length=1, max_length=200)
    # allow: run it this once. always: run it, and stop asking about this tool
    # for the rest of the turn (the browser remembers it for the chat).
    decision: Literal["allow", "always", "deny"]


class QuestionAnswerIn(BaseModel):
    # The labels of the options chosen, and the user's own typed answer.
    selected: list[str] = Field(default_factory=list, max_length=question_answers.MAX_OPTIONS)
    other: str | None = Field(default=None, max_length=question_answers.OTHER_MAX)


class QuestionRequest(BaseModel):
    # The question set being answered: the `id` of a question_request event.
    step_id: str = Field(min_length=1, max_length=200)
    # Decline to answer; the agent then goes on with its best judgement.
    skipped: bool = False
    # One entry per question, in order (ignored when skipped).
    answers: list[QuestionAnswerIn] = Field(default_factory=list, max_length=question_answers.MAX_QUESTIONS)


class BranchRequest(BaseModel):
    # Index of the answer the new chat ends on.
    upto: int = Field(ge=0)


class AppendRequest(BaseModel):
    # Used only when this creates the chat.
    title: str = Field(max_length=TITLE_MAX)
    messages: list[MessageIn] = Field(min_length=1, max_length=20)

    @field_validator("title")
    @classmethod
    def clean_title(cls, title: str) -> str:
        return _clean_title(title)


class SummarizeRequest(BaseModel):
    # Ignored, see TurnRequest.agent_id.
    agent_id: str | None = Field(default=None, max_length=120)


class ChatSummaryOut(BaseModel):
    id: str
    title: str
    agent_id: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime
    # An answer is being written for this chat right now.
    running: bool = False
    # The folder this chat is filed in (chat-folders id), and whether it is pinned.
    folder_id: int | None = None
    pinned: bool = False

    @classmethod
    def of(cls, chat: ChatRecord, running: bool = False) -> ChatSummaryOut:
        return cls(
            id=chat.chat_id,
            title=chat.title,
            agent_id=chat.agent_id,
            message_count=chat.message_count,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            running=running,
            folder_id=chat.folder_id,
            pinned=chat.pinned,
        )


class ChatOut(ChatSummaryOut):
    messages: list[dict[str, Any]]

    @classmethod
    def of(cls, chat: ChatRecord, pricing: Pricing, running: bool = False) -> ChatOut:  # type: ignore[override]
        return cls(**ChatSummaryOut.of(chat, running).model_dump(),
                   messages=[with_cost(message, pricing) for message in decode_messages(chat)])


class TurnOut(BaseModel):
    chat: ChatSummaryOut
    # Subscribe to /events with after=this to get only newer events.
    sequence: int


class SuggestionOut(BaseModel):
    # The message the user will probably type next; null for "none".
    text: str | None = None


def _messages(items: list[MessageIn]) -> list[ChatMessage]:
    return [m.model_dump(exclude_none=True) for m in items]


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")


def _too_large(error: ChatLimitError) -> HTTPException:
    return HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error))


def _busy() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "An answer is still being written for this chat")


# --- history -----------------------------------------------------------------


@router.get("")
async def list_chats(
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> list[ChatSummaryOut]:
    running = await running_chat_ids(stronghold, account)
    return [ChatSummaryOut.of(c, c.chat_id in running) for c in await chats.list()]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_chats(
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Stronghold revokes every share link first and deletes nothing if it cannot."""
    await chats.delete_all()
    await stronghold.forward("DELETE", "/turns", account)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/search")
async def search_chats(
    request: Request,
    q: str = Query(min_length=MIN_QUERY_CHARS, max_length=MAX_QUERY_CHARS),
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Chats whose title or messages contain `q` (case-insensitive, literal),
    newest first, at most 50, each with a snippet around the first message
    match (Stronghold searches). Declared before /{chat_id}, which would otherwise take "search"."""
    return await pass_on(request, stronghold, account, "/chats/search")


@router.get("/{chat_id}")
async def get_chat(
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
    pricing: Pricing = Depends(get_pricing),
) -> ChatOut:
    try:
        return ChatOut.of(await chats.get(chat_id), pricing, chat_id in await running_chat_ids(stronghold, account))
    except ChatNotFound as error:
        raise _not_found() from error


@router.get("/{chat_id}/suggestion")
async def chat_suggestion(
    request: Request,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """The message the user will probably type next, for the chat box's placeholder (Stronghold asks the
    model). With suggestions switched off for the account it is `{text: null}`."""
    if not account.prompt_suggestions:
        return Response('{"text":null}', media_type="application/json")
    return await pass_on(request, stronghold, account, f"/turns/{chat_id}/suggestion")


@router.put("/{chat_id}")
async def put_chat(
    body: PutChatRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> ChatSummaryOut:
    """Creates the chat or replaces it whole. Refused while an answer is
    being written, which would otherwise be lost or land in the wrong place."""
    if chat_id in await running_chat_ids(stronghold, account):
        raise _busy()
    try:
        chat = await chats.put(chat_id, body.title, body.agent_id, _messages(body.messages))
    except ChatLimitError as error:
        raise _too_large(error) from error
    return ChatSummaryOut.of(chat)


@router.patch("/{chat_id}")
async def update_chat(
    body: UpdateChatRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> ChatSummaryOut:
    """Renames, files (folder_id; null takes it out of its folder) or pins a
    chat. Allowed while an answer is being written: it changes no messages."""
    changes: dict[str, Any] = {"title": body.title, "pinned": body.pinned}
    if "folder_id" in body.model_fields_set:
        changes["folder_id"] = body.folder_id
    try:
        chat = await chats.update(chat_id, **changes)
    except ChatNotFound as error:
        raise _not_found() from error
    except FolderNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found") from error
    return ChatSummaryOut.of(chat, chat_id in await running_chat_ids(stronghold, account))


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Also stops an answer still being written for it. Stronghold revokes its share links first."""
    try:
        await chats.delete(chat_id)
    except ChatNotFound as error:
        raise _not_found() from error
    await stronghold.forward("DELETE", f"/turns/{chat_id}", account)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{chat_id}/branch", status_code=status.HTTP_201_CREATED)
async def branch_chat(
    body: BranchRequest,
    chat_id: str = ChatId,
    chats: ChatService = Depends(get_chat_service),
    pricing: Pricing = Depends(get_pricing),
) -> ChatOut:
    """Copies the chat up to and including the answer at `upto` into a new
    chat (new id, "Branch of <title>", same agent) and returns it. The
    original is unchanged, and may even be answering meanwhile: only saved
    messages are copied."""
    try:
        return ChatOut.of(await chats.branch(chat_id, body.upto), pricing)
    except ChatNotFound as error:
        raise _not_found() from error
    except NotABranchPoint as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A branch can only end on one of the assistant's answers"
        ) from error
    except ChatLimitError as error:
        raise _too_large(error) from error


@router.post("/{chat_id}/messages")
async def append_messages(
    body: AppendRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> ChatSummaryOut:
    """Adds messages the browser produced itself - a slash command and its
    result - creating the chat if needed."""
    if chat_id in await running_chat_ids(stronghold, account):
        raise _busy()
    extra = _messages(body.messages)
    try:
        try:
            existing = decode_messages(await chats.get(chat_id))
            chat = await chats.replace_messages(chat_id, [*existing, *extra])
        except ChatNotFound:
            chat = await chats.put(chat_id, body.title, None, extra)
    except ChatLimitError as error:
        raise _too_large(error) from error
    return ChatSummaryOut.of(chat)


# --- turns: Stronghold runs them; Portcullis checks login and permission and adds what only it knows ---------


@router.post("/{chat_id}/turns", status_code=status.HTTP_202_ACCEPTED)
async def start_turn(
    body: TurnRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
    app_settings: SettingsService = Depends(get_settings_service),
) -> Response:
    """Starts answering in Stronghold, which saves the question and keeps going (and saves the answer)
    even if the browser leaves; watch it via /events. The `trusted` block is Portcullis's alone: a
    `trusted` key sent by the browser never reaches Stronghold."""
    payload = {
        **body.model_dump(exclude={"agent_id"}),
        "trusted": {
            "forced_approval": await app_settings.get_bool(FORCE_TOOL_APPROVAL),
            "tools_execute": TOOLS_EXECUTE in account.permission_names,
        },
    }
    answer = await stronghold.forward("POST", f"/turns/{chat_id}", account, json=payload)
    if answer.status != status.HTTP_202_ACCEPTED:
        return as_response(answer)
    started = json.loads(answer.body)
    out = TurnOut(chat=ChatSummaryOut.of(ChatRecord.of(started["chat"]), running=True), sequence=started["sequence"])
    return Response(out.model_dump_json(), status_code=status.HTTP_202_ACCEPTED, media_type="application/json")


@router.get("/{chat_id}/events")
async def turn_events(
    request: Request,
    chat_id: str = ChatId,
    after: int = Query(default=0, ge=0),
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Server-Sent Events for the chat's current (or just finished) turn, relayed from Stronghold as they
    come: a snapshot of the text so far when joining late, then live events, and last a "final" or "error"
    event. 404 when there is no turn to watch. A browser that leaves ends only the relay, never the turn."""
    last_event_id = request.headers.get("last-event-id", "")
    if last_event_id.isdigit():
        after = max(after, int(last_event_id))
    upstream = await stronghold.open_stream(f"/turns/{chat_id}/events", account, params={"after": str(after)})
    if upstream.status_code != status.HTTP_200_OK:
        body = await upstream.aread()
        await upstream.aclose()
        if upstream.status_code >= 500:
            raise StrongholdUnavailable(f"stronghold answered {upstream.status_code}")
        return Response(body, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type", "application/json"))

    async def relay() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(relay(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{chat_id}/approvals")
async def decide_approval(
    body: ApprovalRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
    logs: LogWriter = Depends(get_log_writer),
    app_settings: SettingsService = Depends(get_settings_service),
) -> Response:
    """Answers a tool the running answer is waiting to run (the `id` of an `approval_request` event).
    Only the chat's own account can; once a step is answered nothing else can answer it. Recorded in the
    activity log. While the administrator requires approval, "always" means "this once"."""
    payload = {**body.model_dump(), "trusted": {"forced_approval": await app_settings.get_bool(FORCE_TOOL_APPROVAL)}}
    answer = await stronghold.forward("POST", f"/turns/{chat_id}/approvals", account, json=payload)
    if answer.status != status.HTTP_200_OK:
        return as_response(answer)
    decided = json.loads(answer.body)
    await logs.action(account, "tool.approval", f'{decided["decision"]}: "{decided["tool"]}"')
    return Response('{"decided":true}', media_type="application/json")


@router.post("/{chat_id}/questions")
async def answer_questions(
    body: QuestionRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Answers (or skips) the questions the running answer is waiting on (the `id` of a `question_request`
    event). The answer text is not logged: it is the user's own words, kept only in the chat's saved steps."""
    return as_response(await stronghold.forward("POST", f"/turns/{chat_id}/questions", account, json=body.model_dump()))


@router.post("/{chat_id}/cancel")
async def cancel_turn(
    request: Request,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/turns/{chat_id}/cancel")


# --- summarize / clear ---------------------------------------------------------


def _chat_out(answer: ForwardedResponse, pricing: Pricing) -> Response:
    """Stronghold's saved chat as the browser reads it."""
    if answer.status != status.HTTP_200_OK:
        return as_response(answer)
    return Response(ChatOut.of(ChatRecord.of(json.loads(answer.body)), pricing).model_dump_json(),
                    media_type="application/json")


@router.post("/{chat_id}/summarize")
async def summarize_chat(
    body: SummarizeRequest,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
    pricing: Pricing = Depends(get_pricing),
) -> Response:
    """Replaces the history with one summary (what the agent sees from now on) plus the raw log it
    replaced. Nothing changes if it fails. Counts toward the usage limits like a chat turn."""
    return _chat_out(await stronghold.forward("POST", f"/turns/{chat_id}/summarize", account), pricing)


@router.post("/{chat_id}/clear")
async def clear_chat(
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
    pricing: Pricing = Depends(get_pricing),
) -> Response:
    """Starts the conversation afresh without asking an agent: the old messages are kept as one raw log
    the agent never sees again."""
    return _chat_out(await stronghold.forward("POST", f"/turns/{chat_id}/clear", account), pricing)
