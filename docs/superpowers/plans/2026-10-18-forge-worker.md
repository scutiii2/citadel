# Forge Worker Implementation Plan (plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ember_worker`, the daemon a user runs on their own computer: it connects out to `ember_api`, receives `turn` frames, runs the user's own Claude Code (Agent SDK) or Codex CLI in the requested folder, and streams the result back, relaying tool-permission questions.

**Architecture:** A `WorkerClient` owns the WebSocket (reconnect, heartbeat, dispatch). A `TurnRunner` runs turns as tasks and turns provider events into wire frames. A `Provider` ABC hides each CLI: `ClaudeProvider` (permission relay through the SDK's `can_use_tool`) and `CodexProvider` (mode-only, via `codex exec --json` sandboxes). Everything that touches a real SDK or process sits behind a small protocol so the logic is tested with fakes.

**Tech Stack:** Python 3.11+, asyncio, `websockets` (asyncio client), `claude-agent-sdk`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-18-forge-design.md` (the "Wire protocol (exact)" section is the contract with `ember_api`; plan 1 `2026-10-18-forge-api.md` implements the server side). Plan 3 is `2026-10-18-forge-web.md`.

## Global Constraints

- New project at `apps/Ember/ember_worker/`, shaped like its siblings (root-project-scaffold): `README.md`, `pyproject.toml`, `run.bat`, `shell.bat`, `configs/` (real file gitignored, `.example` committed), `.env` + `.env.example`, `src/`, `tests/`. No other top-level folders. Its own venv `.venv_ember_worker`; it never imports another project.
- Run every command from `apps/Ember/ember_worker/` with `.venv_ember_worker/Scripts/python.exe` (Task 1 creates it).
- Everything is async; no blocking calls on the event loop (subprocesses via `asyncio.create_subprocess_exec`, file reads are tiny). Object-oriented, one responsibility per class, dependencies injected.
- Never log, print or return a pairing token, a CLI login file's contents, or an SDK credential. `status` prints "paired: yes/no" only.
- Wire protocol field names are exactly the spec's. Unknown frame types are ignored. Clip long fields to the server limits: delta text 20,000, tool name 80, summary 500, plan 80, version 40, turn_done text 200,000, error message 2,000.
- Codex cannot relay permission prompts (`codex exec` is non-interactive). Its mode mapping: ask and plan run in the read-only sandbox, accept_edits in `workspace-write`, full_auto in `danger-full-access`. The README and the Forge page (plan 3) say so.
- Claude's Agent SDK use may draw on Anthropic's separate monthly Agent SDK credit instead of the normal plan limit (spec, "Subscription terms and limits"). The README says so.
- Commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Stage only the files a task names; never `git add -A` or `git add .`.
- Do not write anything about reduced motion anywhere.

## File structure

Create (all under `apps/Ember/ember_worker/`):

- `README.md`, `pyproject.toml`, `run.bat`, `shell.bat`, `.gitignore`, `.env.example`, `configs/config_worker.json.example`
- `src/__init__.py` — `__version__`.
- `src/config.py` — `WorkerConfig`, `EnvFile`, `load_config`, `save_pairing`, `ConfigError`.
- `src/events.py` — `HistoryLine`, `TurnRequest`, `TextDelta`, `ToolCall`, `UsageReport`, `Finished`, `Failed`, `TurnEvent`.
- `src/protocol.py` — `ReadyFrame`, `PermissionReply`, `CancelFrame`, `parse_server_frame`, worker frame builders.
- `src/providers/__init__.py`
- `src/providers/base.py` — `Provider`, `PermissionGate`, `CommandRunner`, `SubprocessRunner`, `compose_prompt`, `summarize_tool`, `folder_problem`, `resolve_executable`.
- `src/providers/claude.py` — `ClaudePermissionMapper`, `ClaudeSession`/`ClaudeSessionFactory` protocols, `ClaudeProvider`.
- `src/providers/claude_sdk.py` — `translate_message`, `SdkSession`, `SdkSessionFactory` (the only importer of `claude_agent_sdk`).
- `src/providers/codex.py` — `CodexPermissionMapper`, `CodexEventParser`, `CodexProcess`/`CodexSpawner` protocols, `detect_codex_plan`, `CodexProvider`.
- `src/providers/codex_process.py` — `SubprocessCodexSpawner`.
- `src/providers/registry.py` — `build_provider(name)`.
- `src/runner.py` — `TurnRunner`.
- `src/client.py` — `WorkerClient`, `TokenRejected`.
- `src/run.py` — command line (`pair`, `status`, `run`).
- Tests: `tests/test_config.py`, `test_protocol.py`, `test_provider_base.py`, `test_claude_provider.py`, `test_claude_sdk.py`, `test_codex_provider.py`, `test_runner.py`, `test_client.py`, `test_cli.py`.

---

### Task 1: Project scaffold and configuration

**Files:**
- Create: `README.md`, `pyproject.toml`, `run.bat`, `shell.bat`, `.gitignore`, `.env.example`, `configs/config_worker.json.example`, `src/__init__.py`, `src/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `PROVIDERS = ("claude", "codex")`; `ConfigError`; `token_key(provider) -> str`; `WorkerConfig(url, heartbeat_seconds, plan_override, tokens)` with `.socket_url` and `.paired_providers()`; `EnvFile(path)` with `.read()` and `.set(key, value)`; `load_config(root=ROOT) -> WorkerConfig`; `save_pairing(root, provider, url, token, plan=None)`; `ROOT`.

- [ ] **Step 1: Create the scaffold files**

Create `pyproject.toml`:

```toml
[project]
name = "ember_worker"
description = "Runs your own Claude Code and Codex CLIs for Ember's Forge page"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # The WebSocket client (asyncio implementation, 13+).
    "websockets>=13,<17",
    # Drives your own Claude Code login; its permission callback relays prompts to the Forge page.
    "claude-agent-sdk>=0.1.59",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
ember-worker = "src.run:main"

[tool.setuptools.packages.find]
include = ["src*"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Create `run.bat`:

```bat
@echo off
REM ember_worker launcher. Creates .venv_ember_worker on first run and installs
REM this project into it in editable mode. Arguments are passed through:
REM   run.bat pair <ember_url> <token> --provider claude
REM   run.bat status
REM   run.bat                      (connects every paired worker)
REM
REM LABEL: Ember Worker
REM DESCRIPTION: Connects your own Claude Code and Codex CLIs to Ember's Forge page.
REM LAUNCHER: skip
cd /d "%~dp0"

if not exist ".venv_ember_worker\Scripts\python.exe" (
    echo Creating virtual environment .venv_ember_worker ...
    py -m venv .venv_ember_worker
    call .venv_ember_worker\Scripts\activate
    echo Installing ember_worker in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_ember_worker\Scripts\activate
)

python -m src.run %*
```

Create `shell.bat`:

```bat
@echo off
REM Opens a terminal with .venv_ember_worker active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_ember_worker\Scripts\activate.bat" (
    echo .venv_ember_worker not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_ember_worker\Scripts\activate.bat"
```

Create `.gitignore`:

```
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv_ember_worker/

# Real config and the pairing tokens stay local; only .example twins are committed.
configs/*
!configs/*.example
.env
!.env.example
```

Create `.env.example`:

```
# Written by `run.bat pair`. One pairing token per provider. Never share or commit them.
EMBER_WORKER_TOKEN_CLAUDE=
EMBER_WORKER_TOKEN_CODEX=
```

Create `configs/config_worker.json.example`:

```json
{
  "url": "http://127.0.0.1:8030",
  "heartbeat_seconds": 20,
  "plan_override": {}
}
```

Create `src/__init__.py`:

```python
"""ember_worker: runs your own Claude Code and Codex CLIs for Ember's Forge page."""

__version__ = "0.1.0"
```

Create a first `README.md` (Task 10 completes it):

```markdown
# ember_worker

Connects your own Claude Code and Codex CLIs to Ember's Forge page. It runs on your computer, uses your own CLI logins, and talks to `ember_api` over an outbound WebSocket.

Setup and use are written up in the last task of the plan; see `docs/superpowers/specs/2026-10-18-forge-design.md`.
```

Then create the environment and install:

```bash
cd apps/Ember/ember_worker
py -m venv .venv_ember_worker
.venv_ember_worker/Scripts/python.exe -m pip install -e ".[dev]"
```

Expected: installs `websockets`, `claude-agent-sdk` and `pytest` without error. Then confirm the SDK names this plan relies on:

```bash
.venv_ember_worker/Scripts/python.exe -c "from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ResultMessage, PermissionResultAllow, PermissionResultDeny; from claude_agent_sdk.types import TextBlock, ToolUseBlock; print('sdk ok')"
.venv_ember_worker/Scripts/python.exe -c "from claude_agent_sdk import StreamEvent; print('stream event at top level')"
```

Expected: `sdk ok`. The second command prints either the message or an `ImportError`; `claude_sdk.py` (Task 5) tries the top level first and falls back to `claude_agent_sdk.types`, so either result is fine. If the first command fails, stop and report which name is missing before going on.

- [ ] **Step 2: Write the failing config tests**

Create `tests/test_config.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import ConfigError, EnvFile, WorkerConfig, load_config, save_pairing, token_key

EXAMPLE = {"url": "http://127.0.0.1:8030", "heartbeat_seconds": 20, "plan_override": {}}


def make_root(tmp_path: Path, config: dict | None = EXAMPLE, env: str | None = None) -> Path:
    (tmp_path / "configs").mkdir()
    if config is not None:
        (tmp_path / "configs" / "config_worker.json.example").write_text(json.dumps(config), encoding="utf-8")
    if env is not None:
        (tmp_path / ".env").write_text(env, encoding="utf-8")
    return tmp_path


def test_a_missing_config_is_made_from_its_example_twin(tmp_path: Path) -> None:
    root = make_root(tmp_path)

    config = load_config(root)

    assert (root / "configs" / "config_worker.json").exists()
    assert (config.url, config.heartbeat_seconds, config.plan_override, config.tokens) == (
        "http://127.0.0.1:8030", 20.0, {}, {},
    )


def test_no_config_and_no_example_is_a_clear_error(tmp_path: Path) -> None:
    root = make_root(tmp_path, config=None)

    with pytest.raises(ConfigError, match="config_worker.json"):
        load_config(root)


@pytest.mark.parametrize(
    "url, socket",
    [
        ("http://127.0.0.1:8030", "ws://127.0.0.1:8030/api/forge/worker"),
        ("https://ember.example.com", "wss://ember.example.com/api/forge/worker"),
    ],
)
def test_the_socket_address_follows_the_http_address(url: str, socket: str) -> None:
    assert WorkerConfig(url, 20, {}, {}).socket_url == socket


def test_a_bad_address_is_refused() -> None:
    with pytest.raises(ConfigError, match="http"):
        WorkerConfig("ember.example.com", 20, {}, {}).socket_url


def test_a_trailing_slash_is_dropped_and_bad_values_are_refused(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"url": "https://e.example.com/", "heartbeat_seconds": 5, "plan_override": {"claude": "Max", "bogus": "x", "codex": " "}})

    config = load_config(root)

    assert config.url == "https://e.example.com"
    assert config.plan_override == {"claude": "Max"}  # unknown providers and blanks are dropped

    other = tmp_path / "bad"
    other.mkdir()
    bad = make_root(other, {"url": "", "heartbeat_seconds": 5})
    with pytest.raises(ConfigError, match="url"):
        load_config(bad)


def test_tokens_come_from_dot_env_and_the_environment_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_root(tmp_path, env="# comment\nEMBER_WORKER_TOKEN_CLAUDE=ft_one\nEMBER_WORKER_TOKEN_CODEX=\n")
    config = load_config(root)
    assert config.tokens == {"claude": "ft_one"} and config.paired_providers() == ["claude"]

    monkeypatch.setenv("EMBER_WORKER_TOKEN_CODEX", "ft_two")
    config = load_config(root)
    assert config.paired_providers() == ["claude", "codex"]


def test_env_file_set_keeps_other_lines(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# keep me\nOTHER=1\nEMBER_WORKER_TOKEN_CLAUDE=old\n", encoding="utf-8")

    env = EnvFile(path)
    env.set("EMBER_WORKER_TOKEN_CLAUDE", "new")
    env.set("EMBER_WORKER_TOKEN_CODEX", "added")

    assert path.read_text(encoding="utf-8") == "# keep me\nOTHER=1\nEMBER_WORKER_TOKEN_CLAUDE=new\nEMBER_WORKER_TOKEN_CODEX=added\n"
    assert env.read()["OTHER"] == "1"


def test_save_pairing_writes_the_address_the_plan_and_the_token(tmp_path: Path) -> None:
    root = make_root(tmp_path)

    save_pairing(root, "claude", "https://ember.example.com/", "ft_secret", plan="Max")
    save_pairing(root, "codex", "https://ember.example.com", "ft_other")

    config = load_config(root)
    assert config.url == "https://ember.example.com"
    assert config.plan_override == {"claude": "Max"}
    assert config.tokens == {"claude": "ft_secret", "codex": "ft_other"}
    assert token_key("claude") == "EMBER_WORKER_TOKEN_CLAUDE"
    assert "ft_secret" not in (root / "configs" / "config_worker.json").read_text(encoding="utf-8")
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.config'`.

- [ ] **Step 4: Implement the configuration**

Create `src/config.py`:

```python
"""Worker settings. The Ember address and options live in configs/config_worker.json (a
missing file is made from its .example twin); pairing tokens live in .env, one per provider."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("claude", "codex")
SOCKET_PATH = "/api/forge/worker"
DEFAULT_HEARTBEAT_SECONDS = 20.0


class ConfigError(Exception):
    """Something the user has to fix; the message says what."""


def token_key(provider: str) -> str:
    return f"EMBER_WORKER_TOKEN_{provider.upper()}"


@dataclass(frozen=True)
class WorkerConfig:
    url: str
    heartbeat_seconds: float
    plan_override: dict[str, str]
    tokens: dict[str, str]

    @property
    def socket_url(self) -> str:
        if self.url.startswith("https://"):
            return "wss://" + self.url[len("https://"):] + SOCKET_PATH
        if self.url.startswith("http://"):
            return "ws://" + self.url[len("http://"):] + SOCKET_PATH
        raise ConfigError(f"The Ember address must start with http:// or https:// (it is {self.url!r})")

    def paired_providers(self) -> list[str]:
        return [provider for provider in PROVIDERS if self.tokens.get(provider)]


class EnvFile:
    """A small KEY=VALUE file. Setting one key keeps every other line, comments included."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self._path.exists():
            return values
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    def set(self, key: str, value: str) -> None:
        lines = self._path.read_text(encoding="utf-8").splitlines() if self._path.exists() else []
        for index, line in enumerate(lines):
            if not line.lstrip().startswith("#") and line.partition("=")[0].strip() == key:
                lines[index] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def config_path(root: Path = ROOT) -> Path:
    return root / "configs" / "config_worker.json"


def _read_json(root: Path) -> dict:
    path = config_path(root)
    example = path.with_name(path.name + ".example")
    if not path.exists():
        if not example.exists():
            raise ConfigError(f"{path} is missing and so is its .example twin")
        shutil.copyfile(example, path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ConfigError(f"{path} is not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a JSON object")
    return data


def load_config(root: Path = ROOT) -> WorkerConfig:
    data = _read_json(root)
    url = str(data.get("url", "")).strip().rstrip("/")
    if not url:
        raise ConfigError("config_worker.json needs a url (the address of ember_api)")
    try:
        heartbeat = float(data.get("heartbeat_seconds", DEFAULT_HEARTBEAT_SECONDS))
    except (TypeError, ValueError) as error:
        raise ConfigError("heartbeat_seconds must be a number") from error
    if heartbeat <= 0:
        raise ConfigError("heartbeat_seconds must be above zero")
    overrides = {
        provider: str(value).strip()
        for provider, value in (data.get("plan_override") or {}).items()
        if provider in PROVIDERS and str(value).strip()
    }
    file_values = EnvFile(root / ".env").read()
    tokens = {}
    for provider in PROVIDERS:
        token = os.environ.get(token_key(provider)) or file_values.get(token_key(provider), "")
        if token:
            tokens[provider] = token
    return WorkerConfig(url, heartbeat, overrides, tokens)


def save_pairing(root: Path, provider: str, url: str, token: str, plan: str | None = None) -> None:
    """Remembers the Ember address and plan note in the config, and the token in .env."""
    data = _read_json(root)
    data["url"] = url.strip().rstrip("/")
    overrides = dict(data.get("plan_override") or {})
    if plan and plan.strip():
        overrides[provider] = plan.strip()
    data["plan_override"] = overrides
    config_path(root).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    EnvFile(root / ".env").set(token_key(provider), token)
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 6: Check ignores and commit**

Run: `git check-ignore -v configs/config_worker.json .env` (from `apps/Ember/ember_worker`)
Expected: both listed as ignored. Then:

```bash
git add apps/Ember/ember_worker/README.md apps/Ember/ember_worker/pyproject.toml apps/Ember/ember_worker/run.bat apps/Ember/ember_worker/shell.bat apps/Ember/ember_worker/.gitignore apps/Ember/ember_worker/.env.example apps/Ember/ember_worker/configs/config_worker.json.example apps/Ember/ember_worker/src/__init__.py apps/Ember/ember_worker/src/config.py apps/Ember/ember_worker/tests/test_config.py
git commit -m "feat(ember_worker): project scaffold and configuration

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Events and wire protocol

**Files:**
- Create: `src/events.py`, `src/protocol.py`, `tests/test_protocol.py`

**Interfaces:**
- Produces (events): `HistoryLine(sender, text)`, `TurnRequest(turn_id, group_id, folder, mode, prompt, history: tuple[HistoryLine, ...])`, `TextDelta(text)`, `ToolCall(name, summary)`, `UsageReport(input_tokens, output_tokens)`, `Finished(text)`, `Failed(message)`, alias `TurnEvent`.
- Produces (protocol): `ReadyFrame(worker_id)`, `PermissionReply(request_id, allow)`, `CancelFrame(turn_id)`, alias `ServerFrame = TurnRequest | ReadyFrame | PermissionReply | CancelFrame`; `parse_server_frame(raw) -> ServerFrame | None`; builders `hello_frame(plan, version)`, `heartbeat_frame()`, `delta_frames(turn_id, text) -> list[dict]` (chunks of at most 20,000 characters), `tool_frame(turn_id, name, summary)`, `permission_request_frame(turn_id, request_id, tool, summary)`, `usage_frame(turn_id, input_tokens, output_tokens)`, `turn_done_frame(turn_id, text)`, `turn_error_frame(turn_id, message)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_protocol.py`:

```python
from __future__ import annotations

import json

from src.events import Failed, Finished, HistoryLine, TextDelta, ToolCall, TurnRequest, UsageReport
from src.protocol import (
    CancelFrame,
    PermissionReply,
    ReadyFrame,
    delta_frames,
    heartbeat_frame,
    hello_frame,
    parse_server_frame,
    permission_request_frame,
    tool_frame,
    turn_done_frame,
    turn_error_frame,
    usage_frame,
)


def test_a_turn_frame_becomes_a_request() -> None:
    raw = json.dumps(
        {
            "type": "turn", "turn_id": "t1", "group_id": 3, "folder": "C:/w", "mode": "ask", "prompt": "fix it",
            "history": [{"sender": "user", "text": "hi"}, {"sender": "codex", "text": "yo"}],
        }
    )

    assert parse_server_frame(raw) == TurnRequest(
        turn_id="t1", group_id=3, folder="C:/w", mode="ask", prompt="fix it",
        history=(HistoryLine("user", "hi"), HistoryLine("codex", "yo")),
    )


def test_the_other_server_frames() -> None:
    assert parse_server_frame('{"type": "ready", "worker_id": 4}') == ReadyFrame(4)
    assert parse_server_frame('{"type": "permission_reply", "request_id": "r", "allow": true}') == PermissionReply("r", True)
    assert parse_server_frame('{"type": "permission_reply", "request_id": "r", "allow": false}') == PermissionReply("r", False)
    assert parse_server_frame('{"type": "cancel", "turn_id": "t"}') == CancelFrame("t")


def test_anything_unusable_is_ignored() -> None:
    for raw in ("nope", "[]", '{"type": "dance"}', '{"type": "turn"}', '{"type": "cancel"}',
                '{"type": "permission_reply", "request_id": "r", "allow": "yes"}', '{"type": "ready", "worker_id": "x"}'):
        assert parse_server_frame(raw) is None, raw


def test_worker_frames_match_the_spec() -> None:
    assert hello_frame("Max", "0.1.0") == {"type": "hello", "plan": "Max", "version": "0.1.0"}
    assert hello_frame(None, "0.1.0")["plan"] is None
    assert heartbeat_frame() == {"type": "heartbeat"}
    assert tool_frame("t", "Bash", "npm test") == {"type": "tool", "turn_id": "t", "name": "Bash", "summary": "npm test"}
    assert permission_request_frame("t", "r", "Bash", "rm x") == {
        "type": "permission_request", "turn_id": "t", "request_id": "r", "tool": "Bash", "summary": "rm x",
    }
    assert usage_frame("t", 5, 7) == {"type": "usage", "turn_id": "t", "input_tokens": 5, "output_tokens": 7}
    assert turn_done_frame("t", "ok") == {"type": "turn_done", "turn_id": "t", "text": "ok"}
    assert turn_error_frame("t", "bad") == {"type": "turn_error", "turn_id": "t", "message": "bad"}


def test_long_fields_are_clipped_to_the_server_limits() -> None:
    assert len(hello_frame("p" * 200, "v" * 200)["plan"]) == 80
    assert len(hello_frame("p", "v" * 200)["version"]) == 40
    assert len(tool_frame("t", "n" * 200, "s" * 900)["name"]) == 80
    assert len(tool_frame("t", "n", "s" * 900)["summary"]) == 500
    assert len(permission_request_frame("t", "r", "n" * 200, "s" * 900)["summary"]) == 500
    assert len(turn_error_frame("t", "e" * 5000)["message"]) == 2000
    assert len(turn_done_frame("t", "x" * 300_000)["text"]) == 200_000


def test_deltas_are_split_into_chunks_the_server_accepts() -> None:
    chunks = delta_frames("t", "a" * 45_000)

    assert [len(c["text"]) for c in chunks] == [20_000, 20_000, 5_000]
    assert all(c["type"] == "delta" and c["turn_id"] == "t" for c in chunks)
    assert delta_frames("t", "") == []


def test_events_are_plain_values() -> None:
    assert TextDelta("a") == TextDelta("a")
    assert Finished("x") != Failed("x")
    assert ToolCall("Bash", "ls").name == "Bash" and UsageReport(1, 2).output_tokens == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_protocol.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.events'`.

- [ ] **Step 3: Implement**

Create `src/events.py`:

```python
"""What a turn is made of: the request from Ember, and the events a provider reports back."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HistoryLine:
    sender: str
    text: str


@dataclass(frozen=True)
class TurnRequest:
    turn_id: str
    group_id: int
    folder: str
    mode: str  # ask | accept_edits | plan | full_auto
    prompt: str
    history: tuple[HistoryLine, ...] = ()


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCall:
    name: str
    summary: str


@dataclass(frozen=True)
class UsageReport:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Finished:
    """The turn's final answer. A provider yields exactly one Finished or Failed, last."""

    text: str


@dataclass(frozen=True)
class Failed:
    message: str


TurnEvent = TextDelta | ToolCall | UsageReport | Finished | Failed
```

Create `src/protocol.py`:

```python
"""The frames exchanged with ember_api (spec: Wire protocol). Frames from the server are parsed
into small values; frames for the server are plain dicts, clipped to the server's limits."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.events import HistoryLine, TurnRequest

DELTA_MAX = 20_000
NAME_MAX = 80
SUMMARY_MAX = 500
PLAN_MAX = 80
VERSION_MAX = 40
DONE_MAX = 200_000
ERROR_MAX = 2_000


@dataclass(frozen=True)
class ReadyFrame:
    worker_id: int


@dataclass(frozen=True)
class PermissionReply:
    request_id: str
    allow: bool


@dataclass(frozen=True)
class CancelFrame:
    turn_id: str


ServerFrame = TurnRequest | ReadyFrame | PermissionReply | CancelFrame


def parse_server_frame(raw: str) -> ServerFrame | None:
    """The frame in `raw`, or None for anything malformed or unknown (those are ignored)."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        kind = data.get("type")
        if kind == "ready":
            return ReadyFrame(worker_id=int(data["worker_id"]))
        if kind == "turn":
            history = tuple(HistoryLine(str(line["sender"]), str(line["text"])) for line in data.get("history", []))
            return TurnRequest(
                turn_id=str(data["turn_id"]),
                group_id=int(data["group_id"]),
                folder=str(data["folder"]),
                mode=str(data["mode"]),
                prompt=str(data["prompt"]),
                history=history,
            )
        if kind == "permission_reply":
            if not isinstance(data["allow"], bool):
                return None
            return PermissionReply(request_id=str(data["request_id"]), allow=data["allow"])
        if kind == "cancel":
            return CancelFrame(turn_id=str(data["turn_id"]))
    except (KeyError, TypeError, ValueError):
        return None
    return None


def hello_frame(plan: str | None, version: str) -> dict:
    return {"type": "hello", "plan": plan[:PLAN_MAX] if plan else None, "version": version[:VERSION_MAX]}


def heartbeat_frame() -> dict:
    return {"type": "heartbeat"}


def delta_frames(turn_id: str, text: str) -> list[dict]:
    return [
        {"type": "delta", "turn_id": turn_id, "text": text[start : start + DELTA_MAX]}
        for start in range(0, len(text), DELTA_MAX)
    ]


def tool_frame(turn_id: str, name: str, summary: str) -> dict:
    return {"type": "tool", "turn_id": turn_id, "name": name[:NAME_MAX], "summary": summary[:SUMMARY_MAX]}


def permission_request_frame(turn_id: str, request_id: str, tool: str, summary: str) -> dict:
    return {
        "type": "permission_request",
        "turn_id": turn_id,
        "request_id": request_id,
        "tool": tool[:NAME_MAX],
        "summary": summary[:SUMMARY_MAX],
    }


def usage_frame(turn_id: str, input_tokens: int, output_tokens: int) -> dict:
    return {"type": "usage", "turn_id": turn_id, "input_tokens": input_tokens, "output_tokens": output_tokens}


def turn_done_frame(turn_id: str, text: str) -> dict:
    return {"type": "turn_done", "turn_id": turn_id, "text": text[:DONE_MAX]}


def turn_error_frame(turn_id: str, message: str) -> dict:
    return {"type": "turn_error", "turn_id": turn_id, "message": message[:ERROR_MAX]}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_protocol.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_worker/src/events.py apps/Ember/ember_worker/src/protocol.py apps/Ember/ember_worker/tests/test_protocol.py
git commit -m "feat(ember_worker): turn events and wire protocol frames

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Provider base

**Files:**
- Create: `src/providers/__init__.py`, `src/providers/base.py`, `tests/test_provider_base.py`

**Interfaces:**
- Consumes: `TurnRequest`, `TurnEvent` (Task 2).
- Produces: `PermissionGate` (Protocol: `async ask(tool: str, summary: str) -> bool`); `CommandRunner` (Protocol: `async run(args: list[str]) -> tuple[int, str]`); `SubprocessRunner` (real `CommandRunner`, 15 s timeout; exit code 127 when the program is missing, 124 on timeout); `Provider` (ABC: `name`, `async detect_plan() -> str | None`, `async is_logged_in() -> bool`, `run_turn(request, gate) -> AsyncIterator[TurnEvent]`, `async cancel(turn_id)`); `compose_prompt(request) -> str`; `summarize_tool(name, data, limit=200) -> str`; `folder_problem(folder) -> str | None`; `resolve_executable(name) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_provider_base.py`:

```python
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from src.events import HistoryLine, TurnRequest
from src.providers.base import (
    SubprocessRunner,
    compose_prompt,
    folder_problem,
    resolve_executable,
    summarize_tool,
)


def request(history=(), prompt="do it") -> TurnRequest:
    return TurnRequest("t", 1, "C:/w", "ask", prompt, tuple(history))


def test_a_prompt_with_no_history_is_sent_as_is() -> None:
    assert compose_prompt(request()) == "do it"


def test_history_is_shown_before_the_new_message() -> None:
    text = compose_prompt(request([HistoryLine("user", "plan it"), HistoryLine("claude", "A then B")], "review"))

    assert text.endswith("New message for you:\nreview")
    assert "[user] plan it\n[claude] A then B" in text
    assert text.index("[user]") < text.index("New message")


def test_tool_summaries_prefer_the_meaningful_field() -> None:
    assert summarize_tool("Bash", {"command": "npm test", "timeout": 5}) == "npm test"
    assert summarize_tool("Edit", {"file_path": "a.py", "old_string": "x"}) == "a.py"
    assert summarize_tool("Grep", {"pattern": "foo"}) == "foo"
    assert summarize_tool("Odd", {"n": 1}) == '{"n": 1}'
    assert len(summarize_tool("Bash", {"command": "x" * 900})) == 200
    assert summarize_tool("Odd", {}) == "{}"


def test_a_folder_must_exist(tmp_path: Path) -> None:
    assert folder_problem(str(tmp_path)) is None
    assert folder_problem(str(tmp_path / "missing")) == f"The folder does not exist on this computer: {tmp_path / 'missing'}"
    assert folder_problem("") == "The folder is blank."


def test_resolve_executable_falls_back_to_the_bare_name() -> None:
    assert resolve_executable("definitely-not-installed-xyz") == "definitely-not-installed-xyz"
    assert Path(resolve_executable("python")).name.lower().startswith("python") or resolve_executable("python") == "python"


def test_the_subprocess_runner_returns_exit_code_and_output() -> None:
    runner = SubprocessRunner()

    code, out = asyncio.run(runner.run([sys.executable, "-c", "print('hi')"]))
    assert (code, out.strip()) == (0, "hi")

    code, _out = asyncio.run(runner.run([sys.executable, "-c", "raise SystemExit(3)"]))
    assert code == 3


def test_a_missing_program_is_exit_127() -> None:
    assert asyncio.run(SubprocessRunner().run(["definitely-not-installed-xyz"])) == (127, "")


def test_a_slow_program_is_stopped_with_exit_124() -> None:
    runner = SubprocessRunner(timeout_seconds=0.3)

    code, _out = asyncio.run(runner.run([sys.executable, "-c", "import time; time.sleep(5)"]))

    assert code == 124
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_provider_base.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.providers'`.

- [ ] **Step 3: Implement**

Create `src/providers/__init__.py` containing only `"""The CLIs a worker can drive."""`.

Create `src/providers/base.py`:

```python
"""What every provider shares: the Provider interface, how a turn becomes a prompt, and small
helpers for running the CLIs' own commands."""

from __future__ import annotations

import asyncio
import json
import shutil
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from src.events import TurnEvent, TurnRequest

_SUMMARY_KEYS = ("command", "file_path", "path", "pattern", "url", "query", "description")


class PermissionGate(Protocol):
    """Asks the user (through the Forge page) whether a tool may run."""

    async def ask(self, tool: str, summary: str) -> bool: ...


class CommandRunner(Protocol):
    """Runs a short CLI command (a login or status check) and returns (exit code, stdout)."""

    async def run(self, args: list[str]) -> tuple[int, str]: ...


class SubprocessRunner:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self._timeout = timeout_seconds

    async def run(self, args: list[str]) -> tuple[int, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
        except (FileNotFoundError, PermissionError):
            return 127, ""
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), self._timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return 124, ""
        return process.returncode or 0, stdout.decode("utf-8", errors="replace")


class Provider(ABC):
    """One CLI (Claude Code or Codex) behind a common face."""

    name: str

    @abstractmethod
    async def detect_plan(self) -> str | None:
        """The subscription plan the CLI is logged in with, if it can tell."""

    @abstractmethod
    async def is_logged_in(self) -> bool: ...

    @abstractmethod
    def run_turn(self, request: TurnRequest, gate: PermissionGate) -> AsyncIterator[TurnEvent]:
        """Runs one turn and yields its events; the last is exactly one Finished or Failed."""

    @abstractmethod
    async def cancel(self, turn_id: str) -> None:
        """Asks the turn to stop; run_turn then ends with Failed."""


def compose_prompt(request: TurnRequest) -> str:
    """The message the CLI gets: the new prompt, with what the worker missed shown first."""
    if not request.history:
        return request.prompt
    lines = "\n".join(f"[{line.sender}] {line.text}" for line in request.history)
    return (
        "You are one of several AI workers in a group chat with the user. "
        "Here is what was said since you last took part:\n"
        f"{lines}\n\nNew message for you:\n{request.prompt}"
    )


def summarize_tool(name: str, data: dict, limit: int = 200) -> str:
    """One short line saying what a tool call is about (a command, a file, a pattern)."""
    for key in _SUMMARY_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value[:limit]
    return json.dumps(data, ensure_ascii=False, default=str)[:limit]


def folder_problem(folder: str) -> str | None:
    if not folder.strip():
        return "The folder is blank."
    if not Path(folder).is_dir():
        return f"The folder does not exist on this computer: {folder}"
    return None


def resolve_executable(name: str) -> str:
    """The full path of a program on PATH (Windows needs it for .cmd shims), else the bare name."""
    return shutil.which(name) or name
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_provider_base.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_worker/src/providers/__init__.py apps/Ember/ember_worker/src/providers/base.py apps/Ember/ember_worker/tests/test_provider_base.py
git commit -m "feat(ember_worker): provider interface and shared helpers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Claude provider

**Files:**
- Create: `src/providers/claude.py`, `tests/test_claude_provider.py`

**Interfaces:**
- Consumes: `Provider`, `PermissionGate`, `CommandRunner`, `folder_problem`, `resolve_executable` (Task 3); events.
- Produces: `ClaudePermissionMapper.permission_mode(mode) -> str` (`ask`→`default`, `accept_edits`→`acceptEdits`, `plan`→`plan`, `full_auto`→`bypassPermissions`, anything else→`plan`); `CanUse = Callable[[str, str], Awaitable[bool]]`; `ClaudeSession` Protocol (`events() -> AsyncIterator[TurnEvent]`, `async interrupt()`); `ClaudeSessionFactory` Protocol (`open(request, permission_mode, can_use) -> AsyncContextManager[ClaudeSession]`); `ClaudeProvider(factory, runner, mapper=None, executable="claude")`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_claude_provider.py`:

```python
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest
from src.providers.claude import ClaudePermissionMapper, ClaudeProvider


class FakeRunner:
    def __init__(self, code: int = 0, out: str = "") -> None:
        self.code, self.out, self.calls = code, out, []

    async def run(self, args):
        self.calls.append(args)
        return self.code, self.out


class FakeSession:
    def __init__(self, script) -> None:
        self._script = script
        self.interrupted = False

    async def events(self):
        for item in self._script:
            if callable(item):
                await item()
            else:
                yield item

    async def interrupt(self) -> None:
        self.interrupted = True


class FakeFactory:
    def __init__(self, script=(), fail: Exception | None = None) -> None:
        self.script, self.fail = script, fail
        self.opened = []
        self.session = FakeSession(script)

    @asynccontextmanager
    async def open(self, request, permission_mode, can_use):
        if self.fail:
            raise self.fail
        self.opened.append((request, permission_mode, can_use))
        yield self.session


class Gate:
    def __init__(self, answer: bool = True) -> None:
        self.answer, self.asked = answer, []

    async def ask(self, tool: str, summary: str) -> bool:
        self.asked.append((tool, summary))
        return self.answer


def req(folder: str, mode: str = "ask") -> TurnRequest:
    return TurnRequest("t1", 1, folder, mode, "go")


async def collect(provider, request, gate=None):
    return [event async for event in provider.run_turn(request, gate or Gate())]


def test_modes_map_to_claude_permission_modes() -> None:
    mapper = ClaudePermissionMapper()

    assert [mapper.permission_mode(m) for m in ("ask", "accept_edits", "plan", "full_auto")] == [
        "default", "acceptEdits", "plan", "bypassPermissions",
    ]
    assert mapper.permission_mode("surprise") == "plan"  # unknown modes get the safest one


def test_a_turn_streams_the_sessions_events(tmp_path: Path) -> None:
    factory = FakeFactory([TextDelta("Hi"), ToolCall("Bash", "ls"), Finished("Hi there")])
    provider = ClaudeProvider(factory, FakeRunner())

    events = asyncio.run(collect(provider, req(str(tmp_path), mode="accept_edits")))

    assert events == [TextDelta("Hi"), ToolCall("Bash", "ls"), Finished("Hi there")]
    request, mode, _can_use = factory.opened[0]
    assert (request.turn_id, mode) == ("t1", "acceptEdits")


def test_the_permission_callback_asks_the_gate(tmp_path: Path) -> None:
    factory = FakeFactory([Finished("ok")])
    gate = Gate(answer=False)
    provider = ClaudeProvider(factory, FakeRunner())

    async def go():
        await collect(provider, req(str(tmp_path)), gate)
        _request, _mode, can_use = factory.opened[0]
        return await can_use("Bash", "rm -rf build")

    assert asyncio.run(go()) is False
    assert gate.asked == [("Bash", "rm -rf build")]


def test_a_missing_folder_fails_before_the_cli_starts(tmp_path: Path) -> None:
    factory = FakeFactory([Finished("never")])

    events = asyncio.run(collect(ClaudeProvider(factory, FakeRunner()), req(str(tmp_path / "nope"))))

    assert len(events) == 1 and isinstance(events[0], Failed) and "does not exist" in events[0].message
    assert factory.opened == []


def test_a_cli_crash_becomes_a_failed_event(tmp_path: Path) -> None:
    factory = FakeFactory(fail=RuntimeError("CLI exited with code 1"))

    events = asyncio.run(collect(ClaudeProvider(factory, FakeRunner()), req(str(tmp_path))))

    assert events == [Failed("Claude failed: CLI exited with code 1")]


def test_cancel_interrupts_the_running_session(tmp_path: Path) -> None:
    provider = ClaudeProvider(FakeFactory(), FakeRunner())

    async def go():
        release = asyncio.Event()

        async def wait_for_release():
            await release.wait()

        provider._factory.session = FakeSession([wait_for_release, Finished("late")])
        task = asyncio.create_task(collect(provider, req(str(tmp_path))))
        for _ in range(100):
            if "t1" in provider._sessions:
                break
            await asyncio.sleep(0.01)
        await provider.cancel("t1")
        interrupted = provider._sessions["t1"].interrupted
        release.set()
        await task
        return interrupted, "t1" in provider._sessions

    assert asyncio.run(go()) == (True, False)  # interrupted, and forgotten once the turn ended


def test_cancelling_an_unknown_turn_does_nothing() -> None:
    asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner()).cancel("nope"))


def test_login_and_plan_come_from_claude_auth_status() -> None:
    status = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"})
    runner = FakeRunner(0, status)
    provider = ClaudeProvider(FakeFactory(), runner, executable="claude")

    assert asyncio.run(provider.is_logged_in()) is True
    assert asyncio.run(provider.detect_plan()) == "max"
    assert runner.calls[0] == ["claude", "auth", "status"]


def test_logged_out_missing_or_unreadable_status() -> None:
    out = json.dumps({"loggedIn": False, "authMethod": "none"})
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(1, out)).is_logged_in()) is False
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(1, out)).detect_plan()) is None
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(127, "")).is_logged_in()) is False
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(0, "not json")).detect_plan()) is None
    odd = json.dumps({"loggedIn": True, "subscriptionType": 5})
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(0, odd)).detect_plan()) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_claude_provider.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.providers.claude'`.

- [ ] **Step 3: Implement**

Create `src/providers/claude.py`:

```python
"""Claude Code behind the Provider interface. The Agent SDK itself sits behind
ClaudeSessionFactory (see claude_sdk.py), so everything here is tested with fakes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from src.events import Failed, TurnEvent, TurnRequest
from src.providers.base import CommandRunner, PermissionGate, Provider, folder_problem, resolve_executable

CanUse = Callable[[str, str], Awaitable[bool]]


class ClaudePermissionMapper:
    """Forge's group modes as Claude Code permission modes."""

    _MODES = {"ask": "default", "accept_edits": "acceptEdits", "plan": "plan", "full_auto": "bypassPermissions"}

    def permission_mode(self, mode: str) -> str:
        return self._MODES.get(mode, "plan")


class ClaudeSession(Protocol):
    """One turn's conversation with the Claude CLI."""

    def events(self) -> AsyncIterator[TurnEvent]: ...

    async def interrupt(self) -> None: ...


class ClaudeSessionFactory(Protocol):
    def open(
        self, request: TurnRequest, permission_mode: str, can_use: CanUse
    ) -> AbstractAsyncContextManager[ClaudeSession]: ...


class ClaudeProvider(Provider):
    name = "claude"

    def __init__(
        self,
        factory: ClaudeSessionFactory,
        runner: CommandRunner,
        mapper: ClaudePermissionMapper | None = None,
        executable: str | None = None,
    ) -> None:
        self._factory = factory
        self._runner = runner
        self._mapper = mapper or ClaudePermissionMapper()
        self._executable = executable or resolve_executable("claude")
        self._sessions: dict[str, ClaudeSession] = {}

    async def is_logged_in(self) -> bool:
        return bool((await self._auth_status()).get("loggedIn"))

    async def detect_plan(self) -> str | None:
        plan = (await self._auth_status()).get("subscriptionType")
        return plan if isinstance(plan, str) and plan.strip() else None

    async def _auth_status(self) -> dict:
        _code, out = await self._runner.run([self._executable, "auth", "status"])
        try:
            data = json.loads(out)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    async def run_turn(self, request: TurnRequest, gate: PermissionGate) -> AsyncIterator[TurnEvent]:
        problem = folder_problem(request.folder)
        if problem is not None:
            yield Failed(problem)
            return

        async def can_use(tool: str, summary: str) -> bool:
            return await gate.ask(tool, summary)

        try:
            async with self._factory.open(request, self._mapper.permission_mode(request.mode), can_use) as session:
                self._sessions[request.turn_id] = session
                async for event in session.events():
                    yield event
        except Exception as error:
            yield Failed(f"Claude failed: {error}")
        finally:
            self._sessions.pop(request.turn_id, None)

    async def cancel(self, turn_id: str) -> None:
        session = self._sessions.get(turn_id)
        if session is not None:
            await session.interrupt()
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_claude_provider.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_worker/src/providers/claude.py apps/Ember/ember_worker/tests/test_claude_provider.py
git commit -m "feat(ember_worker): Claude provider with permission mapping and cancel

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Claude Agent SDK adapter

**Files:**
- Create: `src/providers/claude_sdk.py`, `tests/test_claude_sdk.py`

**Interfaces:**
- Consumes: `compose_prompt`, `summarize_tool`, events.
- Produces: `translate_message(message) -> list[TurnEvent]` (pure); `SdkSession(client, prompt)`; `SdkSessionFactory` with `open(request, permission_mode, can_use)` (an async context manager yielding an `SdkSession`).

Behavior of `translate_message`: a `StreamEvent` carrying a `content_block_delta` with a `text_delta` gives `TextDelta`; an `AssistantMessage` (from the main agent, `parent_tool_use_id is None`) gives one `ToolCall` per `ToolUseBlock`; a `ResultMessage` gives a `UsageReport` (when it has usage) then `Finished(result or "")` or, when `is_error`, `Failed(result or "The turn ended with <subtype>.")`; anything else gives `[]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_claude_sdk.py`:

```python
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import AssistantMessage, PermissionResultAllow, PermissionResultDeny, ResultMessage  # noqa: E402
from claude_agent_sdk.types import TextBlock, ToolUseBlock  # noqa: E402

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport  # noqa: E402
from src.providers.claude_sdk import SdkSession, SdkSessionFactory, translate_message  # noqa: E402

try:
    from claude_agent_sdk import StreamEvent
except ImportError:  # older layout
    from claude_agent_sdk.types import StreamEvent


def result(**overrides) -> ResultMessage:
    fields = dict(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s",
        result="All done", usage={"input_tokens": 11, "output_tokens": 22},
    )
    return ResultMessage(**{**fields, **overrides})


def test_text_deltas_come_from_stream_events() -> None:
    event = StreamEvent(
        uuid="u", session_id="s",
        event={"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
    )

    assert translate_message(event) == [TextDelta("Hel")]


def test_other_stream_events_are_ignored() -> None:
    for inner in (
        {"type": "message_start"},
        {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}},
        {"type": "content_block_delta"},
    ):
        assert translate_message(StreamEvent(uuid="u", session_id="s", event=inner)) == []


def test_tool_use_blocks_become_tool_calls_and_text_blocks_are_not_repeated() -> None:
    message = AssistantMessage(
        content=[TextBlock(text="Running tests"), ToolUseBlock(id="1", name="Bash", input={"command": "npm test"})],
        model="m",
    )

    assert translate_message(message) == [ToolCall("Bash", "npm test")]


def test_a_subagents_messages_are_skipped() -> None:
    message = AssistantMessage(
        content=[ToolUseBlock(id="1", name="Bash", input={"command": "ls"})], model="m", parent_tool_use_id="parent"
    )

    assert translate_message(message) == []


def test_a_successful_result_reports_usage_then_the_answer() -> None:
    assert translate_message(result()) == [UsageReport(11, 22), Finished("All done")]


def test_a_result_without_usage_or_text() -> None:
    assert translate_message(result(usage=None, result=None)) == [Finished("")]


def test_an_error_result_fails_the_turn() -> None:
    assert translate_message(result(is_error=True, subtype="error_during_execution", result=None, usage=None)) == [
        Failed("The turn ended with error_during_execution.")
    ]
    assert translate_message(result(is_error=True, result="Credit balance too low", usage=None)) == [
        Failed("Credit balance too low")
    ]


def test_unknown_messages_are_ignored() -> None:
    assert translate_message(object()) == []
    assert translate_message("text") == []


class FakeClient:
    def __init__(self, messages) -> None:
        self.messages, self.queries, self.interrupted = messages, [], False

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_response(self):
        for message in self.messages:
            yield message

    async def interrupt(self) -> None:
        self.interrupted = True


def test_a_session_sends_the_prompt_and_translates_the_reply() -> None:
    client = FakeClient([result()])
    session = SdkSession(client, "hello")

    async def go():
        events = [event async for event in session.events()]
        await session.interrupt()
        return events

    assert asyncio.run(go()) == [UsageReport(11, 22), Finished("All done")]
    assert client.queries == ["hello"] and client.interrupted is True


def test_the_permission_callback_adapter_allows_and_denies() -> None:
    request = TurnRequest("t", 1, ".", "ask", "go")
    seen = []

    async def allow_bash(tool: str, summary: str) -> bool:
        seen.append((tool, summary))
        return tool == "Bash"

    callback = SdkSessionFactory().permission_callback(request, allow_bash)

    allowed = asyncio.run(callback("Bash", {"command": "ls"}, object()))
    denied = asyncio.run(callback("Write", {"file_path": "a.py"}, object()))

    assert isinstance(allowed, PermissionResultAllow) and allowed.updated_input == {"command": "ls"}
    assert isinstance(denied, PermissionResultDeny) and denied.message and denied.interrupt is False
    assert seen == [("Bash", "ls"), ("Write", "a.py")]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_claude_sdk.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.providers.claude_sdk'`.

- [ ] **Step 3: Implement**

Create `src/providers/claude_sdk.py`:

```python
"""The only module that imports claude_agent_sdk. It turns the SDK's messages into TurnEvents
and builds one client per turn; ClaudeProvider (claude.py) knows nothing about the SDK."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
)
from claude_agent_sdk.types import ToolUseBlock

try:
    from claude_agent_sdk import StreamEvent
except ImportError:  # older SDK layouts keep it in types
    from claude_agent_sdk.types import StreamEvent

from src.events import Failed, Finished, TextDelta, ToolCall, TurnEvent, TurnRequest, UsageReport
from src.providers.base import compose_prompt, summarize_tool
from src.providers.claude import CanUse

DECLINED = "The user declined this in Ember."


def translate_message(message: Any) -> list[TurnEvent]:
    """The events one SDK message stands for (usually none)."""
    if isinstance(message, StreamEvent):
        inner = message.event if isinstance(message.event, dict) else {}
        if inner.get("type") == "content_block_delta":
            delta = inner.get("delta") or {}
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                return [TextDelta(delta["text"])]
        return []
    if isinstance(message, AssistantMessage):
        if message.parent_tool_use_id is not None:
            return []
        return [
            ToolCall(block.name, summarize_tool(block.name, block.input))
            for block in message.content
            if isinstance(block, ToolUseBlock)
        ]
    if isinstance(message, ResultMessage):
        events: list[TurnEvent] = []
        usage = message.usage or {}
        if usage:
            events.append(UsageReport(int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)))
        if message.is_error:
            events.append(Failed(message.result or f"The turn ended with {message.subtype}."))
        else:
            events.append(Finished(message.result or ""))
        return events
    return []


class SdkSession:
    """One turn on a connected SDK client."""

    def __init__(self, client: Any, prompt: str) -> None:
        self._client = client
        self._prompt = prompt

    async def events(self) -> AsyncIterator[TurnEvent]:
        await self._client.query(self._prompt)
        async for message in self._client.receive_response():
            for event in translate_message(message):
                yield event

    async def interrupt(self) -> None:
        await self._client.interrupt()


class SdkSessionFactory:
    def permission_callback(self, request: TurnRequest, can_use: CanUse):
        """The SDK's can_use_tool callback, answering through `can_use` (the Forge page)."""

        async def callback(tool_name: str, input_data: dict, _context: Any):
            if await can_use(tool_name, summarize_tool(tool_name, input_data)):
                return PermissionResultAllow(updated_input=input_data)
            return PermissionResultDeny(message=DECLINED, interrupt=False)

        return callback

    @asynccontextmanager
    async def open(self, request: TurnRequest, permission_mode: str, can_use: CanUse):
        options = ClaudeAgentOptions(
            cwd=request.folder,
            permission_mode=permission_mode,
            include_partial_messages=True,
            can_use_tool=self.permission_callback(request, can_use),
        )
        async with ClaudeSDKClient(options=options) as client:
            yield SdkSession(client, compose_prompt(request))
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_claude_sdk.py -q`
Expected: PASS. If constructing an SDK dataclass fails with an unexpected keyword (the SDK's fields changed), adjust only the test's constructor arguments to the installed version (`python -c "import inspect, claude_agent_sdk as s; print(inspect.signature(s.ResultMessage))"`); the production code reads only the attributes named in the interface paragraph above.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_worker/src/providers/claude_sdk.py apps/Ember/ember_worker/tests/test_claude_sdk.py
git commit -m "feat(ember_worker): Claude Agent SDK adapter

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Codex provider

**Files:**
- Create: `src/providers/codex.py`, `src/providers/codex_process.py`, `tests/test_codex_provider.py`

**Interfaces:**
- Consumes: `Provider`, `CommandRunner`, `compose_prompt`, `folder_problem`, `summarize_tool`, `resolve_executable`; events.
- Produces: `CodexPermissionMapper.sandbox(mode) -> str` (`ask`→`read-only`, `plan`→`read-only`, `accept_edits`→`workspace-write`, `full_auto`→`danger-full-access`, anything else→`read-only`); `CodexEventParser` with `feed(line: str) -> list[TurnEvent]` and attribute `last_error: str | None`; `CodexProcess` Protocol (`lines() -> AsyncIterator[str]`, `async wait() -> int`, `async stderr_text() -> str`, `terminate()`); `CodexSpawner` Protocol (`async spawn(args, cwd, stdin_text) -> CodexProcess`); `detect_codex_plan(auth_path: Path) -> str | None`; `CodexProvider(spawner, runner, mapper=None, codex_home=None, executable=None)`; in `codex_process.py`, `SubprocessCodexSpawner`.

Parser contract (from the Codex `exec --json` event stream): `item.completed` with an `agent_message` item gives `TextDelta(text)` and remembers it as the last message; `command_execution` gives `ToolCall("shell", command)`; `file_change` gives `ToolCall("edit", paths joined by ", ")` (paths read from `changes[].path`, or `path`); other item types with a `type` give `ToolCall(type, "")` only for `mcp_tool_call` and `web_search`; `turn.completed` gives `UsageReport(input_tokens, output_tokens)` when `usage` is present, then `Finished(last agent message or "")`; `turn.failed` gives `Failed(error.message or "Codex failed.")`; an `error` event only records `last_error`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_codex_provider.py`:

```python
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport
from src.providers.codex import CodexEventParser, CodexPermissionMapper, CodexProvider, detect_codex_plan


def line(**event) -> str:
    return json.dumps(event)


def test_modes_map_to_codex_sandboxes() -> None:
    mapper = CodexPermissionMapper()

    assert [mapper.sandbox(m) for m in ("ask", "plan", "accept_edits", "full_auto")] == [
        "read-only", "read-only", "workspace-write", "danger-full-access",
    ]
    assert mapper.sandbox("surprise") == "read-only"


def test_the_parser_turns_a_normal_run_into_events() -> None:
    parser = CodexEventParser()
    stream = [
        line(type="thread.started", thread_id="abc"),
        line(type="turn.started"),
        line(type="item.completed", item={"id": "1", "type": "command_execution", "command": "npm test", "status": "completed"}),
        line(type="item.completed", item={"id": "2", "type": "file_change", "changes": [{"path": "a.py", "kind": "update"}, {"path": "b.py", "kind": "add"}]}),
        line(type="item.completed", item={"id": "3", "type": "agent_message", "text": "Fixed it."}),
        line(type="turn.completed", usage={"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 5, "reasoning_output_tokens": 1}),
    ]

    events = [event for raw in stream for event in parser.feed(raw)]

    assert events == [
        ToolCall("shell", "npm test"),
        ToolCall("edit", "a.py, b.py"),
        TextDelta("Fixed it."),
        UsageReport(10, 5),
        Finished("Fixed it."),
    ]


def test_the_final_answer_is_the_last_agent_message() -> None:
    parser = CodexEventParser()
    for text in ("first", "second"):
        parser.feed(line(type="item.completed", item={"type": "agent_message", "text": text}))

    assert parser.feed(line(type="turn.completed")) == [Finished("second")]


def test_failures_and_errors() -> None:
    parser = CodexEventParser()

    assert parser.feed(line(type="error", message="Reconnecting 1/5")) == []
    assert parser.last_error == "Reconnecting 1/5"
    assert parser.feed(line(type="turn.failed", error={"message": "You hit your usage limit"})) == [
        Failed("You hit your usage limit")
    ]
    assert parser.feed(line(type="turn.failed")) == [Failed("Codex failed.")]


def test_noise_is_ignored() -> None:
    parser = CodexEventParser()

    for raw in ("", "not json", "[]", line(type="item.started", item={"type": "agent_message"}), line(type="mystery"),
                line(type="item.completed", item={"type": "reasoning", "text": "hmm"}), line(type="item.completed")):
        assert parser.feed(raw) == [], raw


def test_other_tool_like_items_are_named() -> None:
    parser = CodexEventParser()

    assert parser.feed(line(type="item.completed", item={"type": "web_search", "query": "python asyncio"})) == [
        ToolCall("web_search", "python asyncio")
    ]
    assert parser.feed(line(type="item.completed", item={"type": "mcp_tool_call", "tool": "read_page"})) == [
        ToolCall("mcp_tool_call", "read_page")
    ]


class FakeProcess:
    def __init__(self, lines, code=0, stderr="") -> None:
        self._lines, self._code, self._stderr = lines, code, stderr
        self.terminated = False
        self.release = None

    async def lines(self):
        for item in self._lines:
            if item is None:  # wait here until released (a long-running turn)
                self.release = asyncio.Event()
                await self.release.wait()
                continue
            yield item

    async def wait(self) -> int:
        return self._code

    async def stderr_text(self) -> str:
        return self._stderr

    def terminate(self) -> None:
        self.terminated = True
        if self.release is not None:
            self.release.set()


class FakeSpawner:
    def __init__(self, process) -> None:
        self.process, self.calls = process, []

    async def spawn(self, args, cwd, stdin_text):
        self.calls.append((args, cwd, stdin_text))
        return self.process


class FakeRunner:
    def __init__(self, code: int = 0) -> None:
        self.code, self.calls = code, []

    async def run(self, args):
        self.calls.append(args)
        return self.code, ""


class Gate:
    async def ask(self, tool, summary):
        raise AssertionError("Codex cannot ask")


def request(folder: str, mode: str = "accept_edits") -> TurnRequest:
    return TurnRequest("t1", 1, folder, mode, "go")


async def collect(provider, req):
    return [event async for event in provider.run_turn(req, Gate())]


def test_a_turn_runs_codex_exec_in_the_folder(tmp_path: Path) -> None:
    process = FakeProcess([
        line(type="item.completed", item={"type": "agent_message", "text": "Done"}),
        line(type="turn.completed", usage={"input_tokens": 1, "output_tokens": 2}),
    ])
    spawner = FakeSpawner(process)
    provider = CodexProvider(spawner, FakeRunner(), executable="codex")

    events = asyncio.run(collect(provider, request(str(tmp_path))))

    assert events == [TextDelta("Done"), UsageReport(1, 2), Finished("Done")]
    args, cwd, stdin_text = spawner.calls[0]
    assert args == ["codex", "exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", "-"]
    assert (cwd, stdin_text) == (str(tmp_path), "go")
    assert process.terminated is True  # always cleaned up


def test_a_missing_folder_fails_before_codex_starts(tmp_path: Path) -> None:
    spawner = FakeSpawner(FakeProcess([]))

    events = asyncio.run(collect(CodexProvider(spawner, FakeRunner()), request(str(tmp_path / "nope"))))

    assert len(events) == 1 and isinstance(events[0], Failed)
    assert spawner.calls == []


def test_codex_not_installed(tmp_path: Path) -> None:
    class Missing:
        async def spawn(self, args, cwd, stdin_text):
            raise FileNotFoundError("codex")

    events = asyncio.run(collect(CodexProvider(Missing(), FakeRunner()), request(str(tmp_path))))

    assert len(events) == 1 and "Could not start Codex" in events[0].message


def test_a_run_that_ends_without_an_answer_reports_why(tmp_path: Path) -> None:
    errored = FakeProcess([line(type="error", message="Not logged in")], code=1)
    silent = FakeProcess([], code=2, stderr="boom\n")
    bare = FakeProcess([], code=3)

    one = asyncio.run(collect(CodexProvider(FakeSpawner(errored), FakeRunner()), request(str(tmp_path))))
    two = asyncio.run(collect(CodexProvider(FakeSpawner(silent), FakeRunner()), request(str(tmp_path))))
    three = asyncio.run(collect(CodexProvider(FakeSpawner(bare), FakeRunner()), request(str(tmp_path))))

    assert one == [Failed("Not logged in")]
    assert two == [Failed("boom")]
    assert three == [Failed("Codex exited with code 3")]


def test_cancel_stops_the_process_and_the_turn_reports_it(tmp_path: Path) -> None:
    process = FakeProcess([None])  # runs until terminated
    provider = CodexProvider(FakeSpawner(process), FakeRunner())

    async def go():
        task = asyncio.create_task(collect(provider, request(str(tmp_path))))
        for _ in range(100):
            if "t1" in provider._processes:
                break
            await asyncio.sleep(0.01)
        await provider.cancel("t1")
        return await task

    assert asyncio.run(go()) == [Failed("cancelled")]
    assert process.terminated is True


def test_login_status_uses_the_exit_code() -> None:
    runner = FakeRunner(0)
    assert asyncio.run(CodexProvider(FakeSpawner(None), runner, executable="codex").is_logged_in()) is True
    assert runner.calls == [["codex", "login", "status"]]
    assert asyncio.run(CodexProvider(FakeSpawner(None), FakeRunner(1)).is_logged_in()) is False
    assert asyncio.run(CodexProvider(FakeSpawner(None), FakeRunner(127)).is_logged_in()) is False


def fake_jwt(claims: dict) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part(claims)}.sig"


def test_the_plan_is_read_from_the_id_token_claims(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps({"tokens": {"id_token": fake_jwt({"https://api.openai.com/auth": {"chatgpt_plan_type": "plus"}})}}),
        encoding="utf-8",
    )

    assert detect_codex_plan(auth) == "plus"
    assert asyncio.run(CodexProvider(FakeSpawner(None), FakeRunner(), codex_home=tmp_path).detect_plan()) == "plus"


def test_plan_detection_never_raises(tmp_path: Path) -> None:
    assert detect_codex_plan(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert detect_codex_plan(bad) is None
    for tokens in ({}, {"id_token": "nodots"}, {"id_token": "a.b.c"}, {"id_token": fake_jwt({"x": 1})},
                   {"id_token": fake_jwt({"https://api.openai.com/auth": {"chatgpt_plan_type": 5}})}):
        path = tmp_path / "t.json"
        path.write_text(json.dumps({"tokens": tokens}), encoding="utf-8")
        assert detect_codex_plan(path) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_codex_provider.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.providers.codex'`.

- [ ] **Step 3: Implement the provider**

Create `src/providers/codex.py`:

```python
"""Codex behind the Provider interface, using `codex exec --json`. That mode is
non-interactive, so Codex cannot ask the user: the group mode picks the sandbox up front."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from src.events import Failed, Finished, TextDelta, ToolCall, TurnEvent, TurnRequest, UsageReport
from src.providers.base import (
    CommandRunner,
    PermissionGate,
    Provider,
    compose_prompt,
    folder_problem,
    resolve_executable,
)

_AUTH_CLAIM = "https://api.openai.com/auth"


class CodexPermissionMapper:
    """Forge's group modes as Codex sandboxes (read-only is also what Ask and Plan get)."""

    _SANDBOXES = {
        "ask": "read-only",
        "plan": "read-only",
        "accept_edits": "workspace-write",
        "full_auto": "danger-full-access",
    }

    def sandbox(self, mode: str) -> str:
        return self._SANDBOXES.get(mode, "read-only")


class CodexEventParser:
    """Reads the JSON lines `codex exec --json` prints, one at a time."""

    def __init__(self) -> None:
        self._last_message = ""
        self.last_error: str | None = None

    def feed(self, raw: str) -> list[TurnEvent]:
        try:
            event = json.loads(raw)
        except ValueError:
            return []
        if not isinstance(event, dict):
            return []
        kind = event.get("type")
        if kind == "item.completed":
            return self._item(event.get("item"))
        if kind == "turn.completed":
            events: list[TurnEvent] = []
            usage = event.get("usage")
            if isinstance(usage, dict):
                events.append(UsageReport(int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)))
            events.append(Finished(self._last_message))
            return events
        if kind == "turn.failed":
            error = event.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            return [Failed(message if isinstance(message, str) and message else "Codex failed.")]
        if kind == "error":
            message = event.get("message")
            if isinstance(message, str) and message:
                self.last_error = message
        return []

    def _item(self, item: object) -> list[TurnEvent]:
        if not isinstance(item, dict):
            return []
        kind = item.get("type")
        if kind == "agent_message" and isinstance(item.get("text"), str):
            self._last_message = item["text"]
            return [TextDelta(item["text"])]
        if kind == "command_execution":
            return [ToolCall("shell", str(item.get("command", "")))]
        if kind == "file_change":
            changes = item.get("changes")
            paths = [c.get("path") for c in changes if isinstance(c, dict)] if isinstance(changes, list) else []
            if not paths and isinstance(item.get("path"), str):
                paths = [item["path"]]
            return [ToolCall("edit", ", ".join(p for p in paths if isinstance(p, str)))]
        if kind in ("mcp_tool_call", "web_search"):
            detail = item.get("query") or item.get("tool") or ""
            return [ToolCall(kind, str(detail))]
        return []


class CodexProcess(Protocol):
    def lines(self) -> AsyncIterator[str]: ...

    async def wait(self) -> int: ...

    async def stderr_text(self) -> str: ...

    def terminate(self) -> None: ...


class CodexSpawner(Protocol):
    async def spawn(self, args: list[str], cwd: str, stdin_text: str) -> CodexProcess: ...


def detect_codex_plan(auth_path: Path) -> str | None:
    """The ChatGPT plan named in the logged-in user's id token, read from the file on this computer.
    Best effort: any problem gives None. The token is decoded in memory and never kept or printed."""
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
        token = data["tokens"]["id_token"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        plan = claims[_AUTH_CLAIM]["chatgpt_plan_type"]
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None
    return plan if isinstance(plan, str) and plan.strip() else None


class CodexProvider(Provider):
    name = "codex"

    def __init__(
        self,
        spawner: CodexSpawner,
        runner: CommandRunner,
        mapper: CodexPermissionMapper | None = None,
        codex_home: Path | None = None,
        executable: str | None = None,
    ) -> None:
        self._spawner = spawner
        self._runner = runner
        self._mapper = mapper or CodexPermissionMapper()
        self._codex_home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        self._executable = executable or resolve_executable("codex")
        self._processes: dict[str, CodexProcess] = {}
        self._cancelled: set[str] = set()

    async def is_logged_in(self) -> bool:
        code, _out = await self._runner.run([self._executable, "login", "status"])
        return code == 0

    async def detect_plan(self) -> str | None:
        return detect_codex_plan(self._codex_home / "auth.json")

    async def run_turn(self, request: TurnRequest, gate: PermissionGate) -> AsyncIterator[TurnEvent]:
        problem = folder_problem(request.folder)
        if problem is not None:
            yield Failed(problem)
            return
        args = [
            self._executable, "exec", "--json", "--sandbox", self._mapper.sandbox(request.mode),
            "--skip-git-repo-check", "-",
        ]
        try:
            process = await self._spawner.spawn(args, request.folder, compose_prompt(request))
        except OSError as error:
            yield Failed(f"Could not start Codex ({error}). Is the codex CLI installed?")
            return
        self._processes[request.turn_id] = process
        parser = CodexEventParser()
        terminal = False
        try:
            async for raw in process.lines():
                for event in parser.feed(raw):
                    terminal = terminal or isinstance(event, (Finished, Failed))
                    yield event
            code = await process.wait()
            if not terminal:
                if request.turn_id in self._cancelled:
                    yield Failed("cancelled")
                else:
                    detail = parser.last_error or (await process.stderr_text()).strip()[-500:]
                    yield Failed(detail or f"Codex exited with code {code}")
        finally:
            self._processes.pop(request.turn_id, None)
            self._cancelled.discard(request.turn_id)
            process.terminate()

    async def cancel(self, turn_id: str) -> None:
        process = self._processes.get(turn_id)
        if process is not None:
            self._cancelled.add(turn_id)
            process.terminate()
```

Note on `finally`: when a turn ends normally the process has already exited, so `terminate()` must be a harmless no-op then (the real spawner guarantees this in Step 4).

- [ ] **Step 4: Implement the subprocess spawner**

Create `src/providers/codex_process.py`:

```python
"""The real process behind CodexProvider: `codex exec` as an asyncio subprocess."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from src.providers.codex import CodexProcess


class _SubprocessCodexProcess:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        # stderr is read as it arrives, so a chatty CLI can never block on a full pipe.
        self._stderr = asyncio.create_task(process.stderr.read())

    async def lines(self) -> AsyncIterator[str]:
        async for raw in self._process.stdout:
            yield raw.decode("utf-8", errors="replace").rstrip("\r\n")

    async def wait(self) -> int:
        return await self._process.wait()

    async def stderr_text(self) -> str:
        try:
            return (await self._stderr).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def terminate(self) -> None:
        if self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass


class SubprocessCodexSpawner:
    async def spawn(self, args: list[str], cwd: str, stdin_text: str) -> CodexProcess:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        process.stdin.write(stdin_text.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()
        return _SubprocessCodexProcess(process)
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_codex_provider.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/Ember/ember_worker/src/providers/codex.py apps/Ember/ember_worker/src/providers/codex_process.py apps/Ember/ember_worker/tests/test_codex_provider.py
git commit -m "feat(ember_worker): Codex provider over codex exec --json

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Provider registry and turn runner

**Files:**
- Create: `src/providers/registry.py`, `src/runner.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `Provider`, events, protocol builders.
- Produces: `build_provider(name: str) -> Provider` (`"claude"` → `ClaudeProvider(SdkSessionFactory(), SubprocessRunner())`, `"codex"` → `CodexProvider(SubprocessCodexSpawner(), SubprocessRunner())`; anything else raises `ValueError`); `TurnRunner(provider, send, cancel_grace=5.0)` where `send` is `Callable[[dict], Awaitable[None]]`, with `start(request)`, `permission_reply(request_id, allow)`, `async cancel(turn_id)`, `async shutdown()`, `active_turns() -> set[str]`.

Behavior: each turn runs as a task; provider events become frames in order (`TextDelta` → `delta` chunks, `ToolCall` → `tool`, `UsageReport` → `usage`, `Finished` → `turn_done`, `Failed` → `turn_error`); exactly one terminal frame per turn (`turn_error` "The CLI ended without an answer." when the provider ends without one; an exception becomes `turn_error`); the gate sends a `permission_request` (with a new request id) and waits for `permission_reply`; `cancel` resolves the turn's open questions with `False`, tells the provider, and cancels the task after `cancel_grace` seconds if it is still running (then `turn_error` "cancelled"); a `Failed` from a cancelled turn is reported as "cancelled".

- [ ] **Step 1: Write the failing test**

Create `tests/test_runner.py`:

```python
from __future__ import annotations

import asyncio

import pytest

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport
from src.providers.base import Provider
from src.runner import TurnRunner


class ScriptedProvider(Provider):
    name = "scripted"

    def __init__(self, script) -> None:
        self.script = script
        self.cancelled = []
        self.gate_answers = []

    async def detect_plan(self):
        return None

    async def is_logged_in(self):
        return True

    async def run_turn(self, request, gate):
        for item in self.script:
            if callable(item):
                result = await item(gate)
                if result is not None:
                    self.gate_answers.append(result)
            else:
                yield item

    async def cancel(self, turn_id):
        self.cancelled.append(turn_id)


class Wire:
    def __init__(self) -> None:
        self.frames = []

    async def send(self, frame: dict) -> None:
        self.frames.append(frame)

    def types(self, turn_id: str = "t1") -> list[str]:
        return [f["type"] for f in self.frames if f.get("turn_id") == turn_id]


def request(turn_id: str = "t1") -> TurnRequest:
    return TurnRequest(turn_id, 1, ".", "ask", "go")


async def idle(runner: TurnRunner, timeout: float = 3.0) -> None:
    waited = 0.0
    while runner.active_turns():
        assert waited < timeout, "turn did not end"
        await asyncio.sleep(0.01)
        waited += 0.01


def test_events_become_frames_in_order() -> None:
    async def go():
        wire = Wire()
        provider = ScriptedProvider([TextDelta("Hel"), ToolCall("Bash", "ls"), UsageReport(3, 4), Finished("Hello")])
        runner = TurnRunner(provider, wire.send)
        runner.start(request())
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [
        {"type": "delta", "turn_id": "t1", "text": "Hel"},
        {"type": "tool", "turn_id": "t1", "name": "Bash", "summary": "ls"},
        {"type": "usage", "turn_id": "t1", "input_tokens": 3, "output_tokens": 4},
        {"type": "turn_done", "turn_id": "t1", "text": "Hello"},
    ]


def test_a_failure_is_one_turn_error() -> None:
    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([Failed("not logged in"), TextDelta("ignored")]), wire.send)
        runner.start(request())
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [{"type": "turn_error", "turn_id": "t1", "message": "not logged in"}]


def test_a_provider_that_ends_silently_still_gets_a_terminal_frame() -> None:
    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([TextDelta("partial")]), wire.send)
        runner.start(request())
        await idle(runner)
        return wire.types()

    assert asyncio.run(go()) == ["delta", "turn_error"]


def test_an_exception_becomes_a_turn_error() -> None:
    async def boom(gate):
        raise RuntimeError("kaput")

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([boom]), wire.send)
        runner.start(request())
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [{"type": "turn_error", "turn_id": "t1", "message": "kaput"}]


def test_a_permission_question_waits_for_the_reply() -> None:
    async def ask(gate):
        return await gate.ask("Bash", "rm -rf build")

    async def go():
        wire = Wire()
        provider = ScriptedProvider([ask, Finished("ok")])
        runner = TurnRunner(provider, wire.send)
        runner.start(request())
        for _ in range(100):
            if any(f["type"] == "permission_request" for f in wire.frames):
                break
            await asyncio.sleep(0.01)
        asked = next(f for f in wire.frames if f["type"] == "permission_request")
        assert (asked["turn_id"], asked["tool"], asked["summary"]) == ("t1", "Bash", "rm -rf build")
        assert "turn_done" not in wire.types()  # still waiting
        runner.permission_reply(asked["request_id"], True)
        await idle(runner)
        return provider.gate_answers, wire.types()

    answers, types = asyncio.run(go())
    assert answers == [True] and types == ["permission_request", "turn_done"]


def test_a_reply_for_an_unknown_question_is_ignored() -> None:
    TurnRunner(ScriptedProvider([]), Wire().send).permission_reply("nope", True)


def test_cancel_denies_open_questions_and_tells_the_provider() -> None:
    async def ask(gate):
        return await gate.ask("Bash", "x")

    async def go():
        wire = Wire()
        provider = ScriptedProvider([ask, Failed("stopped")])
        runner = TurnRunner(provider, wire.send)
        runner.start(request())
        for _ in range(100):
            if any(f["type"] == "permission_request" for f in wire.frames):
                break
            await asyncio.sleep(0.01)
        await runner.cancel("t1")
        await idle(runner)
        return provider.gate_answers, provider.cancelled, wire.frames[-1]

    answers, cancelled, last = asyncio.run(go())
    assert answers == [False] and cancelled == ["t1"]
    assert last == {"type": "turn_error", "turn_id": "t1", "message": "cancelled"}


def test_a_turn_that_ignores_cancel_is_stopped_after_the_grace_time() -> None:
    async def stubborn(gate):
        await asyncio.sleep(30)

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([stubborn]), wire.send, cancel_grace=0.05)
        runner.start(request())
        await asyncio.sleep(0.02)
        await runner.cancel("t1")
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [{"type": "turn_error", "turn_id": "t1", "message": "cancelled"}]


def test_cancelling_an_unknown_turn_does_nothing() -> None:
    asyncio.run(TurnRunner(ScriptedProvider([]), Wire().send).cancel("nope"))


def test_two_turns_can_run_at_once() -> None:
    async def slow(gate):
        await asyncio.sleep(0.05)

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([slow, Finished("x")]), wire.send)
        runner.start(request("a"))
        runner.start(request("b"))
        started = runner.active_turns()
        await idle(runner)
        return started, wire.types("a"), wire.types("b")

    started, a, b = asyncio.run(go())
    assert started == {"a", "b"} and a == ["turn_done"] and b == ["turn_done"]


def test_starting_the_same_turn_twice_runs_it_once() -> None:
    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([Finished("x")]), wire.send)
        runner.start(request())
        runner.start(request())
        await idle(runner)
        return wire.types()

    assert asyncio.run(go()) == ["turn_done"]


def test_shutdown_stops_everything() -> None:
    async def forever(gate):
        await asyncio.sleep(60)

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([forever]), wire.send)
        runner.start(request())
        await asyncio.sleep(0.02)
        await runner.shutdown()
        return runner.active_turns()

    assert asyncio.run(go()) == set()


def test_the_registry_builds_known_providers_only() -> None:
    from src.providers.registry import build_provider

    assert build_provider("claude").name == "claude"
    assert build_provider("codex").name == "codex"
    with pytest.raises(ValueError):
        build_provider("gemini")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.runner'`.

- [ ] **Step 3: Implement the registry**

Create `src/providers/registry.py`:

```python
"""Builds the real provider for a name. Imports stay inside the branches so a computer
with only one CLI never loads the other's dependencies."""

from __future__ import annotations

from src.providers.base import Provider, SubprocessRunner


def build_provider(name: str) -> Provider:
    if name == "claude":
        from src.providers.claude import ClaudeProvider
        from src.providers.claude_sdk import SdkSessionFactory

        return ClaudeProvider(SdkSessionFactory(), SubprocessRunner())
    if name == "codex":
        from src.providers.codex import CodexProvider
        from src.providers.codex_process import SubprocessCodexSpawner

        return CodexProvider(SubprocessCodexSpawner(), SubprocessRunner())
    raise ValueError(f"Unknown provider: {name}")
```

- [ ] **Step 4: Implement the runner**

Create `src/runner.py`:

```python
"""Runs turns. Each turn is a task that feeds a provider's events to the server as frames,
and exactly one terminal frame (turn_done or turn_error) closes it."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport
from src.protocol import (
    delta_frames,
    permission_request_frame,
    tool_frame,
    turn_done_frame,
    turn_error_frame,
    usage_frame,
)
from src.providers.base import Provider

logger = logging.getLogger(__name__)

CANCEL_GRACE_SECONDS = 5.0
CANCELLED = "cancelled"

Send = Callable[[dict], Awaitable[None]]


class _Gate:
    """What a provider calls to ask the user; bound to one turn."""

    def __init__(self, runner: TurnRunner, turn_id: str) -> None:
        self._runner = runner
        self._turn_id = turn_id

    async def ask(self, tool: str, summary: str) -> bool:
        return await self._runner._ask(self._turn_id, tool, summary)


class TurnRunner:
    def __init__(self, provider: Provider, send: Send, cancel_grace: float = CANCEL_GRACE_SECONDS) -> None:
        self._provider = provider
        self._send = send
        self._cancel_grace = cancel_grace
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancelled: set[str] = set()
        self._questions: dict[str, asyncio.Future[bool]] = {}
        self._question_turn: dict[str, str] = {}

    def active_turns(self) -> set[str]:
        return set(self._tasks)

    def start(self, request: TurnRequest) -> None:
        if request.turn_id in self._tasks:
            return
        task = asyncio.create_task(self._run(request))
        self._tasks[request.turn_id] = task
        task.add_done_callback(lambda _task, turn_id=request.turn_id: self._tasks.pop(turn_id, None))

    def permission_reply(self, request_id: str, allow: bool) -> None:
        question = self._questions.get(request_id)
        if question is not None and not question.done():
            question.set_result(allow)

    async def cancel(self, turn_id: str) -> None:
        task = self._tasks.get(turn_id)
        if task is None:
            return
        self._cancelled.add(turn_id)
        self._deny_questions(turn_id)
        try:
            await self._provider.cancel(turn_id)
        except Exception:
            logger.warning("the provider could not cancel turn %s", turn_id, exc_info=True)
        asyncio.get_running_loop().call_later(self._cancel_grace, task.cancel)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, request: TurnRequest) -> None:
        turn_id = request.turn_id
        finished = False
        try:
            async for event in self._provider.run_turn(request, _Gate(self, turn_id)):
                if finished:
                    continue
                if isinstance(event, TextDelta):
                    for frame in delta_frames(turn_id, event.text):
                        await self._send(frame)
                elif isinstance(event, ToolCall):
                    await self._send(tool_frame(turn_id, event.name, event.summary))
                elif isinstance(event, UsageReport):
                    await self._send(usage_frame(turn_id, event.input_tokens, event.output_tokens))
                elif isinstance(event, Finished):
                    finished = True
                    await self._send(turn_done_frame(turn_id, event.text))
                elif isinstance(event, Failed):
                    finished = True
                    await self._send(turn_error_frame(turn_id, CANCELLED if turn_id in self._cancelled else event.message))
            if not finished:
                finished = True
                await self._send(turn_error_frame(turn_id, CANCELLED if turn_id in self._cancelled else "The CLI ended without an answer."))
        except asyncio.CancelledError:
            if not finished:
                try:
                    await self._send(turn_error_frame(turn_id, CANCELLED))
                except Exception:
                    pass
            raise
        except Exception as error:
            logger.exception("turn %s failed", turn_id)
            if not finished:
                try:
                    await self._send(turn_error_frame(turn_id, str(error) or type(error).__name__))
                except Exception:
                    pass
        finally:
            self._cancelled.discard(turn_id)
            self._deny_questions(turn_id)

    async def _ask(self, turn_id: str, tool: str, summary: str) -> bool:
        request_id = uuid.uuid4().hex
        question: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._questions[request_id] = question
        self._question_turn[request_id] = turn_id
        try:
            await self._send(permission_request_frame(turn_id, request_id, tool, summary))
            return await question
        finally:
            self._questions.pop(request_id, None)
            self._question_turn.pop(request_id, None)

    def _deny_questions(self, turn_id: str) -> None:
        for request_id, owner in list(self._question_turn.items()):
            question = self._questions.get(request_id)
            if owner == turn_id and question is not None and not question.done():
                question.set_result(False)
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/Ember/ember_worker/src/providers/registry.py apps/Ember/ember_worker/src/runner.py apps/Ember/ember_worker/tests/test_runner.py
git commit -m "feat(ember_worker): turn runner and provider registry

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: WebSocket client

**Files:**
- Create: `src/client.py`, `tests/test_client.py`

**Interfaces:**
- Consumes: `WorkerConfig`, `Provider`, `TurnRunner`, protocol parse/builders, `__version__`.
- Produces: `TokenRejected(Exception)`; `WorkerClient(provider, config, token, *, connect=websockets.asyncio.client.connect, backoff_start=1.0, backoff_max=30.0)` with `async run()`. `run()` loops until cancelled or the token is rejected: it connects to `config.socket_url` with `Authorization: Bearer <token>`, sends `hello` (the config's `plan_override` for the provider, else `provider.detect_plan()`), waits up to 10 seconds for `ready`, then serves: heartbeats every `config.heartbeat_seconds`, and dispatches `turn` (start), `permission_reply`, `cancel` to a `TurnRunner` created per connection. On any disconnect it shuts that runner down and reconnects with exponential backoff (reset after a session that reached `ready`). A rejected token (HTTP 401/403 at the handshake, or a close with code 4401) raises `TokenRejected` out of the loop and `run()` returns after logging it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_client.py`:

```python
from __future__ import annotations

import asyncio
import json

import pytest
from websockets.asyncio.server import serve

from src.client import WorkerClient
from src.config import WorkerConfig
from src.events import Failed, Finished, TextDelta
from src.providers.base import Provider


class ScriptedProvider(Provider):
    name = "claude"

    def __init__(self, script, plan="Max") -> None:
        self.script, self.plan = script, plan
        self.requests, self.cancelled = [], []

    async def detect_plan(self):
        return self.plan

    async def is_logged_in(self):
        return True

    async def run_turn(self, request, gate):
        self.requests.append(request)
        for item in self.script:
            if callable(item):
                await item(gate)
            else:
                yield item

    async def cancel(self, turn_id):
        self.cancelled.append(turn_id)


def make_config(port: int, heartbeat: float = 20, overrides=None) -> WorkerConfig:
    return WorkerConfig(f"http://127.0.0.1:{port}", heartbeat, overrides or {}, {"claude": "ft_test"})


TURN = {"type": "turn", "turn_id": "t1", "group_id": 1, "folder": ".", "mode": "ask", "prompt": "hi", "history": []}


async def with_server(handler, scenario, **server_kwargs):
    async with serve(handler, "127.0.0.1", 0, **server_kwargs) as server:
        port = server.sockets[0].getsockname()[1]
        return await scenario(port)


async def run_client_until(client: WorkerClient, done: asyncio.Event, timeout: float = 5.0) -> None:
    task = asyncio.create_task(client.run())
    try:
        await asyncio.wait_for(done.wait(), timeout)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_hello_ready_then_a_turn_is_run_and_answered() -> None:
    seen, done = [], asyncio.Event()

    async def handler(ws):
        seen.append(("auth", ws.request.headers.get("Authorization")))
        seen.append(json.loads(await ws.recv()))  # hello
        await ws.send(json.dumps({"type": "ready", "worker_id": 7}))
        await ws.send(json.dumps(TURN))
        async for raw in ws:
            frame = json.loads(raw)
            seen.append(frame)
            if frame["type"] == "turn_done":
                done.set()

    async def scenario(port):
        provider = ScriptedProvider([TextDelta("Hi"), Finished("Hi there")])
        await run_client_until(WorkerClient(provider, make_config(port), "ft_test"), done)
        return provider

    provider = asyncio.run(with_server(handler, scenario))

    assert seen[0] == ("auth", "Bearer ft_test")
    assert seen[1]["type"] == "hello" and seen[1]["plan"] == "Max" and seen[1]["version"]
    assert [f["type"] for f in seen[2:]] == ["delta", "turn_done"]
    assert provider.requests[0].prompt == "hi" and provider.requests[0].turn_id == "t1"


def test_the_plan_override_beats_detection() -> None:
    seen, done = [], asyncio.Event()

    async def handler(ws):
        seen.append(json.loads(await ws.recv()))
        done.set()
        await ws.wait_closed()

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([], plan="Pro"), make_config(port, overrides={"claude": "Max 20x"}), "ft_test")
        await run_client_until(client, done)

    asyncio.run(with_server(handler, scenario))

    assert seen[0]["plan"] == "Max 20x"


def test_heartbeats_are_sent_while_connected() -> None:
    beats, done = [], asyncio.Event()

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        async for raw in ws:
            if json.loads(raw)["type"] == "heartbeat":
                beats.append(1)
                if len(beats) >= 2:
                    done.set()

    async def scenario(port):
        await run_client_until(WorkerClient(ScriptedProvider([]), make_config(port, heartbeat=0.05), "ft_test"), done)

    asyncio.run(with_server(handler, scenario))

    assert len(beats) >= 2


def test_permission_questions_travel_both_ways() -> None:
    seen, done = [], asyncio.Event()

    async def ask(gate):
        seen.append(("answer", await gate.ask("Bash", "ls")))

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        await ws.send(json.dumps(TURN))
        async for raw in ws:
            frame = json.loads(raw)
            if frame["type"] == "permission_request":
                await ws.send(json.dumps({"type": "permission_reply", "request_id": frame["request_id"], "allow": True}))
            if frame["type"] == "turn_done":
                done.set()

    async def scenario(port):
        provider = ScriptedProvider([ask, Finished("ok")])
        await run_client_until(WorkerClient(provider, make_config(port), "ft_test"), done)

    asyncio.run(with_server(handler, scenario))

    assert seen == [("answer", True)]


def test_a_cancel_frame_reaches_the_provider() -> None:
    cancelled, done = [], asyncio.Event()

    async def hang(gate):
        await asyncio.sleep(30)

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        await ws.send(json.dumps(TURN))
        await asyncio.sleep(0.1)
        await ws.send(json.dumps({"type": "cancel", "turn_id": "t1"}))
        async for raw in ws:
            if json.loads(raw)["type"] == "turn_error":
                done.set()

    async def scenario(port):
        provider = ScriptedProvider([hang])
        client = WorkerClient(provider, make_config(port), "ft_test")
        client._cancel_grace = 0.05
        await run_client_until(client, done)
        return provider

    provider = asyncio.run(with_server(handler, scenario))

    assert provider.cancelled == ["t1"]


def test_it_reconnects_after_the_server_drops_it() -> None:
    connections, done = [], asyncio.Event()

    async def handler(ws):
        connections.append(1)
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        if len(connections) == 1:
            await ws.close(code=1011)
        else:
            done.set()
            await ws.wait_closed()

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([]), make_config(port), "ft_test", backoff_start=0.01, backoff_max=0.02)
        await run_client_until(client, done)

    asyncio.run(with_server(handler, scenario))

    assert len(connections) == 2


def test_a_running_turn_is_failed_when_the_connection_drops() -> None:
    async def hang(gate):
        await asyncio.sleep(30)

    async def go():
        provider = ScriptedProvider([hang])
        dropped = asyncio.Event()
        ended = []

        async def handler(ws):
            await ws.recv()
            await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
            await ws.send(json.dumps(TURN))
            await asyncio.sleep(0.1)
            await ws.close(code=1011)
            dropped.set()

        async def scenario(port):
            client = WorkerClient(provider, make_config(port), "ft_test", backoff_start=5, backoff_max=5)
            task = asyncio.create_task(client.run())
            await asyncio.wait_for(dropped.wait(), 5)
            await asyncio.sleep(0.2)  # the client notices and shuts the runner down
            ended.append(task.done())
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        await with_server(handler, scenario)
        return ended

    assert asyncio.run(go()) == [False]  # still running (waiting to reconnect), not crashed


def test_a_rejected_token_ends_the_client_without_retrying() -> None:
    connections = []

    async def handler(ws):
        connections.append(1)
        await ws.recv()
        await ws.close(code=4401)

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([]), make_config(port), "ft_bad", backoff_start=0.01)
        await asyncio.wait_for(client.run(), 5)  # returns instead of looping

    asyncio.run(with_server(handler, scenario))

    assert connections == [1]


def test_a_handshake_refusal_also_means_the_token_was_rejected() -> None:
    from http import HTTPStatus

    connections = []

    async def handler(ws):
        connections.append(1)

    def refuse(connection, request):
        return connection.respond(HTTPStatus.FORBIDDEN, "no\n")

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([]), make_config(port), "ft_bad", backoff_start=0.01)
        await asyncio.wait_for(client.run(), 5)

    asyncio.run(with_server(handler, scenario, process_request=refuse))

    assert connections == []


def test_it_keeps_retrying_while_the_server_is_unreachable() -> None:
    async def go():
        client = WorkerClient(ScriptedProvider([]), make_config(1), "ft_test", backoff_start=0.01, backoff_max=0.02)
        task = asyncio.create_task(client.run())
        await asyncio.sleep(0.2)
        alive = not task.done()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return alive

    assert asyncio.run(go()) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.client'`.

- [ ] **Step 3: Implement**

Create `src/client.py`:

```python
"""The worker's side of the Forge socket: connect out with the pairing token, say hello, keep
alive, hand turn / permission_reply / cancel frames to a TurnRunner, and reconnect when the
connection drops."""

from __future__ import annotations

import asyncio
import json
import logging

from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from src import __version__
from src.config import WorkerConfig
from src.events import TurnRequest
from src.protocol import (
    CancelFrame,
    PermissionReply,
    ReadyFrame,
    heartbeat_frame,
    hello_frame,
    parse_server_frame,
)
from src.providers.base import Provider
from src.runner import CANCEL_GRACE_SECONDS, TurnRunner

logger = logging.getLogger(__name__)

READY_TIMEOUT_SECONDS = 10.0
REJECTED_CLOSE_CODE = 4401


class TokenRejected(Exception):
    """Ember does not accept this pairing token (it was revoked, or is wrong)."""


class WorkerClient:
    def __init__(
        self,
        provider: Provider,
        config: WorkerConfig,
        token: str,
        *,
        connect=ws_connect,
        backoff_start: float = 1.0,
        backoff_max: float = 30.0,
    ) -> None:
        self._provider = provider
        self._config = config
        self._token = token
        self._connect = connect
        self._backoff_start = backoff_start
        self._backoff_max = backoff_max
        self._cancel_grace = CANCEL_GRACE_SECONDS

    async def run(self) -> None:
        """Runs until cancelled, or until Ember rejects the token."""
        delay = self._backoff_start
        while True:
            try:
                reached_ready = await self._session()
                delay = self._backoff_start if reached_ready else delay
            except TokenRejected:
                logger.error(
                    "Ember rejected the %s worker's token. Pair it again with a new token from the Forge page.",
                    self._provider.name,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("%s worker disconnected: %s", self._provider.name, error)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._backoff_max)

    async def _session(self) -> bool:
        """One connection. True when it got as far as `ready`."""
        headers = {"Authorization": f"Bearer {self._token}"}
        reached_ready = False
        try:
            async with self._connect(self._config.socket_url, additional_headers=headers) as ws:
                await self._hello(ws)
                reached_ready = True
                await self._serve(ws)
        except InvalidStatus as error:
            if error.response.status_code in (401, 403):
                raise TokenRejected() from error
            raise
        except ConnectionClosed as error:
            if error.rcvd is not None and error.rcvd.code == REJECTED_CLOSE_CODE:
                raise TokenRejected() from error
        return reached_ready

    async def _hello(self, ws) -> None:
        plan = self._config.plan_override.get(self._provider.name) or await self._provider.detect_plan()
        await ws.send(json.dumps(hello_frame(plan, __version__)))
        raw = await asyncio.wait_for(ws.recv(), READY_TIMEOUT_SECONDS)
        if not isinstance(parse_server_frame(raw), ReadyFrame):
            raise ConnectionError("Ember did not answer the hello with ready")
        logger.info("%s worker connected", self._provider.name)

    async def _serve(self, ws) -> None:
        async def send(frame: dict) -> None:
            await ws.send(json.dumps(frame, ensure_ascii=False))

        runner = TurnRunner(self._provider, send, self._cancel_grace)
        beat = asyncio.create_task(self._heartbeat(send))
        try:
            async for raw in ws:
                frame = parse_server_frame(raw)
                if isinstance(frame, TurnRequest):
                    runner.start(frame)
                elif isinstance(frame, PermissionReply):
                    runner.permission_reply(frame.request_id, frame.allow)
                elif isinstance(frame, CancelFrame):
                    await runner.cancel(frame.turn_id)
        finally:
            beat.cancel()
            await asyncio.gather(beat, return_exceptions=True)
            await runner.shutdown()

    async def _heartbeat(self, send) -> None:
        while True:
            await asyncio.sleep(self._config.heartbeat_seconds)
            await send(heartbeat_frame())
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_client.py -q`
Expected: PASS. Likely snags:
- `ws.request.headers` on the server connection: in `websockets` 13+ the server connection has `.request` (a `Request` with `.headers`). If the installed version differs, read the header from `ws.request_headers` instead, in the test only.
- `process_request=refuse` returning `connection.respond(...)`: this is the 13+ API. If the signature differs in the installed version, adapt the test's `refuse` function to it; the client logic (HTTP 403 means `TokenRejected`) does not change.
- If `test_a_cancel_frame_reaches_the_provider` times out, confirm `client._cancel_grace = 0.05` is set before `run()` (it is read when each session builds its runner).

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_worker/src/client.py apps/Ember/ember_worker/tests/test_client.py
git commit -m "feat(ember_worker): WebSocket client with reconnect and heartbeat

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Command line

**Files:**
- Create: `src/run.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config`, `save_pairing`, `ConfigError`, `PROVIDERS`, `build_provider`, `WorkerClient`.
- Produces: `main(argv=None, *, root=ROOT, provider_factory=build_provider) -> int` with subcommands:
  - `pair <url> <token> --provider {claude,codex} [--plan TEXT]`: refuses (exit 1, message on stderr) when the CLI is not logged in; otherwise saves the address, token and optional plan override, prints the detected plan or a hint to pass `--plan`, exits 0.
  - `status`: prints the Ember address, then per provider `logged in: yes/no`, `plan: <detected or override or unknown>`, `paired: yes/no`. Never prints a token. Exit 0.
  - `run` (also the default with no subcommand): runs one `WorkerClient` per paired provider until interrupted; exit 1 with a hint when none is paired.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import load_config
from src.providers.base import Provider
from src.run import main


class FakeProvider(Provider):
    def __init__(self, name: str, logged_in: bool = True, plan: str | None = "Max") -> None:
        self.name, self._logged_in, self._plan = name, logged_in, plan

    async def detect_plan(self):
        return self._plan

    async def is_logged_in(self):
        return self._logged_in

    def run_turn(self, request, gate):  # pragma: no cover - not used here
        raise NotImplementedError

    async def cancel(self, turn_id):  # pragma: no cover
        pass


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "config_worker.json.example").write_text(
        json.dumps({"url": "http://127.0.0.1:8030", "heartbeat_seconds": 20, "plan_override": {}}), encoding="utf-8"
    )
    return tmp_path


def factory(**providers):
    return lambda name: providers[name]


def test_pair_saves_the_address_and_token_after_checking_the_login(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main(
        ["pair", "https://ember.example.com/", "ft_secret", "--provider", "claude"],
        root=root, provider_factory=factory(claude=FakeProvider("claude", plan="max")),
    )

    out = capsys.readouterr().out
    assert code == 0
    config = load_config(root)
    assert (config.url, config.tokens) == ("https://ember.example.com", {"claude": "ft_secret"})
    assert "max" in out and "ft_secret" not in out


def test_pair_refuses_when_the_cli_is_not_logged_in(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main(
        ["pair", "http://127.0.0.1:8030", "ft_secret", "--provider", "codex"],
        root=root, provider_factory=factory(codex=FakeProvider("codex", logged_in=False)),
    )

    err = capsys.readouterr().err
    assert code == 1 and "not logged in" in err
    assert load_config(root).tokens == {}  # nothing was saved


def test_pair_with_an_undetectable_plan_suggests_the_plan_option(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main(
        ["pair", "http://127.0.0.1:8030", "ft_t", "--provider", "claude"],
        root=root, provider_factory=factory(claude=FakeProvider("claude", plan=None)),
    )

    assert code == 0 and "--plan" in capsys.readouterr().out


def test_pair_can_record_the_plan_by_hand(tmp_path: Path) -> None:
    root = make_root(tmp_path)

    main(
        ["pair", "http://127.0.0.1:8030", "ft_t", "--provider", "claude", "--plan", "Max 20x"],
        root=root, provider_factory=factory(claude=FakeProvider("claude", plan=None)),
    )

    assert load_config(root).plan_override == {"claude": "Max 20x"}


def test_status_reports_without_revealing_tokens(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)
    main(
        ["pair", "http://127.0.0.1:8030", "ft_hidden", "--provider", "claude"],
        root=root, provider_factory=factory(claude=FakeProvider("claude")),
    )
    capsys.readouterr()

    code = main(
        ["status"],
        root=root,
        provider_factory=factory(claude=FakeProvider("claude", plan="max"), codex=FakeProvider("codex", logged_in=False, plan=None)),
    )

    out = capsys.readouterr().out
    assert code == 0 and "ft_hidden" not in out
    assert "http://127.0.0.1:8030" in out
    claude_block, codex_block = out.split("codex")
    assert "logged in: yes" in claude_block and "plan: max" in claude_block and "paired: yes" in claude_block
    assert "logged in: no" in codex_block and "plan: unknown" in codex_block and "paired: no" in codex_block


def test_run_without_a_paired_worker_explains_how_to_pair(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)

    code = main([], root=root, provider_factory=factory())

    assert code == 1 and "pair" in capsys.readouterr().err


def test_a_config_problem_is_a_clear_message_not_a_traceback(tmp_path: Path, capsys) -> None:
    code = main(["status"], root=tmp_path, provider_factory=factory())  # no configs folder at all

    assert code == 1 and "config_worker.json" in capsys.readouterr().err


def test_unknown_provider_is_refused_by_the_parser() -> None:
    with pytest.raises(SystemExit):
        main(["pair", "u", "t", "--provider", "gemini"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.run'`.

- [ ] **Step 3: Implement**

Create `src/run.py`:

```python
"""ember_worker entry point: ``python -m src.run`` (see run.bat).

  run.bat pair <ember_url> <token> --provider claude [--plan "Max"]
  run.bat status
  run.bat                       connect every paired worker
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from src.client import WorkerClient
from src.config import PROVIDERS, ROOT, ConfigError, load_config, save_pairing
from src.providers.base import Provider
from src.providers.registry import build_provider

ProviderFactory = Callable[[str], Provider]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ember-worker", description="Connect your Claude Code and Codex CLIs to Ember's Forge page.")
    commands = parser.add_subparsers(dest="command")
    pair = commands.add_parser("pair", help="pair this computer's CLI with a worker made on the Forge page")
    pair.add_argument("url", help="the address of ember_api, for example https://ember.example.com")
    pair.add_argument("token", help="the one-time token the Forge page showed")
    pair.add_argument("--provider", required=True, choices=PROVIDERS)
    pair.add_argument("--plan", help="your subscription plan, when the CLI cannot report it")
    commands.add_parser("status", help="show the login, plan and pairing of each CLI")
    commands.add_parser("run", help="connect every paired worker (the default)")
    return parser


def _error(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


async def _pair(args: argparse.Namespace, root: Path, make_provider: ProviderFactory) -> int:
    provider = make_provider(args.provider)
    if not await provider.is_logged_in():
        return _error(
            f"The {args.provider} CLI is not logged in on this computer. Log in with it first, then pair again."
        )
    save_pairing(root, args.provider, args.url, args.token, args.plan)
    plan = args.plan or await provider.detect_plan()
    print(f"Paired the {args.provider} worker with {args.url.rstrip('/')}.")
    if plan:
        print(f"Plan: {plan}")
    else:
        print('The CLI did not report a plan. If Ember refuses the worker, pair again with --plan "<your plan>".')
    print("Start it with: run.bat")
    return 0


async def _status(root: Path, make_provider: ProviderFactory) -> int:
    config = load_config(root)
    print(f"Ember: {config.url}")
    for name in PROVIDERS:
        provider = make_provider(name)
        logged_in = await provider.is_logged_in()
        plan = config.plan_override.get(name) or (await provider.detect_plan() if logged_in else None) or "unknown"
        print(f"{name}")
        print(f"  logged in: {'yes' if logged_in else 'no'}")
        print(f"  plan: {plan}")
        print(f"  paired: {'yes' if config.tokens.get(name) else 'no'}")
    return 0


async def _run(root: Path, make_provider: ProviderFactory) -> int:
    config = load_config(root)
    paired = config.paired_providers()
    if not paired:
        return _error("No worker is paired yet. Make one on the Forge page, then run: run.bat pair <url> <token> --provider claude")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clients = [WorkerClient(make_provider(name), config, config.tokens[name]) for name in paired]
    print(f"Connecting {', '.join(paired)} to {config.url} ... (Ctrl+C to stop)")
    await asyncio.gather(*(client.run() for client in clients))
    return 0


def main(
    argv: Sequence[str] | None = None, *, root: Path = ROOT, provider_factory: ProviderFactory = build_provider
) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    try:
        if command == "pair":
            return asyncio.run(_pair(args, root, provider_factory))
        if command == "status":
            return asyncio.run(_status(root, provider_factory))
        return asyncio.run(_run(root, provider_factory))
    except ConfigError as error:
        return _error(str(error))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv_ember_worker/Scripts/python.exe -m pytest tests/test_cli.py -q`
Expected: PASS. Then run the whole suite: `.venv_ember_worker/Scripts/python.exe -m pytest -q` — expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_worker/src/run.py apps/Ember/ember_worker/tests/test_cli.py
git commit -m "feat(ember_worker): pair, status and run commands

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: README and a check against the real thing

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the README**

Replace `README.md` with a document in the style of the sibling projects' READMEs covering, in this order:

1. What it is: runs on your own computer, uses your own Claude Code and Codex logins, connects out to `ember_api` over a WebSocket (no inbound ports), and never sends Ember a login or subscription token.
2. Requirements: Python 3.11+; the `claude` CLI logged in (for a Claude worker); the `codex` CLI logged in (for a Codex worker).
3. Setup: run `run.bat` once to build the venv; make a worker on the Forge page; run `run.bat pair <url> <token> --provider claude` (and again for Codex); then `run.bat` to connect. `run.bat status` shows login, plan and pairing without revealing tokens.
4. Modes: Claude maps Ask/Accept edits/Plan/Full auto to Claude Code's `default`/`acceptEdits`/`plan`/`bypassPermissions`, and asks you on the Forge page for anything the mode does not allow. Codex cannot ask (its `exec` mode is non-interactive): Ask and Plan run in the read-only sandbox, Accept edits in `workspace-write`, Full auto in `danger-full-access`.
5. Limits: Anthropic gives paid plans a separate monthly Agent SDK credit for Agent SDK and `claude -p` use, so Claude workers may draw on that credit rather than the normal plan limit (check the current size on Anthropic's help page); Anthropic does not allow offering claude.ai login or Pro/Max limits to other people, so run only your own worker for your own use; plan names are whatever the CLI reports and an administrator lists the eligible ones in Ember.
6. Config: `configs/config_worker.json` (`url`, `heartbeat_seconds`, `plan_override`) and `.env` (`EMBER_WORKER_TOKEN_CLAUDE`, `EMBER_WORKER_TOKEN_CODEX`); both are gitignored with `.example` twins.
7. Tests: `.venv_ember_worker/Scripts/python.exe -m pytest -q`.

- [ ] **Step 2: Check the real CLIs on this computer (manual, no tokens printed)**

From `apps/Ember/ember_worker`:

```bash
.venv_ember_worker/Scripts/python.exe -m src.run status
```

Expected: prints the Ember address and, for each CLI, `logged in: yes/no`, a plan (or `unknown`) and `paired: no`. Record what the real CLIs report: if the Claude plan shows `unknown` while logged in, `claude auth status` does not include `subscriptionType`; say so in the README (users then pass `--plan`). Do the same note for Codex if `detect_codex_plan` returns `unknown` while logged in. Do not print or paste any token or login file.

- [ ] **Step 3: End-to-end check with a running ember_api (manual)**

Start ember_api from plan 1 (`apps/Ember/ember_api/run.bat`), sign in as an administrator, make a Claude worker through the API (`POST /api/forge/workers`) and note the token it returns once. Then:

```bash
.venv_ember_worker/Scripts/python.exe -m src.run pair http://127.0.0.1:8030 <token> --provider claude
.venv_ember_worker/Scripts/python.exe -m src.run
```

Expected: the worker prints `Connecting claude to http://127.0.0.1:8030`, and `GET /api/forge/workers` shows it `online: true` with the plan it reported. Add that plan to the allowlist (`PUT /api/forge/plans/claude`), make a group, invite the worker with a real project folder, and post `@claude say hello`. Expected: a reply appears in `GET /api/forge/groups/{id}/messages`. If a Bash command is requested in Ask mode, the permission request appears there and `POST .../permissions/{request_id}` answers it. Report what worked and what did not; do not paste tokens.

- [ ] **Step 4: Commit**

```bash
git add apps/Ember/ember_worker/README.md
git commit -m "docs(ember_worker): README with setup, modes and limits

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
