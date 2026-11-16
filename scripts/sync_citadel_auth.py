"""Copy canonical authentication package into independent Docker build contexts."""

import argparse
import asyncio
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("portcullis", "stronghold", "legion", "armory", "treasury")


def synchronize(root: Path, check: bool = False) -> None:
    source = root / "libs" / "citadel_auth" / "citadel_auth"
    expected = {path.relative_to(source): path.read_bytes() for path in source.rglob("*.py")}
    for name in SERVICES:
        destination = root / "apps" / name / "src" / "citadel_auth"
        actual = {path.relative_to(destination): path.read_bytes() for path in destination.rglob("*.py")}
        if check:
            if expected != actual:
                raise SystemExit(f"{name}: citadel_auth differs; run uv run scripts/sync_citadel_auth.py")
            continue
        destination.mkdir(parents=True, exist_ok=True)
        for relative in actual.keys() - expected.keys():
            (destination / relative).unlink()
        for relative, content in expected.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if actual.get(relative) != content:
                target.write_bytes(content)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    await asyncio.to_thread(synchronize, ROOT, args.check)


if __name__ == "__main__":
    asyncio.run(main())
