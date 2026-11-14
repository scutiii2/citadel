"""Settings an administrator changes for everyone, kept in the database.

Most settings are yes/no switches listed in `BOOLEAN_SETTINGS` with their
default. A setting nobody changed has no row and reads as its default. The one
exception is the list of pages hidden from every sidebar (`hidden_pages`), kept
as a JSON list because the page names belong to the browser.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import utcnow
from src.models import AppSetting

# Every account's answers ask before each tool runs, whatever its browser sends.
FORCE_TOOL_APPROVAL = "force_tool_approval"

# Which alert channels the calendar may use for everyone; each is on until an administrator switches it off.
CALENDAR_CHANNELS = ("calendar_inapp", "calendar_email", "calendar_push")

BOOLEAN_SETTINGS: dict[str, bool] = {FORCE_TOOL_APPROVAL: False, **{name: True for name in CALENDAR_CHANNELS}}

# Page ids (route paths) the administrator hid from every account's sidebar.
HIDDEN_PAGES = "hidden_pages"
# Chat is the home page and Settings holds each account's own preferences: neither can be hidden.
PROTECTED_PAGES = frozenset({"/", "/settings"})
MAX_HIDDEN_PAGES = 20
_PAGE_ID = re.compile(r"^/[a-z0-9-]{1,31}$")
_MAX_STORED = 200  # AppSetting.value is a String(200)

_TRUE, _FALSE = "1", "0"


class UnknownSetting(KeyError):
    """A name that is not in BOOLEAN_SETTINGS."""


class InvalidPages(ValueError):
    """The list of hidden pages is not acceptable; the message is safe to show."""


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> dict[str, bool]:
        stored = {row.name: row.value for row in await self._session.scalars(select(AppSetting))}
        return {name: (stored[name] == _TRUE if name in stored else default) for name, default in BOOLEAN_SETTINGS.items()}

    async def get_bool(self, name: str) -> bool:
        if name not in BOOLEAN_SETTINGS:
            raise UnknownSetting(name)
        row = await self._session.get(AppSetting, name)
        return BOOLEAN_SETTINGS[name] if row is None else row.value == _TRUE

    async def set_bool(self, name: str, value: bool) -> bool:
        """Saves the setting and returns what it was before."""
        before = await self.get_bool(name)
        row = await self._session.get(AppSetting, name)
        text = _TRUE if value else _FALSE
        if row is None:
            self._session.add(AppSetting(name=name, value=text))
        else:
            row.value = text
            row.updated_at = utcnow()
        await self._session.commit()
        return before

    async def hidden_pages(self) -> list[str]:
        row = await self._session.get(AppSetting, HIDDEN_PAGES)
        if row is None:
            return []
        try:
            value = json.loads(row.value)
        except ValueError:
            return []
        return [page for page in value if isinstance(page, str)] if isinstance(value, list) else []

    async def set_hidden_pages(self, pages: list[str]) -> list[str]:
        """Saves the list (repeats dropped, order kept) and returns the previous one."""
        unique = list(dict.fromkeys(pages))
        if len(unique) > MAX_HIDDEN_PAGES:
            raise InvalidPages(f"At most {MAX_HIDDEN_PAGES} pages can be hidden")
        for page in unique:
            if page in PROTECTED_PAGES:
                raise InvalidPages("That page cannot be hidden")
            if not _PAGE_ID.match(page):
                raise InvalidPages(f"Not a page id: {page[:40]}")
        text = json.dumps(unique, separators=(",", ":"))
        if len(text) > _MAX_STORED:
            raise InvalidPages("The list is too long")
        before = await self.hidden_pages()
        row = await self._session.get(AppSetting, HIDDEN_PAGES)
        if row is None:
            self._session.add(AppSetting(name=HIDDEN_PAGES, value=text))
        else:
            row.value = text
            row.updated_at = utcnow()
        await self._session.commit()
        return before
