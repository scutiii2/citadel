"""No agent file may allow tools of a capability that Armory or Stronghold no longer serves."""

import json
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1] / "agents"
GONE = ("tool_vault_", "tool_obsidian_", "tool_mem_", "tool_notes_", "tool_skill_", "tool_ticket_", "tool_usage_")


def allowed(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8")).get("tools", {}).get("allow", [])


@pytest.mark.parametrize("path", sorted(AGENTS.glob("*.json")), ids=lambda p: p.stem)
def test_no_agent_allows_a_removed_armory_tool(path):
    # Stronghold's own tools carry the "stronghold__" prefix and are fine; a bare tool_<x>_ prefix is an Armory tool.
    bad = [name for name in allowed(path) if name.startswith(GONE)]
    assert bad == []


def test_the_vault_librarian_is_gone():
    assert not (AGENTS / "vault-librarian.json").exists()
