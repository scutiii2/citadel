"""Check provider-key isolation and start-order hints without reading deployment env files.

    python scripts/check_compose.py            checks the real compose files (needs Docker)
    python scripts/check_compose.py --self-test  checks check() on hand-made data (no Docker)
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load(files: list[str]) -> dict:
    """`docker compose config` as JSON, without reading any deployment env file."""
    env = {**os.environ, "COMPOSE_DISABLE_ENV_FILE": "1"}
    env.pop("COMPOSE_ENV_FILES", None)
    args = ["docker", "compose", *[arg for file in files for arg in ("-f", file)],
            "config", "--no-env-resolution", "--format", "json"]
    done = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "docker compose config failed")
    return json.loads(done.stdout)


def _loads_gateways_env(service: dict) -> bool:
    for entry in service.get("env_file", []):
        path = entry["path"] if isinstance(entry, dict) else entry
        if Path(path).name == ".env.gateways":
            return True
    return False


def check(default: dict) -> list[str]:
    """One message per broken invariant; an empty list means all hold."""
    out: list[str] = []
    services = default.get("services", {})
    on_llm = {n for n, s in services.items() if "llm_net" in (s.get("networks") or {})}
    if on_llm != {"legion"}:
        out.append("networks: llm_net must be attached to exactly legion, found " + ", ".join(sorted(on_llm)))
    legion = services.get("legion", {})
    if not {"core", "llm_net"} <= set(legion.get("networks") or {}):
        out.append("networks: legion must be on core and llm_net")
    if not _loads_gateways_env(legion):
        out.append("env_file: legion does not load .env.gateways")
    for name, svc in services.items():
        if name == "legion":
            continue
        if _loads_gateways_env(svc):
            out.append(f"env_file: {name} loads .env.gateways")
        if ".env.gateways" in json.dumps([svc.get("volumes"), svc.get("environment")]):
            out.append(f"volumes: {name} mentions .env.gateways in volumes or environment")
    if "ports" in legion and legion["ports"]:
        out.append("ports: legion must not publish a port")
    for name, service in services.items():
        depends = service.get("depends_on")
        if isinstance(depends, dict) and any(
            options.get("condition", "service_started") != "service_started" for options in depends.values()
        ):
            out.append(f"depends_on: {name} requires more than a start-order hint")
    if default.get("networks", {}).get("llm_net", {}).get("internal"):
        out.append("networks: llm_net must not be internal")
    return out


def _mapping(node):
    if isinstance(node, yaml.MappingNode):
        return {key.value: value for key, value in node.value}
    return {}


def check_source(text: str) -> list[str]:
    """Inspect the YAML shape before Compose normalizes it, including tagged overlays."""
    document = _mapping(yaml.compose(text, Loader=yaml.SafeLoader))
    problems = []
    for name, service in _mapping(document.get("services")).items():
        depends_on = _mapping(service).get("depends_on")
        if depends_on is not None and not isinstance(depends_on, yaml.SequenceNode):
            problems.append(f"depends_on: {name} must be a plain list for a start-order hint")
    return problems


def _good() -> dict:
    return {"services": {"legion": {"networks": {"core": None, "llm_net": None}, "env_file": [{"path": ".env.gateways"}],
                                    "depends_on": {"armory": {}}},
                         "armory": {"networks": {"core": None}, "environment": {"A": "1"}}},
            "networks": {"core": {}, "llm_net": {"name": "citadel_llm"}}}


def self_test() -> None:
    default = _good()
    assert check(default) == []
    assert check_source("services: {armory: {ports: !override [], depends_on: [treasury]}}") == []
    assert check_source("services: {armory: {depends_on: {legion: {condition: service_healthy}}}}")

    def broken(mutate, word):
        d = copy.deepcopy(default)
        mutate(d)
        found = check(d)
        assert len(found) == 1 and word in found[0], (word, found)

    broken(lambda d: d["services"]["armory"]["networks"].update(llm_net=None), "llm_net must be attached")
    broken(lambda d: d["services"]["legion"]["networks"].pop("core"), "legion must be on")
    broken(lambda d: d["services"]["legion"].pop("env_file"), "does not load")
    broken(lambda d: d["services"]["legion"].update(ports=["1:1"]), "ports")
    broken(lambda d: d["services"]["armory"].update(env_file=[{"path": ".env.gateways"}]), "env_file")
    broken(lambda d: d["services"]["armory"].update(volumes=[{"source": "/x/.env.gateways"}]), "volumes")
    broken(lambda d: d["services"]["armory"].update(depends_on={"legion": {"condition": "service_healthy"}}),
           "start-order hint")
    broken(lambda d: d["networks"]["llm_net"].update(internal=True), "internal")
    print("self-test passed")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        sys.exit(0)
    try:
        problems = check(load(["docker-compose.yml"]))
        for filename in sorted(ROOT.glob("docker-compose*.yml")):
            problems.extend(check_source(filename.read_text(encoding="utf-8")))
    except FileNotFoundError:
        print("docker not found; install Docker or use --self-test")
        sys.exit(2)
    except RuntimeError as err:
        print(f"docker compose config failed: {err}")
        sys.exit(2)
    print("\n".join(problems) or "compose invariants hold")
    sys.exit(1 if problems else 0)
