"""Check the files listed in manifest.json against their recorded SHA-256.

Run from apps/ascension/: python design_references/verify.py
Use --update to record the current hashes (after you accept new edits on purpose).
Exit code 1 if any file changed or is missing.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).resolve().parent / "manifest.json"


def digest(path: Path) -> str:
    """SHA-256 of the file with line endings normalised, so CRLF/LF checkouts agree."""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files: dict[str, str] = manifest["files"]
    if "--update" in sys.argv:
        manifest["files"] = {name: digest(ROOT / name) for name in files}
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"updated {len(files)} hashes")
        return 0
    bad = 0
    for name, expected in files.items():
        path = ROOT / name
        if not path.exists():
            print(f"MISSING  {name}")
            bad += 1
        elif digest(path) != expected:
            print(f"CHANGED  {name}")
            bad += 1
        else:
            print(f"ok       {name}")
    print(f"{bad} of {len(files)} files differ" if bad else "all files match")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
