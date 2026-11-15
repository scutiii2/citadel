"""/triage: typed questions asked straight to the Triage Assistant (Laya), without the orchestrator.

Portcullis serves these as /api/triage after checking the login and the chat.use permission.
Option titles come from the title-writer agent. Both count toward the account's token limits."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints, model_validator

from src.agents.directory import AgentDirectory
from src.agents.gateway import AgentGateway, Caller
from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.triage.questions import (
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
from src.usage.limits import limit_reached
from src.usage.rows import stored_rows
from src.usage.service import UsageService

router = APIRouter(prefix="/triage", tags=["triage"])

Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DESCRIPTION_MAX)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]


def get_triage_questions(request: Request) -> TriageQuestions:
    gateway: AgentGateway = request.app.state.agent_gateway
    directory: AgentDirectory = request.app.state.agents
    return TriageQuestions(gateway, directory)


def get_usage(request: Request) -> UsageService:
    return request.app.state.usage


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


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


async def _check(usage: UsageService, who: Requester) -> None:
    block = await usage.check(who.uid)
    if block is not None:
        raise limit_reached(block)


async def _record(usage: UsageService, who: Requester, kind: str, result: dict[str, Any]) -> None:
    await usage.record(who.uid, uuid.uuid4().hex, kind, None, stored_rows(result))


@router.post("/titles")
async def write_titles(
    body: TitlesBody,
    who: Requester = Depends(current_requester),
    triage: TriageQuestions = Depends(get_triage_questions),
    usage: UsageService = Depends(get_usage),
    platform: PortcullisClient = Depends(get_platform),
) -> TitlesOut:
    """A one-word title for each option description, in order. Counts toward the usage limits."""
    await _check(usage, who)
    try:
        outcome = await triage.titles(_caller(who), body.descriptions)
    except TriageUnavailable as error:
        await platform.report_error("triage.titles", str(error))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Option titles are unavailable: {error}") from error
    await _record(usage, who, "triage_titles", outcome.result)
    await platform.log_action(who.uid, "triage.titles", f"Wrote titles for {len(body.descriptions)} options")
    return TitlesOut(titles=outcome.titles)


@router.post("/ask")
async def ask(
    body: AskBody,
    who: Requester = Depends(current_requester),
    triage: TriageQuestions = Depends(get_triage_questions),
    usage: UsageService = Depends(get_usage),
    platform: PortcullisClient = Depends(get_platform),
) -> dict[str, Any]:
    """Asks the Triage Assistant one yes or no, multiple choice or score question about a text. Counts toward the usage limits."""
    await _check(usage, who)
    options = [Option(o.title.lower(), o.description) for o in body.options]
    try:
        outcome = await triage.ask(_caller(who), body.kind, body.text, body.question, options, body.trace, body.levels)
    except TriageRejected as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except TriageUnavailable as error:
        await platform.report_error("triage.ask", str(error))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"The Triage Assistant is unavailable: {error}") from error
    await _record(usage, who, "triage", outcome.result)
    # Never the text or the question: only what kind it was and how it came out.
    if body.kind == "yes_no":
        shape = "yes or no"
    elif body.kind == "score":
        shape = f"score ({len(body.levels)} levels)"
    else:
        shape = f"multiple choice ({len(body.options)} options)"
    picked = outcome.answer.get("answer") or outcome.answer.get("choice") or outcome.answer.get("score")
    flag = ", uncertain" if outcome.answer.get("uncertain") else ""
    await platform.log_action(who.uid, "triage.ask", f"Asked the Triage Assistant a {shape} question: {picked}{flag}")
    return outcome.answer


def _caller(who: Requester) -> Caller:
    return Caller(username=who.username, email=who.email, uid=who.uid)
