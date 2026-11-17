"""Values in the Citadel root `.env` that override a service's own `.env`.

Two forms, both ignored when empty:
- `ARMORY__TAVILY_API_KEY=...` (service name, two underscores) overrides `TAVILY_API_KEY` in Armory only.
- `TAVILY_API_KEY=...` overrides it in every service whose `.env.example` or `.env` lists that name.
The prefixed form wins. Other root variables (gateway admin passwords, CITADEL_*) never reach a service.
The file is `<root>/.env`, or the path in CITADEL_ROOT_ENV (Compose mounts it at /citadel.env)."""

import os
from pathlib import Path


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; comments and blank lines skipped, one pair of quotes removed."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.strip().partition("=")
        if separator and key and not key.startswith("#"):
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[key.strip()] = value
    return values


def _root_file(project: Path) -> Path | None:
    if os.environ.get("CITADEL_ROOT_ENV"):
        return Path(os.environ["CITADEL_ROOT_ENV"])
    return project.parent.parent / ".env" if project.parent.name == "apps" else None


def root_overrides(project_dir: Path) -> dict[str, str]:
    """What the root `.env` sets for the service whose folder is `project_dir`."""
    project = Path(project_dir).resolve()
    source = _root_file(project)
    root = read_env_file(source) if source else {}
    if not root:
        return {}
    service = (os.environ.get("CITADEL_SERVICE") or project.name).upper()
    declared = set(read_env_file(project / ".env.example")) | set(read_env_file(project / ".env"))
    prefix = f"{service}__"
    values = {k: v for k, v in root.items() if v and k in declared}
    values.update({k[len(prefix):]: v for k, v in root.items() if v and k.startswith(prefix) and len(k) > len(prefix)})
    return values


def apply_root_env(project_dir: Path) -> None:
    """Put the overrides into the process environment, so they win over the service's `.env`."""
    os.environ.update(root_overrides(project_dir))
