"""Settings an administrator changes for everyone, kept in the database.

Today that is the list of pages hidden from every sidebar (`hidden_pages`), kept as a JSON list because the page
names belong to the browser. Tool approval is Armory's rule, not stored here.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import utcnow
from src.models import AppSetting

# Page ids (route paths) the administrator hid from every account's sidebar.
HIDDEN_PAGES = "hidden_pages"
# Chat is the home page and Settings holds each account's own preferences: neither can be hidden.
PROTECTED_PAGES = frozenset({"/", "/settings"})
MAX_HIDDEN_PAGES = 20
# Tool approval used to be kept here; Armory owns it now. A row left from then is carried over once (see tool_approval.py).
LEGACY_FORCE_TOOL_APPROVAL = "force_tool_approval"
_PAGE_ID = re.compile(r"^/[a-z0-9-]{1,31}$")
_MAX_STORED = 200  # AppSetting.value is a String(200)


class InvalidPages(ValueError):
    """The list of hidden pages is not acceptable; the message is safe to show."""


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def legacy_force_tool_approval(self) -> bool | None:
        """The old stored switch: None when there is no row."""
        row = await self._session.get(AppSetting, LEGACY_FORCE_TOOL_APPROVAL)
        return None if row is None else row.value == "1"

    async def drop_legacy_force_tool_approval(self) -> None:
        row = await self._session.get(AppSetting, LEGACY_FORCE_TOOL_APPROVAL)
        if row is not None:
            await self._session.delete(row)
            await self._session.commit()

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
