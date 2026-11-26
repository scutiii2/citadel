"""Every tool says whether it only reads. Legion runs read-only tools of one model round at the same time and, in Auto
approval, without asking, so a tool with no `readOnlyHint` is never parallel and always asks. Importing each tool module
runs its @mcp.tool() decorator."""

from __future__ import annotations

import pytest

from src.capabilities.server_manager import tool as server_manager_tool  # noqa: F401
from src.capabilities.generator import tool as generator_tool  # noqa: F401
from src.capabilities.web_research import tool as web_research_tool  # noqa: F401
from src.capabilities.firecrawl import tool as firecrawl_tool  # noqa: F401
from src.capabilities.repo_reader import tool as repo_reader_tool  # noqa: F401
from src.capabilities.tables import tool as tables_tool  # noqa: F401
from src.capabilities.files import tool as files_tool  # noqa: F401
from src.capabilities.email import tool as email_tool  # noqa: F401
from src.capabilities.media_downloader import tool as video_tool  # noqa: F401
from src.capabilities.pdf_merger import tool as pdf_tool  # noqa: F401
from src.server import mcp


@pytest.mark.anyio
async def test_every_tool_declares_read_only_hint():
    tools = [t for t in await mcp.list_tools() if (t.meta or {}).get("keywords")]
    assert tools, "no tools registered"
    missing = [t.name for t in tools if t.annotations is None or t.annotations.readOnlyHint is None]
    assert missing == [], f"tools without readOnlyHint: {missing}"


@pytest.mark.anyio
async def test_tools_that_change_things_are_not_marked_read_only():
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name in ("tool_srv_startApp", "tool_srv_stopApp", "tool_srv_restartApp", "tool_media_download", "tool_media_package"):
        assert by_name[name].annotations.readOnlyHint is False, name
    for name in ("tool_tables_rows", "tool_scrape_page", "tool_srv_listApps"):
        assert by_name[name].annotations.readOnlyHint is True, name
