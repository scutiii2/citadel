# Plan 20k: Ember Global Brain Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Global" page in Ember where everyone signed in browses and searches the global brain's files and active skills, and an account with `brain.global.write` also creates, edits and deletes global files, manages global skills and reviews the queue of shares sent to the global brain.

**Architecture:** Front end only, in `apps/ember`. One new feature folder `features/global/` with a typed client for Portcullis' `/api/brain/global/*` routes (built in Plan 20d), three section components (files, skills, review queue) and a page that switches between them. The write controls and the review queue show only when the account holds `brain.global.write`; the server enforces it anyway. No store: each section keeps its own state with run counters and clears on sign-out and unmount (the content is not private, but nothing is cached across accounts).

**Tech Stack:** Vue 3, TypeScript, Pinia (auth store only), Vitest.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md) (global brain), [roadmap](2026-11-20-scope-roadmap.md) row 20k. Builds on Plan 20d (backend and Portcullis routes), 20f (Notes page patterns), 20g (sharing, the review dialog pattern).

## Global Constraints

- Front end only in `apps/ember`. No backend, Portcullis, Stronghold or Legion change. If a route is missing or answers differently from this plan, record it and stop that piece.
- `apiRequest` only; never `fetch` or a hand-built URL outside the client. Types for files, skills and shares are reused from `features/notes/api/BrainClient.ts`, `features/skills/api/SkillsClient.ts` and `features/sharing/api/SharingClient.ts` (feature to feature imports are allowed; shared code must not import features: `architecture.test.ts`).
- Everything on this page is visible to every account and every agent. Show this sentence once at the top of the page, always, as a note with an icon: "Everyone on this instance, and every agent, can read this. Do not put private data here."
- Shares waiting in the queue were written by other accounts: show their text as plain text with the server's untrusted notice, never as markup (no `v-html`), and drop the text when the dialog closes. Approve and Reject are explicit buttons; opening a share changes nothing.
- Permission: `useAuthStore().hasPermission("brain.global.write")` decides what shows (`canWrite`). Without it there are no create, edit, delete or queue controls, the queue tab is absent and the skills list is the active skills only (`GET /skills`). With it the skills list is `GET /skills/all`.
- Files: only title, text and folder are edited (no tags, no agent switch, no revert: global files have no originals). A save sends only changed fields and the opened revision; a 412 says the file changed and offers nothing but closing and reopening it. Check titles and folders with `folderProblem`, `normalizeFolder`, `FILE_TITLE_MAX` from `BrainClient`. The text limit comes from the server's summary (`max_record_chars`); if the summary fails use 20,000.
- Skills text limits are `SKILL_LIMITS`. Status moves: proposed to active (Approve), active to retired (Retire), retired to proposed (Send back for review). Delete asks for confirmation.
- Ember design rules: tokens only (`radiusScale.test.ts`), shared components (`PageLayout`, `SegmentedControl` in tabs mode, `ListRow`, `SearchField`, `StateMessage`, `BaseModal`, `ConfirmModal`), 44px touch targets, status shown by words plus an icon (never colour alone), a problem is words beside the field. Never add a reduced-motion rule, media query or test.
- Use `pnpm` (not npm), add no dependency. Run `pnpm exec vue-tsc -b` and `pnpm test` from `apps/ember`. Never read `.env*` or `secrets/`.
- Out of scope: sharing from the global brain, tags and revert on global files, a global search across personal and global files on the Notes page, Armory, any change to the Notes page, Skills page or Shares page except none (they are untouched), phone-only layouts beyond the shared components.

## Assumptions to check while working

Record each result in "Changes found during work".

- (a) The Portcullis routes exist as listed in `apps/portcullis/src/routes/brain_sharing.py`: `GET /api/brain/global/files`, `/files/{id}`, `/search`, `/summary`, `/skills`; writer routes `POST/PUT/DELETE /files`, `GET /skills/all`, `PUT /skills/{id}/status`, `PUT /skills/{id}`, `DELETE /skills/{id}`, `GET /shares`, `GET /shares/{id}`, `POST /shares/{id}/approve`, `POST /shares/{id}/reject`. Read that file and `apps/stronghold/src/brain/global_routes.py` before writing the client.
- (b) The global file routes answer with the same row and full shapes as `/api/brain/files` (`row`, `full` in `files_routes.py`), and global write answers add `notice`. Global files are created with `actor="user"`, so they have no revert copy.
- (c) `brainClient.list` builds its folder query the way the plan's client does (`?folder=`); copy its exact form. `apiRequest` returns `void` for 204 and throws `ApiError` with `status` and `message`.
- (d) `useAuthStore().hasPermission(name)` exists (it does in `stores/auth.ts`) and `account.permissions` carries `brain.global.write` for a writer (Plan 20d grants it by role).
- (e) After Plan 20j the nav lists no "Memory" entry. If 20j is not on `main` yet, the nav lists still have it; insert "Global" after "Shares" either way and keep the rest as is.
- (f) `SegmentedControl` in `mode="tabs"` needs `idPrefix` and expects panels with `role="tabpanel"` and matching `id` and `aria-labelledby`; read `SegmentedControl.vue` and one existing user (grep `mode="tabs"`) and copy the wiring.

## Baseline

Fill in before changing anything: Ember `pnpm exec vue-tsc -b` and `pnpm test` pass counts: type-check passed; Vitest 197 files, 2,360 tests passed, no failures. Both ran from the Plan 20k worktree.

## File Map

| File | Change |
|---|---|
| `apps/ember/src/features/global/api/GlobalClient.ts` (+ test) | Create |
| `apps/ember/src/features/global/components/GlobalFileDialog.vue` (+ test) | Create |
| `apps/ember/src/features/global/components/GlobalFiles.vue` (+ test) | Create |
| `apps/ember/src/features/global/components/GlobalSkills.vue` (+ test) | Create |
| `apps/ember/src/features/global/components/GlobalReview.vue` (+ test) | Create |
| `apps/ember/src/features/global/components/GlobalQueue.vue` (+ test) | Create |
| `apps/ember/src/features/global/GlobalView.vue` (+ test) | Create |
| `apps/ember/src/router/index.ts`, `router/pages.ts` | Modify: route `/global`, nav entry after Shares |
| Ember tests that list the nav | Modify (NavRail, AccountView, SidebarEditor, Overview tests) |
| Ember README or AGENTS.md | Modify: only statements this page changes |

---

### Task 1: Client

**Files:**
- Create: `apps/ember/src/features/global/api/GlobalClient.ts`
- Test: `apps/ember/src/features/global/api/GlobalClient.test.ts`

**Interfaces:**
- Consumes: `apiRequest`; types `BrainFile`, `BrainList`, `BrainSummary`, `SearchHit` (`features/notes/api/BrainClient`), `Skill`, `SkillStatus`, `SkillText` (`features/skills/api/SkillsClient`), `Share`, `ShareDetail`, `Landing` (`features/sharing/api/SharingClient`).
- Produces: `GLOBAL_NOTICE` (the sentence above), `GlobalFileDraft = { title: string; body: string; folder: string }`, `GlobalFileChanges = Partial<GlobalFileDraft>`, `GlobalSummary = BrainSummary & { notice: string }`, and `globalClient` with:
  `list(folder?: string) -> BrainList`, `get(id) -> BrainFile`, `search(q) -> SearchHit[]`, `summary() -> GlobalSummary`,
  `create(draft) -> BrainFile`, `update(id, changes, expectedRevision) -> BrainFile`, `remove(id) -> void`,
  `skills() -> Skill[]` (active ones), `allSkills() -> Skill[]` (writer), `setSkillStatus(id, status) -> Skill`, `updateSkill(id, text) -> Skill`, `removeSkill(id) -> void`,
  `queue() -> Share[]`, `share(id) -> ShareDetail`, `approve(id, landing) -> Share`, `reject(id) -> Share`.

- [x] **Step 1: Write the failing test**

Create `GlobalClient.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { globalClient, GLOBAL_NOTICE } from "./GlobalClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));
const request = vi.mocked(apiRequest);

beforeEach(() => vi.clearAllMocks());

describe("globalClient", () => {
  it("reads files, one file, a search and the summary", async () => {
    request.mockResolvedValue({ files: [], folders: [], results: [] });
    await globalClient.list();
    await globalClient.list("team/docs");
    await globalClient.get("f".repeat(32));
    expect(await globalClient.search("tea party")).toEqual([]);
    await globalClient.summary();
    expect(request.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      ["GET", "/api/brain/global/files"],
      ["GET", "/api/brain/global/files?folder=team%2Fdocs"],
      ["GET", `/api/brain/global/files/${"f".repeat(32)}`],
      ["GET", "/api/brain/global/search?q=tea%20party"],
      ["GET", "/api/brain/global/summary"],
    ]);
  });

  it("writes files with the opened revision", async () => {
    request.mockResolvedValue({});
    await globalClient.create({ title: "T", body: "b", folder: "" });
    await globalClient.update("a".repeat(32), { body: "new" }, 3);
    await globalClient.remove("a".repeat(32));
    expect(request.mock.calls).toEqual([
      ["POST", "/api/brain/global/files", { title: "T", body: "b", folder: "" }],
      ["PUT", `/api/brain/global/files/${"a".repeat(32)}`, { body: "new", expected_revision: 3 }],
      ["DELETE", `/api/brain/global/files/${"a".repeat(32)}`],
    ]);
  });

  it("reads active skills for everyone and every skill for a writer, and changes skills", async () => {
    request.mockResolvedValue([]);
    await globalClient.skills();
    await globalClient.allSkills();
    request.mockResolvedValue({});
    await globalClient.setSkillStatus(4, "active");
    await globalClient.updateSkill(4, { title: "t", when_to_use: "w", steps: "s", tools: "" });
    await globalClient.removeSkill(4);
    expect(request.mock.calls).toEqual([
      ["GET", "/api/brain/global/skills"],
      ["GET", "/api/brain/global/skills/all"],
      ["PUT", "/api/brain/global/skills/4/status", { status: "active" }],
      ["PUT", "/api/brain/global/skills/4", { title: "t", when_to_use: "w", steps: "s", tools: "" }],
      ["DELETE", "/api/brain/global/skills/4"],
    ]);
  });

  it("reads and answers the review queue", async () => {
    request.mockResolvedValueOnce({ shares: [{ id: "s1" }] });
    expect(await globalClient.queue()).toEqual([{ id: "s1" }]);
    request.mockResolvedValue({});
    await globalClient.share("s1");
    await globalClient.approve("s1", { title: "T", folder: "shared" });
    await globalClient.reject("s1");
    expect(request.mock.calls.slice(1)).toEqual([
      ["GET", "/api/brain/global/shares/s1"],
      ["POST", "/api/brain/global/shares/s1/approve", { title: "T", folder: "shared" }],
      ["POST", "/api/brain/global/shares/s1/reject"],
    ]);
  });

  it("carries the notice sentence", () => {
    expect(GLOBAL_NOTICE).toBe("Everyone on this instance, and every agent, can read this. Do not put private data here.");
  });
});
```

If `brainClient.list` builds the folder query differently (assumption c), change the expected string in the test and the client together to match it.

- [x] **Step 2: Run it and see it fail**

Run (from `apps/ember`): `pnpm exec vitest run src/features/global/api`
Expected: FAIL (module missing).

- [x] **Step 3: Implement**

Create `GlobalClient.ts`:

```ts
import { apiRequest } from "../../../api/http";
import type { BrainFile, BrainList, BrainSummary, SearchHit } from "../../notes/api/BrainClient";
import type { Landing, Share, ShareDetail } from "../../sharing/api/SharingClient";
import type { Skill, SkillStatus, SkillText } from "../../skills/api/SkillsClient";

/** Shown on the page and by the server: the global brain is read by everyone and every agent. */
export const GLOBAL_NOTICE = "Everyone on this instance, and every agent, can read this. Do not put private data here.";

export interface GlobalFileDraft {
  title: string;
  body: string;
  folder: string;
}
export type GlobalFileChanges = Partial<GlobalFileDraft>;
export type GlobalSummary = BrainSummary & { notice: string };

const base = "/api/brain/global";
const file = (id: string) => `${base}/files/${encodeURIComponent(id)}`;
const skill = (id: number) => `${base}/skills/${id}`;
const share = (id: string) => `${base}/shares/${encodeURIComponent(id)}`;

/** Portcullis' /api/brain/global routes, passed on to Stronghold. Anyone signed in reads; `brain.global.write`
 * writes, lists every skill and reads the queue. */
export const globalClient = {
  list: (folder?: string) => apiRequest<BrainList>("GET", folder ? `${base}/files?folder=${encodeURIComponent(folder)}` : `${base}/files`),
  get: (id: string) => apiRequest<BrainFile>("GET", file(id)),
  search: async (q: string) => (await apiRequest<{ results: SearchHit[] }>("GET", `${base}/search?q=${encodeURIComponent(q)}`)).results,
  summary: () => apiRequest<GlobalSummary>("GET", `${base}/summary`),
  create: (draft: GlobalFileDraft) => apiRequest<BrainFile>("POST", `${base}/files`, draft),
  /** With the revision the server refuses (412) when the file was saved since it was opened. */
  update: (id: string, changes: GlobalFileChanges, expectedRevision: number) =>
    apiRequest<BrainFile>("PUT", file(id), { ...changes, expected_revision: expectedRevision }),
  remove: (id: string) => apiRequest<void>("DELETE", file(id)),
  /** The skills agents are offered: active and not failing. */
  skills: () => apiRequest<Skill[]>("GET", `${base}/skills`),
  /** Every skill with its status (writer). */
  allSkills: () => apiRequest<Skill[]>("GET", `${base}/skills/all`),
  setSkillStatus: (id: number, status: SkillStatus) => apiRequest<Skill>("PUT", `${skill(id)}/status`, { status }),
  updateSkill: (id: number, text: SkillText) => apiRequest<Skill>("PUT", skill(id), text),
  removeSkill: (id: number) => apiRequest<void>("DELETE", skill(id)),
  /** Shares sent to the global brain that wait for a reviewer, newest first (writer). */
  queue: async () => (await apiRequest<{ shares: Share[] }>("GET", `${base}/shares`)).shares,
  share: (id: string) => apiRequest<ShareDetail>("GET", share(id)),
  approve: (id: string, landing: Landing = {}) => apiRequest<Share>("POST", `${share(id)}/approve`, landing),
  reject: (id: string) => apiRequest<Share>("POST", `${share(id)}/reject`),
};
```

- [x] **Step 4: Run the test**

Run: `pnpm exec vitest run src/features/global/api` and `pnpm exec vue-tsc -b`
Expected: pass.

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/global
git commit -m "feat(ember): client for the global brain routes"
```

---

### Task 2: Files section

**Files:**
- Create: `components/GlobalFileDialog.vue` (+ test), `components/GlobalFiles.vue` (+ test) under `apps/ember/src/features/global/`

**Interfaces:**
- Consumes: `globalClient`, `BrainFile`, `BrainFileRow`, `SearchHit`, `normalizeFolder`, `folderProblem`, `FILE_TITLE_MAX`, `ApiError`, `errorMessage`, `formatUtc`.
- Produces:
  - `GlobalFileDialog` props `{ open: boolean; fileId: string | null; canWrite: boolean; maxChars: number }` (`fileId` null means a new file; writers only), emits `close`, `done(message: string)`. Existing file: loads it with `globalClient.get`; a reader sees title, folder and text as plain text; a writer sees title, folder and text fields, Save (sends only changed fields and the opened `revision`), Delete (confirm) and Close. New file: fields, Create.
  - `GlobalFiles` props `{ canWrite: boolean }`. Shows a search field, a folder filter (buttons: "All files" plus one per folder), the file list (title, folder, updated time, characters), and for writers a "New file" button. Clicking a row opens the dialog. After `done` it shows the message as a status note and reloads. Search is debounced 300 ms (copy the timer pattern from `NotesView.vue`), late answers ignored by a run counter, and sign-out clears everything.

- [x] **Step 1: Write the failing tests**

Create `GlobalFileDialog.test.ts`:

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import type { BrainFile } from "../../notes/api/BrainClient";
import { globalClient } from "../api/GlobalClient";
import GlobalFileDialog from "./GlobalFileDialog.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));
const client = vi.mocked(globalClient);

const ID = "a".repeat(32);
const file = (extra: Partial<BrainFile> = {}): BrainFile => ({
  id: ID, title: "Style guide", folder: "team", tags: [], source: "manual", last_editor: "user", agent_editable: false,
  edited: false, revision: 3, created_at: "2026-01-01T00:00:00", updated_at: "2026-01-02T00:00:00", warning: null,
  shared_from: "", body: "Use <b>metric</b> units.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.get.mockResolvedValue(file());
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

async function open(props: { fileId: string | null; canWrite: boolean; maxChars?: number }) {
  wrapper = mount(GlobalFileDialog, { attachTo: document.body, props: { open: true, maxChars: 20_000, ...props }, global: { plugins: [createPinia()] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

describe("GlobalFileDialog", () => {
  it("shows a file to a reader as plain text with no form", async () => {
    const w = await open({ fileId: ID, canWrite: false });
    expect(w.find("pre.text").text()).toBe("Use <b>metric</b> units.");
    expect(w.find("pre.text b").exists()).toBe(false);
    expect(w.find("input[aria-label='Title']").exists()).toBe(false);
    for (const name of ["Save", "Delete", "Create"]) expect(w.findAll("button").some((b) => b.text() === name)).toBe(false);
  });

  it("lets a writer change one field and sends only it with the opened revision", async () => {
    client.update.mockResolvedValue(file({ body: "new", revision: 4 }));
    const w = await open({ fileId: ID, canWrite: true });
    expect(button(w, "Save").attributes("disabled")).toBeDefined();
    await w.find("textarea[aria-label='Text']").setValue("new");
    await button(w, "Save").trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenCalledWith(ID, { body: "new" }, 3);
    expect(w.emitted("done")?.[0][0]).toContain("Saved");
  });

  it("says in words that the file changed when the server answers 412", async () => {
    client.update.mockRejectedValue(new ApiError(412, "This file changed since you opened it."));
    const w = await open({ fileId: ID, canWrite: true });
    await w.find("textarea[aria-label='Text']").setValue("new");
    await button(w, "Save").trigger("click");
    await flushPromises();
    expect(w.find("[role='alert']").text()).toContain("This file changed since someone opened it. Close it and open it again.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("creates a file when fileId is null and refuses a bad folder before sending", async () => {
    client.create.mockResolvedValue(file({ title: "Plan" }));
    const w = await open({ fileId: null, canWrite: true });
    await w.find("input[aria-label='Title']").setValue("Plan");
    await w.find("textarea[aria-label='Text']").setValue("Text");
    await w.find("input[aria-label='Folder']").setValue("a/b/c/d");
    expect(w.find("[role='alert']").text()).not.toBe("");
    expect(button(w, "Create").attributes("disabled")).toBeDefined();
    await w.find("input[aria-label='Folder']").setValue("team");
    await button(w, "Create").trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledWith({ title: "Plan", body: "Text", folder: "team" });
    expect(w.emitted("done")?.[0][0]).toContain("Created");
  });

  it("deletes only after confirmation", async () => {
    client.remove.mockResolvedValue(undefined);
    const w = await open({ fileId: ID, canWrite: true });
    await button(w, "Delete").trigger("click");
    expect(client.remove).not.toHaveBeenCalled();
    await w.findAll("button").filter((b) => b.text() === "Delete").at(-1)!.trigger("click");
    await flushPromises();
    expect(client.remove).toHaveBeenCalledWith(ID);
    expect(w.emitted("done")?.[0][0]).toContain("Deleted");
  });

  it("blocks Save above the text limit and says so in words", async () => {
    const w = await open({ fileId: ID, canWrite: true, maxChars: 10 });
    await w.find("textarea[aria-label='Text']").setValue("x".repeat(11));
    expect(button(w, "Save").attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("10");
  });
});
```

The dialog must give its fields these `aria-label`s: Title, Text, Folder. If the delete confirmation's confirm button has another label (read `ConfirmModal.vue`), change the last `Delete` lookup in the delete test to that label.

Create `GlobalFiles.test.ts`:

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { BrainFileRow, SearchHit } from "../../notes/api/BrainClient";
import { globalClient } from "../api/GlobalClient";
import GlobalFiles from "./GlobalFiles.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { list: vi.fn(), search: vi.fn(), summary: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));
vi.mock("./GlobalFileDialog.vue", () => ({
  default: {
    props: ["open", "fileId", "canWrite", "maxChars"],
    emits: ["close", "done"],
    template: '<div data-test="file-dialog" :data-id="fileId ?? \'new\'"><button data-test="finish" @click="$emit(\'done\', \'Saved.\')">finish</button></div>',
  },
}));
const client = vi.mocked(globalClient);

const row = (id: string, title: string, extra: Partial<BrainFileRow> = {}): BrainFileRow => ({
  id, title, folder: "", tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-02T00:00:00", chars: 12, warning: null, shared_from: "", ...extra,
});
const hit = (id: string, title: string): SearchHit => ({ ...row(id, title), score: 1, snippet: "…" });

let wrapper: VueWrapper | null = null;
async function mountIt(canWrite = false) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(GlobalFiles, { attachTo: document.body, props: { canWrite }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue({ files: [row("f1", "Style guide", { folder: "team" }), row("f2", "Glossary")], folders: ["team"] });
  client.summary.mockResolvedValue({ files: 2, bytes: 100, skipped: 0, max_files: 500, max_total_bytes: 5_000_000, max_record_chars: 5000, notice: "n" });
  client.search.mockResolvedValue([hit("f2", "Glossary")]);
});
afterEach(() => {
  vi.useRealTimers();
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalFiles", () => {
  it("lists the files and filters by folder", async () => {
    const w = await mountIt();
    expect(w.text()).toContain("Style guide");
    expect(w.text()).toContain("Glossary");
    expect(client.list).toHaveBeenLastCalledWith(undefined);
    await w.findAll("button").find((b) => b.text() === "team")!.trigger("click");
    await flushPromises();
    expect(client.list).toHaveBeenLastCalledWith("team");
  });

  it("says when there are no files", async () => {
    client.list.mockResolvedValue({ files: [], folders: [] });
    const w = await mountIt();
    expect(w.text()).toContain("No files yet.");
  });

  it("searches after a pause, shows the hits, and ignores a late answer for old text", async () => {
    const w = await mountIt();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    let finishOld!: (hits: SearchHit[]) => void;
    client.search.mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }));
    await w.find("input[type='search']").setValue("gloss");
    vi.advanceTimersByTime(300);
    client.search.mockResolvedValueOnce([hit("f1", "Style guide")]);
    await w.find("input[type='search']").setValue("style");
    vi.advanceTimersByTime(300);
    await flushPromises();
    finishOld([hit("f2", "Glossary")]);
    await flushPromises();
    expect(client.search).toHaveBeenCalledWith("style");
    expect(w.text()).toContain("Style guide");
    expect(w.text()).not.toContain("Glossary");
    await w.find("input[type='search']").setValue("");
    await flushPromises();
    expect(w.text()).toContain("Glossary");
  });

  it("shows New file only to a writer", async () => {
    expect((await mountIt(false)).text()).not.toContain("New file");
    wrapper?.unmount();
    expect((await mountIt(true)).text()).toContain("New file");
  });

  it("opens the dialog on a row click and reloads with a note after it is done", async () => {
    const w = await mountIt(true);
    await w.find("[data-file-id='f2']").trigger("click");
    expect(w.get("[data-test='file-dialog']").attributes("data-id")).toBe("f2");
    client.list.mockClear();
    await w.get("[data-test='finish']").trigger("click");
    await flushPromises();
    expect(w.find("[data-test='file-dialog']").exists()).toBe(false);
    expect(w.get("[role='status']").text()).toContain("Saved.");
    expect(client.list).toHaveBeenCalled();
  });

  it("shows the error and retries when the list cannot load", async () => {
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    const w = await mountIt();
    expect(w.text()).toContain("Storage is unavailable");
    await w.findAll("button").find((b) => b.text() === "Retry")!.trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Style guide");
  });

  it("clears everything when the account changes and ignores a late reply", async () => {
    const w = await mountIt();
    let late!: (value: { files: BrainFileRow[]; folders: string[] }) => void;
    client.list.mockReturnValueOnce(new Promise((resolve) => { late = resolve; }));
    await w.findAll("button").find((b) => b.text() === "team")!.trigger("click");
    useAuthStore().account = makeAccount({ id: 99, username: "other", email: "o@example.com" });
    late({ files: [row("x", "Leaked")], folders: [] });
    await flushPromises();
    expect(w.text()).not.toContain("Leaked");
    expect(w.text()).not.toContain("Style guide");
  });
});
```

The list rows must carry `data-file-id` (as `FileList.vue` does). The empty state must read "No files yet." and the error state's retry button "Retry"; adjust those two strings to what the shared `StateMessage` renders if they differ.

- [x] **Step 2: Run them and see them fail**

Run: `pnpm exec vitest run src/features/global/components`
Expected: FAIL (components missing).

- [x] **Step 3: Implement**

`GlobalFileDialog.vue`: script setup with `props`, `emit`; `BaseModal :open :title` ("Global file" or "New global file"), `v-if="open"` body. State: `loaded` (BrainFile | null), `loadError`, `title`, `body`, `folder`, `busy`, `error`, `confirmDelete`; a `run` counter dropped on close; `onBeforeUnmount` clears text. Computations: `cleanFolder = normalizeFolder(folder)`, `problem = folderProblem(cleanFolder)`, `tooLong = body.length > maxChars`, `changes` (only fields that differ from `loaded`: `title.trim()`, `body`, `cleanFolder`), `canSave = canWrite && (new ? title.trim() && !problem : changes nonEmpty && title.trim() && !problem) && !tooLong && !busy`. Save: `update(id, changes, loaded.revision)` or `create({title: title.trim(), body, folder: cleanFolder})`; on `ApiError` status 412 set `error` to `"This file changed since someone opened it. Close it and open it again."`, otherwise `errorMessage(err)`. Emit `done("Saved.")` / `done("Created.")` / `done("Deleted.")`. A reader's view is `<pre class="text">{{ loaded.body }}</pre>` with the folder and updated time in words. Problems render as `<p class="error problem" role="alert">` with the warning icon svg used by `ShareReview.vue` (copy it) followed by the words. Copy the style rules of `ShareReview.vue` (lines 140 to 162; rename `.review`), inputs 44px high, tokens only.

`GlobalFiles.vue`: script setup with `canWrite` prop, `useAuthStore`. State: `status` ("loading" | "ready" | "error"), `error`, `files`, `folders`, `folder` (string | null), `query`, `hits` (SearchHit[] | null), `searchError`, `opened` (`{ id: string | null } | null`), `note`, `maxChars` (from `globalClient.summary()` with `.catch(() => null)`, default 20000). `load()` uses a run counter; `watch(folder, load)`; `watch(query, ...)` with a 300 ms timer and a `searches` counter; `watch(() => auth.account?.id, clear, { flush: "sync" })`; `onBeforeUnmount(clear)`. Template: `SearchField` (label "Search global files"), folder buttons (`ListRow`-free: plain buttons with `aria-pressed`, min-height 44px), `StateMessage` for loading, error (with retry) and empty, then `ul` of `ListRow` rows (title, folder or "Top folder", `formatUtc(updated_at)`, characters), a "New file" button when `canWrite`, the note (`role="status"`), and `<GlobalFileDialog v-if="opened" :open="true" :file-id="opened.id" :can-write="canWrite" :max-chars="maxChars" @close="opened = null" @done="finished" />`. `finished(message)` sets `note`, closes the dialog and reloads.

- [x] **Step 4: Run the tests**

Run: `pnpm exec vitest run src/features/global src/radiusScale.test.ts src/architecture.test.ts` and `pnpm exec vue-tsc -b`
Expected: pass.

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/global
git commit -m "feat(ember): browse, search and edit global files"
```

---

### Task 3: Skills section

**Files:**
- Create: `components/GlobalSkills.vue` (+ test) under `apps/ember/src/features/global/`

**Interfaces:**
- Consumes: `globalClient.skills`, `allSkills`, `setSkillStatus`, `updateSkill`, `removeSkill`, `Skill`, `SkillStatus`, `SKILL_LIMITS`, `CharacterCount`, `ConfirmModal`, `BaseModal`, `StateMessage`.
- Produces: `GlobalSkills` with prop `{ canWrite: boolean }`. A reader sees the active skills (title, when to use, the steps in a `<details>`), nothing else. A writer sees three groups (Waiting for approval, Active, Retired) from `allSkills`, with per-skill buttons: Approve (proposed to active), Retire (active to retired), Send back for review (retired to proposed), Edit (a dialog with title, when to use, steps and tools, each with a `CharacterCount` and the `SKILL_LIMITS` maximum), Delete (confirm). A failing skill (`failing: true`) shows the words "Failing: agents are not offered it. Editing resets the counts." with an icon. A status change or edit replaces the row; errors show as `role="alert"` text; one action at a time (`busy`). Skill text is shown as plain text.

- [x] **Step 1: Write the failing tests**

Create `GlobalSkills.test.ts`:

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { Skill } from "../../skills/api/SkillsClient";
import { globalClient } from "../api/GlobalClient";
import GlobalSkills from "./GlobalSkills.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { skills: vi.fn(), allSkills: vi.fn(), setSkillStatus: vi.fn(), updateSkill: vi.fn(), removeSkill: vi.fn() },
}));
const client = vi.mocked(globalClient);

const skill = (id: number, title: string, status: Skill["status"], extra: Partial<Skill> = {}): Skill => ({
  id, title, when_to_use: `when ${title}`, steps: `steps of ${title}`, tools: "", status, successes: 0, failures: 0,
  created_at: "2026-01-01T00:00:00", failing: false, ...extra,
});

const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
let wrapper: VueWrapper | null = null;

async function mountIt(canWrite: boolean) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(GlobalSkills, { attachTo: document.body, props: { canWrite }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

beforeEach(() => {
  vi.clearAllMocks();
  client.skills.mockResolvedValue([skill(1, "Deploy", "active", { steps: "Use <i>care</i>" })]);
  client.allSkills.mockResolvedValue([skill(1, "Deploy", "active"), skill(2, "Backup", "proposed"), skill(3, "Old", "retired")]);
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalSkills", () => {
  it("shows a reader only the active skills, as plain text, with no controls", async () => {
    const w = await mountIt(false);
    expect(client.allSkills).not.toHaveBeenCalled();
    expect(w.text()).toContain("Deploy");
    expect(w.text()).toContain("when Deploy");
    expect(w.find("details pre").text()).toBe("Use <i>care</i>");
    expect(w.find("details pre i").exists()).toBe(false);
    for (const name of ["Approve", "Retire", "Send back for review", "Edit", "Delete"]) {
      expect(w.findAll("button").some((b) => b.text() === name)).toBe(false);
    }
  });

  it("shows a writer the three groups from the full list", async () => {
    const w = await mountIt(true);
    expect(client.skills).not.toHaveBeenCalled();
    const headings = w.findAll("h3").map((h) => h.text());
    expect(headings).toEqual(["Waiting for approval", "Active", "Retired"]);
    expect(w.text()).toContain("Backup");
    expect(w.text()).toContain("Old");
  });

  it("moves a skill between statuses with the right button", async () => {
    const w = await mountIt(true);
    client.setSkillStatus.mockImplementation(async (id, status) => skill(id, id === 2 ? "Backup" : id === 1 ? "Deploy" : "Old", status));
    await button(w, "Approve").trigger("click");
    await flushPromises();
    expect(client.setSkillStatus).toHaveBeenLastCalledWith(2, "active");
    await button(w, "Retire").trigger("click");
    await flushPromises();
    expect(client.setSkillStatus).toHaveBeenCalledWith(1, "retired");
    await button(w, "Send back for review").trigger("click");
    await flushPromises();
    expect(client.setSkillStatus).toHaveBeenCalledWith(3, "proposed");
  });

  it("edits a skill and sends the four fields", async () => {
    client.updateSkill.mockResolvedValue(skill(1, "Deploy", "active", { steps: "new steps" }));
    const w = await mountIt(true);
    await w.findAll("button").filter((b) => b.text() === "Edit")[0].trigger("click");
    await w.find("textarea[aria-label='Steps']").setValue("new steps");
    await button(w, "Save").trigger("click");
    await flushPromises();
    expect(client.updateSkill).toHaveBeenCalledWith(1, { title: "Deploy", when_to_use: "when Deploy", steps: "new steps", tools: "" });
    expect(w.text()).toContain("new steps");
  });

  it("refuses a field over its limit before sending", async () => {
    const w = await mountIt(true);
    await w.findAll("button").filter((b) => b.text() === "Edit")[0].trigger("click");
    await w.find("textarea[aria-label='Steps']").setValue("x".repeat(1201));
    expect(button(w, "Save").attributes("disabled")).toBeDefined();
    expect(client.updateSkill).not.toHaveBeenCalled();
  });

  it("deletes only after confirmation", async () => {
    client.removeSkill.mockResolvedValue(undefined);
    const w = await mountIt(true);
    await w.findAll("button").filter((b) => b.text() === "Delete")[0].trigger("click");
    expect(client.removeSkill).not.toHaveBeenCalled();
    await w.findAll("button").filter((b) => b.text() === "Delete").at(-1)!.trigger("click");
    await flushPromises();
    expect(client.removeSkill).toHaveBeenCalledTimes(1);
  });

  it("says in words that a failing skill is not offered", async () => {
    client.allSkills.mockResolvedValue([skill(1, "Flaky", "active", { failing: true, failures: 4 })]);
    const w = await mountIt(true);
    expect(w.text()).toContain("Failing: agents are not offered it. Editing resets the counts.");
  });

  it("shows an error and retries a failed load", async () => {
    client.skills.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    const w = await mountIt(false);
    expect(w.text()).toContain("Storage is unavailable");
    await button(w, "Retry").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Deploy");
  });

  it("shows the server's reason when an action is refused and keeps the row", async () => {
    client.setSkillStatus.mockRejectedValue(new ApiError(409, "You already have 50 active skills. Retire one first."));
    const w = await mountIt(true);
    await button(w, "Approve").trigger("click");
    await flushPromises();
    expect(w.get("[role='alert']").text()).toContain("You already have 50 active skills. Retire one first.");
    expect(w.text()).toContain("Backup");
  });
});
```

The edit dialog fields need the `aria-label`s Title, When to use, Steps, Tools (inputs or textareas as fits; the test uses `textarea` for Steps, so make Steps a textarea). Group headings are `h3`. If the delete confirmation's confirm button has another label, adjust the last lookup in the delete test (read `ConfirmModal.vue`).

- [x] **Step 2: Run and see them fail**

Run: `pnpm exec vitest run src/features/global/components/GlobalSkills.test.ts`
Expected: FAIL (component missing).

- [x] **Step 3: Implement**

`GlobalSkills.vue`: load with a run counter through `canWrite ? allSkills() : skills()`; groups computed as in `features/skills/SkillsView.vue` (copy the three group titles and hints, adapted: "Waiting for approval", "Active", "Retired"); for a reader show only one list headed "Active skills". `move(skill, status, done)` like `SkillsView.vue`'s `move`, using `globalClient.setSkillStatus`. Edit dialog: `BaseModal` with four fields bound to refs, `SKILL_LIMITS` as `:maxlength`, `CharacterCount` per field (read its props from `CharacterCount.vue`), Save disabled when any required field is empty or over its limit or nothing changed. Delete with `ConfirmModal` (`danger`). Sign-out clears state (`watch(() => auth.account?.id, clear, { flush: "sync" })`).

- [x] **Step 4: Run the tests**

Run: `pnpm exec vitest run src/features/global src/radiusScale.test.ts` and `pnpm exec vue-tsc -b`
Expected: pass.

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/global
git commit -m "feat(ember): global skills for everyone and for writers"
```

---

### Task 4: Review queue

**Files:**
- Create: `components/GlobalReview.vue` (+ test), `components/GlobalQueue.vue` (+ test) under `apps/ember/src/features/global/`

**Interfaces:**
- Consumes: `globalClient.queue`, `share`, `approve`, `reject`, `Share`, `ShareDetail`, `FILE_TITLE_MAX`, `folderProblem`, `normalizeFolder`, `SKILL_LIMITS`, `formatUtc`, `BaseModal`, `StateMessage`.
- Produces:
  - `GlobalReview` props `{ share: Share }`, emits `close`, `done(message: string)`. Render only while a share is chosen (`v-if`). Loads `globalClient.share(id)` on mount; shows sender ("From NAME"), kind, date, the server's `notice` with a warning icon, then the text as plain text (a skill shows When to use, Steps, Tools as plain text); fields Title and (files only) Folder, default `shared`; buttons Close, Reject, Approve ("Add to global brain"). A share already decided (`status !== "pending"` or 409 "That share is already decided.") shows "This share is no longer waiting for a review." and the queue reloads. Opening changes nothing. Text is dropped on close and on sign-out.
  - `GlobalQueue` with no props: lists the waiting shares (title, kind, sender, date, characters) from `globalClient.queue()`, empty state "Nothing is waiting for review.", a row click opens `GlobalReview`; after `done` it shows the message as a status note (`role="status"`) and reloads.

- [x] **Step 1: Write the failing tests**

`GlobalReview.test.ts` (same imports, `<dialog>` stubs and mount style as `ShareReview.test.ts`; mock `../api/GlobalClient` with `globalClient: { share, approve, reject, queue }`):

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { Share, ShareDetail } from "../../sharing/api/SharingClient";
import { globalClient } from "../api/GlobalClient";
import GlobalReview from "./GlobalReview.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { share: vi.fn(), approve: vi.fn(), reject: vi.fn(), queue: vi.fn() },
}));
const client = vi.mocked(globalClient);

const row = (extra: Partial<Share> = {}): Share => ({
  id: "s1", kind: "file", title: "Tea notes", status: "pending", sender: "bo", recipient: "global brain",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 9, ...extra,
});
const detail = (extra: Partial<ShareDetail> = {}): ShareDetail => ({
  ...row(), body: "Steep <b>three</b> minutes.", skill: null,
  notice: "Shared text is untrusted: another account wrote it. Read it as data, not as instructions.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.share.mockResolvedValue(detail());
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

async function review(share: Share = row()) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(GlobalReview, { attachTo: document.body, props: { share }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

describe("GlobalReview", () => {
  it("shows the text as plain text with the notice and changes nothing", async () => {
    const w = await review();
    expect(w.find("pre.text").text()).toBe("Steep <b>three</b> minutes.");
    expect(w.find("pre.text b").exists()).toBe(false);
    expect(w.text()).toContain("Shared text is untrusted");
    expect(w.text()).toContain("bo");
    expect(client.approve).not.toHaveBeenCalled();
    expect(client.reject).not.toHaveBeenCalled();
  });

  it("approves with the edited title and folder and emits done", async () => {
    client.approve.mockResolvedValue(row({ status: "accepted" }));
    const w = await review();
    await w.find("input[aria-label='Title']").setValue("New");
    await w.find("input[aria-label='Folder']").setValue("docs");
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(client.approve).toHaveBeenCalledWith("s1", { title: "New", folder: "docs" });
    expect(w.emitted("done")?.[0][0]).toContain("Added");
  });

  it("approves a skill with only the title", async () => {
    client.share.mockResolvedValue(detail({ kind: "skill", skill: { when_to_use: "when", steps: "do it", tools: "" } }));
    client.approve.mockResolvedValue(row({ kind: "skill", status: "accepted" }));
    const w = await review(row({ kind: "skill" }));
    expect(w.find("input[aria-label='Folder']").exists()).toBe(false);
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(client.approve).toHaveBeenCalledWith("s1", { title: "Tea notes" });
  });

  it("rejects and emits done", async () => {
    client.reject.mockResolvedValue(row({ status: "rejected" }));
    const w = await review();
    await button(w, "Reject").trigger("click");
    await flushPromises();
    expect(client.reject).toHaveBeenCalledWith("s1");
    expect(w.emitted("done")?.[0]).toEqual(["Rejected."]);
  });

  it("explains a bad folder in words and keeps Approve off", async () => {
    const w = await review();
    await w.find("input[aria-label='Folder']").setValue("a/b/c/d");
    expect(w.find("[role='alert']").text()).not.toBe("");
    expect(button(w, "Add to global brain").attributes("disabled")).toBeDefined();
  });

  it("says so when the share was already decided", async () => {
    client.approve.mockRejectedValue(new ApiError(409, "That share is already decided."));
    const w = await review();
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("This share is no longer waiting for a review.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("shows the server's reason when approving is refused and stays open", async () => {
    client.approve.mockRejectedValue(new ApiError(409, "Your long-term memory is full."));
    const w = await review();
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(w.find("[role='alert']").text()).toContain("Your long-term memory is full.");
    expect(w.emitted("done")).toBeUndefined();
  });
});
```

`GlobalReview` must give its fields the `aria-label`s Title and Folder, and the approve button the text "Add to global brain". For the "already decided" case it shows "This share is no longer waiting for a review." in a `role="status"` paragraph and no `role="alert"` duplicate of the server text.

`GlobalQueue.test.ts` (mock `../api/GlobalClient` with `queue`; stub `./GlobalReview.vue` with a component that has prop `share`, shows `share.title` and a button `data-test="finish"` that emits `done("Rejected.")`):

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { Share } from "../../sharing/api/SharingClient";
import { globalClient } from "../api/GlobalClient";
import GlobalQueue from "./GlobalQueue.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { queue: vi.fn() },
}));
vi.mock("./GlobalReview.vue", () => ({
  default: {
    props: ["share"],
    emits: ["close", "done"],
    template: '<div data-test="review">{{ share.title }}<button data-test="finish" @click="$emit(\'done\', \'Rejected.\')">finish</button></div>',
  },
}));
const client = vi.mocked(globalClient);

const share = (id: string, title: string): Share => ({
  id, kind: "file", title, status: "pending", sender: "bo", recipient: "global brain",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 9,
});

let wrapper: VueWrapper | null = null;
async function mountIt() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(GlobalQueue, { attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
beforeEach(() => {
  vi.clearAllMocks();
  client.queue.mockResolvedValue([share("s1", "Tea notes"), share("s2", "Metric units")]);
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalQueue", () => {
  it("lists what waits and says when nothing does", async () => {
    const w = await mountIt();
    expect(w.text()).toContain("Tea notes");
    expect(w.text()).toContain("Metric units");
    wrapper?.unmount();
    client.queue.mockResolvedValue([]);
    expect((await mountIt()).text()).toContain("Nothing is waiting for review.");
  });

  it("opens a review on a row click and reloads with a note after it is done", async () => {
    const w = await mountIt();
    await w.findAll("button").find((b) => b.text().includes("Metric units"))!.trigger("click");
    expect(w.get("[data-test='review']").text()).toContain("Metric units");
    client.queue.mockClear();
    client.queue.mockResolvedValue([share("s1", "Tea notes")]);
    await w.get("[data-test='finish']").trigger("click");
    await flushPromises();
    expect(w.find("[data-test='review']").exists()).toBe(false);
    expect(w.get("[role='status']").text()).toContain("Rejected.");
    expect(client.queue).toHaveBeenCalled();
    expect(w.text()).not.toContain("Metric units");
  });

  it("shows an error and retries", async () => {
    client.queue.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    const w = await mountIt();
    expect(w.text()).toContain("Storage is unavailable");
    await w.findAll("button").find((b) => b.text() === "Retry")!.trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Tea notes");
  });
});
```

- [x] **Step 2: Run and see them fail**

Run: `pnpm exec vitest run src/features/global/components/GlobalReview.test.ts src/features/global/components/GlobalQueue.test.ts`
Expected: FAIL.

- [x] **Step 3: Implement**

`GlobalReview.vue` follows `features/sharing/components/ShareReview.vue` closely (read it and copy its structure, loading, `closed` flag, `clear()`, account watch, `answer()` wrapper and styles) but calls `globalClient.share`, `approve`, `reject`; there is no Block button and no store. Approve builds the landing as in `ShareReview.keep()`: `{ title }` for a skill, `{ title, folder }` for a file. Done messages: "Added to the global brain." and "Rejected.". `GlobalQueue.vue` loads with a run counter, uses `ListRow`, `StateMessage`, and mounts `GlobalReview` with `v-if="reviewing"`.

- [x] **Step 4: Run the tests**

Run: `pnpm exec vitest run src/features/global src/radiusScale.test.ts src/architecture.test.ts` and `pnpm exec vue-tsc -b`
Expected: pass.

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/global
git commit -m "feat(ember): review the queue of shares sent to the global brain"
```

---

### Task 5: Page, route, nav entry and docs

**Files:**
- Create: `apps/ember/src/features/global/GlobalView.vue`, `GlobalView.test.ts`
- Modify: `apps/ember/src/router/index.ts`, `router/pages.ts`, the Ember tests that list the nav, Ember docs

**Interfaces:**
- Consumes: the three section components, `useAuthStore().hasPermission`, `GLOBAL_NOTICE`, `PageLayout`, `SegmentedControl`.
- Produces: route `/global` (name `global`, `meta.permission: "chat.use"`), nav entry `{ to: "/global", label: "Global", description: "The shared brain everyone and every agent can read: files and skills, reviewed by people who may write it.", permission: "chat.use" }` placed directly after "Shares", an icon of three paths (`"M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20"`, `"M2 12h20"`, `"M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"`). `GlobalView` shows the always-visible note, tabs Notes, Skills and (writers only) Review queue, and renders the chosen section with `:can-write`.

- [x] **Step 1: Write the failing tests**

`GlobalView.test.ts` (stub the three sections so the test needs no client mocks):

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../stores/auth";
import { makeAccount } from "../../testing/account";
import GlobalView from "./GlobalView.vue";

vi.mock("./components/GlobalFiles.vue", () => ({
  default: { props: ["canWrite"], template: '<div data-test="files">files {{ canWrite }}</div>' },
}));
vi.mock("./components/GlobalSkills.vue", () => ({
  default: { props: ["canWrite"], template: '<div data-test="skills">skills {{ canWrite }}</div>' },
}));
vi.mock("./components/GlobalQueue.vue", () => ({ default: { template: '<div data-test="queue">queue</div>' } }));

let wrapper: VueWrapper | null = null;
function mountIt(permissions: string[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.account = makeAccount({ permissions });
  wrapper = mount(GlobalView, { attachTo: document.body, global: { plugins: [pinia] } });
  return { w: wrapper, auth };
}
const tab = (w: VueWrapper, name: string) => w.findAll("[role='tab']").find((t) => t.text() === name);
afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalView", () => {
  it("always shows the notice, and a reader gets the notes and skills tabs only", async () => {
    const { w } = mountIt(["chat.use"]);
    await flushPromises();
    expect(w.text()).toContain("Everyone on this instance, and every agent, can read this. Do not put private data here.");
    expect(w.findAll("[role='tab']").map((t) => t.text())).toEqual(["Notes", "Skills"]);
    expect(w.get("[data-test='files']").text()).toBe("files false");
    await tab(w, "Skills")!.trigger("click");
    expect(w.get("[data-test='skills']").text()).toBe("skills false");
  });

  it("shows the review queue tab to a writer and switches sections", async () => {
    const { w } = mountIt(["chat.use", "brain.global.write"]);
    await flushPromises();
    expect(w.findAll("[role='tab']").map((t) => t.text())).toEqual(["Notes", "Skills", "Review queue"]);
    expect(w.get("[data-test='files']").text()).toBe("files true");
    await tab(w, "Review queue")!.trigger("click");
    expect(w.find("[data-test='queue']").exists()).toBe(true);
    await tab(w, "Skills")!.trigger("click");
    expect(w.get("[data-test='skills']").text()).toBe("skills true");
  });

  it("falls back to the notes tab when the writer permission is lost", async () => {
    const { w, auth } = mountIt(["chat.use", "brain.global.write"]);
    await flushPromises();
    await tab(w, "Review queue")!.trigger("click");
    auth.account = makeAccount({ permissions: ["chat.use"] });
    await flushPromises();
    expect(w.find("[data-test='queue']").exists()).toBe(false);
    expect(w.find("[data-test='files']").exists()).toBe(true);
    expect(tab(w, "Review queue")).toBeUndefined();
  });
});
```

If `makeAccount` takes the permissions differently (read `testing/account.ts`), adapt the helper in this test. The tabs come from `SegmentedControl` in `mode="tabs"`, whose buttons carry `role="tab"` (assumption f). If the page needs the router (a `RouterLink` in `PageLayout`), add a stub router or the `RouterLink` stub the other page tests use.

Update the tests that list the nav (NavRail, AccountView, SidebarEditor, Overview tests and any other `grep -rn '"Shares"' src --include=*.test.ts` hit): add "Global" directly after "Shares" in every expected nav list and fixture list. Do not weaken them.

- [x] **Step 2: Run them and see them fail**

Run: `pnpm exec vitest run src/features/global/GlobalView.test.ts src/components/layout/NavRail.test.ts src/features/account src/features/settings src/features/overview`
Expected: FAIL (page missing; nav lists expect "Global").

- [x] **Step 3: Implement**

Create `GlobalView.vue` with `PageLayout` (`title="Global brain"`, description "Files and skills everyone on this instance and every agent can read."), the note `<p class="notice" role="note">` with the warning icon and `GLOBAL_NOTICE`, `SegmentedControl` (`mode="tabs"`, options built from `canWrite`), and the section with `role="tabpanel"` wiring from assumption (f). A `watch` on `canWrite` resets the tab to `notes` when the writer tab disappears. Add the route in `router/index.ts` after `/shares` (lazy import) and the entry in `router/pages.ts`. Update Ember docs only where they list pages (grep the README and `AGENTS.md` for "Shares").

- [x] **Step 4: Run all checks**

Run: `pnpm exec vitest run src/features/global src/router src/components src/features/account src/features/settings src/features/overview src/radiusScale.test.ts src/architecture.test.ts`, then `pnpm exec vue-tsc -b` and `pnpm test`.
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add apps/ember
git commit -m "feat(ember): Global brain page, route and nav entry"
```

---

## Final checks

- [x] Record the Ember counts against the baseline.
- [x] Roadmap row 20k links this plan: `[Written](2026-11-21-plan-20k-ember-global-brain.md)`.

## Manual checklist (the user runs these; do not claim them done)

- [ ] As a normal account: the nav has "Global". The page shows the notice, Notes and Skills tabs, no Review queue tab, no New file or edit controls. Search finds a global file; opening it shows plain text.
- [ ] As an account with `brain.global.write`: New file creates a global file (a second account then sees it); editing sends only what changed; a stale save says the file changed; delete asks first.
- [ ] Global skills: the writer sees three groups and can approve, retire, send back, edit and delete; the normal account sees only active skills.
- [ ] Share a file to the global brain from the Notes page as a normal account; the writer sees it in the Review queue, approves it with a new title and folder, and it appears in Notes (global). Reject another one.
- [ ] 768px, 767px and 375px, light and dark: inputs 44px high, tabs usable, dialogs fit.

## Self-review (writer)

- Row 20k: browse and search files and skills for everyone (Tasks 2 and 3), write and edit with `brain.global.write` (Tasks 2 and 3), review the incoming queue (Task 4), page and nav (Task 5). Front end only.
- Placeholders: only the Baseline blank. Every test is written out; component implementations in Tasks 2 to 5 are described with the exact props, emits, aria-labels, texts and calls the tests rely on, and name the existing files to copy structure and styles from (`ShareReview.vue`, `SkillsView.vue`, `NotesView.vue`).
- Type names match: `globalClient`, `GLOBAL_NOTICE`, `GlobalFileDraft`, `GlobalFileChanges`, `GlobalSummary`, `GlobalFileDialog`, `GlobalFiles`, `GlobalSkills`, `GlobalReview`, `GlobalQueue`, `GlobalView`.

## Changes found during work

(The executor records here every change to a snippet, the result of assumptions a to f, and anything not verified.)
- (a) Matched all global route methods and paths in Portcullis and Stronghold.
- (b) Matched shared row/full serializers and notice on file create/update. Global create defaults to actor=user, so no revert copy.
- (c) `brainClient.list` now takes no folder. Stronghold's global query parameter is `folder`, so retained encoded `?folder=` as specified. Confirmed 204 and ApiError handling.
- File-list retry test uses the shared StateMessage button label, Try again.
- Skills retry test uses the shared StateMessage label, Try again. Skills search filters loaded text locally.
- Status and edit tests now select the named skill, because multiple rows can have the same action.
- Review and queue fixtures grant brain.global.write to match production guards. Queue retry uses Try again. The review emits a decided event to refresh the open queue immediately.
- Added a regression test for preview lifetime. Same-account refresh preserves it; account changes drop it.
- (d) Confirmed hasPermission reads account.permissions, verifies email status, and Portcullis includes the writer permission in the admin role. makeAccount accepts permission overrides.
- (e) Main was at 8205ac13. Plan 20j was absent; retained Memory and inserted Global after Shares. Existing nav expectations changed in NavRail, AccountView, SidebarEditor, and OverviewView tests.
- (f) Confirmed matching tab and panel IDs from SegmentedControl and PdfMergerView. Files and visited Skills keep their local state across tab changes, and approval invalidates only the affected list.
- The roadmap link already exists in the original checkout as a local edit; it was not duplicated in the feature worktree. The Ember README describes Global after Shares.
- Two NavRail tests assert the total item count after loading. Updated 8 to 9 for Global. Added tab/panel association and post-approval refresh coverage.
- Stronghold caveat: manual global files have no revert copy. An approved shared file has source=shared, so its first content edit can save a server-side original. Global routes expose no revert endpoint. Skill shares land as proposed and still need approval in Skills. No Portcullis route gap found.
- Task 1, 0e07216d: client suite 5 passed. Type-check passed.
- Task 2, 97d4f387: feature, radius and architecture checks 34 passed. Type-check passed.
- Task 3, 420b752a: feature and radius checks 33 passed. Type-check passed.
- Task 4, aa97d482: feature, radius and architecture checks 54 passed. Type-check passed.
- Task 5, aee1131b: scoped checks 378 passed. Full suite 204 files and 2,403 tests passed (+7 files, +43 tests versus baseline). Type-check and Git diff checks passed.
- Pending: all manual checklist steps, including a real Stronghold review queue, two accounts, light/dark layouts at 768px, 767px and 375px, and a phone keyboard.
