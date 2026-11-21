"""Create the .env files a fresh clone needs before `docker compose up`.

Existing files are never touched. Secrets are generated and never printed.

    python tools/setup_env.py
"""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ["armory", "legion", "treasury", "stronghold", "portcullis"]


def generated(name: str) -> str:
    """The value for a name that must be filled in; empty means the example's own value stays."""
    if name.endswith("_ADMIN_PASSWORD") or name == "BOOTSTRAP_ADMIN_PASSWORD":
        return secrets.token_urlsafe(24)
    return ""


def make(path: Path) -> None:
    example = path.with_name(path.name + ".example")
    if path.exists():
        print(f"kept    {path.relative_to(ROOT)}")
        return
    lines = []
    for line in example.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and not line.startswith("#") and not value.strip():
            value = generated(name)
        lines.append(f"{name}={value}" if sep and not line.startswith("#") else line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o600)
    print(f"created {path.relative_to(ROOT)}")


if __name__ == "__main__":
    make(ROOT / ".env")
    make(ROOT / ".env.gateways")  # provider keys for the two stack gateways; all values stay empty
    for app in APPS:
        make(ROOT / "apps" / app / ".env")
    print("Read the generated passwords from the files; nothing was printed.")
