"""/templates: an account's saved prompts, kept in Treasury.

Portcullis serves these as /api/templates after checking the login and the chat.use permission."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from src.requester import Requester, current_requester
from src.templates.store import (
    BODY_MAX,
    NAME_MAX,
    TEMPLATE_ID_PATTERN,
    Template,
    TemplateLimitError,
    TemplateNameTaken,
    TemplateNotFound,
    TemplateService,
    purge_owner,
)

router = APIRouter(prefix="/templates", tags=["templates"])

TemplateId = Path(pattern=TEMPLATE_ID_PATTERN)


def get_template_service(request: Request, requester: Requester = Depends(current_requester)) -> TemplateService:
    return TemplateService(request.app.state.store, requester.uid)


class TemplateIn(BaseModel):
    name: str = Field(max_length=NAME_MAX * 4)  # trimmed below, then held to NAME_MAX
    body: str = Field(max_length=BODY_MAX)

    @field_validator("name")
    @classmethod
    def clean_name(cls, name: str) -> str:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise ValueError("name must not be blank")
        if len(cleaned) > NAME_MAX:
            raise ValueError(f"name must be at most {NAME_MAX} characters")
        return cleaned

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, body: str) -> str:
        if not body.strip():
            raise ValueError("body must not be blank")
        return body


class TemplateOut(BaseModel):
    id: str
    name: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, template: Template) -> TemplateOut:
        return cls(
            id=template.id,
            name=template.name,
            body=template.body,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")


def _name_taken(name: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, f'You already have a template named "{name}"')


@router.get("")
async def list_templates(templates: TemplateService = Depends(get_template_service)) -> list[TemplateOut]:
    """Most recently edited first."""
    return [TemplateOut.of(t) for t in await templates.list()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateIn, templates: TemplateService = Depends(get_template_service)
) -> TemplateOut:
    try:
        return TemplateOut.of(await templates.create(body.name, body.body))
    except TemplateNameTaken as error:
        raise _name_taken(body.name) from error
    except TemplateLimitError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.put("/{template_id}")
async def update_template(
    body: TemplateIn,
    template_id: str = TemplateId,
    templates: TemplateService = Depends(get_template_service),
) -> TemplateOut:
    try:
        return TemplateOut.of(await templates.update(template_id, body.name, body.body))
    except TemplateNotFound as error:
        raise _not_found() from error
    except TemplateNameTaken as error:
        raise _name_taken(body.name) from error


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str = TemplateId, templates: TemplateService = Depends(get_template_service)
) -> Response:
    try:
        await templates.delete(template_id)
    except TemplateNotFound as error:
        raise _not_found() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")], request: Request) -> Response:
    """Every template of a deleted account. Portcullis calls it when an administrator deletes the account."""
    await purge_owner(request.app.state.store, uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
