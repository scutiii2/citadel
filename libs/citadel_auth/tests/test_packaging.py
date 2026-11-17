"""Independent build contexts must share auth code and trust ownership rules."""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ("portcullis", "stronghold", "legion", "armory", "treasury")


def test_sync_replicates_and_detects_drift(tmp_path):
    spec = importlib.util.spec_from_file_location("sync_auth", ROOT / "scripts" / "sync_citadel_auth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "libs" / "citadel_auth" / "citadel_auth"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text('VALUE = "canonical"\n')
    module.synchronize(tmp_path)
    module.synchronize(tmp_path, check=True)
    (tmp_path / "apps/armory/src/citadel_auth/__init__.py").write_text('VALUE = "drift"\n')
    with pytest.raises(SystemExit, match="armory"):
        module.synchronize(tmp_path, check=True)
    module.synchronize(tmp_path)
    module.synchronize(tmp_path, check=True)


def test_compose_trust_mounts_are_owner_writable_only():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for receiver in SERVICES:
        service = compose["services"][receiver]
        mounts = {mount.split(":")[1]: mount.split(":") for mount in service["volumes"]}
        for owner in SERVICES:
            mount = mounts[f"/trust/{owner}"]
            assert mount[0] == f"trust_{owner}"
            assert mount[2] == ("rw" if receiver == owner else "ro")
        assert mounts["/identity"] == [f"identity_{receiver}", "/identity", "rw"]
        assert service["environment"]["CITADEL_SERVICE"] == receiver
        assert service["environment"]["CITADEL_TRUST_DIR"] == "/trust"
        assert service["environment"]["CITADEL_IDENTITY_DIR"] == "/identity"
        for other in SERVICES:
            if receiver != other:
                assert not any(mount[0] == f"identity_{other}" for mount in mounts.values())


def test_compose_bootstraps_services_and_advertises_catalog_addresses():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for name, port in (("armory", 29600), ("stronghold", 29650), ("portcullis", 29601), ("legion", 29603)):
        env = compose["services"][name]["environment"]
        assert env["TREASURY_URL"] == "http://treasury:29602"
        assert env["CITADEL_ADVERTISE_URL"] == f"http://{name}:{port}"
        assert not set(env) & {"DB_GATEWAY_URL", "STRONGHOLD_URL", "PORTCULLIS_URL", "ARMORY_URL", "MCP_SERVER_URL"}
    assert compose["services"]["legion"]["environment"]["AI_AGENT_ADVERTISE_URL"] == "http://legion"
