"""The one architecture as agent files: an orchestrator (entry), a router, an architect and a specialist."""

import json
from pathlib import Path

GATEWAY = {"provider": "anthropic", "gateway": "claude"}


def write_extras(directory: Path) -> None:
    """The router, architect and specialist a roster needs besides its orchestrator (ports 9190-9192)."""
    files = {
        "router": {"role": "router", "port": 9190, "llm": {"provider": "decision"}, "plan_tool": False, "delegable": False, "tools": {"deny": ["*"]}},
        "architect": {"role": "architect", "kind": "code", "port": 9191, "llm": GATEWAY, "workers": ["worker"], "tools": {"deny": ["*"]}},
        "worker": {"role": "specialist", "port": 9192, "llm": GATEWAY},
    }
    for name, data in files.items():
        (directory / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def write_roster(directory: Path, **orchestrator) -> None:
    """A complete roster; `ember` is the orchestrator and the entry agent."""
    data = {"role": "orchestrator", "label": "X", "port": 9100, "entry": True, "llm": GATEWAY, **orchestrator}
    (directory / "ember.json").write_text(json.dumps(data), encoding="utf-8")
    write_extras(directory)
