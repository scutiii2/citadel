# Triage strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user picks which LayaAgent decision strategy answers their prompts sent straight to the Triage Assistant from ember_web; an administrator sets a default strategy in ember_admin that applies to every LayaAgent caller.

**Architecture:** Garrison accepts an optional `strategy` in the Laya request JSON and resolves it as request value, then admin default (a one-key overlay file), then today's voter-derived behaviour. ember_api stores the per-user value on `accounts.triage_strategy`, proxies the admin default to Garrison's `/agents/triage-strategy`, and adds the user's value to the Laya request. ember_web gets a Settings row, ember_admin a panel on Workspace settings.

**Tech Stack:** Python (Garrison, FastMCP custom routes, httpx; ember_api, FastAPI, SQLAlchemy, Alembic; pytest), Vue 3 + TypeScript (Vitest).

**Spec:** `docs/superpowers/specs/2026-10-25-triage-strategy-design.md`

## Global Constraints

- Never add a reduced-motion setting, `prefers-reduced-motion` query or test (`AGENTS.md`).
- Strategy names come from the LayaAgent service (`GET /v1/strategies`); never copy the list into Garrison or Ember.
- Resolution order: request `strategy`, then admin default, then voter-derived behaviour. An unset admin default keeps today's behaviour.
- The Jev fallback after an uncertain result is unchanged.
- ember_admin and ember_web: radius only through `--radius-*` tokens, colours only through the `style.css` tokens (`radiusScale.test.ts` enforces it). A control that calls the server stays pending until the server answers.
- Skills are edited only in `.agents/skills/`; this plan touches none.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Spec adjustments found while reading the code

Task 8 writes these back into the spec.

1. **Garrison route is `/agents/triage-strategy`**, not `/admin/triage-strategy`. `/agents` is already in `internal_auth.PROTECTED_PATHS`, and ember_api's `AgentAdmin` already finds the entry agent for `/agents/*` calls.
2. **No new permission.** The admin control reuses `settings.manage` (it sits on the Workspace settings page). No `tuning.manage`, no role migration.
3. **Per-user value is a column `accounts.triage_strategy`** (nullable `String(40)`), mirroring `accounts.prompt_suggestions`, not a new `account_tuning` table. The full tuning spec can move it later.
4. **The admin "unset" state is "not set", not `auto`.** Clearing the override restores the voter-derived behaviour, which is not the service's `auto`. The admin control's first option reads "Not set (follows triage_order)", and a user's first option reads "Default (<admin's choice, or not set>)".
5. **Overlay file is `.data/tuning_overrides.json`** (changed after review: `configs/` is baked into the image, so a file there is lost on rebuild; `.data/` is the `agent_data` volume and is gitignored).
6. **A stored user value the service no longer lists** makes `/api/triage/ask` return 422 with Garrison's message (`Invalid Laya request: unknown strategy ...`), not 503.

## File Structure

Garrison (`apps/garrison`):
- Modify `src/llm/laya_agent.py`: `LAYAAgent.strategies()`.
- Modify `src/llm/laya_provider.py`: `Request.strategy`, parse and validate the field.
- Create `src/core/tuning_overrides.py`: read and write the admin default atomically.
- Create `src/llm/triage_strategy.py`: `describe()` and `update()` for the routes.
- Modify `src/llm/triage_flow.py`: resolve and use the strategy.
- Modify `src/server.py`: `GET` and `PUT /agents/triage-strategy`.
- Modify `tests/fake_laya.py`; tests in `tests/test_laya_agent.py`, `tests/test_laya_provider.py`, `tests/test_triage_flow.py`, new `tests/test_tuning_overrides.py` and `tests/test_triage_strategy.py`.

ember_api (`apps/Ember/ember_api`):
- Modify `src/models/account.py`; create `migrations/versions/0026_triage_strategy.py`; modify `tests/test_migrations.py`.
- Modify `src/services/agent_admin.py`: `triage_strategy`, `set_triage_strategy`.
- Create `src/routes/triage_strategy.py`; modify `src/app.py`.
- Modify `src/services/triage_questions.py` and `src/routes/triage.py`.
- Create `tests/test_triage_strategy.py`; extend `tests/test_triage.py`.

ember_admin (`apps/Ember/ember_admin/src`): create `api/TriageStrategyClient.ts`, `components/admin/TriageStrategyPanel.vue` and its test; modify `views/WorkspaceSettingsView.vue`.

ember_web (`apps/Ember/ember_web/src`): create `api/triage/TriageStrategyClient.ts`; modify `features/settings/SettingsView.vue` and `SettingsView.test.ts`.

---

### Task 1: LAYAAgent lists strategies

**Files:**
- Modify: `apps/garrison/src/llm/laya_agent.py`
- Modify: `apps/garrison/tests/fake_laya.py`
- Test: `apps/garrison/tests/test_laya_agent.py`

**Interfaces:**
- Produces: `LAYAAgent.strategies() -> dict[str, Any]` returning `{"strategies": list[str], "default": str | None}`; raises `LayaServiceError` when unconfigured, unreachable or refused.
- Produces: `fake_laya.STRATEGIES` (tuple of the 8 names) and `FakeService(..., strategy_names=STRATEGIES)` with `strategies()` returning the same shape.

- [ ] **Step 1: Write the failing tests**

Append to `apps/garrison/tests/test_laya_agent.py` (add `import httpx` and `import pytest` at the top if missing):

```python
def test_strategies_lists_the_service_names_and_its_default(monkeypatch):
    seen = {}

    def get(url, headers=None, timeout=None):
        seen.update(url=url, headers=headers)
        return httpx.Response(200, json={"default": "auto", "strategies": ["english-only", "auto"]})

    monkeypatch.setattr(httpx, "get", get)
    result = LAYAAgent("http://laya:9120/", token="t").strategies()
    assert result == {"strategies": ["english-only", "auto"], "default": "auto"}
    assert seen == {"url": "http://laya:9120/v1/strategies", "headers": {"X-Internal-Token": "t"}}


def test_strategies_accepts_a_mapping_of_names(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, json={"default": "auto", "strategies": {"a": "x", "b": "y"}}))
    assert LAYAAgent("http://laya:9120").strategies()["strategies"] == ["a", "b"]


def test_strategies_errors_become_service_errors(monkeypatch):
    with pytest.raises(LayaServiceError, match="not configured"):
        LAYAAgent("").strategies()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(500, text="boom"))
    with pytest.raises(LayaServiceError) as refused:
        LAYAAgent("http://laya:9120").strategies()
    assert refused.value.status == 500

    def down(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "get", down)
    with pytest.raises(LayaServiceError, match="could not be reached"):
        LAYAAgent("http://laya:9120").strategies()
```

If `test_laya_agent.py` does not already import `LAYAAgent` and `LayaServiceError`, add `from src.llm.laya_agent import LAYAAgent, LayaServiceError`.

- [ ] **Step 2: Run to verify failure**

Run (from `apps/garrison`): `python -m pytest tests/test_laya_agent.py -k strategies -v`
Expected: FAIL with `AttributeError: 'LAYAAgent' object has no attribute 'strategies'`.

- [ ] **Step 3: Implement**

In `apps/garrison/src/llm/laya_agent.py`, replace the header line in `_post` and add the method. Change

```python
        headers = {"X-Internal-Token": self._token} if self._token else {}
        try:
            response = httpx.post(f"{self._url}{path}", headers=headers, json=body, timeout=TIMEOUT_SECONDS)
```

to

```python
        try:
            response = httpx.post(f"{self._url}{path}", headers=self._headers(), json=body, timeout=TIMEOUT_SECONDS)
```

and add before `_post`:

```python
    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self._token} if self._token else {}

    def strategies(self) -> dict[str, Any]:
        """The service's strategy names and its default: `{"strategies": [...], "default": "auto"}`."""
        if not self.configured:
            raise LayaServiceError("Laya is not configured: set LAYA_SERVICE_URL")
        try:
            response = httpx.get(f"{self._url}/v1/strategies", headers=self._headers(), timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            raise LayaServiceError(f"The Laya service could not be reached: {error}") from error
        if not response.is_success:
            raise LayaServiceError(f"The Laya service refused the request ({response.status_code})", status=response.status_code)
        body = response.json()
        return {"strategies": list(body["strategies"]), "default": body.get("default")}
```

In `apps/garrison/tests/fake_laya.py` add above `class FakeService`:

```python
STRATEGIES = ("english-only", "typed-only", "english-then-typed", "typed-then-english",
              "most-confident", "average", "consensus", "auto")
```

change the `FakeService.__init__` signature to `def __init__(self, *results: Any, mixed: Any = None, invalid: str = "", strategy_names: tuple[str, ...] = STRATEGIES) -> None:`, add `self.strategy_names = strategy_names` in its body, and add the method:

```python
    def strategies(self):
        return {"strategies": list(self.strategy_names), "default": "auto"}
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_laya_agent.py -v`
Expected: PASS (new and existing tests).

- [ ] **Step 5: Commit**

```bash
git add apps/garrison/src/llm/laya_agent.py apps/garrison/tests/fake_laya.py apps/garrison/tests/test_laya_agent.py
git commit -m "feat(garrison): list the Laya service strategies"
```

---

### Task 2: Requests carry an optional strategy

**Files:**
- Modify: `apps/garrison/src/llm/laya_provider.py:33-49,64-94`
- Test: `apps/garrison/tests/test_laya_provider.py`

**Interfaces:**
- Produces: `Request.strategy: str | None = None` (last field of the dataclass). `parse_request` accepts `"strategy": "<non-empty string>"`, strips it, and raises `ValueError("Invalid Laya request: strategy must be a non-empty string")` for anything else (including `null`).

- [ ] **Step 1: Write the failing tests**

Append to `apps/garrison/tests/test_laya_provider.py` (it already imports `laya_provider` and `pytest`; add them if not):

```python
STRATEGY_BODY = {"text": "t", "questions": {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}}


def test_a_request_may_name_a_strategy():
    request = laya_provider.parse_request(json.dumps({**STRATEGY_BODY, "strategy": " typed-only "}))
    assert request.strategy == "typed-only"
    assert laya_provider.parse_request(json.dumps(STRATEGY_BODY)).strategy is None


@pytest.mark.parametrize("value", ["", "  ", 3, None, ["typed-only"]])
def test_a_bad_strategy_is_refused(value):
    with pytest.raises(ValueError, match="strategy must be a non-empty string"):
        laya_provider.parse_request(json.dumps({**STRATEGY_BODY, "strategy": value}))
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_laya_provider.py -k strategy -v`
Expected: FAIL with `unknown field(s): strategy`.

- [ ] **Step 3: Implement**

In `apps/garrison/src/llm/laya_provider.py`:

Change `_REQUEST_KEYS = {"text", "questions", "min_confidence", "trace", "local_only"}` to `_REQUEST_KEYS = {"text", "questions", "min_confidence", "trace", "local_only", "strategy"}`.

Add to the `Request` dataclass after `local_only`:

```python
    # A Laya service decision strategy that replaces the one the voter settings would choose (llm/triage_flow.py).
    strategy: str | None = None
```

In `parse_request`, replace the final `return Request(text, questions, float(min_confidence), trace, local_only)` with:

```python
    strategy = data.get("strategy")
    if "strategy" in data:
        if not _is_text(strategy):
            raise _fail("strategy must be a non-empty string")
        strategy = strategy.strip()
    return Request(text, questions, float(min_confidence), trace, local_only, strategy)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_laya_provider.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/garrison/src/llm/laya_provider.py apps/garrison/tests/test_laya_provider.py
git commit -m "feat(garrison): accept a strategy in the Laya request"
```

---

### Task 3: Admin default overlay file

**Files:**
- Create: `apps/garrison/src/core/tuning_overrides.py`
- Test: `apps/garrison/tests/test_tuning_overrides.py`

**Interfaces:**
- Produces: `OVERRIDES_PATH: Path` (`configs/config_tuning_overrides.json`); `triage_strategy(path: Path | None = None) -> str | None`; `set_triage_strategy(value: str | None, path: Path | None = None) -> None` (None removes the key). A missing `path` means `OVERRIDES_PATH`, read at call time so tests can patch it. File shape: `{"classifier": {"triage_strategy": "<name>"}}`. An unreadable or invalid file reads as unset and logs a warning; a write replaces it.

- [ ] **Step 1: Write the failing tests**

Create `apps/garrison/tests/test_tuning_overrides.py`:

```python
"""The admin overlay (configs/config_tuning_overrides.json): one key for now, the Triage Assistant's default strategy."""

from __future__ import annotations

import json

from src.core import tuning_overrides


def test_nothing_is_set_without_a_file(tmp_path):
    assert tuning_overrides.triage_strategy(tmp_path / "o.json") is None


def test_a_saved_strategy_is_read_back(tmp_path):
    path = tmp_path / "o.json"
    tuning_overrides.set_triage_strategy("typed-only", path)
    assert tuning_overrides.triage_strategy(path) == "typed-only"
    assert json.loads(path.read_text(encoding="utf-8")) == {"classifier": {"triage_strategy": "typed-only"}}


def test_none_clears_the_key_and_leaves_the_other_keys(tmp_path):
    path = tmp_path / "o.json"
    path.write_text(json.dumps({"classifier": {"triage_strategy": "average", "other": 1}, "x": 2}), encoding="utf-8")
    tuning_overrides.set_triage_strategy(None, path)
    assert tuning_overrides.triage_strategy(path) is None
    assert json.loads(path.read_text(encoding="utf-8")) == {"classifier": {"other": 1}, "x": 2}


def test_a_broken_file_reads_as_unset_and_is_replaced_by_a_write(tmp_path, caplog):
    path = tmp_path / "o.json"
    for bad in ("{not json", "[]", json.dumps({"classifier": []}), json.dumps({"classifier": {"triage_strategy": 5}})):
        path.write_text(bad, encoding="utf-8")
        assert tuning_overrides.triage_strategy(path) is None
    tuning_overrides.set_triage_strategy("consensus", path)
    assert tuning_overrides.triage_strategy(path) == "consensus"


def test_a_write_leaves_no_temporary_file(tmp_path):
    tuning_overrides.set_triage_strategy("auto", tmp_path / "o.json")
    assert [p.name for p in tmp_path.iterdir()] == ["o.json"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_tuning_overrides.py -v`
Expected: FAIL with `ImportError` (no `tuning_overrides`).

- [ ] **Step 3: Implement**

Create `apps/garrison/src/core/tuning_overrides.py`:

```python
"""Admin overrides of Garrison's tuning, kept beside config_tuning.json in configs/config_tuning_overrides.json.

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

from src.core.config_files import CONFIGS_DIR

OVERRIDES_PATH = CONFIGS_DIR / "config_tuning_overrides.json"

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
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_tuning_overrides.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/garrison/src/core/tuning_overrides.py apps/garrison/tests/test_tuning_overrides.py
git commit -m "feat(garrison): store the admin default triage strategy in an overlay file"
```

---

### Task 4: The flow uses the resolved strategy

**Files:**
- Modify: `apps/garrison/src/llm/triage_flow.py:35-40,85-104,132-145,162-190`
- Test: `apps/garrison/tests/test_triage_flow.py`

**Interfaces:**
- Consumes: `Request.strategy` (Task 2), `tuning_overrides.triage_strategy()` (Task 3), `service.strategies()` (Task 1).
- Produces: `TriageFlow` sends every question of a request to the service under one strategy when one resolves (`request.strategy`, else the overlay value); otherwise the existing per-type grouping. An unknown name raises `ValueError("Invalid Laya request: unknown strategy 'x'; choose one of: ...")`. If the service cannot list strategies, the name is passed on unchecked and the service decides.

- [ ] **Step 1: Write the failing tests**

Append to `apps/garrison/tests/test_triage_flow.py`:

```python
# --- the strategy -----------------------------------------------------------------------------------------

def two_questions(**extra):
    return json.dumps({"text": "t", "questions": {
        "area": {"type": "choice", "instructions": "Which?", "criteria": OPTIONS},
        "other": {"type": "choice", "instructions": "Which?", "criteria": OPTIONS},
    }, **extra})


def sure_pair():
    return result(("area", choice("a", 0.9, uncertain=False)), ("other", choice("a", 0.9, uncertain=False)))


def test_a_requested_strategy_replaces_the_voter_derived_one(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions(strategy="consensus"))
    assert [(c["strategy"], list(c["questions"])) for c in service.asked] == [("consensus", ["area", "other"])]


def test_the_admin_default_applies_when_the_request_names_none(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: "typed-only")
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions())
    assert [c["strategy"] for c in service.asked] == ["typed-only"]


def test_the_request_beats_the_admin_default(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: "typed-only")
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions(strategy="average"))
    assert [c["strategy"] for c in service.asked] == ["average"]


def test_without_either_the_voters_choose(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions())
    assert [c["strategy"] for c in service.asked] == ["english-then-typed"]


def test_an_unknown_strategy_is_refused_with_the_valid_names(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair(), strategy_names=("auto", "typed-only"))
    with pytest.raises(ValueError, match=r"Invalid Laya request: unknown strategy 'nope'; choose one of: auto, typed-only"):
        TriageFlow(service=service).answer(two_questions(strategy="nope"))
    assert service.asked == []


def test_a_service_that_cannot_list_strategies_still_gets_the_request(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair())

    def down():
        raise LayaServiceError("down")

    service.strategies = down
    TriageFlow(service=service).answer(two_questions(strategy="consensus"))
    assert [c["strategy"] for c in service.asked] == ["consensus"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_triage_flow.py -k "strategy or admin_default or voters_choose" -v`
Expected: FAIL with `AttributeError: module 'src.llm.triage_flow' has no attribute 'tuning_overrides'`.

- [ ] **Step 3: Implement**

In `apps/garrison/src/llm/triage_flow.py`:

Add the import after `from typing import Any`:

```python
from src.core import tuning_overrides
```

In `TriageFlow.__init__` after `self._override: float | None = None` add:

```python
        self._strategy: str | None = None
```

In `_ask_locals`, replace

```python
        for qid, spec in request.questions.items():
            local = tuple(v for v in config.voters(spec["type"]) if v != JEV)
            if local in _STRATEGIES:
                groups.setdefault(_STRATEGIES[local], {})[qid] = spec
```

with

```python
        for qid, spec in request.questions.items():
            if self._strategy:
                groups.setdefault(self._strategy, {})[qid] = spec
                continue
            local = tuple(v for v in config.voters(spec["type"]) if v != JEV)
            if local in _STRATEGIES:
                groups.setdefault(_STRATEGIES[local], {})[qid] = spec
```

In `_validate`, after the existing `try/except` that calls `self.service.validate`, append:

```python
        if self._strategy:
            try:
                names = self.service.strategies()["strategies"]
            except LayaServiceError as error:
                _log.warning("Laya strategies could not be listed: %s", error)
                return
            if self._strategy not in names:
                raise ValueError(f"Invalid Laya request: unknown strategy {self._strategy!r}; choose one of: {', '.join(names)}")
```

In `_answer`, after the line `self.tokens, self._failures = 0, []` add:

```python
        self._strategy = request.strategy or tuning_overrides.triage_strategy()
```

(`_validate` runs after this line, so it sees the resolved strategy.)

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_triage_flow.py tests/test_laya_provider.py -v`
Expected: PASS, including the existing flow tests (they never set a strategy; if one fails because a real overlay file exists on the machine, patch `triage_flow.tuning_overrides.triage_strategy` to `lambda: None` in `configure()` and note it in the commit message).

- [ ] **Step 5: Commit**

```bash
git add apps/garrison/src/llm/triage_flow.py apps/garrison/tests/test_triage_flow.py
git commit -m "feat(garrison): run the triage flow under a requested or default strategy"
```

---

### Task 5: Garrison routes for the admin default

**Files:**
- Create: `apps/garrison/src/llm/triage_strategy.py`
- Modify: `apps/garrison/src/server.py` (after the `/agents/prompt-preview` route, before `@mcp.tool() def interpret`)
- Test: `apps/garrison/tests/test_triage_strategy.py`

**Interfaces:**
- Consumes: `tuning_overrides` (Task 3), `service.strategies()` (Task 1).
- Produces: `describe(service=None) -> {"default": str | None, "strategies": list[str]}` (`strategies` is `[]` when the service cannot be reached); `update(value: str | None, service=None) -> same shape`, raising `StrategyError(message, status)` (400 unknown name, 502 service unreachable). Routes: `GET /agents/triage-strategy` returns `describe()`; `PUT /agents/triage-strategy` takes `{"strategy": str | null}` and returns `update(...)`; errors are `{"error": message}` with the error's status; a body without a `strategy` key is 400.

- [ ] **Step 1: Write the failing tests**

Create `apps/garrison/tests/test_triage_strategy.py`:

```python
"""The admin default strategy: what the /agents/triage-strategy routes do (llm/triage_strategy.py)."""

from __future__ import annotations

import pytest

from src.core import tuning_overrides
from src.llm import triage_strategy
from src.llm.laya_agent import LayaServiceError
from tests.fake_laya import STRATEGIES, FakeService


@pytest.fixture(autouse=True)
def overlay(tmp_path, monkeypatch):
    path = tmp_path / "overrides.json"
    monkeypatch.setattr(tuning_overrides, "OVERRIDES_PATH", path)
    return path


def test_describe_reports_nothing_set_and_the_service_names():
    assert triage_strategy.describe(FakeService()) == {"default": None, "strategies": list(STRATEGIES)}


def test_update_saves_a_known_strategy_and_clearing_removes_it():
    service = FakeService()
    assert triage_strategy.update("typed-only", service)["default"] == "typed-only"
    assert tuning_overrides.triage_strategy() == "typed-only"
    assert triage_strategy.update(None, service)["default"] is None
    assert tuning_overrides.triage_strategy() is None


def test_update_refuses_an_unknown_name_and_keeps_the_old_one():
    service = FakeService()
    triage_strategy.update("average", service)
    with pytest.raises(triage_strategy.StrategyError) as refused:
        triage_strategy.update("nope", service)
    assert refused.value.status == 400 and "unknown strategy 'nope'" in str(refused.value)
    assert tuning_overrides.triage_strategy() == "average"


def test_describe_still_answers_when_the_service_is_down():
    service = FakeService()
    service.strategies = lambda: (_ for _ in ()).throw(LayaServiceError("down"))
    assert triage_strategy.describe(service) == {"default": None, "strategies": []}


def test_update_to_a_name_needs_the_service_but_clearing_does_not():
    service = FakeService()
    service.strategies = lambda: (_ for _ in ()).throw(LayaServiceError("down"))
    with pytest.raises(triage_strategy.StrategyError) as down:
        triage_strategy.update("average", service)
    assert down.value.status == 502
    assert triage_strategy.update(None, service)["default"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_triage_strategy.py -v`
Expected: FAIL with `ImportError` (no `triage_strategy`).

- [ ] **Step 3: Implement**

Create `apps/garrison/src/llm/triage_strategy.py`:

```python
"""The admin's default decision strategy for the Triage Assistant (routes: server.py /agents/triage-strategy).

The value lives in the overlay file (core/tuning_overrides.py) and applies to every caller of the Laya service
that names no strategy of its own (llm/triage_flow.py). Names are checked against the service's own list."""

from __future__ import annotations

from typing import Any

from src.core import tuning_overrides
from src.llm import laya_agent
from src.llm.laya_agent import LayaServiceError


class StrategyError(Exception):
    """A change that cannot be made; `message` is safe to show and `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def describe(service: Any = None) -> dict[str, Any]:
    """`default` (None when unset) and the service's `strategies` (empty while the service cannot be reached)."""
    service = service or laya_agent.agent()
    try:
        names = service.strategies()["strategies"]
    except LayaServiceError:
        names = []
    return {"default": tuning_overrides.triage_strategy(), "strategies": names}


def update(value: str | None, service: Any = None) -> dict[str, Any]:
    """Sets the default, or clears it with None, and returns `describe()`."""
    service = service or laya_agent.agent()
    if value is not None:
        try:
            names = service.strategies()["strategies"]
        except LayaServiceError as error:
            raise StrategyError(f"The Laya service could not list its strategies: {error}", 502) from error
        if value not in names:
            raise StrategyError(f"unknown strategy {value!r}; choose one of: {', '.join(names)}", 400)
    tuning_overrides.set_triage_strategy(value)
    return describe(service)
```

In `apps/garrison/src/server.py`, inside the same function scope where `agent_store` is imported (line 58 imports `agent_config, agent_events, agent_registry, agent_store`), add `from src.llm import triage_strategy` on the next line, then add after the `agent_prompt_preview` route:

```python
@mcp.custom_route("/agents/triage-strategy", methods=["GET"])
async def triage_strategy_get(_request: Request) -> JSONResponse:
    """The admin default strategy of the Triage Assistant and the strategies the Laya service offers."""
    return JSONResponse(await asyncio.to_thread(triage_strategy.describe))


@mcp.custom_route("/agents/triage-strategy", methods=["PUT"])
async def triage_strategy_put(request: Request) -> JSONResponse:
    """Body: {"strategy": "<name>" | null}; null clears the default."""
    body = await _json_object(request)
    if body is None or "strategy" not in body or not (body["strategy"] is None or isinstance(body["strategy"], str)):
        return JSONResponse({"error": "body must be {\"strategy\": \"<name>\" | null}"}, status_code=400)
    try:
        return JSONResponse(await asyncio.to_thread(triage_strategy.update, body["strategy"]))
    except triage_strategy.StrategyError as error:
        return JSONResponse({"error": str(error)}, status_code=error.status)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_triage_strategy.py tests/test_server.py -v`
Expected: PASS. The routes themselves have no direct test here (they are thin); Task 7 covers their shape through ember_api's fake, and Task 11 checks them against a running Garrison.

- [ ] **Step 5: Commit**

```bash
git add apps/garrison/src/llm/triage_strategy.py apps/garrison/src/server.py apps/garrison/tests/test_triage_strategy.py apps/garrison/src/core/tuning_overrides.py
git commit -m "feat(garrison): routes for the default triage strategy"
```

---

### Task 6: ember_api stores the user's strategy

**Files:**
- Modify: `apps/Ember/ember_api/src/models/account.py:31`
- Create: `apps/Ember/ember_api/migrations/versions/0026_triage_strategy.py`
- Modify: `apps/Ember/ember_api/tests/test_migrations.py` (lines 20-21, `drop_second_brain`, new test)

**Interfaces:**
- Produces: `Account.triage_strategy: Mapped[str | None]` (`String(40)`, nullable, no default); Alembic revision `0026` (down `0025`).

- [ ] **Step 1: Write the failing test**

In `apps/Ember/ember_api/tests/test_migrations.py` change `HEAD = "0025"` to `HEAD = "0026"` and `NEXT = "0026"` to `NEXT = "0027"`. Add after `drop_second_brain`:

```python
def drop_triage_strategy(conn: sqlite3.Connection) -> None:
    """Undo migration 0026 on a database built from the current models."""
    if "triage_strategy" in {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}:
        conn.execute("ALTER TABLE accounts DROP COLUMN triage_strategy")
```

and add a call as the first line of `drop_second_brain`'s body: `drop_triage_strategy(conn)` (every rewind of a model-built database reaches `drop_second_brain` through `drop_log_prompts` or directly). Add the test next to `test_second_brain_column_reverses_and_defaults_off`:

```python
def test_triage_strategy_column_starts_empty_and_reverses(tmp_path: Path) -> None:
    from alembic import command

    run_with(make_database(tmp_path))
    path = tmp_path / "ember.db"
    with closing(sqlite3.connect(path)) as conn:
        column = next(row for row in conn.execute("PRAGMA table_info(accounts)") if row[1] == "triage_strategy")
        assert column[3] == 0  # nullable: no strategy chosen

    async def downgrade():
        database = make_database(tmp_path)
        runner = MigrationRunner(database.engine)
        try:
            async with database.engine.connect() as conn:
                await conn.run_sync(lambda sync: command.downgrade(runner._config(sync), "0025"))
        finally:
            await database.dispose()

    asyncio.run(downgrade())
    with closing(sqlite3.connect(path)) as conn:
        assert "triage_strategy" not in {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    assert run_with(make_database(tmp_path)) == "upgraded"
    assert differences(make_database(tmp_path)) == []
```

- [ ] **Step 2: Run to verify failure**

Run (from `apps/Ember/ember_api`): `python -m pytest tests/test_migrations.py -k triage_strategy -v`
Expected: FAIL (`StopIteration`: no `triage_strategy` column).

- [ ] **Step 3: Implement**

In `apps/Ember/ember_api/src/models/account.py` add after the `prompt_suggestions` column (line 31):

```python
    # The Laya decision strategy this account's prompts to the Triage Assistant use; None follows the
    # administrator's default (see routes/triage_strategy.py).
    triage_strategy: Mapped[str | None] = mapped_column(String(40), nullable=True)
```

Create `apps/Ember/ember_api/migrations/versions/0026_triage_strategy.py`:

```python
"""Per-account decision strategy for prompts sent straight to the Triage Assistant (accounts.triage_strategy).

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("triage_strategy", sa.String(40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("triage_strategy")
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_migrations.py -v`
Expected: PASS. Any other test that rewinds a model-built database and then upgrades fails with `duplicate column name: triage_strategy`; add `drop_triage_strategy(conn)` to that spot and rerun until the file is green. Then run `python -m pytest -q` for the whole ember_api suite.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/models/account.py apps/Ember/ember_api/migrations/versions/0026_triage_strategy.py apps/Ember/ember_api/tests/test_migrations.py
git commit -m "feat(ember_api): add accounts.triage_strategy"
```

---

### Task 7: ember_api routes and the Laya request

**Files:**
- Modify: `apps/Ember/ember_api/src/services/agent_admin.py` (after `set_prompts`)
- Create: `apps/Ember/ember_api/src/routes/triage_strategy.py`
- Modify: `apps/Ember/ember_api/src/app.py` (import list near line 49, include near line 231)
- Modify: `apps/Ember/ember_api/src/services/triage_questions.py` (`build_request`, `TriageQuestions.ask`)
- Modify: `apps/Ember/ember_api/src/routes/triage.py:135`
- Test: create `apps/Ember/ember_api/tests/test_triage_strategy.py`

**Interfaces:**
- Consumes: Garrison `GET/PUT /agents/triage-strategy` (Task 5), `Account.triage_strategy` (Task 6).
- Produces:
  - `AgentAdmin.triage_strategy(account) -> {"default": str | None, "strategies": list[str]}`; `AgentAdmin.set_triage_strategy(account, value: str | None) -> same shape`.
  - `GET /api/admin/triage-strategy` and `PUT` body `{"value": str | null}` (needs `settings.manage`), returning `{"default", "strategies"}`; PUT writes an activity-log entry `triage_strategy.default` with before and after.
  - `GET /api/account/triage-strategy` returning `{"value", "default", "strategies"}` and `PUT` body `{"value": str | null}` (any logged-in account).
  - `build_request(..., levels=None, strategy: str | None = None)` adds `"strategy"` only when set; `TriageQuestions.ask(..., levels=None, strategy=None)`.

- [ ] **Step 1: Write the failing tests**

Create `apps/Ember/ember_api/tests/test_triage_strategy.py`:

```python
"""The default Laya strategy (admin) and each account's own, forwarded to Garrison's /agents/triage-strategy."""

from __future__ import annotations

import json

import httpx

from tests.conftest import FakeAgent, FakeEmailSender, FakeUpstream
from tests.test_admin import login, make_member
from tests.test_registration import as_admin
from tests.test_triage import ASK, YES_NO, laya_answers, run_agents

NAMES = ["english-only", "typed-only", "auto"]
URL = "http://agent-a.internal/agents/triage-strategy"


class Garrison:
    """Garrison's /agents/triage-strategy: the stored default, and a service that offers NAMES."""

    def __init__(self, default: str | None = None, down: bool = False) -> None:
        self.default, self.down = default, down

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/agents/triage-strategy":
            return httpx.Response(404, json={"error": "no route"})
        if self.down:
            return httpx.Response(503, json={"error": "down"})
        if request.method == "PUT":
            value = json.loads(request.content)["strategy"]
            if value is not None and value not in NAMES:
                return httpx.Response(400, json={"error": f"unknown strategy {value!r}"})
            self.default = value
        return httpx.Response(200, json={"default": self.default, "strategies": NAMES})


# -- admin default ------------------------------------------------------------------------------------------
def test_admin_reads_and_sets_the_default(client, upstream: FakeUpstream) -> None:
    upstream.handler = Garrison()
    as_admin(client)

    assert client.get("/api/admin/triage-strategy").json() == {"default": None, "strategies": NAMES}
    saved = client.put("/api/admin/triage-strategy", json={"value": "typed-only"})
    assert (saved.status_code, saved.json()["default"]) == (200, "typed-only")
    assert str(upstream.requests[-1].url) == URL
    assert json.loads(upstream.requests[-1].content) == {"strategy": "typed-only"}
    assert client.put("/api/admin/triage-strategy", json={"value": None}).json()["default"] is None


def test_admin_default_errors_pass_through(client, upstream: FakeUpstream) -> None:
    upstream.handler = Garrison()
    as_admin(client)

    assert client.put("/api/admin/triage-strategy", json={"value": "nope"}).status_code == 400
    assert client.put("/api/admin/triage-strategy", json={}).status_code == 422
    upstream.handler = Garrison(down=True)
    assert client.get("/api/admin/triage-strategy").status_code == 502


def test_only_settings_managers_touch_the_admin_default(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = Garrison()
    assert client.get("/api/admin/triage-strategy").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")
    assert client.get("/api/admin/triage-strategy").status_code == 403
    assert client.put("/api/admin/triage-strategy", json={"value": "auto"}).status_code == 403


# -- an account's own ---------------------------------------------------------------------------------------
def test_an_account_starts_on_the_default_and_picks_its_own(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = Garrison(default="auto")
    assert client.get("/api/account/triage-strategy").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")

    assert client.get("/api/account/triage-strategy").json() == {"value": None, "default": "auto", "strategies": NAMES}
    assert client.put("/api/account/triage-strategy", json={"value": "typed-only"}).json()["value"] == "typed-only"
    assert client.get("/api/account/triage-strategy").json()["value"] == "typed-only"
    assert client.put("/api/account/triage-strategy", json={"value": None}).json()["value"] is None


def test_an_account_cannot_pick_an_unknown_strategy(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = Garrison()
    make_member(client, email, "alice")
    login(client, "alice")

    refused = client.put("/api/account/triage-strategy", json={"value": "nope"})
    assert refused.status_code == 422 and "english-only" in refused.json()["detail"]
    assert client.get("/api/account/triage-strategy").json()["value"] is None


def test_while_garrison_is_down_the_account_can_read_and_clear_but_not_pick(
    client, upstream: FakeUpstream, email: FakeEmailSender
) -> None:
    upstream.handler = Garrison()
    make_member(client, email, "alice")
    login(client, "alice")
    client.put("/api/account/triage-strategy", json={"value": "typed-only"})

    upstream.handler = Garrison(down=True)
    assert client.get("/api/account/triage-strategy").json() == {"value": "typed-only", "default": None, "strategies": []}
    assert client.put("/api/account/triage-strategy", json={"value": "auto"}).status_code == 503
    assert client.put("/api/account/triage-strategy", json={"value": None}).json()["value"] is None


# -- the Laya request ---------------------------------------------------------------------------------------
def test_ask_sends_the_account_strategy_only_when_it_has_one(
    client, upstream: FakeUpstream, agent: FakeAgent, monkeypatch, tmp_path, email: FakeEmailSender
) -> None:
    upstream.handler = Garrison()
    run_agents(tmp_path)
    calls: list[dict] = []
    laya_answers(agent, monkeypatch, {"type": "noul", "noul": 0.9, "answer_confidence": 0.9, "uncertain": False}, calls)
    make_member(client, email, "alice")
    login(client, "alice")

    assert client.post(ASK, json=YES_NO).status_code == 200
    assert "strategy" not in calls[-1]["request"]
    client.put("/api/account/triage-strategy", json={"value": "typed-only"})
    assert client.post(ASK, json=YES_NO).status_code == 200
    assert calls[-1]["request"]["strategy"] == "typed-only"
```

- [ ] **Step 2: Run to verify failure**

Run (from `apps/Ember/ember_api`): `python -m pytest tests/test_triage_strategy.py -v`
Expected: FAIL (404 on `/api/admin/triage-strategy`).

- [ ] **Step 3: Implement**

`services/agent_admin.py`, add after `set_prompts`:

```python
    async def triage_strategy(self, account: Account) -> dict[str, Any]:
        """Garrison's `{"default": str | None, "strategies": [names]}` for the Triage Assistant."""
        body = await self._request("GET", "/agents/triage-strategy", account)
        return body if isinstance(body, dict) else {"default": None, "strategies": []}

    async def set_triage_strategy(self, account: Account, value: str | None) -> dict[str, Any]:
        body = await self._request("PUT", "/agents/triage-strategy", account, json={"strategy": value})
        return body if isinstance(body, dict) else {"default": None, "strategies": []}
```

Create `routes/triage_strategy.py`:

```python
"""The Laya decision strategy of the Triage Assistant.

/api/admin/triage-strategy: the default for everyone, kept by Garrison (llm/triage_strategy.py); needs
settings.manage. /api/account/triage-strategy: the logged-in account's own choice (accounts.triage_strategy);
null follows the default. Strategy names are the Laya service's own list, read through Garrison."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import current_account, get_db_session, get_log_writer, require_permission
from src.models import Account
from src.routes.agent_admin import get_agent_admin
from src.services.agent_admin import AgentAdmin, AgentAdminRefused, AgentAdminUnavailable
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE

admin_router = APIRouter(prefix="/api/admin/triage-strategy", tags=["triage-strategy"])
account_router = APIRouter(prefix="/api/account/triage-strategy", tags=["triage-strategy"])

require_settings_manage = require_permission(SETTINGS_MANAGE)


class StrategyIn(BaseModel):
    # Required (no default): null clears, a missing field is a 422.
    value: str | None


async def _garrison(awaitable) -> Any:
    try:
        return await awaitable
    except AgentAdminUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "ai_agent is unreachable") from error
    except AgentAdminRefused as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error


@admin_router.get("")
async def read_default(
    account: Account = Depends(require_settings_manage), admin: AgentAdmin = Depends(get_agent_admin)
) -> dict[str, Any]:
    return await _garrison(admin.triage_strategy(account))


@admin_router.put("")
async def set_default(
    body: StrategyIn,
    account: Account = Depends(require_settings_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> dict[str, Any]:
    before = (await _garrison(admin.triage_strategy(account))).get("default")
    after = await _garrison(admin.set_triage_strategy(account, body.value))
    await logs.action(account, "triage_strategy.default", f"Default triage strategy: {before or 'not set'} -> {after.get('default') or 'not set'}")
    return after


@account_router.get("")
async def read_own(account: Account = Depends(current_account), admin: AgentAdmin = Depends(get_agent_admin)) -> dict[str, Any]:
    """The account's value, the default it falls back to and the strategies on offer (empty while Garrison is unreachable)."""
    try:
        info = await admin.triage_strategy(account)
    except (AgentAdminUnavailable, AgentAdminRefused):
        info = {"default": None, "strategies": []}
    return {"value": account.triage_strategy, "default": info.get("default"), "strategies": info.get("strategies", [])}


@account_router.put("")
async def set_own(
    body: StrategyIn,
    request: Request,
    account: Account = Depends(current_account),
    admin: AgentAdmin = Depends(get_agent_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if body.value is not None:
        try:
            info = await admin.triage_strategy(account)
        except (AgentAdminUnavailable, AgentAdminRefused) as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The strategy list is unavailable; try again later") from error
        names = info.get("strategies", [])
        if body.value not in names:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown strategy; choose one of: {', '.join(names)}")
    else:
        info = {"default": None, "strategies": []}
    account.triage_strategy = body.value
    session.add(account)
    await session.commit()
    if body.value is None:
        try:
            info = await admin.triage_strategy(account)
        except (AgentAdminUnavailable, AgentAdminRefused):
            pass
    return {"value": account.triage_strategy, "default": info.get("default"), "strategies": info.get("strategies", [])}
```

Check while implementing: `current_account` and `get_db_session` must hand back an `Account` attached to the same session so `session.add` persists the change (compare how `routes/account.py` saves `prompt_suggestions`, around line 179, and copy its commit pattern if it differs); drop the unused `Request` import if unused.

`app.py`: add `triage_strategy,` to the `from src.routes import (...)` list after `triage,` and `app.include_router(triage_strategy.admin_router)` plus `app.include_router(triage_strategy.account_router)` after `app.include_router(triage.router)`.

`services/triage_questions.py`: change `build_request`'s signature to `... trace: bool = False, levels: list[str] | None = None, strategy: str | None = None` and, after the `if trace:` block:

```python
    if strategy:
        request["strategy"] = strategy
```

and `TriageQuestions.ask` to accept `levels: list[str] | None = None, strategy: str | None = None` and pass `build_request(kind, text, question, options, trace, levels, strategy)`.

`routes/triage.py` line 135: `outcome = await triage.ask(_caller(account), body.kind, body.text, body.question, options, body.trace, body.levels, account.triage_strategy)`.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_triage_strategy.py tests/test_triage.py tests/test_agent_admin.py -v`
Expected: PASS. Then `python -m pytest -q` for the whole suite.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src apps/Ember/ember_api/tests/test_triage_strategy.py
git commit -m "feat(ember_api): per-account and default triage strategy"
```

---

### Task 8: ember_admin default-strategy panel

**Files:**
- Create: `apps/Ember/ember_admin/src/api/TriageStrategyClient.ts`
- Create: `apps/Ember/ember_admin/src/components/admin/TriageStrategyPanel.vue`
- Modify: `apps/Ember/ember_admin/src/views/WorkspaceSettingsView.vue`
- Test: `apps/Ember/ember_admin/src/components/admin/TriageStrategyPanel.test.ts`

**Interfaces:**
- Consumes: `GET/PUT /api/admin/triage-strategy` (Task 7).
- Produces: `triageStrategyClient.get(): Promise<{default: string | null; strategies: string[]}>` and `.set(value: string | null)`; `<TriageStrategyPanel />` (no props; emits `modified: [boolean]` like `SettingsPanel`).

First read `apps/Ember/ember_admin/src/components/admin/SettingsPanel.test.ts` and `src/views/WorkspaceSettingsView.vue` and copy how the first mocks `settingsClient` and how the second lists panels; follow the same style below. Also read `.agents/skills/ember-frontend-design/SKILL.md` for the shared tokens before styling.

- [ ] **Step 1: Write the failing test**

Create `TriageStrategyPanel.test.ts` (use the same mock approach as `SettingsPanel.test.ts`; shown here with `vi.mock`):

```ts
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { triageStrategyClient } from "../../api/TriageStrategyClient";
import TriageStrategyPanel from "./TriageStrategyPanel.vue";

vi.mock("../../api/TriageStrategyClient", () => ({
  triageStrategyClient: { get: vi.fn(), set: vi.fn() },
}));

const NAMES = ["english-only", "typed-only", "auto"];

describe("TriageStrategyPanel", () => {
  beforeEach(() => {
    vi.mocked(triageStrategyClient.get).mockResolvedValue({ default: null, strategies: NAMES });
    vi.mocked(triageStrategyClient.set).mockImplementation(async (value) => ({ default: value, strategies: NAMES }));
  });

  it("lists 'not set' first and then the service's strategies", async () => {
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    const options = w.findAll("option").map((o) => o.text());
    expect(options[0]).toMatch(/not set/i);
    expect(options.slice(1)).toEqual(NAMES);
  });

  it("saves only after Save and shows the stored value once the server answers", async () => {
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    await w.find("select").setValue("typed-only");
    expect(triageStrategyClient.set).not.toHaveBeenCalled();
    await w.find("button.primary").trigger("click");
    await flushPromises();
    expect(triageStrategyClient.set).toHaveBeenCalledWith("typed-only");
    expect(w.emitted("modified")?.at(-1)).toEqual([true]);
    expect(w.find(".save-bar").exists()).toBe(false);
  });

  it("keeps the draft and shows the error when the save fails", async () => {
    vi.mocked(triageStrategyClient.set).mockRejectedValue(new Error("ai_agent is unreachable"));
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    await w.find("select").setValue("auto");
    await w.find("button.primary").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("ai_agent is unreachable");
    expect((w.find("select").element as HTMLSelectElement).value).toBe("auto");
  });

  it("offers nothing to pick while the service list is empty", async () => {
    vi.mocked(triageStrategyClient.get).mockResolvedValue({ default: "typed-only", strategies: [] });
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    expect(w.text()).toContain("typed-only");
    expect(w.find("select").attributes("disabled")).toBeDefined();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `apps/Ember/ember_admin`): `npx vitest run src/components/admin/TriageStrategyPanel.test.ts`
Expected: FAIL (cannot resolve `TriageStrategyClient`).

- [ ] **Step 3: Implement**

`src/api/TriageStrategyClient.ts`:

```ts
import { apiRequest } from "./http";

/** The Triage Assistant's default Laya strategy (ember_api's /api/admin/triage-strategy, settings.manage). */
export interface TriageStrategyInfo {
  /** The administrator's default; null means none is set and the voter settings choose. */
  default: string | null;
  /** The strategies the Laya service offers; empty while it cannot be reached. */
  strategies: string[];
}

export const triageStrategyClient = {
  get: () => apiRequest<TriageStrategyInfo>("GET", "/api/admin/triage-strategy"),
  /** null clears the default. */
  set: (value: string | null) => apiRequest<TriageStrategyInfo>("PUT", "/api/admin/triage-strategy", { value }),
};
```

`src/components/admin/TriageStrategyPanel.vue` (same draft/Save/Cancel pattern, classes and `./admin.css` as `SettingsPanel.vue`):

```vue
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { triageStrategyClient, type TriageStrategyInfo } from "../../api/TriageStrategyClient";
import { errorMessage } from "../../utils/errors";
import "./admin.css";

/** Whether a default is set, for a page that counts changed settings. */
const emit = defineEmits<{ modified: [value: boolean] }>();

const NOT_SET = "";
const info = ref<TriageStrategyInfo | null>(null);
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const saved = ref(false);
const draft = ref(NOT_SET);

const stored = computed(() => info.value?.default ?? NOT_SET);
const dirty = computed(() => info.value !== null && draft.value !== stored.value);
const choices = computed(() => {
  const names = info.value?.strategies ?? [];
  // A default the service no longer lists stays visible so the admin can see and replace it.
  return stored.value && !names.includes(stored.value) ? [stored.value, ...names] : names;
});

async function load(): Promise<void> {
  loadError.value = "";
  try {
    info.value = await triageStrategyClient.get();
    draft.value = stored.value;
  } catch (err) {
    loadError.value = errorMessage(err);
  }
}

function cancel(): void {
  draft.value = stored.value;
  saveError.value = "";
}

async function save(): Promise<void> {
  saveError.value = "";
  saving.value = true;
  try {
    info.value = await triageStrategyClient.set(draft.value === NOT_SET ? null : draft.value);
    draft.value = stored.value;
    saved.value = true;
  } catch (err) {
    // The draft stays, so Save can be retried or Cancel drops it.
    saveError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

watch(stored, (value) => emit("modified", value !== NOT_SET), { immediate: true });
onMounted(load);
</script>

<template>
  <div class="admin-panel">
    <p v-if="loadError" class="error">error: {{ loadError }}</p>
    <section class="card">
      <div class="head">
        <span v-if="stored !== NOT_SET" class="dot" title="Changed from the default" aria-hidden="true" />
        <h3>Triage strategy</h3>
        <span v-if="saved && !dirty" class="chip saved">Saved</span>
        <span class="chip scope">Applies to every Laya caller</span>
      </div>
      <label class="field">
        <span>Default strategy</span>
        <select v-model="draft" :disabled="saving || !info || choices.length === 0" aria-label="Default triage strategy" @change="saved = false">
          <option :value="NOT_SET">Not set (follows triage_order)</option>
          <option v-for="name in choices" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
      <p class="muted">
        The decision strategy the Laya service uses when a request names none. Accounts can pick their own for prompts
        they send straight to the Triage Assistant from Ember. "Not set" keeps today's behaviour: the strategy follows
        the order and switches in config_tuning.json.
      </p>
      <div v-if="dirty" class="save-bar" role="group" aria-label="Unsaved change">
        <span class="dot" aria-hidden="true" />
        <span class="msg">You have an unsaved change. It applies to every account that has not picked its own.</span>
        <button type="button" class="small" :disabled="saving" @click="cancel">Cancel</button>
        <button type="button" class="primary" :disabled="saving" @click="save">Save</button>
      </div>
      <p v-if="saveError" class="error">{{ saveError }}</p>
    </section>
  </div>
</template>

<style scoped>
.card {
  padding: 20px;
  background: var(--bg);
}
.card > .muted {
  max-width: 620px;
  font-size: 0.9em;
}
.card h3 {
  margin: 0;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
}
.chip.scope {
  margin-left: auto;
}
.chip.saved {
  color: var(--success);
  border-color: var(--success);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 320px;
  margin-bottom: 12px;
}
.field select {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--surface);
  font: inherit;
}
.save-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
}
.save-bar .msg {
  flex: 1 1 200px;
  font-size: 0.9em;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.card p {
  margin-bottom: 0;
}
</style>
```

In `WorkspaceSettingsView.vue`, import `TriageStrategyPanel` and render `<TriageStrategyPanel />` right after `<SettingsPanel />` in the template line shown at line 9 (keep the other panels as they are).

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/components/admin/TriageStrategyPanel.test.ts src/views src/radiusScale.test.ts` then `npx vue-tsc -b`
Expected: PASS and no type errors.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_admin/src
git commit -m "feat(ember_admin): set the default triage strategy"
```

---

### Task 9: ember_web Settings row

**Files:**
- Create: `apps/Ember/ember_web/src/api/triage/TriageStrategyClient.ts`
- Modify: `apps/Ember/ember_web/src/features/settings/SettingsView.vue`
- Test: `apps/Ember/ember_web/src/features/settings/SettingsView.test.ts`

**Interfaces:**
- Consumes: `GET/PUT /api/account/triage-strategy` (Task 7).
- Produces: `triageStrategyClient.get(): Promise<{value, default, strategies}>`, `.save(value: string | null): Promise<same>`; a Settings row `triage-strategy` in a new group "triage" (scope "Your account") shown with the other groups.

First read `SettingsView.test.ts` (how it mounts, mocks `navPreferencesClient` and stores) and `.agents/skills/ember-frontend-design/SKILL.md`, then follow the same mocks. There is no select component in `components/ui/forms/` (it holds `SettingRow`, `SegmentedControl`, `ToggleSwitch`), so the row uses a native `<select>` styled with the page tokens.

- [ ] **Step 1: Write the failing tests**

Add to `SettingsView.test.ts`, mocking the new client next to the existing `navPreferencesClient` mock:

```ts
vi.mock("../../api/triage/TriageStrategyClient", () => ({
  triageStrategyClient: { get: vi.fn(), save: vi.fn() },
}));
```

and these tests (adapt the mount helper and imports to the file's existing ones):

```ts
const STRATEGY_INFO = { value: null, default: "auto", strategies: ["english-only", "typed-only", "auto"] };

it("shows the triage strategy with 'Default (…)' first and saves a pick with the other account settings", async () => {
  vi.mocked(triageStrategyClient.get).mockResolvedValue(STRATEGY_INFO);
  vi.mocked(triageStrategyClient.save).mockResolvedValue({ ...STRATEGY_INFO, value: "typed-only" });
  const w = await mountSettings();
  await flushPromises();

  const select = w.find('[data-setting-id="triage-strategy"] select');
  expect(select.findAll("option").map((o) => o.text())).toEqual(["Default (auto)", "english-only", "typed-only", "auto"]);
  await select.setValue("typed-only");
  expect(w.find(".settings-save-bar").exists()).toBe(true);
  await w.find(".settings-save-bar button.save").trigger("click");
  await flushPromises();
  expect(triageStrategyClient.save).toHaveBeenCalledWith("typed-only");
  expect(w.find(".settings-save-bar").exists()).toBe(false);
});

it("says 'Default (not set)' when the administrator set none and sends null for the default", async () => {
  vi.mocked(triageStrategyClient.get).mockResolvedValue({ value: "typed-only", default: null, strategies: ["typed-only"] });
  vi.mocked(triageStrategyClient.save).mockResolvedValue({ value: null, default: null, strategies: ["typed-only"] });
  const w = await mountSettings();
  await flushPromises();

  const select = w.find('[data-setting-id="triage-strategy"] select');
  expect(select.findAll("option")[0].text()).toBe("Default (not set)");
  await select.setValue("");
  await w.find(".settings-save-bar button.save").trigger("click");
  await flushPromises();
  expect(triageStrategyClient.save).toHaveBeenCalledWith(null);
});

it("disables the triage strategy while the strategy list is unavailable", async () => {
  vi.mocked(triageStrategyClient.get).mockResolvedValue({ value: null, default: null, strategies: [] });
  const w = await mountSettings();
  await flushPromises();
  expect(w.find('[data-setting-id="triage-strategy"] select').attributes("disabled")).toBeDefined();
});
```

(`mountSettings` stands for whatever helper the file already uses to mount the view with its stores; use that name.) Add a `beforeEach` default of `vi.mocked(triageStrategyClient.get).mockResolvedValue(STRATEGY_INFO)` so the file's existing tests keep passing.

- [ ] **Step 2: Run to verify failure**

Run (from `apps/Ember/ember_web`): `npx vitest run src/features/settings/SettingsView.test.ts`
Expected: FAIL (cannot resolve `TriageStrategyClient`).

- [ ] **Step 3: Implement**

`src/api/triage/TriageStrategyClient.ts`:

```ts
import { apiRequest } from "../http";

/** The account's own Laya strategy for prompts sent straight to the Triage Assistant (ember_api's /api/account/triage-strategy). */
export interface TriageStrategyInfo {
  /** The account's choice; null follows the administrator's default. */
  value: string | null;
  /** The administrator's default; null when none is set. */
  default: string | null;
  /** The strategies the Laya service offers; empty while it cannot be reached. */
  strategies: string[];
}

export const triageStrategyClient = {
  get: () => apiRequest<TriageStrategyInfo>("GET", "/api/account/triage-strategy"),
  /** null goes back to the administrator's default. */
  save: (value: string | null) => apiRequest<TriageStrategyInfo>("PUT", "/api/account/triage-strategy", { value }),
};
```

`SettingsView.vue`:

1. Import: `import { triageStrategyClient, type TriageStrategyInfo } from "../../api/triage/TriageStrategyClient";`
2. `SettingDef.group` type: add `"triage"`. Add to `GROUPS` (after the `sidebar` entry):

```ts
  {
    id: "triage",
    title: "Triage Assistant",
    icon: "M8 2l5 2v4c0 3-2 5-5 6-3-1-5-3-5-6V4z",
    scope: "Your account",
    note: "Applied when you save. Stored on your account.",
  },
```

   Add to `DEFS`:

```ts
  {
    id: "triage-strategy",
    group: "triage",
    label: "Triage strategy",
    description: "How the Triage Assistant decides when you ask it a question directly.",
    keywords: ["laya", "triage", "strategy", "classifier", "english", "typed", "consensus", "average"],
  },
```

3. State, near the other refs:

```ts
const strategyInfo = ref<TriageStrategyInfo | null>(null);
async function loadStrategy(): Promise<void> {
  try { strategyInfo.value = await triageStrategyClient.get(); } catch { strategyInfo.value = null; }
}
const STRATEGY_COST: Record<string, string> = {
  "english-only": "1 call", "typed-only": "1 call", "english-then-typed": "1-2+ calls",
  "typed-then-english": "1-2+ calls", "most-confident": "2 calls", average: "2 calls", consensus: "2 calls", auto: "1-2+ calls",
};
const strategyOptions = computed(() => [
  { value: "", label: `Default (${strategyInfo.value?.default ?? "not set"})` },
  ...(strategyInfo.value?.strategies ?? []).map((name) => ({ value: name, label: name, cost: STRATEGY_COST[name] ?? "" })),
]);
```

4. In `saved` add `triageStrategy: strategyInfo.value?.value ?? "",`. In `dirty` add `|| draft.value.triageStrategy !== saved.value.triageStrategy`. In `save()`, after the sidebar block add:

```ts
    if (next.triageStrategy !== saved.value.triageStrategy) {
      const result = await triageStrategyClient.save(next.triageStrategy || null);
      if (accountId !== auth.account?.id) return;
      strategyInfo.value = result;
      draft.value.triageStrategy = result.value ?? "";
    }
```

   In `modified` add `"triage-strategy": draft.value.triageStrategy !== "",`. In `onMounted` add `void loadStrategy();`. Also make the existing `watch(saved, …)` keep working: it already syncs untouched draft keys, so the late-loaded value reaches the draft.

5. Template, after the `sidebar` card block:

```vue
        <div v-else-if="g.id === 'triage'" class="card">
          <SettingRow
            v-if="shown.has('triage-strategy')"
            setting-id="triage-strategy"
            label="Triage strategy"
            :description="strategyDescription"
            :modified="modified['triage-strategy']"
            @reset="draft.triageStrategy = ''"
          >
            <select
              v-model="draft.triageStrategy"
              class="strategy-select"
              aria-label="Triage strategy"
              :disabled="!strategyInfo || strategyInfo.strategies.length === 0"
            >
              <option v-for="o in strategyOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </SettingRow>
        </div>
```

   add next to `strategyOptions` in the script:

```ts
const strategyDescription = computed(() => {
  const picked = strategyOptions.value.find((o) => o.value === draft.value.triageStrategy);
  const cost = picked && "cost" in picked && picked.cost ? ` Costs ${picked.cost} to the local Laya models per question.` : "";
  return `How the Triage Assistant decides when you ask it a question directly.${cost}`;
});
```

   and style:

```css
.strategy-select { max-width: 220px; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/features/settings && npx vue-tsc -b`
Expected: PASS, no type errors. Then `npx vitest run` for the whole app.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_web/src
git commit -m "feat(ember_web): choose the triage strategy in Settings"
```

---

### Task 10: Docs and spec

**Files:**
- Modify: `apps/garrison/src/llm/README.md`, `apps/garrison/README.md` (the triage section near line 304), `apps/Ember/ember_api/README.md` (route tables), `apps/Ember/ember_admin/README.md`, `apps/Ember/ember_web/src/README.md`
- Modify: `docs/superpowers/specs/2026-10-25-triage-strategy-design.md`

- [ ] **Step 1: Update the docs**

- `apps/garrison/src/llm/README.md`: list `triage_strategy.py` (admin default routes) and note `triage_flow.py` resolves request, then admin default, then voters; list `core/tuning_overrides.py` in the Garrison README where `core/` is described.
- `apps/garrison/README.md`: in the triage section add that a request may carry `"strategy"` (any name from `GET /v1/strategies`), that the admin default lives in `configs/config_tuning_overrides.json`, and the two `/agents/triage-strategy` routes.
- `apps/Ember/ember_api/README.md`: add rows for `GET/PUT /api/admin/triage-strategy` (`settings.manage`) and `GET/PUT /api/account/triage-strategy` (logged in), and mention `accounts.triage_strategy`.
- ember_admin and ember_web READMEs: one line each for the new panel and Settings row.
- Spec: apply the six "Spec adjustments" listed at the top of this plan (route path, no new permission, `accounts.triage_strategy` column instead of `account_tuning`, "not set" semantics, overlay file name, 422 for a stale stored value), and drop the "migration adds columns to account_tuning" sentence.

- [ ] **Step 2: Commit**

```bash
git add apps docs
git commit -m "docs: triage strategy routes, settings and spec adjustments"
```

---

### Task 11: End-to-end check

- [ ] **Step 1: Full suites**

Run: `python -m pytest -q` in `apps/garrison` and in `apps/Ember/ember_api`; `npx vue-tsc -b && npx vitest run` in `ember_admin` and `ember_web`.
Expected: all green. Fix and recommit anything that fails; do not skip.

- [ ] **Step 2: Against the running stack**

With the Citadel stack and LayaAgent running (`docs/deployment.md`): in ember_admin Workspace settings choose a default and Save; `GET /agents/triage-strategy` on the entry agent shows it and `configs/config_tuning_overrides.json` holds it. In ember_web Settings pick a strategy, Save, then send a direct Triage Assistant question and confirm the Laya service log shows that strategy. Pick "Default" and confirm the admin default is used; clear the admin default and confirm the old voter-derived strategy returns. State in the final report what was and was not run.

- [ ] **Step 3: Do not push**

Commits stay local; no push or PR unless asked.
