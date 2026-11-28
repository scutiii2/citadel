"""Create, read, update and delete agents for the admin UI.

`agents/<id>.json` is the tracked, shared default. The admin never writes it:
its edits go to the `agent_overrides` table of `.data/settings.db` (see
agent_spec.overrides_path_for), which replaces an agent's file on this
machine, so a machine-specific model, cap or enabled switch never shows up in
git. The supervisor re-reads both and starts, restarts or stops children to
match (see supervisor.py). Delete is the exception: it removes both. Every
write is validated with agent_spec.load_file plus the set-wide rules
load_dir enforces (distinct enabled ports, exactly one enabled entry agent),
so a bad edit is refused here instead of stopping the supervisor's reload.

All functions are blocking; callers run them in a worker thread.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from src.agents import agent_spec, prompt_config
from src.agents.agent_spec import AgentSpec, AgentSpecError, RosterEntry
from src.agents import agent_roles
from src.providers import llm_config

_LOCK = threading.Lock()


class AgentStoreError(Exception):
    """A refused change. `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _decision_trusted(gateway_id: str) -> bool:
    from src.providers.decision import gateway_client as decision_client

    return decision_client.is_trusted(gateway_id)


def gateway_catalog(saved_only: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Providers and gateways from gateways/<provider>/<gateway>.json.
    Decision presets list Laya and Jev without language tiers. Credentials
    are never returned: only id, label, default model and tier ids.
    `saved_only`: only gateways that are set up on the Model gateways page (a saved
    gateway without a template file is listed with its own label and model)."""
    try:
        raw = llm_config.load_gateways()
    except (OSError, ValueError) as error:
        raise AgentStoreError(f"gateways/ cannot be read: {error}", 500) from error
    catalog: dict[str, list[dict[str, Any]]] = {}
    for provider in agent_spec.PROVIDERS:
        block = raw.get(provider)
        gateways = []
        for gateway_id, entry in (block.items() if isinstance(block, dict) else []):
            if not isinstance(entry, dict):
                continue
            try:
                tiers = [{"tier": name, "id": tier.id} for name, tier in llm_config.tiers(provider, gateway_id).items()]
            except (KeyError, ValueError):
                tiers = []
            item = {
                "id": gateway_id,
                "label": entry.get("label") or gateway_id,
                "model": entry.get("model") if isinstance(entry.get("model"), str) else "",
                "tiers": tiers,
            }
            if provider == "decision":
                item["trusted"] = _decision_trusted(gateway_id)
            gateways.append(item)
        catalog[provider] = gateways
    return _saved(catalog) if saved_only else catalog


def _saved(catalog: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """`catalog` cut down to the gateways saved in Legion's chat and decision gateways."""
    from src import gateway

    chat = gateway.chat_store().all()
    decision = set(gateway.decision_store().all())
    result: dict[str, list[dict[str, Any]]] = {}
    for provider, entries in catalog.items():
        ids = decision if provider == "decision" else {gid for gid, entry in chat.items() if entry.get("provider") == provider}
        kept = [entry for entry in entries if entry["id"] in ids]
        listed = {entry["id"] for entry in kept}
        for gid in sorted(ids - listed):
            saved = chat.get(gid, {})
            tiers = {} if provider == "decision" else llm_config.tiers(provider, gid)  # decision gateways have no tiers
            kept.append({"id": gid, "label": saved.get("label") or gid,
                         "model": saved.get("model") if isinstance(saved.get("model"), str) else "",
                         "tiers": [{"tier": name, "id": tier.id} for name, tier in tiers.items()],
                         **({"trusted": _decision_trusted(gid)} if provider == "decision" else {})})
        result[provider] = kept
    return result


def list_agents(directory: Path = agent_spec.AGENTS_DIR) -> list[dict[str, Any]]:
    """Every agent as its JSON plus `id`; an unreadable one carries `error`.
    `overridden` is true when this machine's override replaces a tracked default
    (so it can be reset)."""
    rows = []
    overrides = _read_overrides(directory)
    for agent_id in _ids(directory):
        try:
            rows.append({
                "id": agent_id, **_effective(agent_id, directory),
                "overridden": agent_id in overrides and _path_of(agent_id, directory).is_file(),
            })
        except AgentStoreError as error:
            rows.append({"id": agent_id, "error": str(error)})
    return rows


def get_agent(agent_id: str, directory: Path = agent_spec.AGENTS_DIR) -> dict[str, Any]:
    return {"id": agent_id, **_effective(agent_id, directory)}


def create_agent(agent_id: str, data: dict[str, Any], directory: Path = agent_spec.AGENTS_DIR) -> dict[str, Any]:
    with _LOCK:
        data = agent_spec.upgrade_decision(data)
        _path_of(agent_id, directory)
        if agent_id in _ids(directory):
            raise AgentStoreError(f"agent {agent_id!r} already exists", 409)
        _validate_change(agent_id, data, directory)
        _save_override(agent_id, data, directory)
    return {"id": agent_id, **data}


def update_agent(agent_id: str, data: dict[str, Any], directory: Path = agent_spec.AGENTS_DIR) -> dict[str, Any]:
    with _LOCK:
        data = agent_spec.upgrade_decision(data)
        _effective(agent_id, directory)
        _validate_change(agent_id, data, directory)
        _save_override(agent_id, data, directory)
    return {"id": agent_id, **data}


def delete_agent(agent_id: str, directory: Path = agent_spec.AGENTS_DIR) -> None:
    """Remove an agent: its tracked file and its override. The entry agent
    cannot be removed: pick another entry agent first, or the set would have none."""
    with _LOCK:
        path = _path_of(agent_id, directory)
        if _effective(agent_id, directory).get("entry") is True:
            raise AgentStoreError(f"{agent_id!r} is the entry agent; make another agent the entry first", 409)
        path.unlink(missing_ok=True)
        if agent_id in _read_overrides(directory):
            agent_spec.remove_override(directory, agent_id)


def reset_agent(agent_id: str, directory: Path = agent_spec.AGENTS_DIR) -> dict[str, Any]:
    """Drop the agent's override so its tracked file applies again. Refused
    when there is no override, or no tracked file to fall back to (removing
    the override would delete the agent: use delete_agent). The tracked file
    must itself leave the whole set valid."""
    with _LOCK:
        path = _path_of(agent_id, directory)
        overrides = _read_overrides(directory)
        if agent_id not in overrides:
            raise AgentStoreError(f"agent {agent_id!r} already uses its default", 409)
        if not path.is_file():
            raise AgentStoreError(f"agent {agent_id!r} has no default file to reset to", 409)
        defaults = _read_json(path)
        _validate_change(agent_id, defaults, directory)
        agent_spec.remove_override(directory, agent_id)
    return {"id": agent_id, **defaults, "overridden": False}


def _read_overrides(directory: Path) -> dict[str, dict[str, Any]]:
    try:
        return agent_spec.read_overrides(directory)
    except AgentSpecError as error:
        raise AgentStoreError(str(error), 500) from error


def _ids(directory: Path) -> list[str]:
    try:
        return agent_spec.agent_ids(directory)
    except AgentSpecError as error:
        raise AgentStoreError(str(error), 500) from error


def _effective(agent_id: str, directory: Path) -> dict[str, Any]:
    """The agent's JSON as it runs here: its override, else its tracked file."""
    path = _path_of(agent_id, directory)
    override = _read_overrides(directory).get(agent_id)
    if override is not None:
        return override
    if not path.is_file():
        raise AgentStoreError(f"agent {agent_id!r} does not exist", 404)
    return _read_json(path)


def _save_override(agent_id: str, data: dict[str, Any], directory: Path) -> None:
    agent_spec.write_override(directory, agent_id, data)


def _path_of(agent_id: str, directory: Path) -> Path:
    if not isinstance(agent_id, str) or not agent_spec._ID_RE.match(agent_id):
        raise AgentStoreError("id must be lowercase letters, digits and dashes")
    return directory / f"{agent_id}.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AgentStoreError(f"{path.name} cannot be read as JSON ({error})", 500) from error
    if not isinstance(data, dict):
        raise AgentStoreError(f"{path.name} must contain a JSON object", 500)
    return data


def _load_spec(agent_id: str, data: dict[str, Any]) -> AgentSpec:
    """Parse `data` as agent file `agent_id` through a scratch file, so errors name `<id>.json`."""
    with tempfile.TemporaryDirectory() as scratch:
        candidate = Path(scratch) / f"{agent_id}.json"
        candidate.write_text(json.dumps(data), encoding="utf-8")
        try:
            return agent_spec.load_file(candidate)
        except AgentSpecError as error:
            raise AgentStoreError(str(error).replace(str(candidate), f"{agent_id}.json")) from error


def _validate_change(agent_id: str, data: dict[str, Any], directory: Path) -> AgentSpec:
    """Raise AgentStoreError unless `data` is a valid file for `agent_id` and
    the whole folder stays valid with it."""
    if not isinstance(data, dict):
        raise AgentStoreError("the agent must be a JSON object")
    spec = _load_spec(agent_id, data)
    _check_gateway(spec)
    _check_trusted(spec)
    others = _other_specs(agent_id, directory)
    if spec.enabled and spec.internal_role == "router" and any(
        o.enabled and o.internal_role == "router" for o in others
    ):
        raise AgentStoreError("at most one enabled internal router is allowed", 409)
    if spec.enabled:
        clash = next((o.id for o in others if o.enabled and o.port == spec.port), None)
        if clash:
            raise AgentStoreError(f"port {spec.port} is already used by enabled agent {clash!r}", 409)
    entries = [o.id for o in others if o.enabled and o.entry]
    if spec.enabled and spec.entry:
        if entries:
            raise AgentStoreError(f"{entries[0]!r} is already the entry agent; unset it there first", 409)
    elif not entries:
        raise AgentStoreError("exactly one enabled agent must be the entry agent", 409)
    try:
        agent_spec.check_roster([*others, spec])
    except AgentSpecError as error:
        raise AgentStoreError(str(error), 409) from error
    return spec


def _check_gateway(spec: AgentSpec) -> None:
    if spec.llm.provider == "decision":
        known = {entry["id"] for source in (gateway_catalog(), gateway_catalog(saved_only=True))
                 for entry in source.get("decision", [])}
        for name in spec.llm.gateway_names:
            if name not in known:
                raise AgentStoreError(f"{spec.id}.json: {name!r} is not a decision gateway")
        return
    gateway = spec.llm.gateway
    if gateway is None and not spec.llm.fallback_gateways:
        return
    # Template files plus gateways saved on the Model gateways page (a saved one may have no template file).
    catalog = gateway_catalog()
    saved = gateway_catalog(saved_only=True)
    known = {entry["id"] for source in (catalog, saved) for entry in source.get(spec.llm.provider, [])}
    # A backup may speak the other chat protocol: the agent then moves a turn to it when the first protocol has none left.
    any_chat = {entry["id"] for source in (catalog, saved) for provider in ("anthropic", "openai") for entry in source.get(provider, [])}
    gateway = gateway or agent_spec.default_gateway(spec.llm.provider)
    if gateway not in known:
        raise AgentStoreError(f"llm.gateway {gateway!r} is not a {spec.llm.provider} gateway in gateways/")
    for index, choice in enumerate(spec.llm.fallback_gateways):
        if choice.gateway not in any_chat:
            raise AgentStoreError(
                f"{spec.id}.json: llm.fallback_gateways[{index}].gateway {choice.gateway!r} "
                "is not a chat gateway in gateways/")


def _gateway_names(spec: AgentSpec) -> list[str]:
    """The gateways an agent may use, in order: its own, then its fallbacks. A decision agent has none."""
    if spec.llm.provider == "decision":
        return []
    return [spec.llm.gateway or agent_spec.default_gateway(spec.llm.provider), *(c.gateway for c in spec.llm.fallback_gateways)]


def _check_trusted(spec: AgentSpec) -> None:
    """An enabled agent always has a trusted gateway, so confidential data has somewhere to go."""
    from src.providers import gateway_client

    if spec.llm.provider == "decision":
        from src.providers.decision import gateway_client as decision_client, rules

        problem = rules.order_problem(spec.id, spec.llm.gateway_names, decision_client.is_trusted) if spec.enabled else None
        if problem:
            raise AgentStoreError(f"{spec.id}.json: {problem}", 409)
        return
    names = _gateway_names(spec)
    if spec.enabled and names and not any(gateway_client.is_trusted(name) for name in names):
        raise AgentStoreError(
            f"{spec.id}.json: none of its gateways ({', '.join(names)}) is trusted; mark one as trusted on the "
            "Model gateways page or add a trusted gateway to llm.fallback_gateways", 409)


def agents_losing_trust(gateway_id: str, directory: Path = agent_spec.AGENTS_DIR) -> list[str]:
    """Enabled agents whose only trusted gateway is `gateway_id`: they would have none if it stopped being trusted
    or were deleted."""
    from src.providers import gateway_client

    lost = []
    for agent_id in _ids(directory):
        try:
            spec = _load_spec(agent_id, _effective(agent_id, directory))
        except AgentStoreError:
            continue
        names = _gateway_names(spec)
        if spec.enabled and gateway_id in names and not any(
                name != gateway_id and gateway_client.is_trusted(name) for name in names):
            lost.append(agent_id)
    return lost


def agents_breaking_order(gateway_id: str, trusted: bool | None, directory: Path = agent_spec.AGENTS_DIR) -> list[str]:
    """Enabled decision agents whose list is allowed now and would not be after the decision gateway `gateway_id`
    got the trust `trusted`, or was deleted (None)."""
    from src.providers.decision import gateway_client as decision_client, rules

    def after(name: str) -> bool:
        return bool(trusted) if name == gateway_id else decision_client.is_trusted(name)

    broken = []
    for agent_id in _ids(directory):
        try:
            spec = _load_spec(agent_id, _effective(agent_id, directory))
        except AgentStoreError:
            continue
        names = spec.llm.gateway_names
        if not spec.enabled or spec.llm.provider != "decision" or gateway_id not in names:
            continue
        if rules.order_problem(spec.id, names, decision_client.is_trusted):
            continue
        left = names if trusted is not None else tuple(name for name in names if name != gateway_id)
        if rules.order_problem(spec.id, left, after):
            broken.append(agent_id)
    return broken


def _other_specs(agent_id: str, directory: Path) -> list[AgentSpec]:
    """Valid specs of every other agent file; a broken one is skipped (it
    cannot clash with anything the supervisor would run)."""
    specs = []
    for other in _ids(directory):
        if other == agent_id:
            continue
        try:
            specs.append(agent_spec.load_file(directory / f"{other}.json"))
        except AgentSpecError:
            continue
    return specs


def get_prompts(path: Path = prompt_config.PATH) -> dict[str, Any]:
    """The shared prompt texts: effective `values`, the built-in `defaults`,
    and which keys the file overrides."""
    return {
        "values": prompt_config.load(path),
        "defaults": dict(prompt_config.DEFAULTS),
        "overridden": sorted(prompt_config.overrides(path)),
    }


def set_prompts(changes: dict[str, Any], path: Path = prompt_config.PATH) -> dict[str, Any]:
    """Change shared prompt texts (None or blank resets one). Every running
    agent restarts to apply them."""
    if any(value is not None and not isinstance(value, str) for value in changes.values()):
        raise AgentStoreError("each prompt must be text, or null to reset it")
    try:
        with _LOCK:
            prompt_config.save(changes, path)
    except prompt_config.PromptConfigError as error:
        raise AgentStoreError(str(error)) from error
    return get_prompts(path)


def preview_prompt(
    agent_id: str, data: dict[str, Any], caveman: bool = False, directory: Path = agent_spec.AGENTS_DIR,
    prompts_path: Path = prompt_config.PATH,
) -> str:
    """The system prompt a draft agent file would produce with today's shared
    texts. Only the file itself is validated (not ports or the entry rule), so
    a half-finished draft can still be previewed. An orchestrator's roster is
    every other enabled agent."""
    if not isinstance(data, dict):
        raise AgentStoreError("the agent must be a JSON object")
    _path_of(agent_id, directory)
    spec = _load_spec(agent_id, data)
    roster = [
        RosterEntry(id=o.id, label=o.label, focus=o.focus)
        for o in _other_specs(agent_id, directory)
        if o.enabled and o.delegable
    ]
    return agent_roles.preview(spec, roster, prompt_config.load(prompts_path), caveman)
