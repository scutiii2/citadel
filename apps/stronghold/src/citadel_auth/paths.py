"""Where a service keeps runtime data and cache: <root>/.data/<service> and <root>/.cache/<service>.

CITADEL_DATA_DIR and CITADEL_CACHE_DIR (process environment, else the Citadel root `.env`) move the
two roots; a relative value is relative to the Citadel root. Outside the apps/<service> layout, such
as in a container, the service's own `.data` and `.cache` folders are used (mount them there)."""

import os
from pathlib import Path

from .rootenv import read_env_file


def _root(project_dir: Path) -> Path | None:
    project = Path(project_dir).resolve()
    return project.parent.parent if project.parent.name == "apps" else None


def _root_env(root: Path, name: str) -> str:
    """One value from the Citadel root `.env`, empty when the file or the key is missing."""
    return read_env_file(root / ".env").get(name, "")


def _folder(project_dir: Path, variable: str, default: str) -> Path:
    project = Path(project_dir).resolve()
    root = _root(project)
    if root is None:
        return project / default
    base = Path(os.environ.get(variable) or _root_env(root, variable) or default)
    return (base if base.is_absolute() else root / base) / project.name


def data_dir(project_dir: Path) -> Path:
    """Runtime data of the service whose folder is `project_dir` (databases, uploads, logs)."""
    return _folder(project_dir, "CITADEL_DATA_DIR", ".data")


def cache_dir(project_dir: Path) -> Path:
    """Files the service can make again (indexes, downloads)."""
    return _folder(project_dir, "CITADEL_CACHE_DIR", ".cache")
