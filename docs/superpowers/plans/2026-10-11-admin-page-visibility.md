# Admin Page Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An admin hides sidebar pages for every account; ember_web honours the list.

**Architecture:** One extra `app_settings` row (`hidden_pages`, JSON list) behind two ember_api routes. ember_web loads it into a store and `visiblePages` filters on it. ember_admin edits it in Workspace settings.

**Tech Stack:** FastAPI + SQLAlchemy async + pytest (ember_api); Vue 3 + TS + Pinia + Vitest (ember_web, ember_admin).

**Spec:** `docs/superpowers/specs/2026-10-11-admin-page-visibility-design.md`

## Global Constraints

- Code is OOP: behaviour in classes with injected collaborators.
- Do NOT commit or push; leave changes in the working tree and report. The owner commits.
- Never read or print `.env*`, `secrets/` or key files. No browser launching; the owner tests by hand.
- Another session has uncommitted ember_web work (`README.md`, `e2e/fakeApi.ts`, `src/api/types.ts`, `CommandFormModal.*`, `MarkdownContent.vue`, `MessageList.vue`, `ToolRunForm.*`, `utils/toolSchema.ts`, `ChatView.vue`). Never edit or revert those hunks. Edit only your own hunks in shared files.
- No literal `border-radius` values (use the radius tokens).
- Protected page ids that can never be hidden: `/` and `/settings`.
- Hide list limits: at most 20 ids, each `^/[a-z0-9-]+$` and at most 32 characters, stored JSON under 200 characters.
- Setting name: `hidden_pages`. Activity log action: `settings.pages`.

---

### Task 1: ember_api service, routes, audit

**Files:**
- Modify: `apps/Ember/ember_api/src/services/settings_service.py`, `src/routes/settings.py`, `src/routes/admin.py` (next to `PUT /settings/{name}` at about line 200), `README.md`
- Test: `apps/Ember/ember_api/tests/test_hidden_pages.py`

**Interfaces:**
- Produces in `settings_service.py`:
  - `HIDDEN_PAGES = "hidden_pages"`, `PROTECTED_PAGES = frozenset({"/", "/settings"})`, `MAX_HIDDEN_PAGES = 20`, `PAGE_ID_PATTERN = r"^/[a-z0-9-]{1,31}$"`.
  - `class InvalidPages(ValueError)` with a message safe to show.
  - `SettingsService.hidden_pages() -> list[str]` (empty when no row or unreadable JSON).
  - `SettingsService.set_hidden_pages(pages: list[str]) -> list[str]` validates (pattern, protected, count, JSON length under 200), de-duplicates keeping order, stores, and returns the **previous** list.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hidden_pages.py
"""GET /api/settings/pages for any account, PUT /api/admin/settings/pages for settings.manage."""
from __future__ import annotations

from tests.test_admin import login, make_member, role_by_name
from tests.test_registration import as_admin


def test_default_is_empty(client) -> None:
    login(client)  # the helper used by tests/test_settings*.py to sign in as the bootstrap admin
    assert client.get("/api/settings/pages").json() == {"hidden": []}


def test_admin_saves_and_everyone_reads(client) -> None:
    as_admin(client)
    saved = client.put("/api/admin/settings/pages", json={"hidden": ["/usage", "/agents", "/usage"]})
    assert saved.status_code == 200 and saved.json() == {"hidden": ["/usage", "/agents"]}
    assert client.get("/api/settings/pages").json() == {"hidden": ["/usage", "/agents"]}


def test_member_cannot_write(client) -> None:
    make_member(client)
    assert client.put("/api/admin/settings/pages", json={"hidden": ["/usage"]}).status_code == 403


def test_bad_lists_are_refused(client) -> None:
    as_admin(client)
    for body in (
        {"hidden": ["/"]}, {"hidden": ["/settings"]}, {"hidden": ["usage"]}, {"hidden": ["/Bad"]},
        {"hidden": [f"/p{i}" for i in range(21)]}, {"hidden": ["/" + "a" * 40]}, {"hidden": "/usage"}, {},
    ):
        assert client.put("/api/admin/settings/pages", json=body).status_code in (400, 422), body
    assert client.get("/api/settings/pages").json() == {"hidden": []}


def test_change_is_logged(client) -> None:
    as_admin(client)
    client.put("/api/admin/settings/pages", json={"hidden": ["/usage"]})
    entries = client.get("/api/logs", params={"action": "settings.pages"}).json()
    assert any(e["action"] == "settings.pages" for e in entries.get("entries", entries))
```

Adapt the helper names (`login`, `as_admin`, `make_member`) to the real ones in `tests/test_admin.py` and `tests/test_registration.py`; look at an existing settings test (`grep -rn "force_tool_approval" tests`) for the exact sign-in and log-reading pattern, and mirror it. Adjust the log assertion to the real shape of `GET /api/logs`.

- [ ] **Step 2: Run to see failure**

Run: `cd apps/Ember/ember_api && .venv_ember_api/Scripts/python.exe -m pytest tests/test_hidden_pages.py -q`
Expected: 404s.

- [ ] **Step 3: Implement the service methods**

```python
# settings_service.py (additions)
import json
import re

HIDDEN_PAGES = "hidden_pages"
PROTECTED_PAGES = frozenset({"/", "/settings"})
MAX_HIDDEN_PAGES = 20
_PAGE_ID = re.compile(r"^/[a-z0-9-]{1,31}$")
_MAX_STORED = 200


class InvalidPages(ValueError):
    """The list of hidden pages is not acceptable."""


# in SettingsService
async def hidden_pages(self) -> list[str]:
    row = await self._session.get(AppSetting, HIDDEN_PAGES)
    if row is None:
        return []
    try:
        value = json.loads(row.value)
    except ValueError:
        return []
    return [p for p in value if isinstance(p, str)] if isinstance(value, list) else []

async def set_hidden_pages(self, pages: list[str]) -> list[str]:
    """Saves the list and returns the previous one."""
    unique = list(dict.fromkeys(pages))
    if len(unique) > MAX_HIDDEN_PAGES:
        raise InvalidPages(f"At most {MAX_HIDDEN_PAGES} pages can be hidden")
    for page in unique:
        if page in PROTECTED_PAGES:
            raise InvalidPages("That page cannot be hidden")
        if not _PAGE_ID.match(page):
            raise InvalidPages(f"Not a page id: {page[:40]}")
    text = json.dumps(unique, separators=(",", ":"))
    if len(text) > _MAX_STORED:
        raise InvalidPages("The list is too long")
    before = await self.hidden_pages()
    row = await self._session.get(AppSetting, HIDDEN_PAGES)
    if row is None:
        self._session.add(AppSetting(name=HIDDEN_PAGES, value=text))
    else:
        row.value = text
        row.updated_at = utcnow()
    await self._session.commit()
    return before
```

Update the module docstring (it says every setting is a yes/no switch). `BOOLEAN_SETTINGS` and `all()` stay unchanged so `GET /api/settings` still returns only booleans.

- [ ] **Step 4: Routes**

In `routes/settings.py` add, before nothing else (path `/pages` does not collide with `GET ""`):

```python
class HiddenPagesOut(BaseModel):
    hidden: list[str]


@router.get("/pages")
async def read_hidden_pages(
    _account: Account = Depends(current_account),
    app_settings: SettingsService = Depends(get_settings_service),
) -> HiddenPagesOut:
    return HiddenPagesOut(hidden=await app_settings.hidden_pages())
```

In `routes/admin.py`, **declare it before** `@router.put("/settings/{name}")` so `pages` is not read as a setting name:

```python
class HiddenPagesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hidden: list[str] = Field(max_length=MAX_HIDDEN_PAGES)


@router.put("/settings/pages")
async def set_hidden_pages(
    body: HiddenPagesIn,
    account: Account = Depends(require_settings_manage),
    app_settings: SettingsService = Depends(get_settings_service),
    logs: LogWriter = Depends(get_log_writer),
) -> dict[str, list[str]]:
    """Hides pages from every account's sidebar (nav only; the pages still open by URL)."""
    try:
        before = await app_settings.set_hidden_pages(body.hidden)
    except InvalidPages as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    now = await app_settings.hidden_pages()
    await logs.action(account, "settings.pages", f"Hidden sidebar pages: {before or 'none'} -> {now or 'none'}")
    return {"hidden": now}
```

Use whatever imports and the log-writer dependency name the neighbouring `PUT /settings/{name}` route already uses.

- [ ] **Step 5: Run** the new tests, then `tests/test_settings*.py tests/test_admin.py -q`. Expected PASS. Add a line to `ember_api/README.md`'s settings section.

---

### Task 2: ember_web store and `visiblePages`

**Files:**
- Modify: `apps/Ember/ember_web/src/api/SettingsClient.ts`, `src/router/pages.ts` (`visiblePages`), `src/components/NavRail.vue` (lines ~33 and ~50), `src/components/SidebarEditor.vue` (~36), `src/views/AccountView.vue` (~25), `src/views/OverviewView.vue` (~13), `src/App.vue` (load alongside games), `src/router/index.ts` (home redirect, keep as is)
- Create: `src/stores/pageVisibility.ts`, `src/stores/pageVisibility.test.ts`
- Modify tests: `src/router/pages.test.ts` (or wherever `visiblePages` is tested), `NavRail`, `SidebarEditor`, `AccountView`, `OverviewView` tests that pass the `hasGames` argument.

**Interfaces:**
- `settingsClient.pages(): Promise<{ hidden: string[] }>` (`GET /api/settings/pages`).
- `usePageVisibilityStore()` exposes `hidden: string[]`, `ready: boolean`, `load(): Promise<void>`, and clears itself when the account changes. Follow the epoch pattern of `stores/games.ts`.
- `visiblePages(hasPermission: (p: string) => boolean, hidden: readonly string[] = []): NavPage[]`. A page is shown when its permission passes and (`to` is `/` or `/settings` or `to` not in `hidden`). The `/games` special case and the `hasGames` argument are removed; the Games entry gets `permission: ""` (already present) so it follows the same rule.

- [ ] **Step 1: Propose this step to the owner and wait for approval (ember_web workflow).**
- [ ] **Step 2: Failing tests:** `visiblePages` hides listed pages, never hides `/` or `/settings`, shows Games with no games; store loads, resets on account change, treats a failed load as "nothing hidden".
- [ ] **Step 3: Implement** the client method, store and `visiblePages`; update the five callers to pass `pageVisibility.hidden`; load the store in `App.vue` next to `games.load()`.
- [ ] **Step 4: Run** `npx vue-tsc -b`, `npx vitest run`, `npx vite build`. Expected PASS.

---

### Task 3: ember_admin section

**Files:**
- Create: `apps/Ember/ember_admin/src/components/admin/SidebarPagesPanel.vue`, `.test.ts`, `src/utils/emberWebPages.ts`
- Modify: `src/api/SettingsClient.ts`, `src/views/WorkspaceSettingsView.vue`, `README.md`
- Test: client test beside the client

**Interfaces:**
- `emberWebPages.ts`: `export const EMBER_WEB_PAGES = [{ id: "/capabilities", label: "Capabilities" }, { id: "/agents", label: "Agents" }, { id: "/games", label: "Games" }, { id: "/usage", label: "Usage" }, { id: "/tickets", label: "Tickets" }] as const;` with a comment: copy of the hideable pages in `ember_web/src/router/pages.ts`; update both together.
- `settingsClient.pages()` and `settingsClient.setPages(hidden: string[])` (`PUT /api/admin/settings/pages`).
- `SidebarPagesPanel.vue`: follows `SettingsPanel.vue`: a draft until Save, a bar naming the effect ("applies to every account"), Cancel, Reset to default (empty list), saved notice, load and save errors. One `LockSwitch` per page, checked = shown. Emits `modified` (stored list is non-empty) like `SettingsPanel`.

- [ ] **Step 1: Failing tests:** lists the five pages all on by default; flipping one marks dirty; Save calls `setPages` with the hidden ids; Cancel restores; Reset empties the draft; load error shows.
- [ ] **Step 2: Implement; add the panel under `SettingsPanel` in `WorkspaceSettingsView.vue`.**
- [ ] **Step 3: Run** `npx vue-tsc -b && npx vitest run && npx vite build` in `ember_admin`. Expected PASS.

---

### Task 4: Final check and docs

- [ ] `cd apps/Ember/ember_api && .venv_ember_api/Scripts/python.exe -m pytest tests/test_hidden_pages.py tests/test_admin.py tests/test_settings*.py -q`
- [ ] `ember_web` and `ember_admin`: `npx vue-tsc -b`, `npx vitest run`, `npx vite build`.
- [ ] Confirm `EMBER_WEB_PAGES` in ember_admin matches the hideable entries of `NAV_PAGES` in ember_web (every `to` except `/` and `/settings`).
- [ ] Update `ember_web/README.md` (own hunk only) and the vault note `Brain/Projects/ember_web.md` per `Brain/AGENTS.md`.
- [ ] Report files changed, commands run with results, deviations.

---

## Self-review

**Spec coverage:** API read and write with validation and audit (Task 1); store, `visiblePages`, always-visible Games, Sidebar editor, rail and Overview (Task 2); admin section with draft and Save (Task 3); protected pages enforced on both server and client; drift check (Task 4).

**Placeholder scan:** Task 1 test helper names are to be matched to the real ones in the existing tests, as stated. No other open items.

**Type consistency:** setting name `hidden_pages`, response shape `{hidden: string[]}`, `visiblePages(hasPermission, hidden)` and `EMBER_WEB_PAGES` ids match across tasks.
