"""/api/nav-preferences: how the logged-in account arranges its nav rail
(order, pinned and hidden pages). Any logged-in account; private to it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints

from src.deps import current_account, get_db_gateway
from src.models import Account
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.nav_preference_service import MAX_PAGES, PAGE_ID_MAX, NavLayout, NavPreferenceService

router = APIRouter(prefix="/api/nav-preferences", tags=["nav-preferences"])

PageId = Annotated[str, StringConstraints(min_length=1, max_length=PAGE_ID_MAX)]


def get_nav_service(
    account: Account = Depends(current_account), store: DocumentStore = Depends(get_db_gateway)
) -> NavPreferenceService:
    return NavPreferenceService(store, account.uid)


def _unavailable(error: DbGatewayError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Nav preferences storage is unavailable")


class NavPreferencesBody(BaseModel):
    order: list[PageId] = Field(default_factory=list, max_length=MAX_PAGES)
    pinned: list[PageId] = Field(default_factory=list, max_length=MAX_PAGES)
    hidden: list[PageId] = Field(default_factory=list, max_length=MAX_PAGES)

    @classmethod
    def of(cls, layout: NavLayout) -> NavPreferencesBody:
        return cls(order=layout.order, pinned=layout.pinned, hidden=layout.hidden)


@router.get("")
async def read_nav_preferences(nav: NavPreferenceService = Depends(get_nav_service)) -> NavPreferencesBody:
    """The saved arrangement. While the gateway is down it answers the default one, so the
    nav rail still renders; saving then fails with 503."""
    try:
        return NavPreferencesBody.of(await nav.get())
    except DbGatewayError:
        return NavPreferencesBody()


@router.put("")
async def save_nav_preferences(
    body: NavPreferencesBody, nav: NavPreferenceService = Depends(get_nav_service)
) -> NavPreferencesBody:
    """Replaces the whole arrangement; returns it as stored."""
    try:
        layout = await nav.replace(NavLayout(order=body.order, pinned=body.pinned, hidden=body.hidden))
    except DbGatewayError as error:
        raise _unavailable(error) from error
    return NavPreferencesBody.of(layout)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def reset_nav_preferences(nav: NavPreferenceService = Depends(get_nav_service)) -> Response:
    try:
        await nav.reset()
    except DbGatewayError as error:
        raise _unavailable(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
