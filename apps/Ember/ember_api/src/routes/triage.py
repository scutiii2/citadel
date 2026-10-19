"""/api/triage: typed questions asked straight to the Triage Assistant (Laya), without the orchestrator.
Needs chat.use. Option titles come from the title-writer agent."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints, model_validator

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.deps import get_agent_gateway, get_db_session, get_log_writer, get_settings, require_permission
from src.models import Account
from src.routes.chats import limit_reached
from src.routes.mcp import get_agent_directory
from src.services.agent_directory import AgentDirectory
from src.services.agent_gateway import AgentGateway, Caller
from src.services.log_service import LogWriter
from src.services.permissions import CHAT_USE
from src.services.triage_questions import (
    DESCRIPTION_MAX,
    MAX_OPTIONS,
    MIN_OPTIONS,
    QUESTION_MAX,
    TEXT_MAX,
    TITLE_MAX,
    Option,
    TriageQuestions,
    TriageRejected,
    TriageUnavailable,
)
from src.services.usage_service import UsageService

router = APIRouter(prefix="/api/triage", tags=["triage"])

require_chat = require_permission(CHAT_USE)
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DESCRIPTION_MAX)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]


def get_triage_questions(
    gateway: AgentGateway = Depends(get_agent_gateway), directory: AgentDirectory = Depends(get_agent_directory)
) -> TriageQuestions:
    return TriageQuestions(gateway, directory)


class TitlesBody(BaseModel):
    descriptions: list[Description] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)


class TitlesOut(BaseModel):
    titles: list[str]


class OptionBody(BaseModel):
    title: Title
    description: Description


class AskBody(BaseModel):
    kind: Literal["choice", "yes_no", "score"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TEXT_MAX)]
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)]
    options: list[OptionBody] = Field(default_factory=list, max_length=MAX_OPTIONS)
    # A score question's level descriptions, lowest first.
    levels: list[Description] = Field(default_factory=list, max_length=MAX_OPTIONS)
    # The full answer, with every model call of the triage flow (ai_agent's `trace`).
    trace: bool = False

    @model_validator(mode="after")
    def _options_match_kind(self) -> AskBody:
        if self.kind != "score" and self.levels:
            raise ValueError("only a score question takes levels")
        if self.kind == "score":
            if self.options:
                raise ValueError("a score question takes levels, not options")
            if len(self.levels) < MIN_OPTIONS:
                raise ValueError(f"a score question needs at least {MIN_OPTIONS} levels")
            return self
        if self.kind == "yes_no":
            if self.options:
                raise ValueError("a yes or no question takes no options")
            return self
        if len(self.options) < MIN_OPTIONS:
            raise ValueError(f"a multiple choice question needs at least {MIN_OPTIONS} options")
        titles = [o.title.lower() for o in self.options]
        if len(set(titles)) != len(titles):
            raise ValueError("option titles must be different")
        return self


@router.post("/titles")
async def write_titles(
    body: TitlesBody,
    account: Account = Depends(require_chat),
    triage: TriageQuestions = Depends(get_triage_questions),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    logs: LogWriter = Depends(get_log_writer),
) -> TitlesOut:
    """A one-word title for each option description, in order. Counts toward the usage limits."""
    usage = UsageService(session, settings.usage)
    block = await usage.check(account.id)
    if block is not None:
        raise limit_reached(block)
    try:
        outcome = await triage.titles(_caller(account), body.descriptions)
    except TriageUnavailable as error:
        await logs.error(account.id, "triage.titles", str(error))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Option titles are unavailable: {error}") from error
    await usage.record(account.id, uuid.uuid4().hex, "triage_titles", None, outcome.result)
    await logs.action(account, "triage.titles", f"Wrote titles for {len(body.descriptions)} options")
    return TitlesOut(titles=outcome.titles)


@router.post("/ask")
async def ask(
    body: AskBody,
    account: Account = Depends(require_chat),
    triage: TriageQuestions = Depends(get_triage_questions),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    logs: LogWriter = Depends(get_log_writer),
) -> dict[str, Any]:
    """Asks the Triage Assistant one yes or no, multiple choice or score question about a text. Counts toward the usage limits."""
    usage = UsageService(session, settings.usage)
    block = await usage.check(account.id)
    if block is not None:
        raise limit_reached(block)
    options = [Option(o.title.lower(), o.description) for o in body.options]
    try:
        outcome = await triage.ask(_caller(account), body.kind, body.text, body.question, options, body.trace, body.levels)
    except TriageRejected as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except TriageUnavailable as error:
        await logs.error(account.id, "triage.ask", str(error))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"The Triage Assistant is unavailable: {error}") from error
    await usage.record(account.id, uuid.uuid4().hex, "triage", None, outcome.result)
    # Never the text or the question: only what kind it was and how it came out.
    if body.kind == "yes_no":
        shape = "yes or no"
    elif body.kind == "score":
        shape = f"score ({len(body.levels)} levels)"
    else:
        shape = f"multiple choice ({len(body.options)} options)"
    picked = outcome.answer.get("answer") or outcome.answer.get("choice") or outcome.answer.get("score")
    flag = ", uncertain" if outcome.answer.get("uncertain") else ""
    await logs.action(account, "triage.ask", f"Asked the Triage Assistant a {shape} question: {picked}{flag}")
    return outcome.answer


def _caller(account: Account) -> Caller:
    return Caller(username=account.username, email=account.email, uid=account.uid)
