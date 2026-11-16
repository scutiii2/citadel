"""Docker-context auth must match canonical package byte for byte."""
from pathlib import Path


def test_citadel_auth_in_sync():
    root = Path(__file__).resolve().parents[3]
    source = root / "libs/citadel_auth/citadel_auth"
    copy = Path(__file__).resolve().parents[1] / "src/citadel_auth"
    assert {p.relative_to(source): p.read_bytes() for p in source.rglob("*.py")} == {
        p.relative_to(copy): p.read_bytes() for p in copy.rglob("*.py")}
