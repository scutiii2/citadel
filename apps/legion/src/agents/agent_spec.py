"""One ai_agent instance's definition: an `agents/<id>.json` file.

Pure on purpose (stdlib only, no provider imports): server.py loads the
file and calls apply_to_environ() BEFORE importing agent_config, because
the provider modules resolve their gateway/default model from env vars at
their own import time (see agent_config.py's long comment). Everything
read later - persona, tool scope, LLM knobs, orchestrator - comes
from current().

The supervisor (supervisor.py) validates every file with load_dir() before
it starts any child, so a typo fails once, loudly, naming the file.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = PROJECT_ROOT / "agents"

PROVIDERS = ("anthropic", "openai", "decision")
ROLES = ("orchestrator", "router", "specialist")
REASONING_EFFORTS = ("off", "low", "medium", "high")
# Model strength, weakest to strongest. Fixed so min_tier/max_tier can be
# compared and the orchestrator sees one vocabulary across every gateway.
TIERS = ("light", "standard", "heavy", "extreme")
# The gateway each provider uses when a file names none - pinned in the env
# so .env's AI_AGENT_GATEWAY cannot silently re-point the agent.
_DEFAULT_GATEWAY = {"anthropic": "claude", "openai": "gpt", "decision": "laya"}

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_TOP_KEYS = {"label", "port", "url", "enabled", "entry", "llm", "identity", "persona", "instructions", "focus", "tools", "role", "memory_recall", "skill_recall", "skill_learning", "plan_tool", "delegable", "decision"}
_LLM_KEYS = {"strategy", "min_confidence", "provider", "gateway", "model", "temperature", "reasoning_effort", "max_tokens", "max_tool_rounds", "max_turn_tokens", "max_turn_seconds", "min_tier", "max_tier", "max_effort", "fallback_gateways"}
_TOOLS_KEYS = {"allow", "deny"}


def default_gateway(provider: str) -> str | None:
    """The gateway a provider uses when an agent names none."""
    return _DEFAULT_GATEWAY.get(provider)


class AgentSpecError(Exception):
    """An agent file is missing, unreadable, or invalid - the message names
    the file and the field."""


@dataclass(frozen=True)
class GatewayChoice:
    """A same-provider backup and its optional model override."""

    gateway: str
    model: str | None = None


@dataclass(frozen=True)
class LlmSpec:
    provider: str
    gateway: str | None = None
    model: str | None = None
    temperature: float | None = None
    reasoning_effort: str = "off"
    max_tokens: int | None = None
    max_tool_rounds: int | None = None
    max_turn_tokens: int | None = None
    max_turn_seconds: float | None = None
    min_tier: str | None = None
    max_tier: str | None = None
    # Highest reasoning effort a delegating orchestrator may request of this
    # agent; None = no cap. Its own reasoning_effort is never above it.
    max_effort: str | None = None
    fallback_gateways: tuple[GatewayChoice, ...] = ()
    strategy: str | None = None
    min_confidence: float | None = None


@dataclass(frozen=True)
class ToolScope:
    """Which mcp_server tools an agent may see and call, as fnmatch globs on
    the tool name without the "main__" prefix. Empty allow = every tool;
    deny always wins."""

    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    def allows(self, name: str) -> bool:
        if self.allow and not any(fnmatchcase(name, glob) for glob in self.allow):
            return False
        return not any(fnmatchcase(name, glob) for glob in self.deny)

    def unmatched(self, names: Iterable[str]) -> list[str]:
        """Globs that match none of `names` - almost always a typo."""
        names = list(names)
        return [glob for glob in (*self.allow, *self.deny) if not any(fnmatchcase(n, glob) for n in names)]


@dataclass(frozen=True)
class TierInfo:
    """One model strength an agent may run on, as the orchestrator sees it."""

    tier: str
    id: str
    use_for: str


@dataclass(frozen=True)
class RosterEntry:
    """One specialist as the orchestrator sees it."""

    id: str
    label: str
    focus: str
    tiers: tuple[TierInfo, ...] = ()
    # Reasoning efforts it accepts from a delegator, weakest first.
    efforts: tuple[str, ...] = ()
    # Its tools.allow globs; with them the orchestrator can tell that the
    # specialist has nothing to work with (see agent_routing.is_usable).
    tool_allow: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentSpec:
    id: str
    label: str
    port: int
    llm: LlmSpec
    enabled: bool = True
    entry: bool = False
    role: str = "specialist"
    # "" = the shared identity template (prompt_config); else replaces the identity line.
    identity: str = ""
    persona: str = ""
    # "" = agent_roles.DEFAULT_INSTRUCTIONS.
    instructions: str = ""
    focus: str = ""
    tools: ToolScope = field(default_factory=ToolScope)
    # Load the user's newest saved notes at the start of each top-level turn (agents/memory_recall.py).
    memory_recall: bool = False
    # Load the user's approved skills that match the question at the start of each top-level turn (agents/skill_recall.py).
    skill_recall: bool = False
    # After a qualifying turn, draft a skill and propose it for the user's approval (agents/skill_reflection.py).
    skill_learning: bool = False
    # Offer the update_plan checklist tool (agents/plan.py); the chat's own toggle can still switch it off.
    plan_tool: bool = True
    # False keeps the agent out of every orchestrator's roster: it is called directly (ember_api), never delegated to.
    delegable: bool = True
    # Address peers and ember_api reach this agent at (what it registers);
    # None = derived from the host and port it listens on.
    url: str | None = None
    source: Path | None = None
    decision: Any = None

    @property
    def orchestrator(self) -> bool:
        return self.role == "orchestrator"

    @property
    def internal_role(self) -> str | None:
        return "router" if self.role == "router" else None

    def effective_gateway(self) -> str | None:
        """The gateway to report in usage rows: the file's own gateway (None
        = the provider used directly)."""
        return self.llm.gateway


class _Checker:
    """Validation helpers that name the file and the field in every error."""

    def __init__(self, path: Path) -> None:
        self._name = path.name

    def fail(self, where: str, message: str) -> AgentSpecError:
        return AgentSpecError(f"{self._name}: {where} {message}")

    def keys(self, data: dict[str, Any], allowed: set[str], prefix: str = "") -> None:
        for key in data:
            if key not in allowed:
                raise self.fail(f"{prefix}{key}", "is not a known field")

    def boolean(self, data: dict[str, Any], key: str, default: bool, prefix: str = "") -> bool:
        value = data.get(key, default)
        if not isinstance(value, bool):
            raise self.fail(f"{prefix}{key}", "must be true or false")
        return value

    def text(self, data: dict[str, Any], key: str, default: str | None, prefix: str = "") -> str | None:
        value = data.get(key, default)
        if value is not None and not isinstance(value, str):
            raise self.fail(f"{prefix}{key}", "must be a string")
        return value

    def integer(self, data: dict[str, Any], key: str, default: int | None, low: int, high: int, prefix: str = "") -> int | None:
        value = data.get(key, default)
        if value is None:
            if default is not None:
                raise self.fail(f"{prefix}{key}", f"must be a whole number from {low} to {high}, not null")
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise self.fail(f"{prefix}{key}", f"must be a whole number from {low} to {high}")
        return value

    def number(self, data: dict[str, Any], key: str, low: float, high: float, prefix: str = "") -> float | None:
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise self.fail(f"{prefix}{key}", f"must be a number from {low:g} to {high:g}")
        return float(value)

    def section(self, data: dict[str, Any], key: str) -> dict[str, Any]:
        value = data.get(key, {})
        if not isinstance(value, dict):
            raise self.fail(key, "must be an object")
        return value

    def globs(self, data: dict[str, Any], key: str) -> tuple[str, ...]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            raise self.fail(f"tools.{key}", "must be a list of non-empty strings")
        return tuple(value)

    def tier(self, data: dict[str, Any], key: str, prefix: str = "") -> str | None:
        value = data.get(key)
        if value is None:
            return None
        if value not in TIERS:
            raise self.fail(f"{prefix}{key}", f"must be one of: {', '.join(TIERS)}")
        return value


def _agent_url(check: _Checker, data: dict[str, Any]) -> str | None:
    """`url`: the http(s) address this agent registers under. A bare origin
    gets /mcp, the path ai_agent serves."""
    value = check.text(data, "url", None)
    if not value:
        return None
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment:
        raise check.fail("url", "must be an http(s) address like http://10.0.0.5:9103/mcp")
    try:
        parts.port  # noqa: B018 - raises ValueError for a port out of range
    except ValueError:
        raise check.fail("url", "has an invalid port") from None
    path = parts.path.rstrip("/") or "/mcp"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def overrides_path_for(directory: Path) -> Path:
    """Where the admin's edits to the agent files in `directory` live: the
    untracked `.data/agent_overrides.json` of the project (`{id: <whole agent
    file>}`). A tracked agents/<id>.json is the shared default; an entry here
    replaces it on this machine. Any other folder (tests) keeps its own
    overrides inside it, in a subfolder the `*.json` scan never matches."""
    if directory == AGENTS_DIR:
        return AGENTS_DIR.parent / ".data" / "agent_overrides.json"
    return directory / ".overrides" / "agent_overrides.json"


def read_overrides(directory: Path) -> dict[str, dict[str, Any]]:
    """The overrides for `directory`; {} when there is no file."""
    path = overrides_path_for(directory)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise AgentSpecError(f"{path}: cannot be read as JSON ({error})") from error
    if not isinstance(data, dict) or not all(isinstance(entry, dict) for entry in data.values()):
        raise AgentSpecError(f"{path}: must be an object of agent objects")
    return data


def agent_ids(directory: Path) -> list[str]:
    """Ids of the tracked agent files in `directory` plus agents that exist
    only as an override, sorted."""
    return sorted({p.stem for p in directory.glob("*.json")} | set(read_overrides(directory)))


def load_file(path: Path) -> AgentSpec:
    """Read and validate one agent file, or its override when the admin
    edited it on this machine. The id is the file name stem."""
    check = _Checker(path)
    agent_id = path.stem
    if not _ID_RE.match(agent_id):
        raise check.fail("id", f"{agent_id!r} must be lowercase letters, digits and dashes (from the file name)")
    data = read_overrides(path.parent).get(agent_id)
    if data is None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise check.fail("file", f"cannot be read as JSON ({error})") from error
    if not isinstance(data, dict):
        raise check.fail("file", "must contain a JSON object")
    check.keys(data, _TOP_KEYS)
    role = data.get("role")
    if role not in ROLES:
        raise check.fail("role", f"is required and must be one of: {', '.join(ROLES)}")

    if "port" not in data:
        raise check.fail("port", "is required")
    port = check.integer(data, "port", None, 1, 65535)
    if port is None:
        raise check.fail("port", "must be a whole number from 1 to 65535, not null")
    if "llm" not in data:
        raise check.fail("llm", "is required")
    llm_data = check.section(data, "llm")
    check.keys(llm_data, _LLM_KEYS, "llm.")
    provider = llm_data.get("provider")
    if provider not in PROVIDERS:
        raise check.fail("llm.provider", f"must be one of: {', '.join(PROVIDERS)}")
    from src.providers.decision.strategy import STRATEGIES

    strategy = llm_data.get("strategy")
    min_confidence = llm_data.get("min_confidence")
    if provider == "decision":
        strategy = strategy or "both"
        if strategy not in STRATEGIES:
            raise check.fail("llm.strategy", f"must be one of: {', '.join(STRATEGIES)}")
        min_confidence = 0.9 if min_confidence is None else check.number(llm_data, "min_confidence", 0.0001, 1.0, "llm.")
        for key in ("gateway", "model", "fallback_gateways"):
            if key in llm_data:
                raise check.fail(f"llm.{key}", "the decision provider has no gateway, model or fallback_gateways; pick llm.strategy")
    elif strategy is not None or min_confidence is not None:
        raise check.fail("llm.strategy", "and llm.min_confidence are only for the decision provider")

    effort = llm_data.get("reasoning_effort", "off")
    if effort not in REASONING_EFFORTS:
        raise check.fail("llm.reasoning_effort", f"must be one of: {', '.join(REASONING_EFFORTS)}")
    max_effort = llm_data.get("max_effort")
    if max_effort is not None and max_effort not in REASONING_EFFORTS:
        raise check.fail("llm.max_effort", f"must be one of: {', '.join(REASONING_EFFORTS)}")
    if max_effort is not None and REASONING_EFFORTS.index(effort) > REASONING_EFFORTS.index(max_effort):
        raise check.fail("llm.reasoning_effort", f"{effort!r} is above llm.max_effort {max_effort!r}")
    min_tier = check.tier(llm_data, "min_tier", "llm.")
    max_tier = check.tier(llm_data, "max_tier", "llm.")
    if min_tier and max_tier and TIERS.index(min_tier) > TIERS.index(max_tier):
        raise check.fail("llm.min_tier", f"{min_tier!r} is stronger than llm.max_tier {max_tier!r}")
    fallback_data = llm_data.get("fallback_gateways", [])
    if not isinstance(fallback_data, list):
        raise check.fail("llm.fallback_gateways", "must be a list")
    if provider == "decision" and fallback_data:
        raise check.fail("llm.fallback_gateways", "Laya does not support gateway failover")
    primary = check.text(llm_data, "gateway", None, "llm.") or _DEFAULT_GATEWAY[provider]
    choices: list[GatewayChoice] = []
    seen = {primary}
    for index, entry in enumerate(fallback_data):
        prefix = f"llm.fallback_gateways[{index}]."
        if isinstance(entry, str):
            entry = {"gateway": entry}
        if not isinstance(entry, dict):
            raise check.fail(prefix[:-1], "must be a gateway name or object")
        check.keys(entry, {"gateway", "model"}, prefix)
        name = check.text(entry, "gateway", None, prefix)
        if not name or not name.strip():
            raise check.fail(prefix + "gateway", "must be a non-empty string")
        if name in seen:
            raise check.fail(prefix + "gateway", "duplicates the primary or another fallback")
        seen.add(name)
        choices.append(GatewayChoice(name, check.text(entry, "model", None, prefix) or None))
    llm = LlmSpec(
        provider=provider,
        gateway=check.text(llm_data, "gateway", None, "llm.") or None,
        model=check.text(llm_data, "model", None, "llm.") or None,
        temperature=check.number(llm_data, "temperature", 0.0, 2.0, "llm."),
        reasoning_effort=effort,
        max_tokens=check.integer(llm_data, "max_tokens", None, 1, 1_000_000, "llm."),
        max_tool_rounds=check.integer(llm_data, "max_tool_rounds", None, 1, 100, "llm."),
        max_turn_tokens=check.integer(llm_data, "max_turn_tokens", None, 1, 100_000_000, "llm."),
        max_turn_seconds=check.number(llm_data, "max_turn_seconds", 0.001, 86_400, "llm."),
        min_tier=min_tier,
        max_tier=max_tier,
        max_effort=max_effort,
        fallback_gateways=tuple(choices),
        strategy=strategy, min_confidence=min_confidence,
    )

    tools_data = check.section(data, "tools")
    check.keys(tools_data, _TOOLS_KEYS, "tools.")
    tools = ToolScope(allow=check.globs(tools_data, "allow"), deny=check.globs(tools_data, "deny"))

    orchestrator = role == "orchestrator"
    memory_recall = check.boolean(data, "memory_recall", False)
    skill_recall = check.boolean(data, "skill_recall", False)
    skill_learning = check.boolean(data, "skill_learning", False)
    if provider == "decision":
        if orchestrator or check.boolean(data, "entry", False):
            raise check.fail("llm.provider", "the decision provider must be a specialist or router, not an entry agent or orchestrator")
        if memory_recall:
            raise check.fail("memory_recall", "the decision provider has no tools, so it cannot recall memory")
        if skill_recall:
            raise check.fail("skill_recall", "the decision provider has no tools, so it cannot recall skills")
        if skill_learning:
            raise check.fail("skill_learning", "the decision provider has no tools, so it cannot learn skills")
        if any(key in llm_data for key in ("temperature", "max_tokens", "max_tool_rounds", "max_turn_tokens", "max_turn_seconds", "min_tier", "max_tier", "max_effort")) or effort != "off":
            raise check.fail("llm", "the decision provider does not accept generation or tool-loop settings")

    policy = None
    if role == "router":
        from src.agents.roles.router.router_contract import RouterPolicy

        if (provider != "decision" or check.boolean(data, "entry", False)
                or check.boolean(data, "delegable", True) or memory_recall or skill_recall or skill_learning
                or check.boolean(data, "plan_tool", True) or "*" not in tools.deny):
            raise check.fail("role", "router requires the decision provider, no entry, no delegation, no tools, memory or plan")
        try:
            policy = RouterPolicy.model_validate(data.get("decision", {}))
        except ValueError as error:
            raise check.fail("decision", str(error)) from error
    elif "decision" in data:
        raise check.fail("decision", "is only supported for role router")

    return AgentSpec(
        id=agent_id,
        url=_agent_url(check, data),
        label=check.text(data, "label", None) or agent_id,
        port=port,
        llm=llm,
        enabled=check.boolean(data, "enabled", True),
        entry=check.boolean(data, "entry", False),
        identity=check.text(data, "identity", "") or "",
        persona=check.text(data, "persona", "") or "",
        instructions=check.text(data, "instructions", "") or "",
        focus=check.text(data, "focus", "") or "",
        tools=tools,
        role=role,
        memory_recall=memory_recall,
        skill_recall=skill_recall,
        skill_learning=skill_learning,
        plan_tool=check.boolean(data, "plan_tool", True),
        delegable=check.boolean(data, "delegable", True),
        source=path,
        decision=policy,
    )


def load_dir(directory: Path) -> list[AgentSpec]:
    """Every agent file in `directory`, validated one by one and as a set:
    enabled agents need distinct ports and exactly one entry agent."""
    ids = agent_ids(directory)
    if not ids:
        raise AgentSpecError(f"{directory}: no agent files found (create <id>.json)")
    specs = [load_file(directory / f"{agent_id}.json") for agent_id in ids]
    enabled = [s for s in specs if s.enabled]
    if sum(s.internal_role == "router" for s in enabled) > 1:
        raise AgentSpecError("at most one enabled internal router is allowed")

    by_port: dict[int, list[str]] = {}
    for spec in enabled:
        by_port.setdefault(spec.port, []).append(f"{spec.id}.json")
    for port, names in by_port.items():
        if len(names) > 1:
            raise AgentSpecError(f"port {port} is used by more than one enabled agent: {', '.join(names)}")

    entries = [f"{s.id}.json" for s in enabled if s.entry]
    if len(entries) != 1:
        found = ", ".join(entries) if entries else "none"
        raise AgentSpecError(f"exactly one enabled agent must set entry: true (found: {found})")
    return specs


_current: AgentSpec | None = None


def current() -> AgentSpec:
    """This process's spec, from the agent file named in AI_AGENT_FILE. Read
    once and cached - an agent's definition never changes while it runs."""
    global _current
    if _current is None:
        file = os.getenv("AI_AGENT_FILE")
        if not file:
            raise AgentSpecError(
                "AI_AGENT_FILE is not set - start agents with python -m src.supervisor, "
                "or set AI_AGENT_FILE to an agents/<id>.json path"
            )
        _current = load_file(Path(file))
    return _current


def reset_cache() -> None:
    global _current
    _current = None


def apply_to_environ(spec: AgentSpec) -> None:
    """Hand a file spec's provider/gateway/model/port to the env vars the
    existing import-time code reads. Set (not setdefault) so they win over
    .env, which agent_config loads with setdefault."""
    os.environ["AI_AGENT_PROVIDER"] = spec.llm.provider
    os.environ["AI_AGENT_GATEWAY"] = spec.llm.gateway or _DEFAULT_GATEWAY[spec.llm.provider]
    # "" (not unset): agent_config reads `os.getenv("AI_AGENT_MODEL") or None`,
    # and an existing key stops .env's setdefault from filling it.
    os.environ["AI_AGENT_MODEL"] = spec.llm.model or ""
    os.environ["AI_AGENT_PORT"] = str(spec.port)
