# Editable garrison tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An administrator edits garrison's runtime tuning from ember_admin, and each user sets their own `max_output_tokens` and `max_tool_rounds` from ember_web Settings, with no file edit and no restart.

**Architecture:** Garrison keeps admin edits in an overlay file `configs/tuning_overrides.json` (flat dotted paths, written atomically, mirrors `src/agents/prompt_config.py`). `config_files.read_section` merges the overlay over `config_tuning.json`, so every reader sees the edit. A turn-start `poll()` notices a changed overlay and clears the readers' caches. Per-user limits live in treasury through ember_api's `DocumentStore`, travel to garrison as `ask(limits=...)`, and are applied as `min(user, effective)` inside `LlmOptions`.

**Tech Stack:** Python 3.11+, FastMCP/Starlette (garrison), FastAPI + pytest (ember_api), Vue 3 + TypeScript + vitest (ember_admin, ember_web).

**Spec:** `docs/superpowers/specs/2026-10-25-tuning-settings-design.md`

## Global Constraints

- Garrison keeps no database; ember_api uses treasury (`DocumentStore`) for new per-account data, no Alembic migration.
- Precedence: `config_tuning.json` < admin overlay < user value; a user value can only lower the effective value.
- Editable by user: `max_output_tokens`, `max_tool_rounds` only.
- Never editable (file-only): `classifier.typesafe`, `vercel`, `chains`, `triage_order`, `auto_tier`, `auto_route`.
- Never add a reduced-motion setting, `prefers-reduced-motion` query or test (repo rule).
- UI work: read `.agents/skills/ember-frontend-design/SKILL.md` and `ember-design-system` first; reuse the existing tokens and components.
- Do not edit `.claude/skills/`; skills live in `.agents/skills/` (nothing in this plan touches skills).
- Commit trailer on every commit: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- Run Python tests from each app folder with that app's own venv (`python -m pytest`).

## File Structure

| File | Responsibility |
|---|---|
| `apps/garrison/src/core/tuning_overrides.py` (new) | Allowlist + validation, load/save/apply of the overlay, `signature`, `poll`, `on_change` |
| `apps/garrison/src/core/config_files.py` | `read_section` merges the overlay; `tuning_view()` for the admin route |
| `apps/garrison/src/llm/{token_limits,decision,gateway_failover}.py` | Register `reset_cache`; `token_limits` also holds the per-turn user limits |
| `apps/garrison/src/llm/llm_options.py` | Applies the user clamp |
| `apps/garrison/src/agents/agent_config.py` | `run_chat(limits=...)`, calls `poll()` |
| `apps/garrison/src/server.py` | `ask(limits=...)`, `status().user_limits`, `/agents/tuning` routes |
| `apps/Ember/ember_api/src/services/agent_admin.py` | `tuning()` / `set_tuning()` forwarding |
| `apps/Ember/ember_api/src/routes/admin_tuning.py` (new) | `/api/admin/tuning`, permission `tuning.manage` |
| `apps/Ember/ember_api/src/services/tuning_limits_service.py` (new) | Per-account limits in treasury |
| `apps/Ember/ember_api/src/routes/account_tuning.py` (new) | `/api/account/tuning` |
| `apps/Ember/ember_api/src/{services/turns.py,services/agent_gateway.py,routes/chats.py}` | Carry `limits` into `ask` |
| `apps/Ember/ember_admin/src/{api/TuningClient.ts,views/TuningAdminView.vue,router,pages}` | Admin Tuning page |
| `apps/Ember/ember_web/src/{api/navigation/TuningClient.ts,features/settings/components/ResponseLimits.vue}` | "Response limits" row in Settings |

---

### Task 1: Overlay module and merge into `read_section`

**Files:**
- Create: `apps/garrison/src/core/tuning_overrides.py`
- Modify: `apps/garrison/src/core/config_files.py` (`read_section`, new `tuning_view`)
- Test: `apps/garrison/tests/test_tuning_overrides.py`

**Interfaces:**
- Produces: `tuning_overrides.OVERLAY_NAME: str`, `PATH: Path`, `TuningError`, `check(path: str, value) -> bool|int|float`, `load(path=PATH) -> dict[str, Any]`, `save(changes: dict[str, Any|None], path=PATH) -> dict[str, Any]`, `apply(raw: dict, path=PATH) -> dict`, `signature(path=PATH) -> int|None`. `config_files.tuning_view(path=TUNING_PATH) -> {"defaults": dict, "overrides": dict, "effective": dict}`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/garrison/tests/test_tuning_overrides.py
"""The admin overlay over config_tuning.json."""

import json
from pathlib import Path

import pytest

from src.core import config_files, tuning_overrides
from src.core.tuning_overrides import TuningError


@pytest.fixture
def tuning(tmp_path):
    path = tmp_path / "config_tuning.json"
    examples = Path(config_files.__file__).resolve().parents[2] / "configs"
    path.with_suffix(".json.example").write_bytes((examples / "config_tuning.json.example").read_bytes())
    return path, tmp_path / tuning_overrides.OVERLAY_NAME


def test_apply_sets_nested_value_and_leaves_base_alone(tuning):
    _, overlay = tuning
    overlay.write_text(json.dumps({"token_limits.default.max_tool_rounds": 20}), encoding="utf-8")
    base = {"token_limits": {"default": {"max_tool_rounds": 15}}}
    merged = tuning_overrides.apply(base, overlay)
    assert merged["token_limits"]["default"]["max_tool_rounds"] == 20
    assert base["token_limits"]["default"]["max_tool_rounds"] == 15


def test_save_none_resets_a_path(tuning):
    _, overlay = tuning
    tuning_overrides.save({"gateway_failover.quota_cooldown_seconds": 60}, overlay)
    assert tuning_overrides.load(overlay) == {"gateway_failover.quota_cooldown_seconds": 60.0}
    tuning_overrides.save({"gateway_failover.quota_cooldown_seconds": None}, overlay)
    assert tuning_overrides.load(overlay) == {}


@pytest.mark.parametrize("path, value", [
    ("classifier.typesafe.url", "https://x"),              # file-only
    ("token_limits.default.max_tool_rounds", 0),           # below range
    ("token_limits.default.max_tool_rounds", 101),         # above range
    ("token_limits.default.max_tool_rounds", True),        # bool is not a number
    ("token_limits.default.max_tool_rounds", 2.5),         # int field
    ("classifier.timeout_seconds", 0),                     # open lower bound
    ("classifier.triage_thresholds.4.jev", 0.5),           # unknown count
    ("classifier.triage_enabled.jev.choice", "yes"),       # bool field
    ("nonsense", 1),
])
def test_save_rejects_bad_changes(tuning, path, value):
    _, overlay = tuning
    with pytest.raises(TuningError):
        tuning_overrides.save({path: value}, overlay)
    assert not overlay.exists()


def test_save_rejects_unknown_path_on_reset(tuning):
    _, overlay = tuning
    with pytest.raises(TuningError):
        tuning_overrides.save({"classifier.chains.triage": None}, overlay)


def test_invalid_entry_in_the_file_is_ignored(tuning):
    _, overlay = tuning
    overlay.write_text(json.dumps({"token_limits.default.max_tool_rounds": 999, "classifier.triage_trace": True}), encoding="utf-8")
    assert tuning_overrides.load(overlay) == {"classifier.triage_trace": True}


def test_unreadable_overlay_is_empty(tuning):
    _, overlay = tuning
    overlay.write_text("{not json", encoding="utf-8")
    assert tuning_overrides.load(overlay) == {}


def test_read_section_merges_the_overlay_next_to_the_tuning_file(tuning):
    path, overlay = tuning
    tuning_overrides.save({"token_limits.default.max_tool_rounds": 20}, overlay)
    limits = config_files.read_section(path, "token_limits")
    assert limits["default"]["max_tool_rounds"] == 20
    assert limits["default"]["max_output_tokens"] == 2048


def test_tuning_view_hides_file_only_keys(tuning):
    path, overlay = tuning
    tuning_overrides.save({"classifier.timeout_seconds": 5}, overlay)
    view = config_files.tuning_view(path)
    assert view["overrides"] == {"classifier.timeout_seconds": 5.0}
    assert view["defaults"]["classifier"]["timeout_seconds"] == 3.0
    assert view["effective"]["classifier"]["timeout_seconds"] == 5.0
    for section in (view["defaults"], view["effective"]):
        assert not {"typesafe", "vercel", "chains", "triage_order"} & set(section["classifier"])


def test_every_allowed_extreme_is_accepted_by_the_real_loaders(tuning, monkeypatch):
    """The allowlist must never admit a value token_limits or decision would refuse."""
    from src.llm import decision, token_limits

    path, overlay = tuning
    extremes = {
        "token_limits.default.max_output_tokens": 200_000, "token_limits.default.max_context_tokens": 1_000,
        "token_limits.default.max_tool_rounds": 100, "token_limits.openai.gateways.ollama.max_context_tokens": 2_000_000,
        "gateway_failover.unavailable_cooldown_seconds": 0, "classifier.timeout_seconds": 60,
        "classifier.max_input_chars": 1, "classifier.triage_fallback": True, "classifier.triage_trace": True,
        "classifier.triage_window": 512, "classifier.triage_prune_ratio": 0, "classifier.triage_pair_ratio": 1,
        "classifier.triage_thresholds.3+.laya-typed": 1, "classifier.triage_enabled.jev.score": False,
    }
    tuning_overrides.save(extremes, overlay)
    monkeypatch.setattr(token_limits, "_CONFIG_PATH", path)
    monkeypatch.setattr(decision, "TUNING_PATH", path)
    token_limits.reset_cache()
    decision.reset_cache()
    try:
        assert token_limits.limits_for("openai", "ollama")["max_context_tokens"] == 2_000_000
        assert decision.settings().triage_window == 512
    finally:
        token_limits.reset_cache()
        decision.reset_cache()
```

- [ ] **Step 2: Run to verify it fails**

Run (in `apps/garrison`): `python -m pytest tests/test_tuning_overrides.py -v`
Expected: FAIL, `ImportError: cannot import name 'tuning_overrides'`.

- [ ] **Step 3: Write `tuning_overrides.py`**

```python
# apps/garrison/src/core/tuning_overrides.py
"""Admin edits to config_tuning.json, kept apart from it.

`configs/tuning_overrides.json` holds only what an admin changed, as flat dotted
paths ({"token_limits.default.max_tool_rounds": 20}). config_files.read_section
merges it over config_tuning.json, so every reader sees an edit without changing
how it parses. Same shape and atomic write as prompt_config.py.

Only paths with a rule below can be edited. Each range matches the validator in
the module that reads the value (token_limits.py, decision.py), so a saved edit
never makes a reader raise. Pure stdlib: config_files imports this module.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

OVERLAY_NAME = "tuning_overrides.json"
PATH = Path(__file__).resolve().parent.parent.parent / "configs" / OVERLAY_NAME


class TuningError(Exception):
    """A rejected change; the message is safe to show."""


@dataclass(frozen=True)
class Rule:
    kind: str  # "int" | "number" | "bool"
    low: float = 0.0
    high: float = 0.0
    low_open: bool = False
    high_open: bool = False


_ID = r"[a-z0-9][a-z0-9_-]{0,39}"
_VOTERS = "laya-english|laya-typed|jev"
_RULES: list[tuple[re.Pattern[str], Rule]] = []


def _add(pattern: str, rule: Rule) -> None:
    _RULES.append((re.compile(pattern), rule))


for _field, _rule in {
    "max_output_tokens": Rule("int", 1, 200_000),
    "max_context_tokens": Rule("int", 1_000, 2_000_000),
    "max_tool_rounds": Rule("int", 1, 100),
}.items():
    _add(rf"token_limits\.{_ID}\.{_field}", _rule)
    _add(rf"token_limits\.{_ID}\.gateways\.{_ID}\.{_field}", _rule)
_add(r"gateway_failover\.(?:quota|auth|unavailable)_cooldown_seconds", Rule("number", 0, 604_800))
_add(r"classifier\.timeout_seconds", Rule("number", 0, 60, low_open=True))
_add(r"classifier\.max_input_chars", Rule("int", 1, 1_000_000))
_add(r"classifier\.triage_(?:fallback|trace)", Rule("bool"))
_add(r"classifier\.triage_window", Rule("int", 512, 32_768))
_add(r"classifier\.triage_prune_ratio", Rule("number", 0, 1, high_open=True))
_add(r"classifier\.triage_pair_ratio", Rule("number", 0, 1, low_open=True))
_add(rf"classifier\.triage_thresholds\.(?:2|3\+)\.(?:{_VOTERS})", Rule("number", 0, 1, low_open=True))
_add(rf"classifier\.triage_enabled\.(?:{_VOTERS})\.(?:choice|noul|score)", Rule("bool"))


def _rule_for(path: str) -> Rule:
    for pattern, rule in _RULES:
        if pattern.fullmatch(path):
            return rule
    raise TuningError(f"{path!r} cannot be edited here")


def check(path: str, value: Any) -> bool | int | float:
    """The value as it will be stored, or TuningError."""
    rule = _rule_for(path)
    if rule.kind == "bool":
        if not isinstance(value, bool):
            raise TuningError(f"{path} must be true or false")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (rule.kind == "int" and not isinstance(value, int)):
        raise TuningError(f"{path} must be a {'whole ' if rule.kind == 'int' else ''}number")
    above = value > rule.low if rule.low_open else value >= rule.low
    below = value < rule.high if rule.high_open else value <= rule.high
    if not (above and below):  # NaN fails both
        raise TuningError(f"{path} must be {'above' if rule.low_open else 'from'} {rule.low:g} and {'below' if rule.high_open else 'up to'} {rule.high:g}")
    return value if rule.kind == "int" else float(value)


def load(path: Path = PATH) -> dict[str, Any]:
    """What the overlay sets. An unreadable file is empty; a bad entry is skipped and logged."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    good: dict[str, Any] = {}
    for key, value in data.items():
        try:
            good[key] = check(key, value)
        except TuningError as error:
            _log.warning("ignoring %s in %s: %s", key, path.name, error)
    return good


def apply(raw: dict[str, Any], path: Path = PATH) -> dict[str, Any]:
    """`raw` (config_tuning.json's object) with the overlay set on top; `raw` itself is not changed."""
    changes = load(path)
    if not changes:
        return raw
    merged = copy.deepcopy(raw)
    for dotted, value in changes.items():
        *parents, leaf = dotted.split(".")
        node = merged
        for part in parents:
            child = node.get(part)
            if not isinstance(child, dict):
                child = node[part] = {}
            node = child
        node[leaf] = value
    return merged


def save(changes: dict[str, Any], path: Path = PATH) -> dict[str, Any]:
    """Apply `changes` (dotted path -> value; None = back to the file's value) and write
    the overlay atomically. Raises TuningError before writing if any change is bad."""
    current = load(path)
    for key, value in changes.items():
        _rule_for(key)
        if value is None:
            current.pop(key, None)
        else:
            current[key] = check(key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(json.dumps(current, indent=2) + "\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return current


def signature(path: Path = PATH) -> int | None:
    """Changes whenever the overlay is rewritten; None when it does not exist."""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None
```

- [ ] **Step 4: Edit `config_files.py`**

Add `from src.core import tuning_overrides` under the existing imports, and replace the body of `read_section` after the `isinstance(raw, dict)` check:

```python
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be an object")
    if path.name == TUNING_PATH.name:
        raw = tuning_overrides.apply(raw, path.with_name(tuning_overrides.OVERLAY_NAME))
    if section not in raw:
```

Append to the file:

```python
# classifier keys an admin edits only in the file: endpoints, models and routing.
_FILE_ONLY_CLASSIFIER = ("typesafe", "vercel", "chains", "triage_order", "auto_tier", "auto_route")


def _editable(raw: dict[str, Any]) -> dict[str, Any]:
    out = {name: raw[name] for name in ("token_limits", "gateway_failover") if name in raw}
    classifier = raw.get("classifier")
    if isinstance(classifier, dict):
        out["classifier"] = {k: v for k, v in classifier.items() if k not in _FILE_ONLY_CLASSIFIER}
    return out


def tuning_view(path: Path = TUNING_PATH) -> dict[str, Any]:
    """What the admin page shows: the file's editable values, the admin's changes, and the two merged."""
    seed_tuning(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be an object")
    overlay = path.with_name(tuning_overrides.OVERLAY_NAME)
    return {
        "defaults": _editable(raw),
        "overrides": tuning_overrides.load(overlay),
        "effective": _editable(tuning_overrides.apply(raw, overlay)),
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_tuning_overrides.py tests/test_config_tuning.py -v`
Expected: PASS (existing `test_config_tuning.py` still passes).

- [ ] **Step 6: Commit**

```bash
git add apps/garrison/src/core/tuning_overrides.py apps/garrison/src/core/config_files.py apps/garrison/tests/test_tuning_overrides.py
git commit -m "feat(garrison): admin tuning overlay merged into config_tuning.json" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Cache invalidation across agent processes

**Files:**
- Modify: `apps/garrison/src/core/tuning_overrides.py` (append `on_change`, `poll`)
- Modify: `apps/garrison/src/llm/token_limits.py`, `decision.py`, `gateway_failover.py` (register resets)
- Modify: `apps/garrison/src/agents/agent_config.py` (`run_chat` start)
- Test: `apps/garrison/tests/test_tuning_overrides.py` (append)

**Interfaces:**
- Consumes: Task 1's `signature`, `PATH`.
- Produces: `tuning_overrides.on_change(reset: Callable[[], None]) -> None`, `tuning_overrides.poll(path: Path | None = None) -> None`, `gateway_failover.reset_cache()`.

- [ ] **Step 1: Write the failing test** (append to `test_tuning_overrides.py`)

```python
def test_poll_clears_registered_caches_once_per_change(tuning, monkeypatch):
    _, overlay = tuning
    calls = []
    monkeypatch.setattr(tuning_overrides, "_resets", [lambda: calls.append(1)])
    monkeypatch.setattr(tuning_overrides, "_seen", None)

    tuning_overrides.poll(overlay)                      # no file: nothing changed
    assert calls == []
    tuning_overrides.save({"classifier.triage_trace": True}, overlay)
    tuning_overrides.poll(overlay)
    tuning_overrides.poll(overlay)                      # same file: no second reset
    assert calls == [1]


def test_a_failing_reset_does_not_stop_the_others_or_the_turn(tuning, monkeypatch):
    _, overlay = tuning
    calls = []

    def boom():
        raise ValueError("bad file")

    monkeypatch.setattr(tuning_overrides, "_resets", [boom, lambda: calls.append(1)])
    monkeypatch.setattr(tuning_overrides, "_seen", None)
    tuning_overrides.save({"classifier.triage_trace": True}, overlay)
    tuning_overrides.poll(overlay)
    assert calls == [1]


def test_an_admin_edit_reaches_token_limits_after_poll(tuning, monkeypatch):
    from src.llm import token_limits

    path, overlay = tuning
    monkeypatch.setattr(token_limits, "_CONFIG_PATH", path)
    monkeypatch.setattr(tuning_overrides, "_seen", None)
    token_limits.reset_cache()
    assert token_limits.max_tool_rounds("anthropic") == 15
    tuning_overrides.save({"token_limits.default.max_tool_rounds": 30}, overlay)
    assert token_limits.max_tool_rounds("anthropic") == 15      # cached until the poll
    tuning_overrides.poll(overlay)
    assert token_limits.max_tool_rounds("anthropic") == 30
    token_limits.reset_cache()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_tuning_overrides.py -k "poll or reaches" -v`
Expected: FAIL, `AttributeError: ... '_resets'`.

- [ ] **Step 3: Append to `tuning_overrides.py`**

```python
_resets: list[Callable[[], None]] = []
_seen: int | None = None  # the overlay signature this process last acted on


def on_change(reset: Callable[[], None]) -> None:
    """Run `reset` (a reader's reset_cache) when poll() sees the overlay changed."""
    _resets.append(reset)


def poll(path: Path | None = None) -> None:
    """Call at the start of a turn. One stat; runs the registered resets only when the
    overlay was rewritten since the last call in this process. A failing reset is logged,
    never raised: a turn must not break because an edit was bad."""
    global _seen
    current = signature(path or PATH)
    if current == _seen:
        return
    _seen = current
    for reset in _resets:
        try:
            reset()
        except Exception:
            _log.exception("tuning reset %s failed", getattr(reset, "__name__", reset))
```

- [ ] **Step 4: Register the readers**

`token_limits.py` — add `from src.core import tuning_overrides` beside the existing `from src.core.config_files ...` import, and at the very end of the file:

```python
tuning_overrides.on_change(reset_cache)
```

`decision.py` — same import; after `def reset_cache()` (ends line ~353):

```python
tuning_overrides.on_change(reset_cache)
```

`gateway_failover.py` — same import; after the `_cooldown_settings()` priming line add:

```python
def reset_cache() -> None:
    """Reload the cooldowns now, so a later failure still never reads disk."""
    _cooldown_settings.cache_clear()
    _cooldown_settings()


tuning_overrides.on_change(reset_cache)
```

- [ ] **Step 5: Poll at turn start**

In `agent_config.py`, add `tuning_overrides` to the `from src.core import approvals, internal_auth, questions, tool_filter` import. In `run_chat`, as the first statement of the body after the docstring (before `request_token = cancellation.bind_request(request_id)`):

```python
    tuning_overrides.poll()
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_tuning_overrides.py tests/test_config_tuning.py tests/test_decision.py tests/test_gateway_failover.py tests/test_agent_config.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/garrison/src apps/garrison/tests/test_tuning_overrides.py
git commit -m "feat(garrison): pick up tuning overlay edits at the start of a turn" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Per-turn user limits

**Files:**
- Modify: `apps/garrison/src/llm/token_limits.py`, `llm_options.py`
- Modify: `apps/garrison/src/agents/agent_config.py` (`run_chat`)
- Modify: `apps/garrison/src/server.py` (`ask`, `status`)
- Test: `apps/garrison/tests/test_user_limits.py` (create)

**Interfaces:**
- Produces: `token_limits.USER_FIELDS = ("max_output_tokens", "max_tool_rounds")`, `token_limits.bind_user_limits(limits: dict | None) -> Token`, `token_limits.reset_user_limits(token)`, `token_limits.apply_user_limit(field: str, value: int) -> int`; `run_chat(..., limits: dict[str, int] | None = None)`; `ask(..., limits: dict[str, int] | None = None)`; `status()["user_limits"] is True`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/garrison/tests/test_user_limits.py
"""A user's own limits lower, never raise, what the admin allows."""

from types import SimpleNamespace
from unittest.mock import patch

from src import server
from src.llm import token_limits
from src.llm.llm_options import LlmOptions


def _options(max_tokens=None, max_tool_rounds=None):
    return LlmOptions("anthropic", "agent", SimpleNamespace(max_tokens=max_tokens, max_tool_rounds=max_tool_rounds))


def test_user_limit_lowers_the_effective_value():
    token = token_limits.bind_user_limits({"max_output_tokens": 500, "max_tool_rounds": 3})
    try:
        assert _options().max_tokens(2048) == 500
        assert _options().max_tool_rounds(15) == 3
    finally:
        token_limits.reset_user_limits(token)


def test_user_limit_never_raises_it():
    token = token_limits.bind_user_limits({"max_output_tokens": 9000})
    try:
        assert _options().max_tokens(2048) == 2048
    finally:
        token_limits.reset_user_limits(token)


def test_an_agent_files_own_cap_is_clamped_too():
    token = token_limits.bind_user_limits({"max_output_tokens": 500})
    try:
        assert _options(max_tokens=4096).max_tokens(2048) == 500
    finally:
        token_limits.reset_user_limits(token)


def test_without_limits_nothing_changes():
    assert _options().max_tokens(2048) == 2048
    assert _options().max_tool_rounds(15) == 15


def test_junk_limits_are_ignored():
    token = token_limits.bind_user_limits({"max_output_tokens": True, "max_tool_rounds": -1, "max_context_tokens": 5, "x": 1})
    try:
        assert token_limits.apply_user_limit("max_output_tokens", 2048) == 2048
        assert token_limits.apply_user_limit("max_tool_rounds", 15) == 15
        assert token_limits.apply_user_limit("max_context_tokens", 100) == 100
    finally:
        token_limits.reset_user_limits(token)


def test_limits_are_unset_after_the_turn():
    token = token_limits.bind_user_limits({"max_tool_rounds": 2})
    token_limits.reset_user_limits(token)
    assert token_limits.apply_user_limit("max_tool_rounds", 15) == 15


def test_status_says_ask_understands_limits():
    with patch.object(server.agent_config, "status", return_value={}):
        assert server.status()["user_limits"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_user_limits.py -v`
Expected: FAIL, `AttributeError: module 'src.llm.token_limits' has no attribute 'bind_user_limits'`.

- [ ] **Step 3: `token_limits.py`**

Change the imports to add `from contextvars import ContextVar, Token`, `from types import MappingProxyType`. Insert before `def reset_cache()`:

```python
# The asking user's own caps for one turn, set by run_chat from ask(limits=...). Like
# tool_filter.py it is a ContextVar, so the providers' signatures stay as they are.
USER_FIELDS = ("max_output_tokens", "max_tool_rounds")
_user_limits: ContextVar[Mapping[str, int]] = ContextVar("user_limits", default=MappingProxyType({}))


def bind_user_limits(limits: dict[str, Any] | None) -> Token:
    """Cap this turn at the user's values. Anything but a positive int for a known field is dropped."""
    clean = {
        field: value for field, value in (limits or {}).items()
        if field in USER_FIELDS and isinstance(value, int) and not isinstance(value, bool) and value > 0
    }
    return _user_limits.set(clean)


def reset_user_limits(token: Token) -> None:
    _user_limits.reset(token)


def apply_user_limit(field: str, value: int) -> int:
    """`value`, lowered to the user's cap for `field` when they set one. Never raises it."""
    cap = _user_limits.get().get(field)
    return value if cap is None else min(value, cap)
```

Add `from collections.abc import Mapping` to the imports.

- [ ] **Step 4: `llm_options.py`**

Add `from src.llm import token_limits` under the existing imports and replace the two methods:

```python
    def max_tokens(self, default: int) -> int:
        # An agent file's llm.max_tokens replaces the tuning default, so the user's cap is applied last.
        return token_limits.apply_user_limit("max_output_tokens", self._llm.max_tokens or default)

    def max_tool_rounds(self, default: int) -> int:
        return token_limits.apply_user_limit("max_tool_rounds", self._llm.max_tool_rounds or default)
```

- [ ] **Step 5: `run_chat` and `ask`**

`agent_config.py`: confirm `token_limits` is importable there (`grep -n token_limits src/agents/agent_config.py`; if absent add `from src.llm import token_limits`). Add the parameter `limits: dict[str, int] | None = None,` after `exact_context: bool = False,` in `run_chat`'s signature, add one line to its docstring (`limits: the asking user's own max_output_tokens / max_tool_rounds for this turn; they only lower the configured values (llm/token_limits.py).`), bind next to the other tokens, and reset in the `finally`:

```python
    limits_token = token_limits.bind_user_limits(limits)
```
```python
        token_limits.reset_user_limits(limits_token)
```
(put the reset first in the `finally` block, above `llm_options.reset_effort(effort_token)`).

`server.py`:
- `ask(...)` signature: add `limits: dict[str, int] | None = None,` after `exact_context: bool = False,`. Add to the docstring before `ctx,`: `limits: the asking user's own max_output_tokens and max_tool_rounds for this turn; they lower the configured values, never raise them.`
- Replace the `private_args = ...` line's neighbours so the call forwards it: add `limit_args = {"limits": limits} if limits else {}` after `private_args`, and `**limit_args` at the end of the `run_chat(...)` keyword list.
- `status()`: add `"user_limits": True,` after `"exact_context": True,` and `` `user_limits` says ask() understands limits.`` to its docstring.

- [ ] **Step 6: Add the forwarding test**

Find the existing test that calls `server.ask` with a patched `run_chat` (`grep -n "run_chat" tests/test_internal_auth.py tests/test_server.py`), copy its setup, and add:

```python
def test_ask_forwards_limits_to_run_chat():
    # same patching as the neighbouring ask() test; only the assertion differs
    ...
    assert run_chat.call_args.kwargs["limits"] == {"max_output_tokens": 500}
```
where the call is `asyncio.run(server.ask("hi", limits={"max_output_tokens": 500}))`. Also assert the key is absent when `limits` is not passed (`"limits" not in run_chat.call_args.kwargs`).

- [ ] **Step 7: Run to verify it passes**

Run: `python -m pytest tests/test_user_limits.py tests/test_llm_options.py tests/test_server.py tests/test_internal_auth.py tests/test_agent_config.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/garrison/src apps/garrison/tests
git commit -m "feat(garrison): per-turn user limits that only lower the configured caps" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `/agents/tuning` routes and docs

**Files:**
- Modify: `apps/garrison/src/server.py` (two routes after the prompts routes)
- Modify: `apps/garrison/configs/README.md`
- Test: `apps/garrison/tests/test_tuning_routes.py` (create)

**Interfaces:**
- Consumes: Task 1 `config_files.tuning_view`, `tuning_overrides.save/poll`.
- Produces: `GET /agents/tuning` -> `{defaults, overrides, effective}`; `PUT /agents/tuning` body `{dotted.path: value | null}` -> same body, `400 {"error": str}` on a bad change or non-object body. Both are protected by the existing `/agents` prefix in `PROTECTED_PATHS`.

- [ ] **Step 1: Write the failing test**

```python
# apps/garrison/tests/test_tuning_routes.py
"""/agents/tuning: what ember_api's admin page reads and writes."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src import server
from src.core import config_files, tuning_overrides


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "config_tuning.json"
    examples = Path(config_files.__file__).resolve().parents[2] / "configs"
    path.with_suffix(".json.example").write_bytes((examples / "config_tuning.json.example").read_bytes())
    monkeypatch.setattr(config_files, "TUNING_PATH", path)
    monkeypatch.setattr(tuning_overrides, "_seen", None)
    return TestClient(server.mcp.streamable_http_app())


def test_get_returns_defaults_overrides_and_effective(client):
    body = client.get("/agents/tuning").json()
    assert body["overrides"] == {}
    assert body["defaults"]["token_limits"]["default"]["max_tool_rounds"] == 15
    assert body["effective"] == body["defaults"]
    assert "chains" not in body["defaults"]["classifier"]


def test_put_saves_and_returns_the_merged_view(client):
    response = client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["overrides"] == {"token_limits.default.max_tool_rounds": 20}
    assert body["effective"]["token_limits"]["default"]["max_tool_rounds"] == 20
    assert body["defaults"]["token_limits"]["default"]["max_tool_rounds"] == 15


def test_put_null_resets_a_path(client):
    client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": 20})
    body = client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": None}).json()
    assert body["overrides"] == {}


def test_put_refuses_a_bad_change_and_saves_nothing(client):
    response = client.put("/agents/tuning", json={"token_limits.default.max_tool_rounds": 500, "classifier.triage_trace": True})
    assert response.status_code == 400
    assert "max_tool_rounds" in response.json()["error"]
    assert client.get("/agents/tuning").json()["overrides"] == {}


def test_put_refuses_a_body_that_is_not_an_object(client):
    assert client.put("/agents/tuning", json=[1]).status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_tuning_routes.py -v`
Expected: FAIL (404 on `/agents/tuning`).

- [ ] **Step 3: Add the routes** (in `server.py`, after `agent_prompts_put`; add `tuning_overrides` to the `src.core` imports and `config_files` if not yet imported there: `from src.core import config_files, tuning_overrides`)

```python
def _tuning_overlay() -> Path:
    return config_files.TUNING_PATH.with_name(tuning_overrides.OVERLAY_NAME)


@mcp.custom_route("/agents/tuning", methods=["GET"])
async def tuning_get(_request: Request) -> JSONResponse:
    """The editable tuning values: the file's, the admin's changes, and the two merged."""
    return JSONResponse(await asyncio.to_thread(config_files.tuning_view, config_files.TUNING_PATH))


@mcp.custom_route("/agents/tuning", methods=["PUT"])
async def tuning_put(request: Request) -> JSONResponse:
    """Body: {"token_limits.default.max_tool_rounds": 20, ...}; null puts a path back to the
    file's value. Nothing is saved if any change is refused. Each agent process picks the
    edit up at the start of its next turn."""
    changes = await _json_object(request)
    if changes is None:
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    try:
        await asyncio.to_thread(tuning_overrides.save, changes, _tuning_overlay())
    except tuning_overrides.TuningError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    tuning_overrides.poll(_tuning_overlay())
    return JSONResponse(await asyncio.to_thread(config_files.tuning_view, config_files.TUNING_PATH))
```

If `Path` is not imported in `server.py`, add `from pathlib import Path`.

- [ ] **Step 4: Document** — append to `apps/garrison/configs/README.md`:

```markdown
## tuning_overrides.json

Written by the admin Tuning page (ember_admin), not by hand. It holds only what an admin
changed, as flat dotted paths such as `"token_limits.default.max_tool_rounds": 20`, and is
merged over `config_tuning.json` when that file is read. Delete a line (or reset it on the page)
to go back to the file's value. Gitignore it like the other local configs. Keys that are not
listed in `src/core/tuning_overrides.py` (URLs, models, chains, `triage_order`) stay file-only.
Each agent process notices a change at the start of its next turn; no restart is needed.
```

Add `apps/garrison/configs/tuning_overrides.json` to the repo's `.gitignore` next to `config_tuning.json` (check with `git check-ignore -v apps/garrison/configs/config_tuning.json` to find the right file).

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_tuning_routes.py tests/test_server.py tests/test_internal_auth.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/garrison .gitignore
git commit -m "feat(garrison): /agents/tuning to read and edit the tuning overlay" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ember_api admin proxy and `tuning.manage`

**Files:**
- Modify: `apps/Ember/ember_api/src/services/permissions.py` (and every place `AGENTS_MANAGE` is listed)
- Modify: `apps/Ember/ember_api/src/services/agent_admin.py` (two methods)
- Create: `apps/Ember/ember_api/src/routes/admin_tuning.py`
- Modify: `apps/Ember/ember_api/src/app.py` (import + `include_router`)
- Test: `apps/Ember/ember_api/tests/test_admin_tuning.py`

**Interfaces:**
- Consumes: garrison `GET/PUT /agents/tuning` (Task 4).
- Produces: `AgentAdmin.tuning(account) -> dict`, `AgentAdmin.set_tuning(account, changes: dict) -> dict`; `GET /api/admin/tuning`, `PUT /api/admin/tuning` (body: `{"changes": {path: value|null}}`), permission `tuning.manage`; activity-log source `tuning.update`.

- [ ] **Step 1: Find every permission list**

Run: `grep -rn "AGENTS_MANAGE\|agents.manage" apps/Ember/ember_api/src apps/Ember/ember_api/migrations apps/Ember/ember_api/tests`
Add `TUNING_MANAGE = "tuning.manage"` with the description `"Change garrison's runtime tuning (token limits, failover, classifier)"` and put it in `STAFF_PERMISSIONS` and in every other list/seed/migration `AGENTS_MANAGE` appears in. If the permission is seeded by a migration (look at how `tickets.manage` was added: `grep -rn "tickets.manage" migrations`), add a migration `0026_tuning_manage.py` the same way; if seeding is code-only, no migration. Update any existing test that asserts the full permission list.

- [ ] **Step 2: Write the failing test**

```python
# apps/Ember/ember_api/tests/test_admin_tuning.py
"""/api/admin/tuning: forwarded to garrison's /agents/tuning, tuning.manage only."""

from __future__ import annotations

import json

import httpx

from tests.conftest import FakeEmailSender, FakeUpstream
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

VIEW = {"defaults": {"token_limits": {"default": {"max_tool_rounds": 15}}}, "overrides": {}, "effective": {"token_limits": {"default": {"max_tool_rounds": 15}}}}


def garrison(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/agents/tuning" and request.method == "GET":
        return httpx.Response(200, json=VIEW)
    if request.url.path == "/agents/tuning" and request.method == "PUT":
        changes = json.loads(request.content)
        if "bad" in changes:
            return httpx.Response(400, json={"error": "'bad' cannot be edited here"})
        return httpx.Response(200, json={**VIEW, "overrides": changes})
    return httpx.Response(404, json={"error": "no route"})


def test_admin_reads_and_edits(client, upstream: FakeUpstream) -> None:
    upstream.handler = garrison
    as_admin(client)

    assert client.get("/api/admin/tuning").json() == VIEW
    saved = client.put("/api/admin/tuning", json={"changes": {"token_limits.default.max_tool_rounds": 20}})
    assert saved.status_code == 200
    assert saved.json()["overrides"] == {"token_limits.default.max_tool_rounds": 20}
    sent = upstream.requests[-1]
    assert sent.headers["x-requester-username"] == "root"
    assert json.loads(sent.content) == {"token_limits.default.max_tool_rounds": 20}


def test_garrison_refusal_is_a_400_with_its_message(client, upstream: FakeUpstream) -> None:
    upstream.handler = garrison
    as_admin(client)
    refused = client.put("/api/admin/tuning", json={"changes": {"bad": 1}})
    assert (refused.status_code, refused.json()["detail"]) == (400, "'bad' cannot be edited here")


def test_garrison_down_is_a_502(client, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: httpx.Response(503, json={"error": "down"})
    as_admin(client)
    assert client.get("/api/admin/tuning").status_code == 502


def test_a_change_is_written_to_the_activity_log(client, upstream: FakeUpstream) -> None:
    upstream.handler = garrison
    as_admin(client)
    client.put("/api/admin/tuning", json={"changes": {"token_limits.default.max_tool_rounds": 20}})
    entries = client.get("/api/admin/logs", params={"kind": "activity"}).json()
    assert any(e["source"] == "tuning.update" for e in entries["entries"] if isinstance(entries, dict)) or any(
        e.get("source") == "tuning.update" for e in entries
    )


def test_a_member_without_the_permission_is_refused(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = garrison
    make_member(client, email)
    login(client, "alice")
    assert client.get("/api/admin/tuning").status_code == 403
    assert client.put("/api/admin/tuning", json={"changes": {}}).status_code == 403
```

Before relying on the log assertion, run `grep -n "api/admin/logs\|kind" tests/test_agent_admin.py tests/test_logs.py | head` and replace the last assertion with whatever the existing agent-admin test does to check `agents.update` was logged.

- [ ] **Step 3: Run to verify it fails**

Run (in `apps/Ember/ember_api`): `python -m pytest tests/test_admin_tuning.py -v`
Expected: FAIL (404 on the routes).

- [ ] **Step 4: `AgentAdmin` methods** — add after `gateways()` in `services/agent_admin.py`:

```python
    async def tuning(self, account: Account) -> dict[str, Any]:
        """garrison's editable tuning: {defaults, overrides, effective}."""
        return await self._request("GET", "/agents/tuning", account)

    async def set_tuning(self, account: Account, changes: dict[str, Any]) -> dict[str, Any]:
        """Save `changes` (dotted path -> value, None = back to the file's value); returns the new view."""
        return await self._request("PUT", "/agents/tuning", account, json=changes)
```

- [ ] **Step 5: The route**

```python
# apps/Ember/ember_api/src/routes/admin_tuning.py
"""/api/admin/tuning: garrison's runtime tuning (token limits, failover, classifier).

Needs tuning.manage. garrison validates and stores the edit in its overlay file; each
agent applies it at the start of its next turn. Every change is written to the activity log."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.routes.agent_admin import _call, get_agent_admin
from src.services.agent_admin import AgentAdmin
from src.services.log_service import LogWriter
from src.services.permissions import TUNING_MANAGE

router = APIRouter(prefix="/api/admin/tuning", tags=["tuning"])

require_tuning_manage = require_permission(TUNING_MANAGE)


class TuningChangesIn(BaseModel):
    changes: dict[str, Any]


@router.get("")
async def read_tuning(account: Account = Depends(require_tuning_manage), admin: AgentAdmin = Depends(get_agent_admin)) -> Any:
    return await _call(admin.tuning(account))


@router.put("")
async def update_tuning(
    body: TuningChangesIn,
    account: Account = Depends(require_tuning_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    view = await _call(admin.set_tuning(account, body.changes))
    await logs.action(account, "tuning.update", "Changed tuning: " + ", ".join(f"{k}={v}" for k, v in body.changes.items())[:500])
    return view
```

`_call` maps garrison 400 to `HTTPException(400, str(error))` already only for 404/409 -> else 400, so a refusal is 400 with the message in `detail`. In `app.py` import `admin_tuning` with the other routes and `app.include_router(admin_tuning.router)` after `agent_admin.prompts_router`.

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_admin_tuning.py tests/test_agent_admin.py tests/test_admin.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/Ember/ember_api
git commit -m "feat(ember_api): admin tuning proxy behind tuning.manage" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: ember_api per-account limits and the chat path

**Files:**
- Create: `apps/Ember/ember_api/src/services/tuning_limits_service.py`
- Create: `apps/Ember/ember_api/src/routes/account_tuning.py`
- Modify: `apps/Ember/ember_api/src/app.py` (include router), account-deletion purge (where `nav_preference_service.purge_owner` is called: `grep -rn purge_owner src`)
- Modify: `apps/Ember/ember_api/src/services/turns.py` (`TurnOptions.limits`, the `ask(...)` call), `src/services/agent_gateway.py` (`ask(limits=...)`), `src/routes/chats.py` (load limits), `tests/conftest.py` (`FakeAgent.ask` accepts `limits`)
- Test: `tests/test_account_tuning.py`, extend `tests/test_agent_gateway.py`

**Interfaces:**
- Consumes: `AgentAdmin.tuning(account)` (Task 5), garrison `status().user_limits` and `ask(limits=...)` (Task 3).
- Produces: `TuningLimitsService(store: DocumentStore, owner_uid: str)` with `get() -> dict[str, int]`, `replace(limits: dict[str, int | None]) -> dict[str, int]`, `reset()`, and module `purge_owner(store, uid)`; `GET/PUT/DELETE /api/account/tuning`; `TurnOptions.limits: dict[str, int]`; `AgentGateway.ask(..., limits: dict[str, int] | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/Ember/ember_api/tests/test_account_tuning.py
"""/api/account/tuning: the logged-in account's own response limits."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from tests.conftest import FakeUpstream
from tests.test_registration import as_admin

URL = "/api/account/tuning"
VIEW = {"defaults": {}, "overrides": {}, "effective": {"token_limits": {"default": {"max_output_tokens": 2048, "max_tool_rounds": 15}}}}


def garrison_up(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=VIEW)


def test_needs_login(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={}).status_code == 401


def test_default_is_unset_with_the_admin_values_as_ceiling(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = garrison_up
    as_admin(client)
    assert client.get(URL).json() == {
        "limits": {"max_output_tokens": None, "max_tool_rounds": None},
        "ceiling": {"max_output_tokens": 2048, "max_tool_rounds": 15},
    }


def test_save_read_back_and_clear_one(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = garrison_up
    as_admin(client)
    saved = client.put(URL, json={"max_output_tokens": 500, "max_tool_rounds": 4})
    assert saved.status_code == 200
    assert saved.json()["limits"] == {"max_output_tokens": 500, "max_tool_rounds": 4}
    cleared = client.put(URL, json={"max_output_tokens": None, "max_tool_rounds": 4})
    assert cleared.json()["limits"] == {"max_output_tokens": None, "max_tool_rounds": 4}


def test_value_above_the_admin_ceiling_is_refused(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = garrison_up
    as_admin(client)
    over = client.put(URL, json={"max_output_tokens": 5000, "max_tool_rounds": 4})
    assert over.status_code == 400
    assert "2048" in over.json()["detail"]
    assert client.get(URL).json()["limits"]["max_tool_rounds"] is None


def test_out_of_range_is_a_422(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = garrison_up
    as_admin(client)
    assert client.put(URL, json={"max_tool_rounds": 0}).status_code == 422
    assert client.put(URL, json={"max_tool_rounds": 101}).status_code == 422


def test_garrison_down_still_reads_but_cannot_save(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = garrison_up
    as_admin(client)
    client.put(URL, json={"max_tool_rounds": 4})
    upstream.handler = lambda request: httpx.Response(503, json={"error": "down"})
    body = client.get(URL).json()
    assert body["limits"]["max_tool_rounds"] == 4
    assert body["ceiling"] == {"max_output_tokens": None, "max_tool_rounds": None}
    assert client.put(URL, json={"max_tool_rounds": 3}).status_code == 502


def test_delete_clears_everything(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = garrison_up
    as_admin(client)
    client.put(URL, json={"max_tool_rounds": 4})
    assert client.delete(URL).status_code == 204
    assert client.get(URL).json()["limits"] == {"max_output_tokens": None, "max_tool_rounds": None}
```

Add to `tests/test_agent_gateway.py` a test next to the existing `exact_context`/`private_extensions` ones (copy its fake MCP setup): with a status that has `user_limits: True`, `ask(..., limits={"max_output_tokens": 500})` sends `arguments["limits"] == {"max_output_tokens": 500}`; with a status lacking `user_limits` the key is absent and the turn still runs.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_account_tuning.py -v`
Expected: FAIL (404).

- [ ] **Step 3: The service**

```python
# apps/Ember/ember_api/src/services/tuning_limits_service.py
"""Per-account response limits: how many tokens an answer may use and how many tool rounds it may take.

One document per account in treasury (collection "tuning_limits", key the account uid), like
nav_preferences. A missing field means "use the admin's value". garrison applies them as
min(user, admin), so they can only lower what the admin allows."""

from __future__ import annotations

from src.db import utcnow
from src.services.db_gateway import DocumentStore

COLLECTION = "tuning_limits"
FIELDS = ("max_output_tokens", "max_tool_rounds")
# Same outer bounds garrison's allowlist uses for these two keys.
BOUNDS = {"max_output_tokens": (1, 200_000), "max_tool_rounds": (1, 100)}


class TuningLimitsService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def get(self) -> dict[str, int]:
        doc = await self._store.get(COLLECTION, self._owner)
        if doc is None:
            return {}
        return {f: doc[f] for f in FIELDS if isinstance(doc.get(f), int) and not isinstance(doc.get(f), bool)}

    async def replace(self, limits: dict[str, int | None]) -> dict[str, int]:
        kept = {f: limits[f] for f in FIELDS if limits.get(f) is not None}
        if not kept:
            await self._store.delete(COLLECTION, self._owner)
            return {}
        await self._store.put(COLLECTION, self._owner, {
            "owner": self._owner, **kept, "updated_at": utcnow().isoformat(timespec="seconds"),
        })
        return kept

    async def reset(self) -> None:
        await self._store.delete(COLLECTION, self._owner)


async def purge_owner(store: DocumentStore, owner_uid: str) -> None:
    """Forget one account's limits (used when the account is deleted)."""
    await store.delete(COLLECTION, owner_uid)
```

- [ ] **Step 4: The route**

```python
# apps/Ember/ember_api/src/routes/account_tuning.py
"""/api/account/tuning: the logged-in account's own response limits (lower only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.deps import current_account, get_db_gateway
from src.models import Account
from src.routes.agent_admin import get_agent_admin
from src.services.agent_admin import AgentAdmin, AgentAdminRefused, AgentAdminUnavailable
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.tuning_limits_service import FIELDS, TuningLimitsService

router = APIRouter(prefix="/api/account/tuning", tags=["account-tuning"])


def get_limits_service(
    account: Account = Depends(current_account), store: DocumentStore = Depends(get_db_gateway)
) -> TuningLimitsService:
    return TuningLimitsService(store, account.uid)


class LimitsBody(BaseModel):
    max_output_tokens: int | None = Field(default=None, ge=1, le=200_000)
    max_tool_rounds: int | None = Field(default=None, ge=1, le=100)


class LimitsOut(BaseModel):
    limits: LimitsBody
    ceiling: LimitsBody


async def _ceiling(admin: AgentAdmin, account: Account) -> LimitsBody:
    """The admin's current values (what the user's own can not exceed); empty when garrison is unreachable."""
    try:
        default = (await admin.tuning(account))["effective"]["token_limits"]["default"]
    except (AgentAdminUnavailable, AgentAdminRefused, KeyError, TypeError):
        return LimitsBody()
    return LimitsBody(**{f: default.get(f) for f in FIELDS})


@router.get("")
async def read_limits(
    account: Account = Depends(current_account),
    service: TuningLimitsService = Depends(get_limits_service),
    admin: AgentAdmin = Depends(get_agent_admin),
) -> LimitsOut:
    try:
        stored = await service.get()
    except DbGatewayError:
        stored = {}
    return LimitsOut(limits=LimitsBody(**stored), ceiling=await _ceiling(admin, account))


@router.put("")
async def save_limits(
    body: LimitsBody,
    account: Account = Depends(current_account),
    service: TuningLimitsService = Depends(get_limits_service),
    admin: AgentAdmin = Depends(get_agent_admin),
) -> LimitsOut:
    """Saves both values (null clears one). Refused while garrison is unreachable, because
    the admin's current value is the cap."""
    try:
        admin_values = (await admin.tuning(account))["effective"]["token_limits"]["default"]
    except (AgentAdminUnavailable, AgentAdminRefused, KeyError, TypeError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The agents are unreachable, so limits cannot be checked") from error
    for field in FIELDS:
        value, cap = getattr(body, field), admin_values.get(field)
        if value is not None and isinstance(cap, int) and value > cap:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} cannot be above {cap}")
    try:
        stored = await service.replace(body.model_dump())
    except DbGatewayError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Limits storage is unavailable") from error
    return LimitsOut(limits=LimitsBody(**stored), ceiling=LimitsBody(**{f: admin_values.get(f) for f in FIELDS}))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def reset_limits(service: TuningLimitsService = Depends(get_limits_service)) -> Response:
    try:
        await service.reset()
    except DbGatewayError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Limits storage is unavailable") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

`get_agent_admin(request)` needs only `request`, so it works for any logged-in account. Include the router in `app.py` after `nav_preferences.router`, and call `tuning_limits_service.purge_owner(store, uid)` wherever `nav_preference_service.purge_owner` is called.

- [ ] **Step 5: Carry the limits into the turn**

- `services/turns.py`: in `TurnOptions` add after `disabled_tools`:
  ```python
      # The account's own response limits (max_output_tokens, max_tool_rounds); they only lower the admin's.
      limits: dict[str, int] = field(default_factory=dict)
  ```
  and in the `self._gateway.ask(...)` call add `limits=dict(turn.options.limits) or None,` after `private_extensions=...`.
- `services/agent_gateway.py` `ask`: add `limits=None,` to the keyword parameters, and before `return await self._call(url, caller, "ask", arguments, on_event)`:
  ```python
          if limits:
              # Not fail-closed: an agent from before this existed simply keeps the admin's values.
              status = await self._call(url, caller, "status", {})
              if status.get("user_limits"):
                  arguments["limits"] = limits
  ```
  Also add `limits=None` to the protocol/base `ask` signature at line ~62 if the class has one (`grep -n "disabled_tools" src/services/agent_gateway.py` shows both places).
- `routes/chats.py`: import `TuningLimitsService` and, directly before the `try: options = TurnOptions(` block (~line 815), add:
  ```python
      try:
          limits = await TuningLimitsService(store, account.uid).get()
      except DbGatewayError:
          limits = {}
  ```
  using the same `store` variable the private-extensions lookup above it uses (read the lines just above to get its name), then pass `limits=limits,` into `TurnOptions(...)`.
- `tests/conftest.py` `FakeAgent.ask`: add `limits=None` next to `disabled_tools` and record it the way `disabled_tools` is recorded, then add a chat-turn test in `tests/test_account_tuning.py` (copy the smallest existing test that starts a turn, e.g. one that asserts `disabled_tools`) asserting a saved `{"max_tool_rounds": 4}` reaches `FakeAgent` as `limits == {"max_tool_rounds": 4}` and that a turn where only the `tuning_limits` read fails still runs with `limits == {}`. Fail just that collection in the fake, not the whole store: `chats.py` returns 503 when the disabled-agents read fails, and that must stay (closed on failure, so a switched-off agent is never offered).

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_account_tuning.py tests/test_agent_gateway.py tests/test_chats.py tests/test_turns.py tests/test_nav_preferences.py -q`
Expected: PASS. Then the whole suite: `python -m pytest -q` (expected: PASS).

- [ ] **Step 7: Commit**

```bash
git add apps/Ember/ember_api
git commit -m "feat(ember_api): per-account response limits sent with each chat turn" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: ember_admin Tuning page

**Files:**
- Create: `apps/Ember/ember_admin/src/api/TuningClient.ts`
- Create: `apps/Ember/ember_admin/src/views/TuningAdminView.vue`
- Modify: `apps/Ember/ember_admin/src/router/index.ts`, `src/router/pages.ts`
- Test: `apps/Ember/ember_admin/src/views/TuningAdminView.test.ts`

**Interfaces:**
- Consumes: `GET/PUT /api/admin/tuning` (Task 5).
- Produces: `tuningClient.get(): Promise<TuningView>`, `tuningClient.save(changes: Record<string, number | boolean | null>): Promise<TuningView>`.

- [ ] **Step 1: Read first** `.agents/skills/ember-frontend-design/SKILL.md`, the `ember-design-system` skill, `src/components/admin/SettingsPanel.vue` and `src/views/WorkspaceSettingsView.vue`. Use their page layout, panel, row, Save/Cancel bar and "changed" dot patterns; the markup below uses plain elements and must be mapped onto those components and classes (no new colors, one radius scale, no reduced-motion handling).

- [ ] **Step 2: The client**

```ts
// apps/Ember/ember_admin/src/api/TuningClient.ts
import { apiRequest } from "./http";

/** garrison's editable tuning as ember_api returns it (/api/admin/tuning). */
export interface TuningView {
  /** What config_tuning.json says (editable sections only). */
  defaults: Record<string, unknown>;
  /** What an admin changed: dotted path -> value. */
  overrides: Record<string, number | boolean>;
  /** The two merged; what the agents use. */
  effective: Record<string, unknown>;
}

export type TuningChanges = Record<string, number | boolean | null>;

export const tuningClient = {
  /** tuning.manage only. */
  get: () => apiRequest<TuningView>("GET", "/api/admin/tuning"),
  /** tuning.manage only. A null value puts a path back to the file's value. Nothing is saved if one change is refused. */
  save: (changes: TuningChanges) => apiRequest<TuningView>("PUT", "/api/admin/tuning", { changes }),
};
```

- [ ] **Step 3: Write the failing test**

```ts
// apps/Ember/ember_admin/src/views/TuningAdminView.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import { tuningClient, type TuningView } from "../api/TuningClient";
import TuningAdminView from "./TuningAdminView.vue";

vi.mock("../api/TuningClient", () => ({ tuningClient: { get: vi.fn(), save: vi.fn() } }));

const view = (overrides: TuningView["overrides"] = {}): TuningView => {
  const defaults = {
    token_limits: { default: { max_output_tokens: 2048, max_context_tokens: 100000, max_tool_rounds: 15 } },
    gateway_failover: { quota_cooldown_seconds: 3600, auth_cooldown_seconds: 3600, unavailable_cooldown_seconds: 30 },
    classifier: {
      timeout_seconds: 3, max_input_chars: 16000, triage_fallback: false, triage_trace: false, triage_window: 4096,
      triage_prune_ratio: 0.25, triage_pair_ratio: 0.5,
      triage_thresholds: { "2": { jev: 0.9 }, "3+": { jev: 0.9 } },
      triage_enabled: { jev: { choice: true, noul: true, score: true } },
    },
  };
  return { defaults, overrides, effective: defaults };
};

beforeEach(() => vi.clearAllMocks());

async function show(v: TuningView) {
  vi.mocked(tuningClient.get).mockResolvedValue(v);
  const wrapper = mount(TuningAdminView);
  await flushPromises();
  return wrapper;
}

it("shows the effective value and sends only the edited field on Save", async () => {
  const wrapper = await show(view());
  const rounds = wrapper.get('[data-path="token_limits.default.max_tool_rounds"]');
  expect((rounds.element as HTMLInputElement).value).toBe("15");

  await rounds.setValue("20");
  vi.mocked(tuningClient.save).mockResolvedValue(view({ "token_limits.default.max_tool_rounds": 20 }));
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();

  expect(tuningClient.save).toHaveBeenCalledWith({ "token_limits.default.max_tool_rounds": 20 });
});

it("marks a changed field and resets it with null", async () => {
  const wrapper = await show(view({ "gateway_failover.quota_cooldown_seconds": 60 }));
  const row = wrapper.get('[data-row="gateway_failover.quota_cooldown_seconds"]');
  expect(row.attributes("data-changed")).toBe("true");

  vi.mocked(tuningClient.save).mockResolvedValue(view());
  await row.get('[data-test="reset"]').trigger("click");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();

  expect(tuningClient.save).toHaveBeenCalledWith({ "gateway_failover.quota_cooldown_seconds": null });
});

it("toggles a boolean and saves it", async () => {
  const wrapper = await show(view());
  vi.mocked(tuningClient.save).mockResolvedValue(view({ "classifier.triage_trace": true }));
  await wrapper.get('[data-path="classifier.triage_trace"]').setValue(true);
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(tuningClient.save).toHaveBeenCalledWith({ "classifier.triage_trace": true });
});

it("shows the refusal and keeps the draft", async () => {
  const wrapper = await show(view());
  vi.mocked(tuningClient.save).mockRejectedValue(new Error("token_limits.default.max_tool_rounds must be from 1 and up to 100"));
  const rounds = wrapper.get('[data-path="token_limits.default.max_tool_rounds"]');
  await rounds.setValue("500");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("must be from 1 and up to 100");
  expect((rounds.element as HTMLInputElement).value).toBe("500");
});

it("disables Save until something changed", async () => {
  const wrapper = await show(view());
  expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
});
```

- [ ] **Step 4: Run to verify it fails**

Run (in `apps/Ember/ember_admin`): `npx vitest run src/views/TuningAdminView.test.ts`
Expected: FAIL (cannot resolve `./TuningAdminView.vue`).

- [ ] **Step 5: The view** (script is final; map the template's elements onto the design system's page/panel/row components per Step 1)

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import PageLayout from "../components/PageLayout.vue";
import { tuningClient, type TuningChanges, type TuningView } from "../api/TuningClient";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** One editable value: where it lives in config_tuning.json, how to label it, and its bounds
 * (the same ones garrison enforces; garrison's answer is what the page shows on a refusal). */
interface Field {
  path: string;
  label: string;
  kind: "int" | "number" | "bool";
  unit?: string;
  min?: number;
  max?: number;
}
interface Group { id: string; title: string; note: string; fields: Field[] }

const VOTERS = ["laya-english", "laya-typed", "jev"];
const KINDS = ["choice", "noul", "score"];

const GROUPS: Group[] = [
  {
    id: "limits", title: "Token limits", note: "The default for every provider. A user can set a lower value of their own for output and tool rounds.",
    fields: [
      { path: "token_limits.default.max_output_tokens", label: "Max output tokens", kind: "int", min: 1, max: 200000 },
      { path: "token_limits.default.max_context_tokens", label: "Max context tokens", kind: "int", min: 1000, max: 2000000 },
      { path: "token_limits.default.max_tool_rounds", label: "Max tool rounds", kind: "int", min: 1, max: 100 },
    ],
  },
  {
    id: "failover", title: "Gateway failover", note: "How long a failing gateway is skipped before it is tried again.",
    fields: [
      { path: "gateway_failover.quota_cooldown_seconds", label: "After a quota error", kind: "number", unit: "s", min: 0, max: 604800 },
      { path: "gateway_failover.auth_cooldown_seconds", label: "After an auth error", kind: "number", unit: "s", min: 0, max: 604800 },
      { path: "gateway_failover.unavailable_cooldown_seconds", label: "After an outage", kind: "number", unit: "s", min: 0, max: 604800 },
    ],
  },
  {
    id: "classifier", title: "Classifier", note: "Changes how questions are routed. Nothing checks the result of an edit, so change one value at a time.",
    fields: [
      { path: "classifier.timeout_seconds", label: "Timeout", kind: "number", unit: "s", min: 0.1, max: 60 },
      { path: "classifier.max_input_chars", label: "Max input characters", kind: "int", min: 1, max: 1000000 },
      { path: "classifier.triage_window", label: "Triage window", kind: "int", min: 512, max: 32768 },
      { path: "classifier.triage_prune_ratio", label: "Prune ratio", kind: "number", min: 0, max: 0.99 },
      { path: "classifier.triage_pair_ratio", label: "Pair ratio", kind: "number", min: 0.01, max: 1 },
      { path: "classifier.triage_fallback", label: "Use the fallback classifier", kind: "bool" },
      { path: "classifier.triage_trace", label: "Trace decisions", kind: "bool" },
    ],
  },
  {
    id: "thresholds", title: "Confidence thresholds", note: "A voter's answer counts only above this confidence. 2 = two options, 3+ = three or more.",
    fields: ["2", "3+"].flatMap((count) => VOTERS.map((voter): Field => ({
      path: `classifier.triage_thresholds.${count}.${voter}`, label: `${voter}, ${count} options`, kind: "number", min: 0.01, max: 1,
    }))),
  },
  {
    id: "voters", title: "Voters", note: "Which voter may answer which kind of question.",
    fields: VOTERS.flatMap((voter) => KINDS.map((kind): Field => ({
      path: `classifier.triage_enabled.${voter}.${kind}`, label: `${voter}, ${kind}`, kind: "bool",
    }))),
  },
];

const view = ref<TuningView | null>(null);
const draft = ref<Record<string, number | boolean | null>>({});
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);

/** Reads `a.b.c` out of a nested object. */
function at(source: Record<string, unknown> | undefined, path: string): number | boolean | undefined {
  let node: unknown = source;
  for (const part of path.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "number" || typeof node === "boolean" ? node : undefined;
}

const dirty = computed(() => Object.keys(draft.value).length > 0);
const isChanged = (path: string): boolean => path in (view.value?.overrides ?? {});
/** What the field shows: the draft when edited, else the value the agents use now. */
function shown(field: Field): number | boolean | "" {
  if (field.path in draft.value) return draft.value[field.path] ?? at(view.value?.defaults, field.path) ?? "";
  return at(view.value?.effective, field.path) ?? "";
}

function edit(field: Field, raw: string | boolean): void {
  saveError.value = "";
  const next = field.kind === "bool" ? raw === true : raw === "" ? NaN : Number(raw);
  const current = at(view.value?.effective, field.path);
  if (Number.isNaN(next) || next === current) delete draft.value[field.path];
  else draft.value[field.path] = next;
  draft.value = { ...draft.value };
}

/** Stage a return to the file's value; it applies on Save like any edit. */
function reset(field: Field): void {
  draft.value = { ...draft.value, [field.path]: null };
}

function cancel(): void {
  draft.value = {};
  saveError.value = "";
}

async function load(): Promise<void> {
  loadError.value = "";
  try {
    view.value = await tuningClient.get();
  } catch (error) {
    loadError.value = errorMessage(error);
  }
}

async function save(): Promise<void> {
  saving.value = true;
  saveError.value = "";
  try {
    view.value = await tuningClient.save(draft.value as TuningChanges);
    draft.value = {};
  } catch (error) {
    saveError.value = errorMessage(error);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageLayout class="admin-panel" title="Tuning" description="Runtime limits and routing for the agents. Applies to every account; each agent picks a change up at the start of its next answer.">
    <p v-if="loadError" role="alert">{{ loadError }}</p>
    <template v-else-if="view">
      <section v-for="group in GROUPS" :key="group.id" class="panel">
        <h2>{{ group.title }}</h2>
        <p>{{ group.note }}</p>
        <div v-for="field in group.fields" :key="field.path" class="row" :data-row="field.path" :data-changed="isChanged(field.path)">
          <label :for="field.path">{{ field.label }}</label>
          <input v-if="field.kind === 'bool'" :id="field.path" :data-path="field.path" type="checkbox" :checked="shown(field) === true" @change="edit(field, ($event.target as HTMLInputElement).checked)" />
          <input v-else :id="field.path" :data-path="field.path" type="number" :min="field.min" :max="field.max" :step="field.kind === 'int' ? 1 : 'any'" :value="shown(field)" @input="edit(field, ($event.target as HTMLInputElement).value)" />
          <span v-if="field.unit">{{ field.unit }}</span>
          <span v-if="isChanged(field.path) || field.path in draft" class="changed-dot" title="Differs from config_tuning.json" />
          <button v-if="isChanged(field.path) && draft[field.path] !== null" type="button" data-test="reset" @click="reset(field)">Reset</button>
        </div>
      </section>
      <p v-if="saveError" role="alert">{{ saveError }}</p>
      <div class="actions">
        <button type="button" data-test="cancel" :disabled="!dirty || saving" @click="cancel">Cancel</button>
        <button type="button" data-test="save" :disabled="!dirty || saving" @click="save">Save</button>
      </div>
    </template>
  </PageLayout>
</template>
```

- [ ] **Step 6: Route and nav**

`router/index.ts`: add next to the `admin-settings` route (line ~42), inside the same children list:

```ts
        { path: "tuning", name: "admin-tuning", component: () => import("../views/TuningAdminView.vue"), meta: { permission: "tuning.manage" } },
```

`router/pages.ts`: add `"tuning.manage"` to `ADMIN_PERMISSIONS`; add to `ADMIN_SECTIONS` after the "Workspace settings" entry:

```ts
  { to: "/admin/tuning", label: "Tuning", icon: ["M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3", "M1 14h6M9 8h6M17 16h6"], permission: "tuning.manage" },
```
and add `"/admin/tuning"` to `DEFAULT_ORDER` after `"/admin/settings"`. Update `router/index.test.ts` / `pages` tests that assert the page list (run the suite to find them).

- [ ] **Step 7: Run to verify it passes**

Run: `npx vitest run` then `npx vue-tsc -b`
Expected: all PASS, no type errors (including `radiusScale.test.ts` and `pageLayout.test.ts`, which police the design rules).

- [ ] **Step 8: Commit**

```bash
git add apps/Ember/ember_admin
git commit -m "feat(ember_admin): Tuning page for garrison's runtime limits" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: ember_web "Response limits" in Settings

**Files:**
- Create: `apps/Ember/ember_web/src/api/navigation/TuningClient.ts`
- Create: `apps/Ember/ember_web/src/features/settings/components/ResponseLimits.vue`
- Modify: `apps/Ember/ember_web/src/features/settings/SettingsView.vue` (mount it)
- Test: `apps/Ember/ember_web/src/features/settings/components/ResponseLimits.test.ts`

**Interfaces:**
- Consumes: `GET/PUT/DELETE /api/account/tuning` (Task 6).
- Produces: `tuningClient.get(): Promise<AccountLimits>`, `tuningClient.save(limits: Limits): Promise<AccountLimits>`, `tuningClient.reset(): Promise<void>`.

- [ ] **Step 1: Read first** the two frontend skills, `src/features/settings/components/SidebarEditor.vue` (an account-scoped, save-on-click group) and how `SettingsView.vue` places `SidebarEditor` (search for `SidebarEditor` and the `sidebar` group in `GROUPS`/`DEFS`). Mount `ResponseLimits` the same way, as a group titled "Response limits" with scope "Your account", and register it in `DEFS` so the search box finds it (label "Response limits", keywords `["tokens", "tool rounds", "length", "output"]`). Use `SettingRow` and the existing number-input style.

- [ ] **Step 2: The client**

```ts
// apps/Ember/ember_web/src/api/navigation/TuningClient.ts
import { apiRequest } from "../http";

/** The two caps a user may lower for their own answers. null = use the admin's value. */
export interface Limits {
  max_output_tokens: number | null;
  max_tool_rounds: number | null;
}

export interface AccountLimits {
  limits: Limits;
  /** The admin's current values: a user value above them is refused. null when the agents are unreachable. */
  ceiling: Limits;
}

/** ember_api's /api/account/tuning routes (any logged-in account). */
export const tuningClient = {
  get: () => apiRequest<AccountLimits>("GET", "/api/account/tuning"),
  save: (limits: Limits) => apiRequest<AccountLimits>("PUT", "/api/account/tuning", limits),
  reset: () => apiRequest<void>("DELETE", "/api/account/tuning"),
};
```

- [ ] **Step 3: Write the failing test**

```ts
// apps/Ember/ember_web/src/features/settings/components/ResponseLimits.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import { tuningClient, type AccountLimits } from "../../../api/navigation/TuningClient";
import ResponseLimits from "./ResponseLimits.vue";

vi.mock("../../../api/navigation/TuningClient", () => ({ tuningClient: { get: vi.fn(), save: vi.fn(), reset: vi.fn() } }));

const body = (limits: Partial<AccountLimits["limits"]> = {}): AccountLimits => ({
  limits: { max_output_tokens: null, max_tool_rounds: null, ...limits },
  ceiling: { max_output_tokens: 2048, max_tool_rounds: 15 },
});

beforeEach(() => vi.clearAllMocks());

async function show(value: AccountLimits) {
  vi.mocked(tuningClient.get).mockResolvedValue(value);
  const wrapper = mount(ResponseLimits);
  await flushPromises();
  return wrapper;
}

it("shows the admin value as the maximum and an empty box when unset", async () => {
  const wrapper = await show(body());
  const rounds = wrapper.get('[data-field="max_tool_rounds"]');
  expect((rounds.element as HTMLInputElement).value).toBe("");
  expect(rounds.attributes("max")).toBe("15");
  expect(wrapper.text()).toContain("15");
});

it("saves both values, sending null for an empty box", async () => {
  const wrapper = await show(body());
  vi.mocked(tuningClient.save).mockResolvedValue(body({ max_tool_rounds: 4 }));
  await wrapper.get('[data-field="max_tool_rounds"]').setValue("4");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(tuningClient.save).toHaveBeenCalledWith({ max_output_tokens: null, max_tool_rounds: 4 });
});

it("shows the refusal when a value is above the admin's", async () => {
  const wrapper = await show(body());
  vi.mocked(tuningClient.save).mockRejectedValue(new Error("max_tool_rounds cannot be above 15"));
  await wrapper.get('[data-field="max_tool_rounds"]').setValue("40");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("cannot be above 15");
});

it("clears both limits", async () => {
  const wrapper = await show(body({ max_tool_rounds: 4 }));
  vi.mocked(tuningClient.reset).mockResolvedValue(undefined);
  await wrapper.get('[data-test="clear"]').trigger("click");
  await flushPromises();
  expect(tuningClient.reset).toHaveBeenCalled();
  expect((wrapper.get('[data-field="max_tool_rounds"]').element as HTMLInputElement).value).toBe("");
});

it("keeps Save off until a value changed", async () => {
  const wrapper = await show(body({ max_tool_rounds: 4 }));
  expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
});
```

- [ ] **Step 4: Run to verify it fails**

Run (in `apps/Ember/ember_web`): `npx vitest run src/features/settings/components/ResponseLimits.test.ts`
Expected: FAIL (cannot resolve `./ResponseLimits.vue`).

- [ ] **Step 5: The component** (script is final; map the template onto `SettingRow`/the page's number-input style per Step 1)

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { tuningClient, type AccountLimits, type Limits } from "../../../api/navigation/TuningClient";
import { errorMessage } from "../../../utils/errors";

/** Two caps for the user's own answers. They only lower what the admin allows, so each box's
 * maximum is the admin's current value. Empty = use the admin's value. */
const FIELDS = [
  { id: "max_output_tokens", label: "Longest answer", unit: "tokens", hint: "The most one reply may use." },
  { id: "max_tool_rounds", label: "Most tool rounds", unit: "rounds", hint: "How many times the agent may use tools before it must answer." },
] as const;

const stored = ref<AccountLimits | null>(null);
const draft = ref<Record<string, string>>({});
const error = ref("");
const saving = ref(false);

const text = (value: number | null): string => (value === null ? "" : String(value));

function adopt(value: AccountLimits): void {
  stored.value = value;
  draft.value = Object.fromEntries(FIELDS.map((f) => [f.id, text(value.limits[f.id])]));
}

const dirty = computed(() => stored.value !== null && FIELDS.some((f) => draft.value[f.id] !== text(stored.value!.limits[f.id])));
const anySet = computed(() => stored.value !== null && FIELDS.some((f) => stored.value!.limits[f.id] !== null));

function payload(): Limits {
  const value = (id: string): number | null => (draft.value[id] === "" ? null : Number(draft.value[id]));
  return { max_output_tokens: value("max_output_tokens"), max_tool_rounds: value("max_tool_rounds") };
}

async function run(action: () => Promise<void>): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    await action();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

const save = () => run(async () => adopt(await tuningClient.save(payload())));
const clear = () => run(async () => {
  await tuningClient.reset();
  adopt({ limits: { max_output_tokens: null, max_tool_rounds: null }, ceiling: stored.value!.ceiling });
});

onMounted(() => run(async () => adopt(await tuningClient.get())));
</script>

<template>
  <div v-if="stored" class="response-limits">
    <div v-for="field in FIELDS" :key="field.id" class="row">
      <label :for="`limit-${field.id}`">{{ field.label }}</label>
      <p>{{ field.hint }} <template v-if="stored.ceiling[field.id] !== null">The most you can set is {{ stored.ceiling[field.id] }}.</template></p>
      <input
        :id="`limit-${field.id}`" v-model="draft[field.id]" :data-field="field.id" type="number" inputmode="numeric"
        min="1" :max="stored.ceiling[field.id] ?? undefined" step="1" placeholder="Default"
      />
      <span>{{ field.unit }}</span>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button type="button" data-test="clear" :disabled="!anySet || saving" @click="clear">Use defaults</button>
      <button type="button" data-test="save" :disabled="!dirty || saving" @click="save">Save</button>
    </div>
  </div>
  <p v-else-if="error" role="alert">{{ error }}</p>
</template>
```

- [ ] **Step 6: Mount it** in `SettingsView.vue` per Step 1 (new `GROUPS` entry `{ id: "limits", title: "Response limits", icon: "M2 4h12M2 8h8M2 12h5", scope: "Your account", note: "Applied when you save. Stored on your account." }`, a `DEFS` entry for search, and `<ResponseLimits />` rendered in that group). Extend `SettingsView.test.ts` mocks with `vi.mock("../../api/navigation/TuningClient", ...)` so the existing tests still mount.

- [ ] **Step 7: Run to verify it passes**

Run: `npx vitest run` then `npx vue-tsc -b`
Expected: all PASS, no type errors.

- [ ] **Step 8: Commit**

```bash
git add apps/Ember/ember_web
git commit -m "feat(ember_web): response limits in Settings" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: End-to-end check and docs

**Files:**
- Modify: `apps/Ember/ember_api/configs/README.md` (one line), `docs/superpowers/specs/2026-10-25-tuning-settings-design.md` (only if reality differed)

- [ ] **Step 1: Full suites**

Run each, expecting PASS:
- `apps/garrison`: `python -m pytest -q`
- `apps/Ember/ember_api`: `python -m pytest -q`
- `apps/Ember/ember_admin`: `npx vitest run && npx vue-tsc -b`
- `apps/Ember/ember_web`: `npx vitest run && npx vue-tsc -b`

- [ ] **Step 2: Live check** (start the stack with the repo's usual launcher; use the preview tools, not a hand-run server)

1. As an admin, open Tuning, set "Max tool rounds" to 3, Save. Confirm `apps/garrison/configs/tuning_overrides.json` contains `{"token_limits.default.max_tool_rounds": 3}` and `config_tuning.json` is unchanged.
2. Ask a question that needs several tools; the answer stops after 3 rounds. Reset the field; the next answer uses 15 again with no restart.
3. In Settings set "Most tool rounds" to 2 as a normal user; confirm 16 is refused with "cannot be above" when the admin value is 15, and 2 is applied on the next answer.
4. Stop garrison; Settings still shows saved values, Save answers 502; Tuning shows the error.

- [ ] **Step 3: Docs** — add one line to the `usage` row area of `apps/Ember/ember_api/configs/README.md` is not needed (no new ember_api config key). Instead, state in the commit body which behaviours were checked live and which were not. Update the spec only where the built behaviour differs from it.

- [ ] **Step 4: Commit** (only if Step 3 changed files)

```bash
git add docs apps/Ember/ember_api/configs/README.md
git commit -m "docs: tuning settings notes after live check" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** overlay + merge (T1), cross-process reload (T2), user clamp incl. agent-file caps and old-agent safety (T3), garrison endpoints (T4), `tuning.manage` + activity log + 502/400 mapping (T5), per-account treasury store + ceiling + chat path + treasury-down fallback (T6), admin UI with default/changed/reset (T7), Settings row (T8), live check (T9).
- **Not built, on purpose:** per-provider and per-gateway token limits and `triage_order` in the UI (the backend accepts the per-provider paths, the page shows only `token_limits.default`); delegated sub-agents do not get the user's limits; no eval on a classifier edit; concurrent admin saves are last-write-wins.
- **Risks to watch while executing:** Task 5 Step 1 (where permissions are seeded may need a migration), Task 6 Step 5 (`store` variable name in `chats.py`, `FakeAgent` shape), Task 3 Step 6 (copy the neighbouring `ask()` test setup).
