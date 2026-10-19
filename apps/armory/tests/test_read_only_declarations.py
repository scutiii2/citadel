"""Which built-in tools declare readOnlyHint. ember's "Auto" approval mode runs a tool that declares
it without asking the user, so the list is pinned: a new declaration is a decision, not an accident."""

from __future__ import annotations

import asyncio
import pathlib

import pytest
from mcp.server.fastmcp import FastMCP

from src import commands
from src.services import capability_meta, capability_registry
from src.services.capability_loader import CapabilityLoader

CAPABILITIES = pathlib.Path(__file__).resolve().parents[1] / "src" / "capabilities"

# capability id -> the tools that declare readOnlyHint
READ_ONLY = {
    "video": {"tool_vid_probe", "tool_vid_status", "tool_vid_listFiles"},
    "pdf": {"tool_pdf_inspect", "tool_pdf_listFiles"},
    "vault": {"tool_vault_search", "tool_vault_listNotes", "tool_vault_readNote"},
    "usage": {"tool_usage_summary"},
    "repo": {"tool_repo_listRepos", "tool_repo_log", "tool_repo_diff", "tool_repo_grep"},
    "web": {"tool_web_search", "tool_web_readPage"},
    "notes": {"tool_notes_listNotes", "tool_notes_searchNotes", "tool_notes_readNote"},
    "memory": {"tool_mem_search"},
}
# Capabilities whose tools change something, spend credits or crawl, or run commands: none may declare it.
# generator joined it when its tools gained email_to (they can send mail).
NEVER = ("server_manager", "tables", "firecrawl", "email", "tickets", "generator")


@pytest.fixture
def loaded(tmp_path, monkeypatch):
    import src.server

    server = FastMCP("read-only-test")
    monkeypatch.setattr(src.server, "mcp", server)
    monkeypatch.setattr(capability_registry, "_REGISTRY", {})
    monkeypatch.setattr(capability_meta, "_BY_FOLDER", {})
    monkeypatch.setattr(commands, "_COMMANDS", {})
    config = tmp_path / "capabilities.json"
    config.write_text("{}")
    loader = CapabilityLoader(server, "src.capabilities", config)
    loader.scan()
    for capability_id in READ_ONLY:
        asyncio.run(loader.set_online(capability_id, True))
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def declared(tool) -> bool:
    return bool(tool.annotations and tool.annotations.readOnlyHint is True)


def test_exactly_these_tools_declare_read_only(loaded):
    assert {name for name, tool in loaded.items() if declared(tool)} == set().union(*READ_ONLY.values())


@pytest.mark.parametrize("capability_id", sorted(READ_ONLY))
def test_every_tool_of_a_read_only_capability_is_loaded_and_declared(loaded, capability_id):
    for name in READ_ONLY[capability_id]:
        assert name in loaded, name
        assert declared(loaded[name]), name


def test_the_notes_write_tools_are_not_read_only(loaded):
    for name in ("tool_pdf_merge", "tool_notes_createNote", "tool_notes_updateNote", "tool_notes_appendToNote", "tool_mem_save", "tool_mem_forget"):
        assert name in loaded and not declared(loaded[name]), name


@pytest.mark.parametrize("folder", NEVER)
def test_capabilities_that_change_things_or_spend_credits_never_declare_it(folder):
    source = (CAPABILITIES / folder / "tool.py").read_text(encoding="utf-8")

    # email and tickets mix reads and writes: they may declare a read tool, but only one at a time.
    allowed = {"email": 1, "tickets": 2}.get(folder, 0)
    assert source.count("readOnlyHint=True") == allowed, folder


def test_video_download_is_not_read_only(loaded):
    assert "tool_vid_download" in loaded and not declared(loaded["tool_vid_download"])
