"""Check that the stack gateways stay private to Legion. Never reads a real .env.gateways: it uses a temp copy and a sentinel.

    python scripts/check_compose.py            checks the real compose files (needs Docker)
    python scripts/check_compose.py --self-test  checks check() on hand-made data (no Docker)
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATEWAYS = ("conversation-gateway", "decision-gateway")
SENTINEL = "CHECK_COMPOSE_SENTINEL"  # written into a throwaway .env.gateways; compose copies env_file values into environment
ADMIN_OVERLAY = ["docker-compose.yml", "docker-compose.gateway-admin.yml"]


def load(files: list[str]) -> dict:
    """`docker compose config` as JSON, with throwaway admin passwords in the child environment only."""
    env = {**os.environ, "CONVERSATION_GATEWAY_ADMIN_PASSWORD": "x", "DECISION_GATEWAY_ADMIN_PASSWORD": "x"}
    # Compose JSON drops env_file and inlines its values, so read a copy of the files next to a sentinel .env.gateways.
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            shutil.copy(ROOT / f, tmp)
        (Path(tmp) / ".env.gateways").write_text(f"{SENTINEL}=1\n", encoding="utf-8")
        args = ["docker", "compose", "--project-directory", tmp, *[a for f in files for a in ("-f", str(Path(tmp) / f))], "config", "--format", "json"]
        done = subprocess.run(args, cwd=tmp, env=env, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "docker compose config failed")
    return json.loads(done.stdout)


def _loads_gateways_env(service: dict) -> bool:
    return SENTINEL in (service.get("environment") or {})


def check(default: dict, overlay: dict) -> list[str]:
    """One message per broken invariant; an empty list means all hold."""
    out: list[str] = []
    services = default.get("services", {})
    for name in GATEWAYS:
        if name not in services:
            out.append(f"services: {name} is missing")
    if out:
        return out
    for name in GATEWAYS:
        svc = services.get(name)
        if svc is None:
            continue
        if svc.get("ports"):
            out.append(f"ports: {name} publishes a port in the default config")
        if set(svc.get("networks") or {}) != {"llm_net"}:
            out.append(f"networks: {name} must be on llm_net only")
        if not _loads_gateways_env(svc):
            out.append(f"env_file: {name} does not load .env.gateways")
        if any(v.get("target") == "/citadel.env" or "docker.sock" in str(v.get("source", "")) for v in svc.get("volumes") or []):
            out.append(f"volumes: {name} mounts /citadel.env or the Docker socket")
        ports = overlay.get("services", {}).get(name, {}).get("ports") or []
        if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1":
            out.append(f"ports: {name} must publish exactly one port on 127.0.0.1 in the admin overlay")
    on_llm = {n for n, s in services.items() if "llm_net" in (s.get("networks") or {})}
    if on_llm != {"legion", *GATEWAYS}:
        out.append("networks: llm_net must be attached to exactly legion and the two gateways, found " + ", ".join(sorted(on_llm)))
    legion = services.get("legion", {})
    if not {"core", "llm_net"} <= set(legion.get("networks") or {}):
        out.append("networks: legion must be on core and llm_net")
    for name, svc in services.items():
        if name in GATEWAYS:
            continue
        if _loads_gateways_env(svc):
            out.append(f"env_file: {name} loads .env.gateways")
        if ".env.gateways" in json.dumps([svc.get("volumes"), svc.get("environment")]):
            out.append(f"volumes: {name} mentions .env.gateways in volumes or environment")
    if set(legion.get("depends_on") or {}) & set(GATEWAYS):
        out.append("depends_on: legion must not depend on a gateway")
    if default.get("networks", {}).get("llm_net", {}).get("internal"):
        out.append("networks: llm_net must not be internal")
    return out


def _good() -> tuple[dict, dict]:
    gw = lambda: {"networks": {"llm_net": None}, "environment": {SENTINEL: "1"}, "volumes": []}
    default = {"services": {"conversation-gateway": gw(), "decision-gateway": gw(),
                            "legion": {"networks": {"core": None, "llm_net": None}, "depends_on": {"armory": {}}},
                            "armory": {"networks": {"core": None}, "environment": {"A": "1"}}},
               "networks": {"core": {}, "llm_net": {"name": "citadel_llm"}}}
    port = {"ports": [{"host_ip": "127.0.0.1", "target": 29407, "published": "29407"}]}
    return default, {"services": {n: copy.deepcopy(port) for n in GATEWAYS}}


def self_test() -> None:
    default, overlay = _good()
    assert check(default, overlay) == []

    def broken(mutate, word, over=False):
        d, o = copy.deepcopy(default), copy.deepcopy(overlay)
        mutate(o if over else d)
        found = check(d, o)
        assert len(found) == 1 and word in found[0], (word, found)

    broken(lambda d: d["services"].pop("decision-gateway"), "missing")
    broken(lambda d: d["services"]["conversation-gateway"].update(ports=["29407:29407"]), "ports")
    broken(lambda d: d["services"]["decision-gateway"]["networks"].update(core=None), "networks")
    broken(lambda d: d["services"]["armory"]["networks"].update(llm_net=None), "llm_net must be attached")
    broken(lambda d: d["services"]["legion"]["networks"].pop("core"), "legion must be on")
    broken(lambda d: d["services"]["armory"]["environment"].update({SENTINEL: "1"}), "env_file")
    broken(lambda d: d["services"]["conversation-gateway"]["volumes"].append({"target": "/citadel.env"}), "volumes")
    broken(lambda d: d["services"]["armory"].update(volumes=[{"source": "/x/.env.gateways"}]), "volumes")
    broken(lambda d: d["services"]["legion"]["depends_on"].update({"decision-gateway": {}}), "depends_on")
    broken(lambda d: d["networks"]["llm_net"].update(internal=True), "internal")
    broken(lambda o: o["services"]["decision-gateway"]["ports"][0].update(host_ip="0.0.0.0"), "admin overlay", over=True)
    print("self-test passed")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        sys.exit(0)
    try:
        problems = check(load(["docker-compose.yml"]), load(ADMIN_OVERLAY))
    except FileNotFoundError:
        print("docker not found; install Docker or use --self-test")
        sys.exit(2)
    except RuntimeError as err:
        print(f"docker compose config failed: {err}")
        sys.exit(2)
    print("\n".join(problems) or "compose invariants hold")
    sys.exit(1 if problems else 0)
