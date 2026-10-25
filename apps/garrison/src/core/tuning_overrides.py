"""Admin overrides of Garrison's tuning, kept in .data/tuning_overrides.json.

It lives in .data/ (runtime state, the `agent_data` volume in Docker) rather than configs/, because configs/ is
baked into the image and an admin's change there would be lost on every rebuild.

One key so far: `classifier.triage_strategy`, the Laya service strategy the Triage Assistant uses when a request
names none. The file is read on every use, so every agent process sees a change at once and none needs a restart.
An unreadable or invalid file counts as "nothing set" and is logged; the next write replaces it. The write is
atomic (temporary file, then replace) like config_files.seed_tuning."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

OVERRIDES_PATH = Path(__file__).resolve().parent.parent.parent / ".data" / "tuning_overrides.json"

_log = logging.getLogger(__name__)


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _log.warning("%s is unreadable and ignored: %s", path.name, error)
        return {}
    if not isinstance(raw, dict):
        _log.warning("%s must be an object and is ignored", path.name)
        return {}
    return raw


def triage_strategy(path: Path | None = None) -> str | None:
    path = path or OVERRIDES_PATH
    section = _read(path).get("classifier")
    value = section.get("triage_strategy") if isinstance(section, dict) else None
    if value is not None and not (isinstance(value, str) and value.strip()):
        _log.warning("%s: classifier.triage_strategy must be a non-empty string and is ignored", path.name)
        return None
    return value


def set_triage_strategy(value: str | None, path: Path | None = None) -> None:
    path = path or OVERRIDES_PATH
    raw = _read(path)
    section = raw.get("classifier")
    section = dict(section) if isinstance(section, dict) else {}
    if value is None:
        section.pop("triage_strategy", None)
    else:
        section["triage_strategy"] = value
    raw["classifier"] = section
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump(raw, output, indent=2)
            output.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
