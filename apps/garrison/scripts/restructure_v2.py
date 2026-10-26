"""One-shot: move garrison modules into agents/, providers/, tools/, runtime/ and rewrite imports.

Usage (from apps/garrison):  python scripts/restructure_v2.py --check | --apply
Deleted after the move commit."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

ORCHESTRATOR = ["delegation", "plan", "ask_user", "memory_recall", "skill_recall", "skill_reflection",
                "context_summarizer", "auto_route"]
ROUTER = ["router_client", "router_contract", "router_engine", "router_routing", "router_service"]
PROVIDERS = ["base_provider", "cancellation", "cooldown", "gateway_failover", "token_limits", "model_limits",
             "model_tiers", "reasoning_effort", "llm_config", "llm_options", "context_breakdown", "turn_guard"]
LANGUAGE = ["anthropic_provider", "openai_provider"]
DECISION = ["decision", "laya_model", "laya_provider", "laya_classifier", "jev_classifier",
            "typesafe_classifier", "triage_flow", "triage_strategy"]

# old module (dotted, under src) -> new module
MODMAP: dict[str, str] = {}


def _add(old_pkg: str, names: list[str], new_pkg: str) -> None:
    for name in names:
        MODMAP[f"src.{old_pkg}.{name}"] = f"src.{new_pkg}.{name}"


_add("agents", ORCHESTRATOR, "agents.roles.orchestrator")
_add("agents", ROUTER, "agents.roles.router")
_add("llm", ["agent_roles", "auto_tier"], "agents")
_add("llm", PROVIDERS, "providers")
_add("llm", LANGUAGE, "providers.language")
_add("llm", DECISION, "providers.decision")
for path in sorted((SRC / "core").glob("*.py")):
    if path.stem != "__init__":
        MODMAP[f"src.core.{path.stem}"] = f"src.runtime.{path.stem}"
for pkg in ("mcp_client", "private_extensions"):
    for path in sorted((SRC / pkg).glob("*.py")):
        if path.stem != "__init__":
            MODMAP[f"src.{pkg}.{path.stem}"] = f"src.tools.{pkg}.{path.stem}"

PACKAGE_MAP = {"src.mcp_client": "src.tools.mcp_client", "src.private_extensions": "src.tools.private_extensions"}
OLD_PACKAGES = {"src.llm", "src.core", "src.agents", "src.mcp_client", "src.private_extensions"}
_DOTTED = re.compile(r"\bsrc\.(?:llm|core|agents|mcp_client|private_extensions)(?:\.\w+)*")


def to_path(dotted: str) -> Path:
    return ROOT / (dotted.replace(".", "/") + ".py")


def new_module(old: str) -> str | None:
    """New dotted name for an old module or package; None when it does not move."""
    if old in MODMAP:
        return MODMAP[old]
    return PACKAGE_MAP.get(old)


def rewrite_dotted(text: str) -> str:
    """Rewrite every dotted reference, longest module prefix first (covers patch("src.llm.x.y") strings)."""

    def sub(match: re.Match[str]) -> str:
        parts = match.group(0).split(".")
        for end in range(len(parts), 1, -1):
            moved = new_module(".".join(parts[:end]))
            if moved:
                return ".".join([moved, *parts[end:]])
        return match.group(0)

    return _DOTTED.sub(sub, text)


def rewrite_imports(source: str) -> str:
    """Rewrite `from src.x import a, b` forms with the AST (names of one old package may split across new ones)."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        if node.module not in OLD_PACKAGES:
            continue
        groups: dict[str, list[str]] = {}
        for alias in node.names:
            target = new_module(f"{node.module}.{alias.name}")
            module = target.rsplit(".", 1)[0] if target and node.module not in PACKAGE_MAP else node.module
            if target and node.module in PACKAGE_MAP:
                module = target.rsplit(".", 1)[0]
            name = alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
            groups.setdefault(module, []).append(name)
        indent = " " * node.col_offset
        text = "".join(f"{indent}from {module} import {', '.join(names)}\n" for module, names in groups.items())
        edits.append((node.lineno - 1, node.end_lineno, text))
    for start, end, text in sorted(edits, reverse=True):
        lines[start:end] = [text]
    return rewrite_dotted("".join(lines))


def python_files() -> list[Path]:
    return [p for folder in ("src", "tests", "scripts") for p in (ROOT / folder).rglob("*.py")
            if "__pycache__" not in p.parts and p.name != "restructure_v2.py"]


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def main(apply: bool) -> int:
    missing = [old for old in MODMAP if not to_path(old).exists()]
    if missing:
        print("missing source files:", *missing, sep="\n  ")
        return 1
    for old, new in sorted(MODMAP.items()):
        print(f"{old} -> {new}")
    if not apply:
        return 0
    for old, new in MODMAP.items():
        target = to_path(new)
        target.parent.mkdir(parents=True, exist_ok=True)
        git("mv", str(to_path(old).relative_to(ROOT)), str(target.relative_to(ROOT)))
    for path in python_files():
        original = path.read_text(encoding="utf-8")
        updated = rewrite_imports(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
    for new in set(MODMAP.values()):
        package = to_path(new).parent
        while package != SRC:
            init = package / "__init__.py"
            if not init.exists():
                init.write_text("", encoding="utf-8")
                git("add", str(init.relative_to(ROOT)))
            package = package.parent
    for pkg in ("llm", "core", "mcp_client", "private_extensions"):
        init = SRC / pkg / "__init__.py"
        if init.exists():
            git("rm", "-q", "-f", str(init.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("--check", "--apply"):
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1] == "--apply"))
