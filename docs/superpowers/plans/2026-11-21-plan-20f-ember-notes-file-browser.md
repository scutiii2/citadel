# Ember Notes Page as the Long-Term File Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Notes page of the Ember Windows app becomes the browser of the user's long-term memory (the Brain files kept by Stronghold): folders, search, create, edit with conflict handling, restore the original text of an agent or shared file, a switch that lets agents edit a file, and a quota line with a near-full and full warning.

**Architecture:** The backend already exists (Plans 20b and 20d): Portcullis serves `GET/POST /api/brain/files`, `GET/PUT/DELETE /api/brain/files/{id}`, `POST /api/brain/files/{id}/revert`, `GET /api/brain/search` and `GET /api/brain/summary`. This plan changes only `apps/ember`: a typed API client, a Pinia store that keeps the list, folders, quota and search results and ignores late replies, two presentational components (`FileList`, `FileEditor`) and a rewritten `NotesView` that wires them into the existing `ListEditorLayout`. The old Notes page (private notes in Treasury, Laya tag suggestions, publishing to Obsidian) is removed from Ember in the same change; its backend routes go in a later plan.

**Tech Stack:** Vue 3 + TypeScript, Pinia, Vitest and `@vue/test-utils`, Tauri shell (untouched).

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, section "Brain (Stronghold)" ("Notes page becomes the long-term file browser", "Automatic records show a warning that editing may break the agent using them", "the user can allow edits per file"). Roadmap row 20f. Backend: `docs/superpowers/plans/2026-11-20-plan-20b-long-term-brain.md` and `2026-11-21-plan-20d-global-brain-and-sharing.md`. UI rules: `.agents/skills/ember-frontend-design/SKILL.md`, `mobile-ui.md` and `.agents/skills/ember-design-system/SKILL.md` (read all three before Task 3).

## Global Constraints

- Work only in `apps/ember` (the Windows app). `apps/ember_web` is reference only; do not copy anything there. No backend, Portcullis, Stronghold or Legion change.
- Never call `fetch` or build an `/api` URL by hand outside `apiRequest` (`src/api/http.ts`). The client uses `apiRequest` only.
- Radius only through `--radius-*` tokens, colour only through tokens, no hex and no literal radius (`radiusScale.test.ts` fails on one). Never add a reduced-motion setting, media query or test. Animations always play.
- Reuse the shared pieces the old page used: `ListEditorLayout`, `PageLayout`, `ListRow`, `SearchField`, `StateMessage`, `ConfirmModal`, `DangerZone`, `TagInput`, `ToggleSwitch`, `CharacterCount`, `useUnsavedGuard`, the global `chip`, `primary`, `danger`, `status-badge` classes. Do not write a page-local empty, load-error or counter style.
- A change that calls the server stays pending until the server answers; never show unconfirmed state. Status (agent file, nearly full, full) uses an icon plus text, never colour alone.
- Hit areas of at least 44 by 44 CSS px on touch (below 768px) for rows, chips, switches and buttons; visible focus ring; every icon-only control has an `aria-label`.
- Unsaved edits are never lost silently: switching file, going back and leaving the page ask first.
- Private content (file titles, text, tags, folders) is cleared when the page unmounts and when the account signs out; a late reply must never show after that.
- File text and titles never go into a console message, an error message built by this code, a test name or a snapshot.
- Agents can read every file in the Brain. The editor says so beside the agent switch, and never offers a way to hide a file from agents.
- Use `pnpm` (not npm). No new dependency. Keep each file's line endings.

---

## File Map

All paths under `apps/ember/src/features/notes/` unless noted.

- Create `api/BrainClient.ts` and `api/BrainClient.test.ts` (types, `brainClient`, limits, `normalizeTag`, `normalizeFolder`, `folderProblem`).
- Create `stores/brain.ts` and `stores/brain.test.ts`.
- Create `components/FileList.vue` and `components/FileList.test.ts`.
- Create `components/FileEditor.vue` and `components/FileEditor.test.ts`.
- Rewrite `NotesView.vue` and `NotesView.test.ts`.
- Delete `api/NotesClient.ts`, `api/NotesClient.test.ts`, `components/NotePromotionPanel.vue`, `components/NotePromotionPanel.test.ts`, `NotesPublicationDraft.test.ts`.
- Modify `apps/ember/src/router/pages.ts` (the Notes description only).
- Modify `apps/ember/README.md` only if it describes the Notes page (grep first; skip and say so if not).
- Roadmap: the row for 20f is already split by the author (this plan is 20f).

## Out of scope (note in the report, do not build)

The global brain (browse, write, review queue), sharing (send, inbox, blocks), the Skills review page, agent proposals and their inbox, the Stronghold Admin brain settings page, a Markdown preview, moving or renaming a whole folder, bulk actions, the Obsidian publishing panel (removed here; the Brains page stays until Plan 22), Laya or tag-writer suggestions, removal of Stronghold's `/notes` and `/memory` routes (later plan). The `notes` capability mapping in `router/capabilityPages.ts` stays; it still points at `/notes`.

## Assumptions to check at build time (record each result under "Changes found during work")

- (a) Response and request shapes: read `apps/stronghold/src/brain/files_routes.py` (`row()`, `full()`, `NewFile`, `FileChange`, `RevertFile`), `apps/portcullis/src/routes/brain_files.py` and `apps/stronghold/src/brain/files.py` (`summary`). `GET /api/brain/files` answers `{files: row[], folders: string[]}` newest first; a row has no text (it has `chars`), a full file has `body` and no `chars`. The route needs `chat.use`, the same permission as the nav entry.
- (b) Status codes the page relies on: 412 for a stale `expected_revision` on PUT and revert; 409 for "limit reached", "already exists", "nothing to revert"; 422 for a bad title, folder, tag or text length; 403 never reaches a user edit. `apiRequest` throws `ApiError` whose `message` is the server's `detail` (a list of field errors is joined). Read `src/api/http.ts`.
- (c) Tag rules: `normalize_tags` in `apps/stronghold/src/notes/store.py` (30 characters, 10 tags, `[a-z0-9][a-z0-9_-]*`). The client's `normalizeTag` must match; copy it from the old `NotesClient.ts` before you delete that file.
- (d) The shared components behave as the old `NotesView.vue` uses them (props, slots, `v-model`, `commit()` and `add()` on `TagInput`; `ToggleSwitch` `@change` with a checkbox target; `StateMessage` kinds; `ListEditorLayout` slots `list`, `head`, `editor`, `placeholder`). `chip`, `chip.active`, `primary`, `danger`, `error`, `muted`, `status-badge`, `sr-only`, `pane-scroll` and `line-icon` exist (`style.css`, `infoPage.css`).
- (e) Everything that references the files to delete: grep `features/notes`, `NotePromotionPanel`, `NotesClient`, `normalizeTag`, `NOTE_` across `src`, tests, docs and `architecture.test.ts`. `NotePromotionPanel` uses `brainsClient`; the Brains page keeps that client, so nothing else is removed.
- (f) Tests that assert the Notes nav description or label (grep the old description text "Private notes, just for your account." in `src`). Only the description changes; the label stays "Notes".
- (g) The rules of `architecture.test.ts`, `radiusScale.test.ts` and `themeContrast.test.ts` so new files comply on the first run. Compute the contrast of `--warning` and `--danger` as text on `--surface` and `--bg` in light and dark. If a pair is under 4.5:1 (Plan 20e found both under it in the light theme), tint only the icon and keep the text on `--text` or `--muted`, as in `StackMenu.vue`.
- (h) Vue 3.5 (`useId`), camelCase `v-model:tagText` arguments compile, and jsdom lacks `<dialog>.showModal` (copy the polyfill from the old `NotesView.test.ts`).

## Baseline

- Baseline at main commit e77ba795 in the Plan 20f worktree: vue-tsc exited 0. Vitest passed 187 files and 2,272 cases. Both pnpm commands used --config.verify-deps-before-run=false to run the existing dependency tree after lockfile verification stalled.

## Changes found during work

### Assumption checks

- (a) Stronghold lists newest first and includes ancestor folders. List and search rows carry `chars`, full responses carry `body`, and summary supplies usage, limits and skipped files. Portcullis uses `require_chat` (`chat.use`), matching the Notes page.
- (b) PUT and revert use `expected_revision` and return 412 on stale revisions. Duplicate locations, quotas and missing originals can return 409. Validation failures return 422. Agent authorization failures are separate from the signed-in user's edits. `apiRequest` exposes the status and server detail with `ApiError`.
- (c) Copied the legacy client tag normalization before deleting it. The result fits Stronghold's 30-character, 10-tag and allowed-character rules.
- (d) Shared component models, slots, `TagInput.commit()` and `add()`, the checkbox change event, and CSS utilities fit the snippets. Editor, list and modal tests exercise the actual components.
- (e) Legacy client and publication panel callers were confined to the replaced view and its tests. The router still imports NotesView and the Brains page still uses BrainsClient.
- (f) The old description appeared only in `router/pages.ts`. Changed that description. The Notes label, path, route name and permission stay the same.
- (g) Architecture, radius and theme test suites passed. WCAG contrast ratios for light and dark respectively were warning on surface 4.11:1 / 8.81:1, warning on background 4.44:1 / 9.60:1, danger on surface 3.98:1 / 7.03:1, and danger on background 4.30:1 / 7.66:1. Warning and quota text use neutral tokens. Icons carry the status tint.
- (h) Vue 3.5 supports `useId` and the camelCase model arguments type-check. Installed jsdom lacks both dialog methods. The page tests use the old suite's dialog polyfill.

### Adjustments and verification

- Kept folder chips in the list scroller so many folders cannot hide file rows. Added an icon to the agent-file list badge.
- Offer the agent-edit switch on saved non-agent files. The create endpoint has no `agent_editable` field. The editor explains agent read access for drafts and saved files.
- Clear editor fields, conflict, search, dialogs and the active request generation on account change and unmount. Invalidate the previous search at keystroke time, before the next debounced request. Added three page regression tests for these cases and one editor regression test for the agent-edit switch.
- Hide the stale-save override after a stale restore when there is no editor draft to save. Size mobile retry, dialog and tag-option controls with the page's existing 767px breakpoint.
- Copied the author's roadmap split from the main checkout into the worktree. The Ember README contains no Notes description to update.
- Replaced the old `NotesView.test.ts` (58 cases) with 22 file-browser cases. Deleted `NotesClient.test.ts` (17 cases, including nine parameterized tag cases), `NotePromotionPanel.test.ts` (six), and `NotesPublicationDraft.test.ts` (one). Private Treasury notes, Laya tag suggestions and Obsidian publishing left the Ember Notes page. No other test expectations changed.
- Observed the expected failing test run before each task's implementation. Focused green runs covered 11 API client cases, 16 store cases, 25 component cases plus 20 architecture/radius/theme checks, and 22 page cases. The final Ember type check exited 0. The full suite passed 188 files and 2,264 cases, compared with 187 files and 2,272 cases at baseline. Commands ran inside the Plan 20f worktree with `--config.verify-deps-before-run=false` after pnpm stalled during lockfile verification.

---

### Task 1: Brain files API client

**Files:**
- Create: `apps/ember/src/features/notes/api/BrainClient.ts`
- Test: `apps/ember/src/features/notes/api/BrainClient.test.ts`

**Interfaces:**
- Consumes: `apiRequest(method, path, body?)` (`src/api/http.ts`).
- Produces: types `FileSource`, `BrainFileRow`, `BrainFile`, `BrainList`, `SearchHit`, `BrainSummary`, `FileDraft`, `FileChanges`; constants `FILE_TITLE_MAX`, `FILE_TAG_MAX`, `FILE_TAGS_MAX`, `FOLDER_DEPTH_MAX`; functions `normalizeTag(raw)`, `normalizeFolder(raw)`, `folderProblem(folder)`; `brainClient` with `list()`, `get(id)`, `create(draft)`, `update(id, changes, expectedRevision?)`, `revert(id, expectedRevision?)`, `remove(id)`, `search(query)`, `summary()`.

- [x] **Step 1: Write the failing test**

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { brainClient, folderProblem, normalizeFolder, normalizeTag } from "./BrainClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("brainClient", () => {
  it("lists, reads and summarises", async () => {
    await brainClient.list();
    await brainClient.get("f-1");
    await brainClient.summary();
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/files");
    expect(request).toHaveBeenNthCalledWith(2, "GET", "/api/brain/files/f-1");
    expect(request).toHaveBeenNthCalledWith(3, "GET", "/api/brain/summary");
  });

  it("creates a file from a draft", async () => {
    const draft = { title: "Tea", body: "Green", tags: ["tea"], folder: "food" };
    await brainClient.create(draft);
    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/brain/files", draft);
  });

  it("changes a file and sends the revision the editor opened", async () => {
    await brainClient.update("f-1", { title: "New" }, 3);
    expect(request).toHaveBeenCalledExactlyOnceWith("PUT", "/api/brain/files/f-1", { title: "New", expected_revision: 3 });
  });

  it("sends no revision when none is given", async () => {
    await brainClient.update("f-1", { agent_editable: true });
    expect(request).toHaveBeenCalledExactlyOnceWith("PUT", "/api/brain/files/f-1", { agent_editable: true });
  });

  it("reverts with the revision, and deletes", async () => {
    await brainClient.revert("f-1", 4);
    await brainClient.remove("f-1");
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/brain/files/f-1/revert", { expected_revision: 4 });
    expect(request).toHaveBeenNthCalledWith(2, "DELETE", "/api/brain/files/f-1");
  });

  it("searches with the query encoded", async () => {
    await brainClient.search("a b&c");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/brain/search?q=a%20b%26c");
  });

  it("encodes a file id", async () => {
    await brainClient.get("a/b");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/brain/files/a%2Fb");
  });
});

describe("normalizeTag", () => {
  it("follows the server's rules", () => {
    expect(normalizeTag("  Work Stuff! ")).toBe("work-stuff");
    expect(normalizeTag("--x")).toBe("x");
    expect(normalizeTag("a".repeat(40))).toHaveLength(30);
    expect(normalizeTag("!!!")).toBe("");
  });
});

describe("folders", () => {
  it("normalizeFolder cleans what was typed", () => {
    expect(normalizeFolder("  Projects / Citadel Notes/ ")).toBe("projects/citadel-notes");
    expect(normalizeFolder("\\a\\b")).toBe("a/b");
    expect(normalizeFolder("a//b")).toBe("a/b");
    expect(normalizeFolder("///")).toBe("");
  });

  it("folderProblem accepts the top level and up to three levels", () => {
    expect(folderProblem("")).toBe("");
    expect(folderProblem("a")).toBe("");
    expect(folderProblem("a/b/c")).toBe("");
    expect(folderProblem("a-1/b_2")).toBe("");
  });

  it("folderProblem refuses a fourth level, a bad start and a long name", () => {
    for (const bad of ["a/b/c/d", "-a", "a/_b", "a/", "x".repeat(41)]) expect(folderProblem(bad)).not.toBe("");
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run (from `apps/ember`): `pnpm exec vitest run src/features/notes/api/BrainClient.test.ts`
Expected: FAIL, the module `./BrainClient` does not exist.

- [x] **Step 3: Write the client**

```ts
import { apiRequest } from "../../../api/http";

export type FileSource = "manual" | "automatic" | "shared";

/** A file without its text, as the list and search routes answer. Times are naive UTC strings. */
export interface BrainFileRow {
  id: string;
  title: string;
  /** "" is the top level; otherwise up to three lowercase levels, "projects/citadel". */
  folder: string;
  tags: string[];
  /** manual: written by the user; automatic: written by an agent; shared: imported from another account. */
  source: FileSource;
  last_editor: "user" | "agent";
  /** Agents may edit this file (an automatic file is always editable by agents). */
  agent_editable: boolean;
  /** The user changed an agent's or a shared file; its original text can be restored. */
  edited: boolean;
  /** Counts every save. A save sends the one the editor opened so the server can refuse a stale one. */
  revision: number;
  created_at: string;
  updated_at: string;
  chars: number;
  /** Set on an agent-written file: editing it may break the agent that uses it. */
  warning: string | null;
  /** The sender's username on a shared file, else "". */
  shared_from: string;
}

/** One file with its text (the list rows carry `chars` instead). */
export interface BrainFile extends Omit<BrainFileRow, "chars"> {
  body: string;
}

export interface BrainList {
  files: BrainFileRow[];
  /** Every folder that holds a file, with its parents, sorted. */
  folders: string[];
}

export interface SearchHit extends BrainFileRow {
  score: number;
  snippet: string;
}

/** The account's use of its quota, with the live limits. */
export interface BrainSummary {
  files: number;
  bytes: number;
  /** Files in the folder that could not be read; they are not listed. */
  skipped: number;
  max_files: number;
  max_total_bytes: number;
  max_record_chars: number;
}

export interface FileDraft {
  title: string;
  body: string;
  tags: string[];
  folder: string;
}

/** A save sends only what changed. `agent_editable` is the switch for agents. */
export type FileChanges = Partial<FileDraft> & { agent_editable?: boolean };

// The limits the server enforces that do not change at run time (stronghold `brain/records.py`, `notes/store.py`).
export const FILE_TITLE_MAX = 200;
export const FILE_TAG_MAX = 30;
export const FILE_TAGS_MAX = 10;
export const FOLDER_DEPTH_MAX = 3;

const path = (id: string) => `/api/brain/files/${encodeURIComponent(id)}`;

/** Portcullis's /api/brain routes (chat.use), passed on to Stronghold. */
export const brainClient = {
  /** Newest first. */
  list: () => apiRequest<BrainList>("GET", "/api/brain/files"),
  get: (id: string) => apiRequest<BrainFile>("GET", path(id)),
  create: (draft: FileDraft) => apiRequest<BrainFile>("POST", "/api/brain/files", draft),
  /** With `expectedRevision` the server refuses with 412 when the file was saved since. */
  update: (id: string, changes: FileChanges, expectedRevision?: number) =>
    apiRequest<BrainFile>("PUT", path(id), expectedRevision === undefined ? changes : { ...changes, expected_revision: expectedRevision }),
  /** Puts back the text from before the user's first edit of an agent or shared file. */
  revert: (id: string, expectedRevision?: number) =>
    apiRequest<BrainFile>("POST", `${path(id)}/revert`, expectedRevision === undefined ? {} : { expected_revision: expectedRevision }),
  remove: (id: string) => apiRequest<void>("DELETE", path(id)),
  /** Keyword (BM25) search over titles, tags and text. */
  search: (query: string) => apiRequest<{ results: SearchHit[] }>("GET", `/api/brain/search?q=${encodeURIComponent(query)}`),
  summary: () => apiRequest<BrainSummary>("GET", "/api/brain/summary"),
};

/** A tag as the server keeps it: lowercase, spaces become "-", other characters go,
 * no leading "-" or "_", at most 30 characters. "" means nothing usable was left. */
export function normalizeTag(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/^[-_]+/, "")
    .slice(0, FILE_TAG_MAX);
}

/** A folder as typed, cleaned: lowercase, "/" between levels, spaces become "-", other characters go. */
export function normalizeFolder(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s*[\\/]\s*/g, "/")
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_/-]/g, "")
    .replace(/\/+/g, "/")
    .replace(/^\/+|\/+$/g, "");
}

const SEGMENT = /^[a-z0-9][a-z0-9_-]{0,39}$/;

/** Why a cleaned folder cannot be saved, or "" when it can. The server checks again and also refuses reserved names. */
export function folderProblem(folder: string): string {
  if (folder === "") return "";
  const levels = folder.split("/");
  if (levels.length > FOLDER_DEPTH_MAX || !levels.every((level) => SEGMENT.test(level))) {
    return `A folder is up to ${FOLDER_DEPTH_MAX} levels of lowercase letters, digits, - and _ (40 characters each, starting with a letter or digit).`;
  }
  return "";
}
```

- [x] **Step 4: Run the test to verify it passes**

Run: `pnpm exec vitest run src/features/notes/api/BrainClient.test.ts`
Expected: PASS (all tests).

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/notes/api/BrainClient.ts apps/ember/src/features/notes/api/BrainClient.test.ts
git commit -m "feat(ember): API client for the long-term brain files"
```

---

### Task 2: Brain files store

**Files:**
- Create: `apps/ember/src/features/notes/stores/brain.ts`
- Test: `apps/ember/src/features/notes/stores/brain.test.ts`

**Interfaces:**
- Consumes: `brainClient` and the types from Task 1; `useAuthStore().account` (`src/stores/auth.ts`); `errorMessage` (`src/utils/errors.ts`).
- Produces: `useBrainStore()` with refs `status` (`"idle" | "loading" | "ready" | "error"`), `error`, `files` (`BrainFileRow[]`), `folders` (`string[]`), `summary` (`BrainSummary | null`), `hits` (`SearchHit[] | null`, null = no search), `searching`, `searchError`; actions `load()`, `search(query)`, `clearSearch()`, `create(draft)`, `save(id, changes, revision)`, `revert(id, revision)`, `remove(id)`, `forget()`. The mutating actions return the saved `BrainFile` (`remove` returns nothing) and rethrow the `ApiError` so the page can tell a 412 from other failures.

- [x] **Step 1: Write the failing test**

```ts
import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { brainClient, type BrainFile, type BrainFileRow, type BrainSummary, type SearchHit } from "../api/BrainClient";
import { useBrainStore } from "./brain";

vi.mock("../api/BrainClient", () => ({
  brainClient: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), revert: vi.fn(), remove: vi.fn(), search: vi.fn(), summary: vi.fn() },
}));

const client = vi.mocked(brainClient);

const row = (id: string, title = `file ${id}`, folder = ""): BrainFileRow => ({
  id, title, folder, tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", chars: 5, warning: null, shared_from: "",
});
const file = (id: string, title = `file ${id}`, body = "text", folder = ""): BrainFile => {
  const { chars: _chars, ...rest } = row(id, title, folder);
  return { ...rest, body };
};
const SUMMARY: BrainSummary = { files: 2, bytes: 1200, skipped: 0, max_files: 500, max_total_bytes: 5_000_000, max_record_chars: 20_000 };
const hit = (id: string): SearchHit => ({ ...row(id), score: 1, snippet: "…" });

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useBrainStore() };
}

const later = <T>() => {
  let done!: (value: T) => void;
  const promise = new Promise<T>((resolve) => { done = resolve; });
  return { promise, done };
};

beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue({ files: [row("a"), row("b")], folders: ["x"] });
  client.summary.mockResolvedValue(SUMMARY);
});

describe("load", () => {
  it("shows the server's files, folders and quota", async () => {
    const { store } = setup();
    expect(store.status).toBe("idle");
    const loading = store.load();
    expect(store.status).toBe("loading");
    await loading;
    expect(store.status).toBe("ready");
    expect(store.files.map((f) => f.id)).toEqual(["a", "b"]);
    expect(store.folders).toEqual(["x"]);
    expect(store.summary).toEqual(SUMMARY);
  });

  it("does nothing without an account", async () => {
    const { auth, store } = setup();
    auth.account = null;
    await store.load();
    expect(client.list).not.toHaveBeenCalled();
  });

  it("still shows the list when only the quota fails", async () => {
    const { store } = setup();
    client.summary.mockRejectedValue(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.summary).toBeNull();
  });

  it("a first failure is an error state with the server's text; a later one keeps the list", async () => {
    const { store } = setup();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("error");
    expect(store.error).toBe("Storage is unavailable");
    await store.load();
    expect(store.status).toBe("ready");
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.files).toHaveLength(2);
    expect(store.error).toBe("Storage is unavailable");
  });

  it("a newer load wins over an older reply that arrives late", async () => {
    const { store } = setup();
    const slow = later<{ files: BrainFileRow[]; folders: string[] }>();
    client.list.mockReturnValueOnce(slow.promise);
    const first = store.load();
    client.list.mockResolvedValueOnce({ files: [row("new")], folders: [] });
    await store.load();
    slow.done({ files: [row("old")], folders: [] });
    await first;
    expect(store.files.map((f) => f.id)).toEqual(["new"]);
  });

  it("a reply that arrives after forget shows nothing", async () => {
    const { store } = setup();
    const slow = later<{ files: BrainFileRow[]; folders: string[] }>();
    client.list.mockReturnValueOnce(slow.promise);
    const loading = store.load();
    store.forget();
    slow.done({ files: [row("late")], folders: [] });
    await loading;
    expect(store.files).toEqual([]);
    expect(store.status).toBe("idle");
  });
});

describe("search", () => {
  it("shows the hits, and an empty query clears them", async () => {
    const { store } = setup();
    client.search.mockResolvedValue({ results: [hit("a")] });
    await store.search("  tea ");
    expect(client.search).toHaveBeenCalledExactlyOnceWith("tea");
    expect(store.hits?.map((h) => h.id)).toEqual(["a"]);
    await store.search("   ");
    expect(store.hits).toBeNull();
    expect(client.search).toHaveBeenCalledTimes(1);
  });

  it("ignores an older search that answers last", async () => {
    const { store } = setup();
    const slow = later<{ results: SearchHit[] }>();
    client.search.mockReturnValueOnce(slow.promise);
    const first = store.search("old");
    client.search.mockResolvedValueOnce({ results: [hit("new")] });
    await store.search("new");
    slow.done({ results: [hit("old")] });
    await first;
    expect(store.hits?.map((h) => h.id)).toEqual(["new"]);
    expect(store.searching).toBe(false);
  });

  it("a failed search shows the reason and falls back to no hits", async () => {
    const { store } = setup();
    client.search.mockRejectedValue(new ApiError(422, "Invalid brain request."));
    await store.search("x");
    expect(store.hits).toBeNull();
    expect(store.searchError).toBe("Invalid brain request.");
    expect(store.searching).toBe(false);
  });

  it("clearSearch drops hits and a search still on its way", async () => {
    const { store } = setup();
    const slow = later<{ results: SearchHit[] }>();
    client.search.mockReturnValueOnce(slow.promise);
    const searching = store.search("x");
    store.clearSearch();
    slow.done({ results: [hit("a")] });
    await searching;
    expect(store.hits).toBeNull();
    expect(store.searching).toBe(false);
  });
});

describe("changes", () => {
  it("create puts the new file first, looks again, and returns the file", async () => {
    const { store } = setup();
    await store.load();
    client.create.mockResolvedValue(file("c", "Created", "body"));
    client.list.mockResolvedValue({ files: [row("c", "Created"), row("a"), row("b")], folders: ["x", "y"] });
    const draft = { title: "Created", body: "body", tags: [], folder: "y" };
    const made = await store.create(draft);
    expect(client.create).toHaveBeenCalledExactlyOnceWith(draft);
    expect(made.id).toBe("c");
    expect(store.files.map((f) => f.id)).toEqual(["c", "a", "b"]);
    expect(store.folders).toEqual(["x", "y"]);
    expect(client.list).toHaveBeenCalledTimes(2);
  });

  it("save sends the changes and the revision, and moves the file to the top", async () => {
    const { store } = setup();
    await store.load();
    client.update.mockResolvedValue({ ...file("b", "Renamed"), revision: 2 });
    client.list.mockResolvedValue({ files: [row("b", "Renamed"), row("a")], folders: [] });
    const saved = await store.save("b", { title: "Renamed" }, 1);
    expect(client.update).toHaveBeenCalledExactlyOnceWith("b", { title: "Renamed" }, 1);
    expect(saved.revision).toBe(2);
    expect(store.files.map((f) => [f.id, f.title])).toEqual([["b", "Renamed"], ["a", "file a"]]);
  });

  it("a refused save changes nothing and passes the error on", async () => {
    const { store } = setup();
    await store.load();
    client.update.mockRejectedValue(new ApiError(412, "This file changed since you opened it."));
    await expect(store.save("a", { title: "x" }, 1)).rejects.toMatchObject({ status: 412 });
    expect(store.files.map((f) => f.title)).toEqual(["file a", "file b"]);
  });

  it("revert and remove call the server with the revision and update the list", async () => {
    const { store } = setup();
    await store.load();
    client.revert.mockResolvedValue({ ...file("a", "Original"), revision: 3 });
    client.list.mockResolvedValue({ files: [row("a", "Original"), row("b")], folders: [] });
    await store.revert("a", 2);
    expect(client.revert).toHaveBeenCalledExactlyOnceWith("a", 2);
    expect(store.files[0]).toMatchObject({ id: "a", title: "Original" });
    client.remove.mockResolvedValue(undefined);
    client.list.mockResolvedValue({ files: [row("b")], folders: [] });
    await store.remove("a");
    expect(client.remove).toHaveBeenCalledExactlyOnceWith("a");
    expect(store.files.map((f) => f.id)).toEqual(["b"]);
  });

  it("a change that finishes after forget does not bring files back", async () => {
    const { store } = setup();
    await store.load();
    const slow = later<BrainFile>();
    client.update.mockReturnValueOnce(slow.promise);
    const saving = store.save("a", { title: "x" }, 1);
    store.forget();
    slow.done(file("a", "x"));
    await saving;
    await flushPromises();
    expect(store.files).toEqual([]);
  });
});

describe("private data", () => {
  it("signing out clears everything", async () => {
    const { auth, store } = setup();
    client.search.mockResolvedValue({ results: [hit("a")] });
    await store.load();
    await store.search("a");
    auth.account = null;
    expect(store.files).toEqual([]);
    expect(store.folders).toEqual([]);
    expect(store.summary).toBeNull();
    expect(store.hits).toBeNull();
    expect(store.status).toBe("idle");
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pnpm exec vitest run src/features/notes/stores/brain.test.ts`
Expected: FAIL, the module `./brain` does not exist.

- [x] **Step 3: Write the store**

```ts
import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import {
  brainClient,
  type BrainFile,
  type BrainFileRow,
  type BrainSummary,
  type FileChanges,
  type FileDraft,
  type SearchHit,
} from "../api/BrainClient";

/** The account's long-term memory files as the server holds them: list, folders, quota and search results.
 * The text of a file is not kept here (the page asks for it when a file opens). Everything is private: it is
 * dropped by `forget()` and when the account changes, and a reply that arrives after that, or after a newer
 * request, is ignored. Changes show only after the server answered. */
export const useBrainStore = defineStore("brain", () => {
  const auth = useAuthStore();
  const status = ref<"idle" | "loading" | "ready" | "error">("idle");
  const error = ref("");
  const files = ref<BrainFileRow[]>([]);
  const folders = ref<string[]>([]);
  const summary = ref<BrainSummary | null>(null);
  const hits = ref<SearchHit[] | null>(null);
  const searching = ref(false);
  const searchError = ref("");
  let loads = 0;
  let searches = 0;
  let epoch = 0; // raised by forget(): a change that started before it must not write after it

  async function load(): Promise<void> {
    if (!auth.account) return;
    const run = ++loads;
    if (status.value !== "ready") status.value = "loading";
    try {
      const [list, totals] = await Promise.all([brainClient.list(), brainClient.summary().catch(() => null)]);
      if (run !== loads) return;
      files.value = list.files;
      folders.value = list.folders;
      if (totals) summary.value = totals;
      status.value = "ready";
      error.value = "";
    } catch (err) {
      if (run !== loads) return;
      error.value = errorMessage(err);
      status.value = status.value === "ready" ? "ready" : "error";
    }
  }

  async function search(query: string): Promise<void> {
    const text = query.trim();
    const run = ++searches;
    searchError.value = "";
    if (!text || !auth.account) {
      hits.value = null;
      searching.value = false;
      return;
    }
    searching.value = true;
    try {
      const found = await brainClient.search(text);
      if (run === searches) hits.value = found.results;
    } catch (err) {
      if (run === searches) {
        hits.value = null;
        searchError.value = errorMessage(err);
      }
    } finally {
      if (run === searches) searching.value = false;
    }
  }

  function clearSearch(): void {
    searches++;
    hits.value = null;
    searching.value = false;
    searchError.value = "";
  }

  /** The saved file as a list row, first in the list (it was just changed) and in the hits that show it. */
  function place(record: BrainFile): void {
    const row: BrainFileRow & { body?: string } = { ...record, chars: record.body.length };
    delete row.body;
    files.value = [row, ...files.value.filter((f) => f.id !== row.id)];
    if (hits.value) hits.value = hits.value.map((h) => (h.id === row.id ? { ...h, ...row } : h));
  }

  /** Runs a change. Errors go to the caller (a 412 means the file changed since it was opened). */
  async function change(work: () => Promise<BrainFile>): Promise<BrainFile> {
    const started = epoch;
    const record = await work();
    if (started === epoch) {
      place(record);
      await load();
    }
    return record;
  }

  const create = (draft: FileDraft) => change(() => brainClient.create(draft));
  const save = (id: string, changes: FileChanges, revision: number) => change(() => brainClient.update(id, changes, revision));
  const revert = (id: string, revision: number) => change(() => brainClient.revert(id, revision));

  async function remove(id: string): Promise<void> {
    const started = epoch;
    await brainClient.remove(id);
    if (started !== epoch) return;
    files.value = files.value.filter((f) => f.id !== id);
    if (hits.value) hits.value = hits.value.filter((h) => h.id !== id);
    await load();
  }

  function forget(): void {
    epoch++;
    loads++;
    searches++;
    status.value = "idle";
    error.value = "";
    files.value = [];
    folders.value = [];
    summary.value = null;
    hits.value = null;
    searching.value = false;
    searchError.value = "";
  }

  watch(() => auth.account?.id, forget, { flush: "sync" });

  return { status, error, files, folders, summary, hits, searching, searchError, load, search, clearSearch, create, save, revert, remove, forget };
});
```

- [x] **Step 4: Run the test to verify it passes**

Run: `pnpm exec vitest run src/features/notes/stores/brain.test.ts`
Expected: PASS. If a test fails because `watch` on `auth.account?.id` does not fire for `auth.account = null` the way `stack.ts` does, read `src/features/chat/stores/stack.ts` (Plan 20e) and copy its watch exactly.

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/notes/stores/brain.ts apps/ember/src/features/notes/stores/brain.test.ts
git commit -m "feat(ember): store for the long-term brain files with late replies ignored"
```

---

### Task 3: FileList and FileEditor components

**Files:**
- Create: `apps/ember/src/features/notes/components/FileList.vue`, `FileList.test.ts`
- Create: `apps/ember/src/features/notes/components/FileEditor.vue`, `FileEditor.test.ts`

**Interfaces:**
- Consumes: Task 1 types and helpers; shared components (assumption (d)).
- Produces:
  - `FileList` props: `rows: (BrainFileRow | SearchHit)[]`, `folders: string[]`, `selectedId: string | null`, `draftTitle: string | null` (non-null shows an unsaved "New file" row; `""` shows the title "New file"), `isSearch: boolean`, `searchBusy: boolean`, `searchError: string`, `disabled: boolean`; models `query: string`, `folder: string | null` (null = All, "" = No folder, else a folder path); emits `select(id: string)`.
  - `FileEditor` props: `file: Pick<BrainFile, "source" | "last_editor" | "edited" | "warning" | "shared_from"> | null` (null = a new file), `folders: string[]`, `knownTags: {tag: string; count: number}[]`, `maxChars: number`, `folderProblem: string`, `canRevert: boolean`, `revertHint: string`, `disabled: boolean`; models `title`, `body`, `tags`, `tagText`, `folder`, `agentEditable`; emits `revert`, `remove`; exposes `commitTags()` and `focusTitle()`.

- [x] **Step 1: Write the failing FileList test**

```ts
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { BrainFileRow, SearchHit } from "../api/BrainClient";
import FileList from "./FileList.vue";

const row = (id: string, title: string, extra: Partial<BrainFileRow> = {}): BrainFileRow => ({
  id, title, folder: "", tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", chars: 5, warning: null, shared_from: "", ...extra,
});

function mountList(props: Record<string, unknown> = {}) {
  const wrapper = mount(FileList, {
    props: {
      rows: [row("a", "Tea notes", { folder: "food", tags: ["tea"] }), row("b", "Plan", { source: "automatic" })],
      folders: ["food"], selectedId: null, draftTitle: null, isSearch: false, searchBusy: false, searchError: "", disabled: false,
      query: "", folder: null,
      "onUpdate:query": (value: string) => wrapper.setProps({ query: value }),
      "onUpdate:folder": (value: string | null) => wrapper.setProps({ folder: value }),
      ...props,
    },
  });
  return wrapper;
}

const rowsOf = (w: ReturnType<typeof mountList>) => w.findAll("ul[aria-label='Files'] li");

describe("FileList", () => {
  it("lists the rows with folder, tags and an agent mark", () => {
    const w = mountList();
    expect(rowsOf(w)).toHaveLength(2);
    expect(rowsOf(w)[0]!.text()).toContain("Tea notes");
    expect(rowsOf(w)[0]!.text()).toContain("food");
    expect(rowsOf(w)[0]!.text()).toContain("tea");
    expect(rowsOf(w)[1]!.text()).toContain("Agent file");
  });

  it("marks shared, edited and agent-editable files", () => {
    const w = mountList({ rows: [row("a", "S", { source: "shared", shared_from: "bo", edited: true }), row("b", "E", { agent_editable: true })] });
    expect(rowsOf(w)[0]!.text()).toContain("Shared by bo");
    expect(rowsOf(w)[0]!.text()).toContain("Edited");
    expect(rowsOf(w)[1]!.text()).toContain("Agents can edit");
  });

  it("selecting a row says which", async () => {
    const w = mountList();
    await w.get('[data-file-id="b"]').trigger("click");
    expect(w.emitted("select")).toEqual([["b"]]);
  });

  it("marks the open row and shows an unsaved new file first", () => {
    const w = mountList({ selectedId: "a", draftTitle: "" });
    expect(rowsOf(w)[0]!.text()).toContain("New file");
    expect(rowsOf(w)[0]!.text()).toContain("Not saved yet");
    expect(w.get('[data-file-id="a"]').attributes("aria-current")).toBe("true");
  });

  it("folder buttons set the folder and say which is pressed", async () => {
    const w = mountList();
    const group = w.get('[role="group"][aria-label="Folders"]');
    const buttons = group.findAll("button");
    expect(buttons.map((b) => b.text())).toEqual(["All", "No folder", "food"]);
    expect(buttons[0]!.attributes("aria-pressed")).toBe("true");
    await buttons[2]!.trigger("click");
    expect(w.emitted("update:folder")![0]).toEqual(["food"]);
    expect(w.findAll('[aria-label="Folders"] button')[2]!.attributes("aria-pressed")).toBe("true");
    await w.findAll('[aria-label="Folders"] button')[1]!.trigger("click");
    expect(w.emitted("update:folder")![1]).toEqual([""]);
  });

  it("has no folder buttons without folders, or while showing search results", () => {
    expect(mountList({ folders: [] }).find('[aria-label="Folders"]').exists()).toBe(false);
    expect(mountList({ isSearch: true }).find('[aria-label="Folders"]').exists()).toBe(false);
  });

  it("typing in the search box updates the query", async () => {
    const w = mountList();
    await w.get('input[aria-label="Search files"]').setValue("tea");
    expect(w.emitted("update:query")![0]).toEqual(["tea"]);
  });

  it("shows search results with their snippet", () => {
    const hit: SearchHit = { ...row("a", "Tea notes"), score: 2, snippet: "green tea steeps" };
    const w = mountList({ rows: [hit], isSearch: true });
    expect(w.text()).toContain("Search results");
    expect(rowsOf(w)[0]!.text()).toContain("green tea steeps");
  });

  it("explains an empty list and an empty search", () => {
    expect(mountList({ rows: [] }).text()).toContain("No files here yet.");
    const searched = mountList({ rows: [], isSearch: true });
    expect(searched.text()).toContain("No files match your search.");
  });

  it("shows a search that is running and one that failed", () => {
    expect(mountList({ searchBusy: true }).get('[role="status"]').text()).toContain("Searching");
    expect(mountList({ searchError: "Invalid brain request." }).get('[role="alert"]').text()).toBe("Invalid brain request.");
  });

  it("disables the rows while a change is running", () => {
    const w = mountList({ disabled: true });
    expect(w.get('[data-file-id="a"]').attributes("disabled")).toBeDefined();
  });
});
```

- [x] **Step 2: Run it to verify it fails**

Run: `pnpm exec vitest run src/features/notes/components/FileList.test.ts`
Expected: FAIL, `./FileList.vue` does not exist.

- [x] **Step 3: Write `FileList.vue`**

```vue
<script setup lang="ts">
import ListRow from "../../../components/ui/lists/ListRow.vue";
import SearchField from "../../../components/ui/lists/SearchField.vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { formatUtc } from "../../../utils/time";
import type { BrainFileRow, SearchHit } from "../api/BrainClient";

/** The left pane of the Notes page: search, the folder buttons and the file rows. It only shows what it is given;
 * the page filters, searches and decides what opens. */
defineProps<{
  rows: (BrainFileRow | SearchHit)[];
  folders: string[];
  selectedId: string | null;
  /** A file the user started but has not saved: shown first. "" means no title yet. */
  draftTitle: string | null;
  /** The rows are search results: the folder buttons do not apply. */
  isSearch: boolean;
  searchBusy: boolean;
  searchError: string;
  disabled: boolean;
}>();

const query = defineModel<string>("query", { required: true });
const folder = defineModel<string | null>("folder", { required: true });
defineEmits<{ select: [id: string] }>();
</script>

<template>
  <div class="file-list">
    <div class="list-heading">
      <span>{{ isSearch ? "Search results" : "Files" }}</span>
      <span>{{ rows.length }} {{ rows.length === 1 ? "file" : "files" }}</span>
    </div>
    <SearchField v-model="query" class="search" label="Search files" placeholder="Search titles, tags and text…" maxlength="200" />
    <p v-if="searchBusy" class="muted note" role="status">Searching …</p>
    <p v-if="searchError" class="error note" role="alert">{{ searchError }}</p>
    <div v-if="folders.length && !isSearch" class="folders" role="group" aria-label="Folders">
      <button type="button" class="chip" :class="{ active: folder === null }" :aria-pressed="folder === null" @click="folder = null">All</button>
      <button type="button" class="chip" :class="{ active: folder === '' }" :aria-pressed="folder === ''" @click="folder = ''">No folder</button>
      <button
        v-for="name in folders" :key="name" type="button" class="chip" :class="{ active: folder === name }"
        :aria-pressed="folder === name" @click="folder = name"
      >{{ name }}</button>
    </div>
    <div class="list-scroll pane-scroll">
      <StateMessage v-if="rows.length === 0 && draftTitle === null && !searchBusy" kind="empty" :title="isSearch ? 'No files match your search.' : undefined">
        {{ isSearch ? "Try other words." : "No files here yet." }}
      </StateMessage>
      <ul v-else class="list" aria-label="Files">
        <li v-if="draftTitle !== null">
          <ListRow class="file-row" active>
            <span class="title">{{ draftTitle.trim() || "New file" }}</span>
            <span class="muted">Not saved yet</span>
          </ListRow>
        </li>
        <li v-for="row in rows" :key="row.id">
          <ListRow class="file-row" :active="row.id === selectedId" :data-file-id="row.id" :disabled="disabled" @click="$emit('select', row.id)">
            <span class="title">{{ row.title }}</span>
            <span v-if="'snippet' in row && row.snippet" class="snippet">{{ row.snippet }}</span>
            <span v-if="row.folder" class="muted path">{{ row.folder }}</span>
            <span class="badges">
              <span v-for="tag in row.tags" :key="tag" class="status-badge">{{ tag }}</span>
              <span v-if="row.source === 'automatic'" class="status-badge agent-mark">Agent file</span>
              <span v-else-if="row.source === 'shared'" class="status-badge">Shared by {{ row.shared_from || "another account" }}</span>
              <span v-if="row.agent_editable && row.source !== 'automatic'" class="status-badge">Agents can edit</span>
              <span v-if="row.edited" class="status-badge">Edited</span>
            </span>
            <span class="muted when">{{ formatUtc(row.updated_at) }}</span>
          </ListRow>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.file-list { display: flex; flex: 1; flex-direction: column; min-height: 0; }
.list-heading { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 8px; padding: 0 4px; font-size: .8em; color: var(--muted); }
.search { margin-bottom: 10px; flex-shrink: 0; }
.note { margin: 0 4px 8px; font-size: .85em; }
.folders { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; flex-shrink: 0; }
.list-scroll { flex: 1; min-height: 0; }
.list { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; }
.list li { border-bottom: 1px solid var(--border); }
.title { font-weight: 600; overflow-wrap: anywhere; }
.snippet { color: var(--muted); overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.path, .when { font-size: .8em; overflow-wrap: anywhere; }
.badges { display: flex; flex-wrap: wrap; gap: 4px; }
.agent-mark { border-color: var(--warning); }
@media (max-width: 767px) {
  .folders .chip, .list-scroll :deep(button) { min-width: 44px; min-height: 44px; }
  .file-row { min-height: 88px; }
}
</style>
```

- [x] **Step 4: Run it to verify it passes**

Run: `pnpm exec vitest run src/features/notes/components/FileList.test.ts`
Expected: PASS. If `'snippet' in row` does not type-check in `vue-tsc`, narrow with a helper `snippetOf(row)` in the script and say so under "Changes found during work".

- [x] **Step 5: Write the failing FileEditor test**

```ts
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import FileEditor from "./FileEditor.vue";

const manual = { source: "manual", last_editor: "user", edited: false, warning: null, shared_from: "" } as const;
const MODELS = ["title", "body", "tags", "tagText", "folder", "agentEditable"] as const;

function mountEditor(props: Record<string, unknown> = {}) {
  const handlers = Object.fromEntries(MODELS.map((name) => [`onUpdate:${name}`, (value: unknown) => wrapper.setProps({ [name]: value })]));
  const wrapper = mount(FileEditor, {
    props: {
      title: "Tea", body: "Green", tags: [], tagText: "", folder: "", agentEditable: false,
      file: manual, folders: [], knownTags: [], maxChars: 20_000, folderProblem: "", canRevert: false, revertHint: "", disabled: false,
      ...handlers, ...props,
    },
    attachTo: document.body,
  });
  return wrapper;
}

describe("FileEditor", () => {
  it("shows the title and the text with their limits", () => {
    const w = mountEditor({ maxChars: 500 });
    expect((w.get('input[aria-label="Title"]').element as HTMLInputElement).value).toBe("Tea");
    expect(w.get('input[aria-label="Title"]').attributes("maxlength")).toBe("200");
    expect((w.get('textarea[aria-label="File text"]').element as HTMLTextAreaElement).value).toBe("Green");
    expect(w.get('textarea[aria-label="File text"]').attributes("maxlength")).toBe("500");
  });

  it("typing updates the models", async () => {
    const w = mountEditor();
    await w.get('input[aria-label="Title"]').setValue("Coffee");
    await w.get('textarea[aria-label="File text"]').setValue("Black");
    expect(w.emitted("update:title")![0]).toEqual(["Coffee"]);
    expect(w.emitted("update:body")![0]).toEqual(["Black"]);
  });

  it("warns, in words, about an agent's file and offers no agent switch", () => {
    const w = mountEditor({ file: { ...manual, source: "automatic", last_editor: "agent", warning: "Written by an agent. Editing it may break the agent that uses it." } });
    expect(w.get('[data-test="agent-warning"]').text()).toContain("Editing it may break the agent that uses it.");
    expect(w.find('input[type="checkbox"]').exists()).toBe(false);
    expect(w.text()).toContain("An agent wrote this file, so agents can edit it.");
  });

  it("says who shared a shared file", () => {
    const w = mountEditor({ file: { ...manual, source: "shared", shared_from: "bo" } });
    expect(w.get('[data-test="shared-note"]').text()).toContain("Shared by bo");
  });

  it("says when an agent last changed a file the user wrote", () => {
    const w = mountEditor({ file: { ...manual, last_editor: "agent" } });
    expect(w.text()).toContain("An agent last changed this file.");
  });

  it("the agent switch updates the model, and the page says agents can read every file", async () => {
    const w = mountEditor();
    expect(w.text()).toContain("Agents can read every file here.");
    await w.get('input[type="checkbox"]').setValue(true);
    expect(w.emitted("update:agentEditable")![0]).toEqual([true]);
  });

  it("shows the folder problem", () => {
    const w = mountEditor({ folderProblem: "A folder is up to 3 levels." });
    expect(w.get('[role="alert"]').text()).toBe("A folder is up to 3 levels.");
  });

  it("typing a folder is kept as typed, and leaving the box cleans it", async () => {
    const w = mountEditor();
    const input = w.get('input[aria-label="Folder"]');
    await input.setValue("Projects / Citadel");
    expect(w.emitted("update:folder")![0]).toEqual(["Projects / Citadel"]);
    await input.trigger("blur");
    expect(w.emitted("update:folder")![1]).toEqual(["projects/citadel"]);
  });

  it("an existing folder can be picked", async () => {
    const w = mountEditor({ folders: ["food", "food/tea"] });
    await w.get('button[aria-label="Use folder food/tea"]').trigger("click");
    expect(w.emitted("update:folder")![0]).toEqual(["food/tea"]);
  });

  it("restore original is only there for an edited file, and waits for a clean editor", async () => {
    expect(mountEditor().text()).not.toContain("Restore original");
    const edited = { ...manual, source: "automatic", edited: true, warning: "w" } as const;
    const blocked = mountEditor({ file: edited, canRevert: false, revertHint: "Save or discard your changes first." });
    const button = blocked.findAll("button").find((b) => b.text() === "Restore original")!;
    expect(button.attributes("disabled")).toBeDefined();
    expect(blocked.text()).toContain("Save or discard your changes first.");
    const ready = mountEditor({ file: edited, canRevert: true });
    await ready.findAll("button").find((b) => b.text() === "Restore original")!.trigger("click");
    expect(ready.emitted("revert")).toHaveLength(1);
  });

  it("delete is offered for a saved file only", async () => {
    const saved = mountEditor();
    await saved.findAll("button").find((b) => b.text() === "Delete this file")!.trigger("click");
    expect(saved.emitted("remove")).toHaveLength(1);
    expect(mountEditor({ file: null }).text()).not.toContain("Delete this file");
  });

  it("disables the fields while a change is running", () => {
    const w = mountEditor({ disabled: true });
    expect(w.get('input[aria-label="Title"]').attributes("disabled")).toBeDefined();
    expect(w.get('textarea[aria-label="File text"]').attributes("disabled")).toBeDefined();
  });

  it("exposes commitTags and focusTitle", () => {
    const w = mountEditor();
    expect(typeof w.vm.commitTags).toBe("function");
    w.vm.focusTitle();
    expect(document.activeElement).toBe(w.get('input[aria-label="Title"]').element);
  });
});
```

- [x] **Step 6: Run it to verify it fails**

Run: `pnpm exec vitest run src/features/notes/components/FileEditor.test.ts`
Expected: FAIL, `./FileEditor.vue` does not exist.

- [x] **Step 7: Write `FileEditor.vue`**

```vue
<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from "vue";
import DangerZone from "../../../components/ui/status/DangerZone.vue";
import CharacterCount from "../../../components/ui/status/CharacterCount.vue";
import TagInput from "../../../components/ui/forms/TagInput.vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import { growOnResize, growToContent } from "../../../utils/browser/autoGrow";
import { FILE_TAG_MAX, FILE_TAGS_MAX, FILE_TITLE_MAX, normalizeFolder, normalizeTag, type BrainFile } from "../api/BrainClient";

/** The right pane of the Notes page: the fields of one file and what the user may do with it. It holds no
 * state of its own; the page owns the draft, saves it and answers `revert` and `remove`. */
const props = defineProps<{
  /** The saved file's details; null for a file not saved yet. */
  file: Pick<BrainFile, "source" | "last_editor" | "edited" | "warning" | "shared_from"> | null;
  folders: string[];
  /** Tags the account already uses, most used first. */
  knownTags: { tag: string; count: number }[];
  /** The live limit for one file's text. */
  maxChars: number;
  /** Why the folder cannot be saved, or "". */
  folderProblem: string;
  canRevert: boolean;
  /** Why Restore original is off, or "". */
  revertHint: string;
  disabled: boolean;
}>();

const title = defineModel<string>("title", { required: true });
const body = defineModel<string>("body", { required: true });
const tags = defineModel<string[]>("tags", { required: true });
const tagText = defineModel<string>("tagText", { required: true });
const folder = defineModel<string>("folder", { required: true });
const agentEditable = defineModel<boolean>("agentEditable", { required: true });
defineEmits<{ revert: []; remove: [] }>();

const uid = useId();
const titleField = ref<HTMLInputElement | null>(null);
const bodyField = ref<HTMLTextAreaElement | null>(null);
const tagField = ref<InstanceType<typeof TagInput> | null>(null);

// Grow the text within the editor scroller, including after a viewport resize.
watch([body, bodyField], async () => {
  await nextTick();
  if (bodyField.value) growToContent(bodyField.value);
});
growOnResize(bodyField);

const folderHint = computed(() => folder.value.trim() || "No folder");
const agentHint = computed(() => (props.file?.source === "automatic" || agentEditable.value ? "Agents can edit" : "Agents can read"));

defineExpose({
  /** A tag still in the box is part of the file: add it before saving. */
  commitTags: () => tagField.value?.commit(),
  focusTitle: () => titleField.value?.focus(),
});
</script>

<template>
  <div class="file-editor">
    <div class="writing">
      <p v-if="file?.source === 'automatic'" class="notice warn" role="note" data-test="agent-warning">
        <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        {{ file.warning || "Written by an agent. Editing it may break the agent that uses it." }}
      </p>
      <p v-else-if="file?.source === 'shared'" class="notice" role="note" data-test="shared-note">
        {{ file.shared_from ? `Shared by ${file.shared_from}.` : "Shared with you." }} This is your own copy; you can edit it.
      </p>
      <p v-else-if="file?.last_editor === 'agent'" class="notice" role="note">
        An agent last changed this file. Saving your own changes removes this mark.
      </p>
      <label class="title-field">
        <span class="sr-only">Title</span>
        <input ref="titleField" v-model="title" type="text" :maxlength="FILE_TITLE_MAX" aria-label="Title" :aria-describedby="`${uid}-title-count`" placeholder="Untitled file" :disabled="disabled" />
        <CharacterCount :id="`${uid}-title-count`" class="count" :length="title.length" :max="FILE_TITLE_MAX" />
      </label>
      <label class="body-field">
        <span class="sr-only">File text</span>
        <textarea ref="bodyField" v-model="body" rows="10" placeholder="Start writing…" :maxlength="maxChars" aria-label="File text" :aria-describedby="`${uid}-body-count`" :disabled="disabled" />
        <CharacterCount :id="`${uid}-body-count`" class="count" :length="body.length" :max="maxChars" />
      </label>
    </div>
    <div class="tools">
      <details class="folder-tools">
        <summary><span>Folder and tags</span><span class="summary-hint">{{ folderHint }}{{ tags.length ? ` · ${tags.join(", ")}` : "" }} <span aria-hidden="true">›</span></span></summary>
        <div class="field">
          <span class="field-label">Folder</span>
          <input v-model="folder" type="text" maxlength="130" aria-label="Folder" placeholder="No folder (top level)" :disabled="disabled" @blur="folder = normalizeFolder(folder)" />
          <p v-if="folderProblem" class="error" role="alert">{{ folderProblem }}</p>
          <div v-if="folders.length" class="picks">
            <span class="muted">Existing folders:</span>
            <button v-for="name in folders" :key="name" type="button" class="chip" :aria-label="`Use folder ${name}`" :disabled="disabled" @click="folder = name">{{ name }}</button>
          </div>
          <span class="field-label">Tags</span>
          <TagInput ref="tagField" v-model="tags" v-model:text="tagText" :known="knownTags" :normalize="normalizeTag" :max="FILE_TAGS_MAX" :max-length="FILE_TAG_MAX" :disabled="disabled" />
        </div>
      </details>
      <details class="agent-tools">
        <summary><span>Agent access</span><span class="summary-hint">{{ agentHint }} <span aria-hidden="true">›</span></span></summary>
        <div class="field">
          <p class="muted hint">Agents can read every file here. Do not store passwords, keys or other private data.</p>
          <p v-if="file?.source === 'automatic'" class="muted hint">An agent wrote this file, so agents can edit it.</p>
          <ToggleSwitch v-else :checked="agentEditable" :disabled="disabled" @change="agentEditable = ($event.target as HTMLInputElement).checked">
            Let agents edit this file
          </ToggleSwitch>
        </div>
      </details>
      <details v-if="file?.edited" class="original-tools">
        <summary><span>Original text</span><span aria-hidden="true">›</span></summary>
        <div class="field">
          <p class="muted hint">You changed this file. The text from before your first change is kept.</p>
          <div><button type="button" class="chip" :disabled="!canRevert || disabled" @click="$emit('revert')">Restore original</button></div>
          <p v-if="revertHint" class="muted hint">{{ revertHint }}</p>
        </div>
      </details>
      <details v-if="file" class="manage-tools">
        <summary>Manage file <span aria-hidden="true">›</span></summary>
        <DangerZone class="danger-zone"><template #label><b>Danger zone</b></template><button type="button" class="danger" :disabled="disabled" @click="$emit('remove')">Delete this file</button></DangerZone>
      </details>
    </div>
  </div>
</template>

<style scoped src="../../../components/layout/editorPage.css"></style>
<style scoped>
.file-editor { display: flex; flex: 1; flex-direction: column; min-height: 0; }
.title-field, .body-field { display: flex; flex-direction: column; min-width: 0; gap: 10px; }
.title-field input { width: 100%; padding: 0; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text); font: inherit; font-size: 1.65em; font-weight: 600; letter-spacing: -.025em; line-height: 1.4; }
.body-field { flex: 1; gap: 12px; }
.body-field textarea { width: 100%; min-height: 230px; padding: 0; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text); font: inherit; line-height: 1.9; resize: none; overflow-y: hidden; }
.count { align-self: flex-end; }
.notice { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); font-size: .85em; }
.notice.warn { border-color: var(--warning); background: color-mix(in srgb, var(--warning) 12%, var(--bg)); }
.notice.warn .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.tools { flex-shrink: 0; border-top: 1px solid var(--border); padding: 0 28px; }
.tools > details + details { border-top: 1px solid var(--border); }
summary > [aria-hidden], .summary-hint { color: var(--muted); }
.summary-hint { font-size: .9em; min-width: 0; text-align: right; overflow-wrap: anywhere; }
.tools details[open] > summary { color: var(--accent); }
.field { display: flex; flex-direction: column; gap: 12px; padding: 0 0 16px; }
.field-label { font-size: .85em; color: var(--muted); }
.field input[type="text"] { width: 100%; }
.picks { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.hint { margin: 0; font-size: .85em; }
.danger-zone { margin-bottom: 16px; }
@media (max-width: 900px) and (min-width: 768px) { .tools { padding-inline: 20px; } }
@media (max-width: 767px) {
  .title-field input { font-size: 1.45em; }
  .body-field textarea { min-height: 250px; }
  .tools { padding-inline: 20px; }
  summary, .tools button { min-width: 44px; min-height: 44px; }
}
</style>
```

- [x] **Step 8: Run both component tests, the radius test and the type check**

Run: `pnpm exec vitest run src/features/notes/components src/radiusScale.test.ts` then `pnpm exec vue-tsc -b`
Expected: PASS and no type errors. Fix a snippet that does not fit the real components (for example a `ToggleSwitch` event name or a `CharacterCount` prop) and record it under "Changes found during work". Check the contrast pairs of assumption (g) and apply the fallback if one fails.

- [x] **Step 9: Commit**

```bash
git add apps/ember/src/features/notes/components/FileList.vue apps/ember/src/features/notes/components/FileList.test.ts apps/ember/src/features/notes/components/FileEditor.vue apps/ember/src/features/notes/components/FileEditor.test.ts
git commit -m "feat(ember): file list and file editor components for the Notes page"
```

---

### Task 4: The Notes page, removal of the old notes code, docs

**Files:**
- Rewrite: `apps/ember/src/features/notes/NotesView.vue` and `NotesView.test.ts`
- Delete: `api/NotesClient.ts`, `api/NotesClient.test.ts`, `components/NotePromotionPanel.vue`, `components/NotePromotionPanel.test.ts`, `NotesPublicationDraft.test.ts` (all under `apps/ember/src/features/notes/`)
- Modify: `apps/ember/src/router/pages.ts` (the Notes description)
- Modify: `apps/ember/README.md` only if it describes the Notes page

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces: the page behind the existing `/notes` route (`name: "notes"`, `permission: "chat.use"`); the route and the nav label "Notes" do not change.

- [x] **Step 1: Write the failing page test**

Replace `NotesView.test.ts` with the following. The `<dialog>` polyfill and the `dialogButton` helper are the ones the old test used.

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import { makeAccount } from "../../testing/account";
import { brainClient, type BrainFile, type BrainFileRow, type BrainSummary, type SearchHit } from "./api/BrainClient";
import NotesView from "./NotesView.vue";
import { useBrainStore } from "./stores/brain";

vi.mock("./api/BrainClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/BrainClient")>()),
  brainClient: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), revert: vi.fn(), remove: vi.fn(), search: vi.fn(), summary: vi.fn() },
}));

const client = vi.mocked(brainClient);

const row = (id: string, title: string, extra: Partial<BrainFileRow> = {}): BrainFileRow => ({
  id, title, folder: "", tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", chars: 5, warning: null, shared_from: "", ...extra,
});
const full = (id: string, title: string, body = "text", extra: Partial<BrainFileRow> = {}): BrainFile => {
  const { chars: _chars, ...rest } = row(id, title, extra);
  return { ...rest, body };
};
const SUMMARY: BrainSummary = { files: 2, bytes: 1200, skipped: 0, max_files: 500, max_total_bytes: 5_000_000, max_record_chars: 20_000 };

let wrapper: VueWrapper | null = null;

async function setup(files: BrainFileRow[] = [], options: { folders?: string[]; summary?: Partial<BrainSummary> } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  client.list.mockResolvedValue({ files, folders: options.folders ?? [] });
  client.summary.mockResolvedValue({ ...SUMMARY, ...options.summary });
  wrapper = mount(NotesView, { attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}

const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom does not implement <dialog>.showModal; give it the open flag the component reads.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  vi.useRealTimers();
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

const buttonByText = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text);
// The confirm button draws its label letter by letter, so it is found by class, not by text.
const confirm = () => document.body.querySelector<HTMLButtonElement>("dialog[open] .confirm");
const cancel = () => document.body.querySelector<HTMLButtonElement>("dialog[open] button.cancel");
const rows = (w: VueWrapper) => w.findAll("ul[aria-label='Files'] li");
const title = (w: VueWrapper) => w.get('input[aria-label="Title"]');
const text = (w: VueWrapper) => w.get('textarea[aria-label="File text"]');
async function open(w: VueWrapper, id: string) {
  await w.get(`[data-file-id="${id}"]`).trigger("click");
  await flushPromises();
}

describe("NotesView", () => {
  it("lists the server's files and shows the quota", async () => {
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    expect(rows(w).map((r) => r.text())[0]).toContain("Tea");
    expect(rows(w)).toHaveLength(2);
    expect(w.get('[data-test="quota"]').text()).toContain("2 of 500 files");
    expect(w.get('[data-test="quota"]').text()).not.toContain("full");
  });

  it("warns in words when the quota is nearly full, and refuses a new file when it is full", async () => {
    const near = await setup([row("a", "Tea")], { summary: { files: 410 } });
    expect(near.get('[data-test="quota"]').text()).toContain("nearly full");
    near.unmount();
    const w = await setup([row("a", "Tea")], { summary: { files: 500 } });
    expect(w.get('[data-test="quota"]').text()).toContain("full");
    await buttonByText(w, "New file")!.trigger("click");
    expect(w.find('input[aria-label="Title"]').exists()).toBe(false);
    expect(w.get('[role="status"]').text()).toContain("full");
  });

  it("names files that could not be read", async () => {
    const w = await setup([row("a", "Tea")], { summary: { skipped: 2 } });
    expect(w.text()).toContain("2 files in your brain folder could not be read");
  });

  it("a folder button shows that folder and its subfolders", async () => {
    const w = await setup(
      [row("a", "Top"), row("b", "Food", { folder: "food" }), row("c", "Tea", { folder: "food/tea" }), row("d", "Other", { folder: "foodie" })],
      { folders: ["food", "food/tea", "foodie"] },
    );
    await w.findAll('[aria-label="Folders"] button').find((b) => b.text() === "food")!.trigger("click");
    expect(rows(w).map((r) => r.find(".title").text())).toEqual(["Food", "Tea"]);
    await w.findAll('[aria-label="Folders"] button').find((b) => b.text() === "No folder")!.trigger("click");
    expect(rows(w).map((r) => r.find(".title").text())).toEqual(["Top"]);
  });

  it("searches the server after a pause, shows the snippet, and clearing restores the list", async () => {
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    // Fake only the timers the page's pause uses, after setup: flushPromises needs the real setImmediate.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const hit: SearchHit = { ...row("b", "Plan"), score: 2, snippet: "the plan for tea" };
    client.search.mockResolvedValue({ results: [hit] });
    await w.get('input[aria-label="Search files"]').setValue("plan");
    expect(client.search).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();
    expect(client.search).toHaveBeenCalledExactlyOnceWith("plan");
    expect(rows(w)).toHaveLength(1);
    expect(rows(w)[0]!.text()).toContain("the plan for tea");
    await w.get('input[aria-label="Search files"]').setValue("");
    await flushPromises();
    expect(rows(w)).toHaveLength(2);
  });

  it("opens a file by fetching its text", async () => {
    client.get.mockResolvedValue(full("a", "Tea", "Green tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    expect(client.get).toHaveBeenCalledExactlyOnceWith("a");
    expect((title(w).element as HTMLInputElement).value).toBe("Tea");
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Green tea");
  });

  it("shows why a file could not be opened and can try again", async () => {
    client.get.mockRejectedValueOnce(new ApiError(404, "No such file."));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    expect(w.get('[role="alert"]').text()).toContain("No such file.");
    client.get.mockResolvedValueOnce(full("a", "Tea", "Back"));
    await w.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Back");
  });

  it("creates a file in the folder that is showing, with a cleaned folder name", async () => {
    const w = await setup([row("b", "Food", { folder: "food" })], { folders: ["food"] });
    await w.findAll('[aria-label="Folders"] button').find((b) => b.text() === "food")!.trigger("click");
    await buttonByText(w, "New file")!.trigger("click");
    await flushPromises();
    expect((w.get('input[aria-label="Folder"]').element as HTMLInputElement).value).toBe("food");
    await title(w).setValue("  Rice ");
    await text(w).setValue("Boil it");
    await w.get('input[aria-label="Folder"]').setValue("Food / Grains");
    client.create.mockResolvedValue(full("n", "Rice", "Boil it", { folder: "food/grains" }));
    client.list.mockResolvedValue({ files: [row("n", "Rice", { folder: "food/grains" }), row("b", "Food", { folder: "food" })], folders: ["food", "food/grains"] });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ title: "Rice", body: "Boil it", tags: [], folder: "food/grains" });
    expect(w.text()).toContain("Saved.");
    expect(rows(w)[0]!.text()).toContain("Rice");
  });

  it("a save sends only what changed, with the revision it opened", async () => {
    client.get.mockResolvedValue({ ...full("a", "Tea", "Green"), revision: 4 });
    const w = await setup([row("a", "Tea", { revision: 4 })]);
    await open(w, "a");
    await text(w).setValue("Green and black");
    client.update.mockResolvedValue({ ...full("a", "Tea", "Green and black"), revision: 5 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenCalledExactlyOnceWith("a", { body: "Green and black" }, 4);
    expect(w.text()).toContain("Saved.");
    expect(w.find(".unsaved").exists()).toBe(false);
  });

  it("the agent switch is saved as agent_editable", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await w.get('input[type="checkbox"]').setValue(true);
    client.update.mockResolvedValue({ ...full("a", "Tea"), agent_editable: true, revision: 2 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenCalledExactlyOnceWith("a", { agent_editable: true }, 1);
  });

  it("a refused save offers the newer version or saving over it", async () => {
    client.get.mockResolvedValueOnce(full("a", "Tea", "Mine v1"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await text(w).setValue("Mine v2");
    client.update.mockRejectedValueOnce(new ApiError(412, "This file changed since you opened it."));
    client.get.mockResolvedValueOnce({ ...full("a", "Tea", "Theirs", { last_editor: "agent" }), revision: 7 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(w.get(".conflict").text()).toContain("An agent changed this file after you opened it.");
    client.update.mockResolvedValueOnce({ ...full("a", "Tea", "Mine v2"), revision: 8 });
    await buttonByText(w, "Save mine anyway")!.trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenLastCalledWith("a", { body: "Mine v2" }, 7);
    expect(w.find(".conflict").exists()).toBe(false);
  });

  it("showing their version drops the user's edits", async () => {
    client.get.mockResolvedValueOnce(full("a", "Tea", "Mine v1"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await text(w).setValue("Mine v2");
    client.update.mockRejectedValueOnce(new ApiError(412, "This file changed since you opened it."));
    client.get.mockResolvedValueOnce({ ...full("a", "Tea", "Theirs"), revision: 3 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    await buttonByText(w, "Show their version (drops my changes)")!.trigger("click");
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Theirs");
    expect(w.find(".conflict").exists()).toBe(false);
  });

  it("another failure shows the server's reason and keeps the edits", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await w.get('input[aria-label="Folder"]').setValue("reserved");
    await text(w).setValue("More");
    client.update.mockRejectedValue(new ApiError(422, "That folder name is reserved."));
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(w.get(".form-error").text()).toBe("That folder name is reserved.");
    expect((text(w).element as HTMLTextAreaElement).value).toBe("More");
  });

  it("a folder the server would refuse keeps Save off and says why", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await w.get('input[aria-label="Folder"]').setValue("a/b/c/d");
    expect(buttonByText(w, "Save")!.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("A folder is up to 3 levels");
  });

  it("an agent's file shows the warning, and restore asks first and waits for a clean editor", async () => {
    const agent = { source: "automatic", last_editor: "user", edited: true, warning: "Written by an agent. Editing it may break the agent that uses it." } as const;
    client.get.mockResolvedValue({ ...full("a", "Plan", "Steps", agent), revision: 3 });
    const w = await setup([row("a", "Plan", { ...agent, revision: 3 })]);
    await open(w, "a");
    expect(w.get('[data-test="agent-warning"]').text()).toContain("may break the agent that uses it");
    await text(w).setValue("Changed");
    expect(buttonByText(w, "Restore original")!.attributes("disabled")).toBeDefined();
    await text(w).setValue("Steps");
    expect(buttonByText(w, "Restore original")!.attributes("disabled")).toBeUndefined();
    await buttonByText(w, "Restore original")!.trigger("click");
    await flushPromises();
    client.revert.mockResolvedValue({ ...full("a", "Plan", "Original steps", { ...agent, edited: false }), revision: 4 });
    confirm()!.click();
    await flushPromises();
    expect(client.revert).toHaveBeenCalledExactlyOnceWith("a", 3);
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Original steps");
    expect(w.text()).toContain("Original text restored.");
  });

  it("deleting asks first, then removes the file and shows the list", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    await open(w, "a");
    await buttonByText(w, "Delete this file")!.trigger("click");
    await flushPromises();
    expect(client.remove).not.toHaveBeenCalled();
    client.remove.mockResolvedValue(undefined);
    client.list.mockResolvedValue({ files: [row("b", "Plan")], folders: [] });
    confirm()!.click();
    await flushPromises();
    expect(client.remove).toHaveBeenCalledExactlyOnceWith("a");
    expect(w.text()).toContain("File deleted.");
    expect(rows(w)).toHaveLength(1);
    expect(w.find('input[aria-label="Title"]').exists()).toBe(false);
  });

  it("switching file with unsaved edits asks first", async () => {
    client.get.mockImplementation(async (id: string) => full(id, id === "a" ? "Tea" : "Plan", "Body"));
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    await open(w, "a");
    await text(w).setValue("Edited");
    await w.get('[data-file-id="b"]').trigger("click");
    await flushPromises();
    expect(client.get).toHaveBeenCalledTimes(1);
    expect(document.body.querySelector("dialog[open]")!.textContent).toContain("Discard your changes?");
    cancel()!.click();
    await flushPromises();
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Edited");
    await w.get('[data-file-id="b"]').trigger("click");
    await flushPromises();
    confirm()!.click();
    await flushPromises();
    expect((title(w).element as HTMLInputElement).value).toBe("Plan");
  });

  it("a failed load shows the reason with a way to try again", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().account = makeAccount();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    client.summary.mockResolvedValue(SUMMARY);
    wrapper = mount(NotesView, { attachTo: document.body, global: { plugins: [pinia] } });
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Storage is unavailable");
    client.list.mockResolvedValue({ files: [row("a", "Tea")], folders: [] });
    await wrapper.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect(rows(wrapper)).toHaveLength(1);
  });

  it("drops the files from memory when the page goes away", async () => {
    const w = await setup([row("a", "Tea")]);
    const store = useBrainStore();
    expect(store.files).toHaveLength(1);
    w.unmount();
    wrapper = null;
    expect(store.files).toEqual([]);
  });
});
```

- [x] **Step 2: Run it to verify it fails**

Run: `pnpm exec vitest run src/features/notes/NotesView.test.ts`
Expected: FAIL (the old page does not use the brain store or the new labels).

- [x] **Step 3: Rewrite `NotesView.vue`**

```vue
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import "../../components/layout/infoPage.css";
import ListEditorLayout from "../../components/layout/ListEditorLayout.vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import { ApiError } from "../../api/http";
import { useUnsavedGuard } from "../../composables/useUnsavedGuard";
import { errorMessage } from "../../utils/errors";
import { brainClient, folderProblem, normalizeFolder, type BrainFile, type FileChanges } from "./api/BrainClient";
import FileEditor from "./components/FileEditor.vue";
import FileList from "./components/FileList.vue";
import { useBrainStore } from "./stores/brain";

/** The Notes page: the account's long-term memory as a file browser. A list on the left (folders, search,
 * files) and an editor on the right; on a narrow screen one at a time. Edits are a draft until Save. Agents
 * read every file; the editor has a switch that lets them edit one. */

const NEW = "new";
const store = useBrainStore();

// The open file: an id, NEW for one not saved yet, or null for none.
const selected = ref<string | null>(null);
// The version the editor holds as saved (its revision goes with every save); null for a new file.
const opened = ref<BrainFile | null>(null);
const opening = ref(false);
const openError = ref("");
let openRun = 0; // a late answer for a file the user has left is dropped
const form = reactive({ title: "", body: "", tags: [] as string[], folder: "", agentEditable: false });
const saved = reactive({ title: "", body: "", tags: [] as string[], folder: "", agentEditable: false });
const tagText = ref("");
const editor = ref<InstanceType<typeof FileEditor> | null>(null);
const listHost = ref<HTMLElement | null>(null);
// The newer version the server holds, while a refused save waits for the user's choice.
const conflict = ref<BrainFile | null>(null);
const saving = ref(false);
const removing = ref(false);
const reverting = ref(false);
const formError = ref("");
const notice = ref("");
const query = ref("");
const folder = ref<string | null>(null);

const busy = computed(() => saving.value || removing.value || reverting.value || opening.value);
const sameTags = (a: string[], b: string[]) => a.length === b.length && a.every((tag, i) => tag === b[i]);
const cleanFolder = computed(() => normalizeFolder(form.folder));
const problem = computed(() => folderProblem(cleanFolder.value));
// A tag typed but not added yet counts as an unsaved edit, so it is never lost silently.
const dirty = computed(
  () =>
    selected.value !== null &&
    !opening.value &&
    (form.title.trim() !== saved.title ||
      form.body !== saved.body ||
      cleanFolder.value !== saved.folder ||
      form.agentEditable !== saved.agentEditable ||
      !sameTags(form.tags, saved.tags) ||
      tagText.value.trim() !== ""),
);
const canSave = computed(() => form.title.trim() !== "" && dirty.value && !busy.value && conflict.value === null && problem.value === "");
const canRevert = computed(() => opened.value?.edited === true && !dirty.value && !busy.value);
const revertHint = computed(() => (opened.value?.edited && dirty.value ? "Save or discard your changes first." : ""));

const maxChars = computed(() => store.summary?.max_record_chars ?? 20_000);
const knownTags = computed(() => {
  const counts = new Map<string, number>();
  for (const file of store.files) for (const tag of file.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  return [...counts]
    .filter(([tag]) => !form.tags.includes(tag))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([tag, count]) => ({ tag, count }));
});

const shown = computed(() => {
  if (store.hits !== null) return store.hits;
  const wanted = folder.value;
  if (wanted === null) return store.files;
  return store.files.filter((f) => (wanted === "" ? f.folder === "" : f.folder === wanted || f.folder.startsWith(`${wanted}/`)));
});

function formatBytes(bytes: number): string {
  return bytes < 1_000_000 ? `${Math.round(bytes / 1000)} KB` : `${(bytes / 1_000_000).toFixed(1)} MB`;
}
const quotaLevel = computed<"" | "near" | "full">(() => {
  const s = store.summary;
  if (!s) return "";
  if (s.files >= s.max_files || s.bytes >= s.max_total_bytes) return "full";
  return s.files >= s.max_files * 0.8 || s.bytes >= s.max_total_bytes * 0.8 ? "near" : "";
});
const quotaText = computed(() => {
  const s = store.summary;
  return s ? `${s.files} of ${s.max_files} files · ${formatBytes(s.bytes)} of ${formatBytes(s.max_total_bytes)}` : "";
});
const headLabel = computed(() => {
  if (selected.value === NEW) return "New file";
  if (opened.value?.source === "automatic") return "Written by an agent";
  if (opened.value?.source === "shared") return "Shared with you";
  return "Your file";
});

// Search waits for a pause in typing; an empty box shows the list again.
let timer: ReturnType<typeof setTimeout> | undefined;
watch(query, (value) => {
  clearTimeout(timer);
  if (value.trim() === "") store.clearSearch();
  else timer = setTimeout(() => void store.search(value), 300);
});

onMounted(() => void store.load());
onBeforeUnmount(() => {
  clearTimeout(timer);
  store.forget();
});

/** Fills the editor, and what counts as saved, from a file (or empty for a new one). */
function fillEditor(file: BrainFile | null, startFolder = ""): void {
  saved.title = form.title = file?.title ?? "";
  saved.body = form.body = file?.body ?? "";
  form.tags = [...(file?.tags ?? [])];
  saved.tags = [...form.tags];
  saved.folder = form.folder = file?.folder ?? startFolder;
  saved.agentEditable = form.agentEditable = file?.agent_editable ?? false;
  opened.value = file;
  conflict.value = null;
  tagText.value = "";
}

async function show(target: string | null): Promise<void> {
  const previous = selected.value;
  const run = ++openRun;
  selected.value = target;
  formError.value = "";
  notice.value = "";
  openError.value = "";
  opening.value = false;
  fillEditor(null, target === NEW ? (folder.value ?? "") : "");
  if (target !== null && target !== NEW) {
    opening.value = true;
    try {
      const file = await brainClient.get(target);
      if (run === openRun) fillEditor(file);
    } catch (err) {
      if (run === openRun) openError.value = errorMessage(err);
    } finally {
      if (run === openRun) opening.value = false;
    }
  }
  await nextTick();
  if (run !== openRun) return;
  if (target !== null) editor.value?.focusTitle();
  else (listHost.value?.querySelector<HTMLElement>(`[data-file-id="${previous}"]`) ?? listHost.value?.querySelector<HTMLElement>("input"))?.focus();
}

// Leaving unsaved edits asks first; the target waits here meanwhile.
const discardTarget = ref<string | null | undefined>(undefined);
function go(target: string | null): void {
  if (busy.value || target === selected.value) return;
  if (dirty.value) discardTarget.value = target;
  else void show(target);
}
function discard(): void {
  const target = discardTarget.value;
  discardTarget.value = undefined;
  if (target !== undefined) void show(target);
}

// Leaving the page with unsaved edits asks first, like the Settings page.
const { open: leaveOpen, answer: answerLeave } = useUnsavedGuard({ dirty: () => dirty.value, busy: () => busy.value });

function startNew(): void {
  if (quotaLevel.value === "full") {
    notice.value = "Your brain is full. Delete a file, or ask an administrator to raise the limit.";
    return;
  }
  go(NEW);
}

function changesFromEditor(): FileChanges {
  const changes: FileChanges = {};
  if (form.title.trim() !== saved.title) changes.title = form.title.trim();
  if (form.body !== saved.body) changes.body = form.body;
  if (!sameTags(form.tags, saved.tags)) changes.tags = [...form.tags];
  if (cleanFolder.value !== saved.folder) changes.folder = cleanFolder.value;
  if (form.agentEditable !== saved.agentEditable) changes.agent_editable = form.agentEditable;
  return changes;
}

async function save(): Promise<void> {
  if (selected.value === null) return;
  editor.value?.commitTags(); // a tag still in the box is part of the file
  if (tagText.value.trim() !== "") return; // it could not be added (too many tags): its message is showing
  if (!canSave.value) return;
  saving.value = true;
  formError.value = "";
  try {
    const record =
      selected.value === NEW
        ? await store.create({ title: form.title.trim(), body: form.body, tags: [...form.tags], folder: cleanFolder.value })
        : await store.save(selected.value, changesFromEditor(), opened.value?.revision ?? 1);
    selected.value = record.id;
    fillEditor(record);
    notice.value = "Saved.";
  } catch (err) {
    if (err instanceof ApiError && err.status === 412 && selected.value !== NEW) await loadConflict(selected.value);
    else formError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

/** The server refused because the file changed: fetch its newer version and ask what to do. */
async function loadConflict(id: string): Promise<void> {
  try {
    conflict.value = await brainClient.get(id);
  } catch (err) {
    formError.value = errorMessage(err);
  }
}
/** Drops the user's edits for the newer version. */
function showTheirs(): void {
  const theirs = conflict.value;
  if (theirs === null) return;
  fillEditor(theirs);
  notice.value = "Showing the newer version.";
  void store.load();
}
/** Saves the user's edits over the newer version: only the fields the user changed are sent. */
async function keepMine(): Promise<void> {
  const theirs = conflict.value;
  if (theirs === null) return;
  opened.value = theirs;
  conflict.value = null;
  await save();
}

const confirmRevert = ref(false);
async function revert(): Promise<void> {
  const file = opened.value;
  if (file === null || reverting.value) return;
  reverting.value = true;
  formError.value = "";
  try {
    fillEditor(await store.revert(file.id, file.revision));
    notice.value = "Original text restored.";
  } catch (err) {
    if (err instanceof ApiError && err.status === 412) await loadConflict(file.id);
    else formError.value = errorMessage(err);
  } finally {
    reverting.value = false;
    confirmRevert.value = false;
  }
}

const confirmDelete = ref(false);
async function remove(): Promise<void> {
  const id = selected.value;
  if (id === null || id === NEW || removing.value) return;
  removing.value = true;
  formError.value = "";
  try {
    await store.remove(id);
    await show(null);
    notice.value = "File deleted.";
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    removing.value = false;
    confirmDelete.value = false;
  }
}
</script>

<template>
  <PageLayout class="notes info-content" :class="{ 'file-open': selected !== null }" title="Notes" description="Your long-term memory: the files you and your agents keep." wide fill>
    <template #actions>
      <button type="button" class="primary new-file" :disabled="busy" @click="startNew">New file</button>
    </template>
    <div class="column">
      <p v-if="quotaText" class="quota" :class="quotaLevel" data-test="quota">
        <svg v-if="quotaLevel" class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        {{ quotaText }}<template v-if="quotaLevel === 'full'"> · full</template><template v-else-if="quotaLevel === 'near'"> · nearly full</template>
      </p>
      <p v-if="store.summary?.skipped" class="muted skipped" role="status">
        {{ store.summary.skipped }} {{ store.summary.skipped === 1 ? "file" : "files" }} in your brain folder could not be read and {{ store.summary.skipped === 1 ? "is" : "are" }} not shown.
      </p>
      <p v-if="notice" class="notice-line" role="status">{{ notice }}</p>
      <p v-if="store.status === 'ready' && store.error" class="error" role="alert">Could not refresh your files: {{ store.error }}</p>
      <StateMessage v-if="store.status === 'idle' || store.status === 'loading'" kind="loading">Loading …</StateMessage>
      <StateMessage v-else-if="store.status === 'error'" kind="error" @retry="store.load()">Could not load your files: {{ store.error }}</StateMessage>

      <ListEditorLayout
        v-else
        class="layout"
        :editing="selected !== null"
        list-label="Files list"
        editor-label="File editor"
        back-label="All files"
        visible-scrollbars
        :busy="busy"
        :saving="saving"
        :dirty="dirty"
        :can-save="canSave"
        @back="go(null)"
        @submit="save"
      >
        <template #list>
          <div ref="listHost" class="list-host">
            <FileList
              v-model:query="query"
              v-model:folder="folder"
              :rows="shown"
              :folders="store.folders"
              :selected-id="selected === NEW ? null : selected"
              :draft-title="selected === NEW ? form.title : null"
              :is-search="store.hits !== null"
              :search-busy="store.searching"
              :search-error="store.searchError"
              :disabled="busy"
              @select="go"
            />
          </div>
        </template>

        <template #head>
          <span class="context-label"><svg class="line-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg>{{ headLabel }}</span>
        </template>

        <template #editor>
          <StateMessage v-if="opening" kind="loading">Opening …</StateMessage>
          <StateMessage v-else-if="openError" kind="error" @retry="selected !== null && show(selected)">Could not open this file: {{ openError }}</StateMessage>
          <template v-else>
            <FileEditor
              :key="selected ?? ''"
              ref="editor"
              v-model:title="form.title"
              v-model:body="form.body"
              v-model:tags="form.tags"
              v-model:tagText="tagText"
              v-model:folder="form.folder"
              v-model:agentEditable="form.agentEditable"
              :file="opened"
              :folders="store.folders"
              :known-tags="knownTags"
              :max-chars="maxChars"
              :folder-problem="problem"
              :can-revert="canRevert"
              :revert-hint="revertHint"
              :disabled="busy"
              @revert="confirmRevert = true"
              @remove="confirmDelete = true"
            />
            <p v-if="formError" class="error form-error" role="alert">{{ formError }}</p>
            <div v-if="conflict" class="conflict" role="alert">
              <p>{{ conflict.last_editor === "agent" ? "An agent" : "Another session" }} changed this file after you opened it.</p>
              <div class="conflict-actions">
                <button type="button" class="chip" @click="showTheirs">Show their version (drops my changes)</button>
                <button type="button" class="chip" @click="keepMine">Save mine anyway</button>
              </div>
            </div>
          </template>
        </template>

        <template #placeholder>
          <svg class="line-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg>
          <h3>What you and your agents remember</h3>
          <p>Pick a file, or start a new one.</p>
          <button type="button" class="chip" @click="startNew">Create a file</button>
        </template>
      </ListEditorLayout>
    </div>

    <ConfirmModal
      :open="confirmDelete"
      title="Delete this file?"
      message="This file will be gone for good, with the saved original text if it has one."
      confirm-label="Delete file"
      danger
      :busy="removing"
      @confirm="remove"
      @close="confirmDelete = false"
    />
    <ConfirmModal
      :open="confirmRevert"
      title="Restore the original text?"
      message="The text, title and tags from before your first change come back. Your changes are replaced."
      confirm-label="Restore original"
      danger
      :busy="reverting"
      @confirm="revert"
      @close="confirmRevert = false"
    />
    <ConfirmModal
      :open="leaveOpen"
      title="Leave without saving?"
      message="This file has changes you have not saved."
      confirm-label="Leave page"
      danger
      @confirm="answerLeave(true)"
      @close="answerLeave(false)"
    />
    <ConfirmModal
      :open="discardTarget !== undefined"
      title="Discard your changes?"
      message="This file has changes you have not saved."
      confirm-label="Discard"
      danger
      @confirm="discard"
      @close="discardTarget = undefined"
    />
  </PageLayout>
</template>

<style scoped src="../../components/layout/editorPage.css"></style>
<style scoped>
.layout { --workspace-columns: 360px minmax(0, 1fr); }
.layout :deep(.list-pane) { overflow: hidden; }
.column { display: flex; flex: 1; min-height: 0; flex-direction: column; }
.list-host { display: flex; flex: 1; flex-direction: column; min-height: 0; }
.new-file { flex-shrink: 0; min-height: 40px; }
.quota { display: flex; align-items: center; gap: 6px; margin: 0 0 8px; font-size: .85em; color: var(--muted); font-variant-numeric: tabular-nums; }
.quota.near .line-icon { color: var(--warning); }
.quota.full .line-icon { color: var(--danger); }
.skipped, .notice-line { margin: 0 0 8px; font-size: .85em; }
.conflict { display: flex; flex-direction: column; gap: 8px; margin: 12px 20px; padding: 12px; border: 1px solid var(--warning); border-radius: var(--radius-md); font-size: .9em; }
.conflict p { margin: 0; }
.conflict-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.form-error { margin: 12px 20px; }
@media (max-width: 900px) and (min-width: 768px) { .notes .layout { --workspace-columns: 280px minmax(0, 1fr); } }
@media (max-width: 767px) {
  .notes :deep(.page-column) { padding: 18px 16px 12px; }
  .notes :deep(.page-head) { flex-direction: row; align-items: center; margin-bottom: 16px; gap: 10px; }
  .notes :deep(.page-title) { margin: 0; }
  .notes :deep(.page-description) { display: none; }
  .notes :deep(.page-actions button) { min-width: 44px; min-height: 44px; }
  .notes.file-open :deep(.page-head) { display: none; }
}
</style>
```

- [x] **Step 4: Run the page test, then delete the old notes code**

Run: `pnpm exec vitest run src/features/notes/NotesView.test.ts`
Expected: PASS. Fix a snippet that does not fit (for example how the discard dialog button is found, or the label of the shared `StateMessage` retry button) and record it.

Then delete the old files and check nothing else needs them (assumption (e)):

```bash
git rm apps/ember/src/features/notes/api/NotesClient.ts apps/ember/src/features/notes/api/NotesClient.test.ts apps/ember/src/features/notes/components/NotePromotionPanel.vue apps/ember/src/features/notes/components/NotePromotionPanel.test.ts apps/ember/src/features/notes/NotesPublicationDraft.test.ts
```

Run: `pnpm exec vue-tsc -b` and `pnpm test`
Expected: no type errors; every suite passes. List under "Changes found during work" every existing test that was removed with the old files (the old `NotesView.test.ts` had 58 cases, `NotesClient.test.ts` 8, `NotePromotionPanel.test.ts` 6, `NotesPublicationDraft.test.ts` 1) and say that their behaviours (private notes, Laya tag suggestions, publishing to Obsidian) no longer exist in Ember by design.

- [x] **Step 5: Update the nav description, docs and check the roadmap**

In `apps/ember/src/router/pages.ts` change the Notes entry's `description` from `"Private notes, just for your account."` to `"Your long-term memory: files you and your agents keep, in folders."`. Update any test that asserted the old description (assumption (f)). Grep `apps/ember/README.md` for a description of the Notes page; if it has one, update it; otherwise skip and say so in the report.

Check `docs/superpowers/plans/2026-11-20-scope-roadmap.md`: the row for 20f must link this plan and read "Ember Notes page as the long-term file browser" (the author already did this; fix a typo only).

- [x] **Step 6: Commit**

```bash
git add -A apps/ember/src/features/notes apps/ember/src/router/pages.ts docs/superpowers/plans
git commit -m "feat(ember): Notes page is the long-term file browser; old notes client and publishing panel removed"
```

---

## Manual checklist (the user runs it; Codex copies it into the report as pending)

- Desktop, 768px, 767px and 375px, light and dark.
- Open the Notes page with a few files in two folders: the folder buttons filter (a parent shows its subfolders); search finds a word in a file's text; clearing the box restores the list.
- Create a file in the folder that is showing; type a folder with capitals and spaces and see it cleaned when you leave the box; try four levels and see Save stay off with the reason.
- Edit a file, Save, and see "Saved." with the unsaved marker gone; change a file in a second window, then save in the first and use both conflict buttons.
- Let an agent write a file (ask Ember to remember something in a long-term file): it shows "Agent file", the warning with its icon, no agent switch; edit it, see "Edited", and Restore original puts the first text back.
- Turn on "Let agents edit this file" for one of your own files and check an agent can change it afterwards (Plan 20b's rule), and that it cannot with the switch off.
- Delete a file; fill the quota to 80% and to full and read the line and the refusal of New file.
- Switch file, go back and leave the page with unsaved edits: each asks first. Tab through the page; Esc closes the dialogs; the buttons are 44px on a phone.
- A damaged `.md` file in the brain folder: the page names how many files could not be read.

Unverified by the work above: the page against a real Stronghold with real agent-written files, layout on a real phone with the keyboard open, light and dark contrast beyond the pairs computed, a brain with thousands of files (the list is not virtualised).
