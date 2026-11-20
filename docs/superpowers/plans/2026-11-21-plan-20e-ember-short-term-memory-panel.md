# Ember Short-Term Memory Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Memory" control in the chat header of the Ember Windows app that shows a chat's short-term memory (the items agents and the user saved for this chat), lets the user pin, unpin, remove and add items, warns when the stack is nearly full or full, and compacts it on demand.

**Architecture:** The backend already exists (Plan 20a): Portcullis serves `GET /api/chats/{id}/stack`, `POST .../items`, `PUT .../items/{item}`, `DELETE .../items/{item}` and `POST .../compact`. This plan adds only front end in `apps/ember`: a thin API client, a Pinia store that keeps the active chat's stack and ignores late replies, a presentational `StackPanel` (list, warning, Compact, add form) and a `StackMenu` (header button plus a non-modal popover that is a bottom sheet below 768px) wired into `ChatHeader` and `ChatView`. Every change waits for the server's answer before the screen shows it.

**Tech Stack:** Vue 3 + TypeScript, Pinia, Vitest and `@vue/test-utils`, Tauri shell (untouched).

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, section "Brain (Stronghold)", short-term memory ("Near full, the user is warned that it needs compaction; it compacts on the next prompt, or the user compacts manually. Overflow drops the oldest item and keeps pinned ones."). Roadmap row 20e. Backend: `docs/superpowers/plans/2026-11-20-plan-20a-stronghold-mcp-short-term-memory.md`. UI rules: `.agents/skills/ember-frontend-design/SKILL.md`, `mobile-ui.md` and `.agents/skills/ember-design-system/SKILL.md` (read all three before Task 3).

## Global Constraints

- Work only in `apps/ember` (the Windows app). `apps/ember_web` is reference only; do not copy anything there. No backend, Portcullis, Stronghold or Legion change.
- Never call `fetch` or build an `/api` URL by hand outside `apiRequest` (`src/api/http.ts`). The client uses `apiRequest` only.
- Radius only through `--radius-*` tokens, colour only through tokens, no hex and no literal radius (`radiusScale.test.ts` fails on one). Never add a reduced-motion setting, media query or test. Animations always play.
- Reuse the shared pieces: `StateMessage` for loading, load-error and empty; the global `pill-btn primary` and `pill-btn ghost` classes; `useOutsideClose`; `useNarrow`; `ActionButton` conventions. Do not write a page-local `.empty`, `.load-error` or counter style.
- A change that calls the server stays pending until the server answers; never show unconfirmed state. Status uses an icon plus text, never colour alone.
- Hit areas of at least 44 by 44 CSS px on touch (below 768px) for the pin and remove buttons and the header button; visible focus ring (`:focus-visible` from `style.css`); every icon-only control has an `aria-label`.
- The popover is not a modal: no focus trap, no scroll lock. Esc closes it and returns focus to its button; a press outside closes it. Below 768px it is a sheet anchored with `bottom: var(--rail-height)`.
- Private content (the items) is cleared when the chat changes, when the control unmounts and when the account signs out; a late reply for another chat must never show.
- Item text never goes into a console message, an error message built by this code, a test name or a snapshot.
- Use `pnpm` (not npm). No new dependency. Keep each file's line endings.

---

## File Map

All paths under `apps/ember/src/features/chat/` unless noted.

- Create `api/StackClient.ts` and `api/StackClient.test.ts`.
- Create `stores/stack.ts` and `stores/stack.test.ts`.
- Create `components/StackPanel.vue` and `components/StackPanel.test.ts`.
- Create `components/StackMenu.vue` and `components/StackMenu.test.ts`.
- Modify `components/ChatHeader.vue` and `components/ChatHeader.test.ts` (new optional prop `chatId`).
- Modify `views/ChatView.vue` (pass `:chat-id="activeId"`).
- Modify `apps/ember/README.md` only if it lists chat features (grep first; skip and say so if not).
- Roadmap row 20e.

## Assumptions to check at build time (record each result under "Changes found during work")

- (a) `activeId` in `ChatView.vue` is the same chat id Portcullis and Stronghold know, and a chat exists on the server once it has messages (the stack routes answer 404 for a chat that is not saved yet). Read `chat.ts`, `ConversationStorage.ts` and how the first turn creates a chat.
- (b) `apiRequest` resolves with `undefined` for a 204 answer (the DELETE route) and throws `ApiError` with the server's `detail` as `message` for 4xx and 5xx; read the rest of `src/api/http.ts`.
- (c) The usage-limit refusal of `POST .../compact` (Stronghold `limit_reached`) arrives as an `ApiError` whose `message` is readable text; find its status and detail text (grep `limit_reached` in `apps/stronghold/src/usage/limits.py`).
- (d) `pill-btn`, `pill-btn primary`, `pill-btn ghost`, `link-btn`, `sr-only` and the global `button[aria-busy="true"]` spinner exist in `src/style.css`; `--rail-height`, `--danger`, `--warning`, `--code-bg`, `--accent` exist.
- (e) `architecture.test.ts` and `radiusScale.test.ts` rules (what they forbid) so new files comply on the first run.
- (f) How `ChatHeader.test.ts` mounts the header (props, Pinia) so adding `StackMenu` inside it does not break the existing tests; `StackMenu` must render nothing without a `chatId`.
- (g) `useNarrow()` returns a ref that flips at 768px (the plan's CSS uses a `max-width: 767px` media query instead, so it is only needed if you teleport the sheet); `CharacterCount` is not needed (the server's per-item character cap is not in the stack view). The installed Vue version is 3.5 or later (`useId` in `StackPanel.vue`); if not, build the id by hand.
- (h) The `busy` and `working` refs in `ChatView.vue` (`locked = busy || !!working`) are true for the whole time an answer is being written, including agent steps.

## Baseline

- `pnpm exec vue-tsc -b` passed.
- `pnpm test` passed: 183 files, 2,227 tests, zero failures.
- Both commands ran in the Plan 20e worktree under `apps/ember`, using the main checkout’s installed dependencies (matching lockfile). The registry was unavailable, so pnpm’s dependency recheck was disabled per command with `--config.verify-deps-before-run=false`.

---

### Task 1: Stack API client

**Files:**
- Create: `apps/ember/src/features/chat/api/StackClient.ts`
- Test: `apps/ember/src/features/chat/api/StackClient.test.ts`

**Interfaces:**
- Consumes: `apiRequest(method, path, body?)` (`src/api/http.ts`).
- Produces: types `StackItem { id: number; text: string; pinned: boolean; source: string; at: string }`, `StackView { items: StackItem[]; used: number; limit: number; warn: boolean; full: boolean }`, `CompactResult extends StackView { compacted: boolean; replaced: number }`; `stackClient` with `view(chatId)`, `add(chatId, text, pinned?)`, `setPinned(chatId, itemId, pinned)`, `remove(chatId, itemId)`, `compact(chatId)`.

- [x] **Step 1: Write the failing test**

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { stackClient } from "./StackClient";
import { apiRequest } from "../../../api/http";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("stackClient", () => {
  it("reads a chat's stack", async () => {
    await stackClient.view("c-1");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/chats/c-1/stack");
  });

  it("adds an item, pinned only when asked", async () => {
    await stackClient.add("c-1", "I live in Paris");
    await stackClient.add("c-1", "Never email Bo", true);
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/chats/c-1/stack/items", { text: "I live in Paris", pinned: false });
    expect(request).toHaveBeenNthCalledWith(2, "POST", "/api/chats/c-1/stack/items", { text: "Never email Bo", pinned: true });
  });

  it("pins, unpins and removes one item", async () => {
    await stackClient.setPinned("c-1", 3, true);
    await stackClient.remove("c-1", 3);
    expect(request).toHaveBeenNthCalledWith(1, "PUT", "/api/chats/c-1/stack/items/3", { pinned: true });
    expect(request).toHaveBeenNthCalledWith(2, "DELETE", "/api/chats/c-1/stack/items/3");
  });

  it("compacts with a bodiless POST", async () => {
    await stackClient.compact("c-1");
    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/chats/c-1/stack/compact");
  });

  it("encodes a chat id so it cannot change the path", async () => {
    await stackClient.view("a/../b");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/chats/a%2F..%2Fb/stack");
  });
});
```

- [x] **Step 2: Run to see it fail**

Run (from `apps/ember`): `pnpm exec vitest run src/features/chat/api/StackClient.test.ts`
Expected: cannot find `./StackClient`.

- [x] **Step 3: Write `StackClient.ts`**

```ts
import { apiRequest } from "../../../api/http";

/** One short fact in a chat's short-term memory. `source` is `user`, `agent` or `compaction` (a summary of older items). */
export interface StackItem {
  id: number;
  text: string;
  pinned: boolean;
  source: string;
  at: string;
}

/** A chat's stack and how full it is. `warn` is on from 80% (the server decides); `full` when no free slot is left. */
export interface StackView {
  items: StackItem[];
  used: number;
  limit: number;
  warn: boolean;
  full: boolean;
}

/** What compacting answers: `compacted` is false when there was nothing to replace. */
export interface CompactResult extends StackView {
  compacted: boolean;
  replaced: number;
}

const base = (chatId: string): string => `/api/chats/${encodeURIComponent(chatId)}/stack`;

export const stackClient = {
  view: (chatId: string) => apiRequest<StackView>("GET", base(chatId)),
  add: (chatId: string, text: string, pinned = false) => apiRequest<StackItem>("POST", `${base(chatId)}/items`, { text, pinned }),
  setPinned: (chatId: string, itemId: number, pinned: boolean) => apiRequest<StackItem>("PUT", `${base(chatId)}/items/${itemId}`, { pinned }),
  remove: (chatId: string, itemId: number) => apiRequest<void>("DELETE", `${base(chatId)}/items/${itemId}`),
  compact: (chatId: string) => apiRequest<CompactResult>("POST", `${base(chatId)}/compact`),
};
```

- [x] **Step 4: Run, then commit**

Run: `pnpm exec vitest run src/features/chat/api/StackClient.test.ts` (pass), `pnpm exec vue-tsc -b`.

```bash
git add apps/ember/src/features/chat/api
git commit -m "feat(ember): API client for a chat's short-term memory"
```

(Add the `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` line to every commit.)

---

### Task 2: Stack store

**Files:**
- Create: `apps/ember/src/features/chat/stores/stack.ts`
- Test: `apps/ember/src/features/chat/stores/stack.test.ts`

**Interfaces:**
- Consumes: `stackClient` and its types (Task 1); `ApiError`, `isApiStatus` (`src/api/http.ts`); `useAuthStore` (`src/stores/auth.ts`).
- Produces: `useStackStore()` (setup store, id `"stack"`) with
  - `entry(chatId): StackEntry` where `StackEntry = { status: "idle" | "loading" | "ready" | "missing" | "error"; view: StackView | null; error: string; addError: string; pending: boolean; compacting: boolean; notice: string }` (a readonly snapshot; an unknown chat gives the idle entry);
  - `load(chatId: string): Promise<void>` (keeps the current view on screen while it refreshes; a late reply for an older call is dropped; 404 gives `missing`; other errors keep the old view and set `error`, or `status "error"` when there is no view);
  - `add(chatId, text): Promise<boolean>` (true on success; on failure sets `addError` with the server's message and keeps nothing else changed);
  - `setPinned(chatId, itemId, pinned): Promise<void>`, `remove(chatId, itemId): Promise<void>` (failures set `error`);
  - `compact(chatId): Promise<void>` (sets `compacting` while it waits, then `view` from the answer and `notice`; a failure sets `error`);
  - `forget(chatId): void` (drops the entry and invalidates its pending replies).
  - Every successful change ends by reloading the view (`load`), so the screen always shows the server's list.
  - Notice texts: compacted: `Replaced N items with a summary.` (`1 item` for one); not compacted: `Nothing to compact.`
  - The store forgets everything when the account signs out (`auth.account` becomes `null`).

- [x] **Step 1: Write the failing test**

```ts
import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { stackClient, type StackItem, type StackView } from "../api/StackClient";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { useStackStore } from "./stack";

vi.mock("../api/StackClient", () => ({
  stackClient: { view: vi.fn(), add: vi.fn(), setPinned: vi.fn(), remove: vi.fn(), compact: vi.fn() },
}));

const client = vi.mocked(stackClient);

const item = (id: number, text = `item ${id}`, pinned = false): StackItem => ({ id, text, pinned, source: "agent", at: "2026-01-01T00:00:00Z" });
const view = (...items: StackItem[]): StackView => ({ items, used: items.length, limit: 40, warn: false, full: false });

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useStackStore() };
}

beforeEach(() => {
  vi.clearAllMocks();
  client.view.mockResolvedValue(view(item(1), item(2)));
});

describe("load", () => {
  it("shows the server's list", async () => {
    const { store } = setup();
    expect(store.entry("c-1").status).toBe("idle");
    const loading = store.load("c-1");
    expect(store.entry("c-1").status).toBe("loading");
    await loading;
    const shown = store.entry("c-1");
    expect(shown.status).toBe("ready");
    expect(shown.view?.items.map((i) => i.id)).toEqual([1, 2]);
  });

  it("a chat that is not saved yet is missing, not an error", async () => {
    const { store } = setup();
    client.view.mockRejectedValue(new ApiError(404, "No such chat."));
    await store.load("c-1");
    expect(store.entry("c-1")).toMatchObject({ status: "missing", view: null, error: "" });
  });

  it("an error with nothing to show is an error state with the server's text", async () => {
    const { store } = setup();
    client.view.mockRejectedValue(new ApiError(503, "Storage is unavailable"));
    await store.load("c-1");
    expect(store.entry("c-1")).toMatchObject({ status: "error", view: null, error: "Storage is unavailable" });
  });

  it("a refresh that fails keeps the list on screen and says so", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.view.mockRejectedValue(new ApiError(503, "Storage is unavailable"));
    await store.load("c-1");
    const shown = store.entry("c-1");
    expect(shown.status).toBe("ready");
    expect(shown.view?.items).toHaveLength(2);
    expect(shown.error).toBe("Storage is unavailable");
  });

  it("drops a late reply when a newer load has started", async () => {
    const { store } = setup();
    let first!: (v: StackView) => void;
    client.view.mockImplementationOnce(() => new Promise<StackView>((resolve) => { first = resolve; }));
    const slow = store.load("c-1");
    client.view.mockResolvedValueOnce(view(item(9, "newer")));
    await store.load("c-1");
    first(view(item(1, "older")));
    await slow;
    expect(store.entry("c-1").view?.items.map((i) => i.text)).toEqual(["newer"]);
  });

  it("a reply that arrives after forget is not shown", async () => {
    const { store } = setup();
    let reply!: (v: StackView) => void;
    client.view.mockImplementationOnce(() => new Promise<StackView>((resolve) => { reply = resolve; }));
    const pending = store.load("c-1");
    store.forget("c-1");
    reply(view(item(1, "private")));
    await pending;
    expect(store.entry("c-1")).toMatchObject({ status: "idle", view: null });
  });
});

describe("changes", () => {
  it("add waits for the server, then shows the reloaded list", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.add.mockResolvedValue(item(3, "new"));
    client.view.mockResolvedValue(view(item(1), item(2), item(3, "new")));
    expect(await store.add("c-1", "new")).toBe(true);
    expect(client.add).toHaveBeenCalledWith("c-1", "new");
    expect(store.entry("c-1").view?.items).toHaveLength(3);
    expect(store.entry("c-1").pending).toBe(false);
  });

  it("a refused add keeps the list and puts the server's reason beside the field", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.add.mockRejectedValue(new ApiError(422, "An item holds at most 500 characters."));
    expect(await store.add("c-1", "x")).toBe(false);
    const shown = store.entry("c-1");
    expect(shown.addError).toBe("An item holds at most 500 characters.");
    expect(shown.view?.items).toHaveLength(2);
    await store.add("c-1", "y");
    client.add.mockResolvedValue(item(3));
    await store.add("c-1", "ok");
    expect(store.entry("c-1").addError).toBe("");
  });

  it("is pending while it waits", async () => {
    const { store } = setup();
    await store.load("c-1");
    let done!: () => void;
    client.setPinned.mockImplementation(() => new Promise((resolve) => { done = () => resolve(item(1, "x", true)); }));
    const waiting = store.setPinned("c-1", 1, true);
    expect(store.entry("c-1").pending).toBe(true);
    done();
    await waiting;
    expect(store.entry("c-1").pending).toBe(false);
  });

  it("pin and remove reload; a failure shows the reason and keeps the list", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.setPinned.mockResolvedValue(item(1, "x", true));
    client.remove.mockResolvedValue(undefined);
    await store.setPinned("c-1", 1, true);
    await store.remove("c-1", 2);
    expect(client.setPinned).toHaveBeenCalledWith("c-1", 1, true);
    expect(client.remove).toHaveBeenCalledWith("c-1", 2);
    expect(client.view).toHaveBeenCalledTimes(3);
    client.remove.mockRejectedValue(new ApiError(404, "No such item in this stack."));
    await store.remove("c-1", 2);
    expect(store.entry("c-1").error).toBe("No such item in this stack.");
  });
});

describe("compact", () => {
  it("shows the summary result", async () => {
    const { store } = setup();
    await store.load("c-1");
    let done!: (r: StackView & { compacted: boolean; replaced: number }) => void;
    client.compact.mockImplementation(() => new Promise((resolve) => { done = resolve; }));
    const waiting = store.compact("c-1");
    expect(store.entry("c-1").compacting).toBe(true);
    done({ ...view(item(5, "summary")), compacted: true, replaced: 8 });
    await waiting;
    const shown = store.entry("c-1");
    expect(shown).toMatchObject({ compacting: false, notice: "Replaced 8 items with a summary." });
    expect(shown.view?.items.map((i) => i.id)).toEqual([5]);
  });

  it("says so when there was nothing to compact, and uses the singular", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.compact.mockResolvedValue({ ...view(item(1)), compacted: false, replaced: 0 });
    await store.compact("c-1");
    expect(store.entry("c-1").notice).toBe("Nothing to compact.");
    client.compact.mockResolvedValue({ ...view(item(5)), compacted: true, replaced: 1 });
    await store.compact("c-1");
    expect(store.entry("c-1").notice).toBe("Replaced 1 item with a summary.");
  });

  it("a failed compaction shows the server's reason and keeps the list", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.compact.mockRejectedValue(new ApiError(502, "The context summarizer did not answer."));
    await store.compact("c-1");
    const shown = store.entry("c-1");
    expect(shown.error).toBe("The context summarizer did not answer.");
    expect(shown.compacting).toBe(false);
    expect(shown.view?.items).toHaveLength(2);
  });

  it("the next change clears an old notice", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.compact.mockResolvedValue({ ...view(item(5)), compacted: true, replaced: 3 });
    await store.compact("c-1");
    client.remove.mockResolvedValue(undefined);
    await store.remove("c-1", 5);
    expect(store.entry("c-1").notice).toBe("");
  });
});

describe("privacy", () => {
  it("forget drops the chat and signing out drops everything", async () => {
    const { auth, store } = setup();
    await store.load("c-1");
    await store.load("c-2");
    store.forget("c-1");
    expect(store.entry("c-1").view).toBeNull();
    expect(store.entry("c-2").view).not.toBeNull();
    auth.account = null;
    await flushPromises();
    expect(store.entry("c-2").view).toBeNull();
  });
});
```

- [x] **Step 2: Run to see it fail**

Run: `pnpm exec vitest run src/features/chat/stores/stack.test.ts`
Expected: cannot find `./stack`.

- [x] **Step 3: Write `stores/stack.ts`**

```ts
import { defineStore } from "pinia";
import { reactive, watch } from "vue";
import { ApiError, isApiStatus } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { stackClient, type CompactResult, type StackView } from "../api/StackClient";

export interface StackEntry {
  status: "idle" | "loading" | "ready" | "missing" | "error";
  view: StackView | null;
  /** The last load or change that failed (shown beside the list). */
  error: string;
  /** The last refused add (shown beside the field). */
  addError: string;
  /** A change is waiting for the server. */
  pending: boolean;
  compacting: boolean;
  /** What the last compaction did. */
  notice: string;
}

const idle = (): StackEntry => ({ status: "idle", view: null, error: "", addError: "", pending: false, compacting: false, notice: "" });
const FAILED = "Memory is unavailable right now.";

const reason = (error: unknown): string => (error instanceof ApiError && error.message ? error.message : FAILED);

function noticeOf(result: CompactResult): string {
  if (!result.compacted) return "Nothing to compact.";
  return `Replaced ${result.replaced} ${result.replaced === 1 ? "item" : "items"} with a summary.`;
}

/** The active chat's short-term memory, as the server holds it. Items are private: an entry is dropped when its chat
 * is left, and a reply that arrives after that (or after a newer load) is ignored. */
export const useStackStore = defineStore("stack", () => {
  const entries = reactive<Record<string, StackEntry>>({});
  const latest = new Map<string, number>();
  let counter = 0;

  // Always return the reactive entry (`??=` would return the raw object the first time, and the identity checks below would fail).
  const own = (chatId: string): StackEntry => {
    if (!entries[chatId]) entries[chatId] = idle();
    return entries[chatId]!;
  };
  const entry = (chatId: string): StackEntry => entries[chatId] ?? idle();

  async function load(chatId: string): Promise<void> {
    const current = own(chatId);
    const token = ++counter;
    latest.set(chatId, token);
    if (!current.view) current.status = "loading";
    try {
      const view = await stackClient.view(chatId);
      if (latest.get(chatId) !== token) return;
      Object.assign(current, { view, status: "ready", error: "" });
    } catch (error) {
      if (latest.get(chatId) !== token) return;
      if (isApiStatus(error, 404)) Object.assign(current, { view: null, status: "missing", error: "" });
      else Object.assign(current, { status: current.view ? "ready" : "error", error: reason(error) });
    }
  }

  async function change(chatId: string, work: () => Promise<unknown>, onError: (message: string) => void): Promise<boolean> {
    const current = own(chatId);
    current.pending = true;
    current.notice = "";
    try {
      await work();
    } catch (error) {
      if (entries[chatId] === current) {
        onError(reason(error));
        current.pending = false;
      }
      return false;
    }
    if (entries[chatId] === current) {
      current.pending = false;
      await load(chatId);
    }
    return true;
  }

  async function add(chatId: string, text: string): Promise<boolean> {
    const current = own(chatId);
    current.addError = "";
    return change(chatId, () => stackClient.add(chatId, text), (message) => { current.addError = message; });
  }

  async function setPinned(chatId: string, itemId: number, pinned: boolean): Promise<void> {
    const current = own(chatId);
    current.error = "";
    await change(chatId, () => stackClient.setPinned(chatId, itemId, pinned), (message) => { current.error = message; });
  }

  async function remove(chatId: string, itemId: number): Promise<void> {
    const current = own(chatId);
    current.error = "";
    await change(chatId, () => stackClient.remove(chatId, itemId), (message) => { current.error = message; });
  }

  async function compact(chatId: string): Promise<void> {
    const current = own(chatId);
    current.error = "";
    current.notice = "";
    current.compacting = true;
    try {
      const result = await stackClient.compact(chatId);
      if (entries[chatId] !== current) return;
      latest.set(chatId, ++counter); // this answer is newer than any load still on its way
      Object.assign(current, { view: result, status: "ready", notice: noticeOf(result) });
    } catch (error) {
      if (entries[chatId] === current) current.error = reason(error);
    } finally {
      current.compacting = false;
    }
  }

  function forget(chatId: string): void {
    delete entries[chatId];
    latest.delete(chatId);
  }

  function forgetAll(): void {
    for (const chatId of Object.keys(entries)) forget(chatId);
  }

  const auth = useAuthStore();
  watch(() => auth.account, (account) => { if (!account) forgetAll(); });

  return { entry, load, add, setPinned, remove, compact, forget };
});
```

- [x] **Step 4: Run, then commit**

Run: `pnpm exec vitest run src/features/chat/stores/stack.test.ts`, `pnpm exec vue-tsc -b`. If a test fails because of how Pinia unwraps a returned function or reactive entry, fix the store, not the rule the test states (late replies never show, pending until the server answers).

```bash
git add apps/ember/src/features/chat/stores
git commit -m "feat(ember): store for a chat's short-term memory with late replies ignored"
```

---

### Task 3: The panel

**Files:**
- Create: `apps/ember/src/features/chat/components/StackPanel.vue`
- Test: `apps/ember/src/features/chat/components/StackPanel.test.ts`

**Interfaces:**
- Consumes: `StackEntry`-shaped data and `StackView` (Tasks 1 and 2), `StateMessage`.
- Produces: `StackPanel` with props `status` (`"loading" | "ready" | "missing" | "error"`), `view: StackView | null`, `error: string`, `addError: string`, `pending: boolean`, `compacting: boolean`, `notice: string`, `locked: boolean` (an answer is being written); emits `add(text: string)`, `pin(id: number, pinned: boolean)`, `remove(id: number)`, `compact()`, `retry()`; exposes `clearDraft()`. Pure presentation: it never calls the store or the client.

Read the three UI skills before writing CSS. The component follows these rules (they are what the tests pin):

- Root `div.stack-panel` with `role="dialog"`, `aria-label="Short-term memory"`, `data-test="stack-panel"`.
- Loading: `StateMessage kind="loading"` ("Loading memory"). Load error with no view: `StateMessage kind="error"` with the `error` text and `@retry`. `missing`: `StateMessage kind="empty"` titled "Not saved yet", text "Send a message first. Short-term memory is kept once the chat is saved."
- With a view: a summary line `"<used> of <limit> items"` with a thin progress bar (`role="progressbar"`, `aria-valuenow`, `aria-valuemax`); when `view.full`, a status line `data-test="stack-full"` with an icon and the text "Full. Adding an item drops the oldest unpinned one."; when `view.warn` and not full, `data-test="stack-warn"` with an icon and "Nearly full. It is compacted when you send your next message, or compact it now."; both have `role="status"`.
- A "Compact now" button (`pill-btn ghost`, `data-test="compact"`), `aria-busy` while `compacting`, disabled while `compacting`, `pending`, `locked`, or when no item is unpinned (title "Nothing to compact"; while `locked` a quiet line "Available when the answer is done."). While `compacting`, the visible label is "Compacting" and a quiet line says it can take a moment.
- `notice` is shown as `role="status"` text under the button; `error` (with a view present) as `role="alert"` text, `data-test="stack-error"`.
- The list: `ul.items` of `li[data-test="stack-item"]`. Each row: a pin toggle button (`aria-pressed`, `aria-label` "Pin item" or "Unpin item", `data-test="pin"`), the text (wraps, `overflow-wrap: anywhere`), a small source label ("You", "Agent", "Summary" for `compaction`; an unknown source shows nothing) and a remove button (`aria-label` "Remove item", `data-test="remove"`). A pinned row shows a visible "Pinned" text next to its icon. Both buttons are disabled while `pending` or `compacting`. Item text is rendered as text (no HTML).
- Empty list: `StateMessage kind="empty"` "Nothing is remembered in this chat yet. Agents save short facts here, and you can add one." plus the line "Pinned items are never dropped when the list is full." under a non-empty list.
- The add form: a labelled textarea (label "Add something to remember", 2 rows, `maxlength` 2000, `data-test="add-text"`), Enter submits and Shift+Enter inserts a newline, an "Add" button (`pill-btn primary`, `type="submit"`, disabled while the trimmed text is empty or `pending` or `compacting`). `addError` shows beside the field (`role="alert"`, `data-test="add-error"`, tied with `aria-describedby` and `aria-invalid`) and the typed text is kept. The panel clears the text only when the parent calls `clearDraft()`.

- [x] **Step 1: Write the failing test**

```ts
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StackPanel from "./StackPanel.vue";
import type { StackItem, StackView } from "../api/StackClient";

const item = (id: number, text: string, pinned = false, source = "agent"): StackItem => ({ id, text, pinned, source, at: "2026-01-01T00:00:00Z" });
const view = (items: StackItem[], extra: Partial<StackView> = {}): StackView => ({ items, used: items.length, limit: 40, warn: false, full: false, ...extra });

function mountPanel(props: Partial<InstanceType<typeof StackPanel>["$props"]> = {}) {
  return mount(StackPanel, {
    props: {
      status: "ready", view: view([item(1, "I live in Paris", false, "user"), item(2, "Never email Bo", true), item(3, "Older facts, summed up", false, "compaction")]),
      error: "", addError: "", pending: false, compacting: false, notice: "", locked: false, ...props,
    },
  });
}

describe("StackPanel", () => {
  it("lists the items with their source, and marks a pinned one with text as well as an icon", () => {
    const w = mountPanel();
    const rows = w.findAll("[data-test=stack-item]");
    expect(rows).toHaveLength(3);
    expect(rows[0]!.text()).toContain("I live in Paris");
    expect(rows[0]!.text()).toContain("You");
    expect(rows[1]!.text()).toContain("Pinned");
    expect(rows[1]!.get("[data-test=pin]").attributes("aria-pressed")).toBe("true");
    expect(rows[1]!.get("[data-test=pin]").attributes("aria-label")).toBe("Unpin item");
    expect(rows[2]!.text()).toContain("Summary");
    expect(w.get(".summary").text()).toContain("3 of 40 items");
  });

  it("renders item text as text, never as HTML", () => {
    const w = mountPanel({ view: view([item(1, "<img src=x onerror=alert(1)>")]) });
    expect(w.find("img").exists()).toBe(false);
    expect(w.get("[data-test=stack-item]").text()).toContain("<img");
  });

  it("warns when nearly full and when full, with an icon and text", () => {
    const warn = mountPanel({ view: view([item(1, "a")], { warn: true }) });
    expect(warn.get("[data-test=stack-warn]").text()).toContain("compact it now");
    expect(warn.get("[data-test=stack-warn]").find("svg").exists()).toBe(true);
    expect(warn.find("[data-test=stack-full]").exists()).toBe(false);
    const full = mountPanel({ view: view([item(1, "a")], { warn: true, full: true }) });
    expect(full.get("[data-test=stack-full]").text()).toContain("drops the oldest unpinned");
    expect(full.find("[data-test=stack-warn]").exists()).toBe(false);
    expect(mountPanel().find("[data-test=stack-warn]").exists()).toBe(false);
  });

  it("emits what the user does", async () => {
    const w = mountPanel();
    await w.findAll("[data-test=pin]")[0]!.trigger("click");
    await w.findAll("[data-test=pin]")[1]!.trigger("click");
    await w.findAll("[data-test=remove]")[2]!.trigger("click");
    await w.get("[data-test=compact]").trigger("click");
    expect(w.emitted("pin")).toEqual([[1, true], [2, false]]);
    expect(w.emitted("remove")).toEqual([[3]]);
    expect(w.emitted("compact")).toHaveLength(1);
  });

  it("compacting is off while busy, locked, or when only pinned items remain", () => {
    expect(mountPanel({ compacting: true }).get("[data-test=compact]").attributes("disabled")).toBeDefined();
    expect(mountPanel({ compacting: true }).get("[data-test=compact]").attributes("aria-busy")).toBe("true");
    expect(mountPanel({ pending: true }).get("[data-test=compact]").attributes("disabled")).toBeDefined();
    const locked = mountPanel({ locked: true });
    expect(locked.get("[data-test=compact]").attributes("disabled")).toBeDefined();
    expect(locked.text()).toContain("Available when the answer is done");
    const pinnedOnly = mountPanel({ view: view([item(1, "a", true)]) });
    expect(pinnedOnly.get("[data-test=compact]").attributes("disabled")).toBeDefined();
    expect(pinnedOnly.get("[data-test=compact]").attributes("title")).toBe("Nothing to compact");
    expect(mountPanel().get("[data-test=compact]").attributes("disabled")).toBeUndefined();
  });

  it("shows the compaction result and a failure", () => {
    expect(mountPanel({ notice: "Replaced 8 items with a summary." }).text()).toContain("Replaced 8 items with a summary.");
    const failed = mountPanel({ error: "The context summarizer did not answer." });
    expect(failed.get("[data-test=stack-error]").text()).toContain("did not answer");
    expect(failed.get("[data-test=stack-error]").attributes("role")).toBe("alert");
  });

  it("add: Enter submits the trimmed text, Shift+Enter does not, and the text stays until cleared", async () => {
    const w = mountPanel();
    const field = w.get("[data-test=add-text]");
    await field.setValue("  Prefers metric  ");
    await field.trigger("keydown", { key: "Enter", shiftKey: true });
    expect(w.emitted("add")).toBeUndefined();
    await field.trigger("keydown", { key: "Enter" });
    expect(w.emitted("add")).toEqual([["Prefers metric"]]);
    expect((field.element as HTMLTextAreaElement).value).toBe("  Prefers metric  ");
    (w.vm as unknown as { clearDraft: () => void }).clearDraft();
    await w.vm.$nextTick();
    expect((field.element as HTMLTextAreaElement).value).toBe("");
  });

  it("add is off for empty text and while busy; a refusal sits beside the field", async () => {
    const w = mountPanel();
    expect(w.get("button[type=submit]").attributes("disabled")).toBeDefined();
    await w.get("[data-test=add-text]").setValue("x");
    expect(w.get("button[type=submit]").attributes("disabled")).toBeUndefined();
    await w.setProps({ pending: true });
    expect(w.get("button[type=submit]").attributes("disabled")).toBeDefined();
    await w.setProps({ pending: false, addError: "An item holds at most 500 characters." });
    const field = w.get("[data-test=add-text]");
    expect(field.attributes("aria-invalid")).toBe("true");
    expect(w.get("[data-test=add-error]").text()).toContain("at most 500");
    expect(field.attributes("aria-describedby")).toBe(w.get("[data-test=add-error]").attributes("id"));
  });

  it("shows loading, a retryable load error, an unsaved chat and an empty list", async () => {
    expect(mountPanel({ status: "loading", view: null }).text()).toContain("Loading memory");
    const failed = mountPanel({ status: "error", view: null, error: "Storage is unavailable" });
    expect(failed.text()).toContain("Storage is unavailable");
    await failed.get("button.chip").trigger("click");
    expect(failed.emitted("retry")).toHaveLength(1);
    expect(mountPanel({ status: "missing", view: null }).text()).toContain("Send a message first");
    expect(mountPanel({ view: view([]) }).text()).toContain("Nothing is remembered in this chat yet");
  });
});
```

- [x] **Step 2: Run to see it fail**

Run: `pnpm exec vitest run src/features/chat/components/StackPanel.test.ts`
Expected: cannot find `./StackPanel.vue`.

- [x] **Step 3: Write `StackPanel.vue`**

```vue
<script setup lang="ts">
import { computed, ref, useId } from "vue";
import type { StackItem, StackView } from "../api/StackClient";
import StateMessage from "../../../components/ui/status/StateMessage.vue";

/** A chat's short-term memory: how full it is, the items (pin, remove), Compact, and a field to add one.
 * Presentation only: the parent owns the data and the server calls. A change shows only after the server answered. */
const props = defineProps<{
  status: "loading" | "ready" | "missing" | "error";
  view: StackView | null;
  error: string;
  addError: string;
  pending: boolean;
  compacting: boolean;
  notice: string;
  /** An answer is being written: compacting now would race the turn's own compaction. */
  locked: boolean;
}>();

const emit = defineEmits<{
  add: [text: string];
  pin: [id: number, pinned: boolean];
  remove: [id: number];
  compact: [];
  retry: [];
}>();

const SOURCE: Record<string, string> = { user: "You", agent: "Agent", compaction: "Summary" };
const sourceLabel = (item: StackItem): string => SOURCE[item.source] ?? "";

const draft = ref("");
const errorId = useId();
const busy = computed(() => props.pending || props.compacting);
const canAdd = computed(() => draft.value.trim() !== "" && !busy.value);
const hasUnpinned = computed(() => !!props.view?.items.some((item) => !item.pinned));
const canCompact = computed(() => hasUnpinned.value && !busy.value && !props.locked);
const percent = computed(() => (props.view && props.view.limit > 0 ? Math.min(100, Math.round((props.view.used / props.view.limit) * 100)) : 0));

function submit(): void {
  const text = draft.value.trim();
  if (text && !busy.value) emit("add", text);
}

function onEnter(event: KeyboardEvent): void {
  if (event.shiftKey || event.isComposing) return; // a newline, or an input method still choosing
  event.preventDefault();
  submit();
}

defineExpose({ clearDraft: (): void => { draft.value = ""; } });
</script>

<template>
  <div class="stack-panel" role="dialog" aria-label="Short-term memory" data-test="stack-panel">
    <StateMessage v-if="status === 'loading' && !view" kind="loading">Loading memory</StateMessage>
    <StateMessage v-else-if="status === 'error' && !view" kind="error" @retry="emit('retry')">{{ error }}</StateMessage>
    <StateMessage v-else-if="status === 'missing'" kind="empty" title="Not saved yet">
      Send a message first. Short-term memory is kept once the chat is saved.
    </StateMessage>
    <template v-else-if="view">
      <p class="summary"><strong>{{ view.used }} of {{ view.limit }} items</strong></p>
      <div class="bar" role="progressbar" aria-label="Memory used" :aria-valuenow="view.used" aria-valuemin="0" :aria-valuemax="view.limit">
        <i :class="{ warn: view.warn, full: view.full }" :style="{ width: `${percent}%` }" />
      </div>
      <p v-if="view.full" class="status full" role="status" data-test="stack-full">
        <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        Full. Adding an item drops the oldest unpinned one.
      </p>
      <p v-else-if="view.warn" class="status warn" role="status" data-test="stack-warn">
        <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        Nearly full. It is compacted when you send your next message, or compact it now.
      </p>
      <div class="actions">
        <button
          type="button" class="pill-btn ghost" data-test="compact" :aria-busy="compacting ? 'true' : undefined"
          :disabled="!canCompact" :title="hasUnpinned ? undefined : 'Nothing to compact'" @click="emit('compact')"
        >{{ compacting ? "Compacting" : "Compact now" }}</button>
        <span v-if="compacting" class="hint">This can take a moment.</span>
        <span v-else-if="locked" class="hint">Available when the answer is done.</span>
      </div>
      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <p v-if="error" class="error" role="alert" data-test="stack-error">{{ error }}</p>
      <ul v-if="view.items.length" class="items">
        <li v-for="item in view.items" :key="item.id" data-test="stack-item">
          <button
            type="button" class="icon-btn" :class="{ on: item.pinned }" data-test="pin" :aria-pressed="item.pinned"
            :aria-label="item.pinned ? 'Unpin item' : 'Pin item'" :disabled="busy" @click="emit('pin', item.id, !item.pinned)"
          >
            <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M10 2l4 4-3 1-2 3-3-3 3-2zM6 10l-3 3" /></svg>
          </button>
          <span class="body">
            <span class="text">{{ item.text }}</span>
            <span class="meta">
              <span v-if="item.pinned" class="pinned">Pinned</span>
              <span v-if="sourceLabel(item)">{{ sourceLabel(item) }}</span>
            </span>
          </span>
          <button type="button" class="icon-btn" data-test="remove" aria-label="Remove item" :disabled="busy" @click="emit('remove', item.id)">
            <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
          </button>
        </li>
      </ul>
      <StateMessage v-else kind="empty">Nothing is remembered in this chat yet. Agents save short facts here, and you can add one.</StateMessage>
      <p v-if="view.items.length" class="note">Pinned items are never dropped when the list is full.</p>
      <form class="add" @submit.prevent="submit">
        <label for="stack-add">Add something to remember</label>
        <textarea
          id="stack-add" v-model="draft" rows="2" maxlength="2000" data-test="add-text"
          :aria-invalid="addError ? 'true' : undefined" :aria-describedby="addError ? errorId : undefined" @keydown.enter="onEnter"
        />
        <p v-if="addError" :id="errorId" class="error" role="alert" data-test="add-error">{{ addError }}</p>
        <button type="submit" class="pill-btn primary" :disabled="!canAdd">Add</button>
      </form>
    </template>
  </div>
</template>

<style scoped>
.stack-panel {
  box-sizing: border-box;
  width: min(360px, calc(100vw - 32px));
  max-height: 70vh;
  overflow-y: auto;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  color: var(--text);
  background: var(--surface);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.18);
  font-size: 0.9em;
}
.summary { margin: 0 0 8px; }
.bar { height: 6px; overflow: hidden; border-radius: var(--radius-full); background: var(--code-bg); }
.bar i { display: block; height: 100%; background: var(--accent); }
.bar i.warn { background: var(--warning); }
.bar i.full { background: var(--danger); }
.status { display: flex; align-items: flex-start; gap: 6px; margin: 10px 0 0; }
.status.warn { color: var(--warning); }
.status.full { color: var(--danger); }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0 0; }
.hint, .note, .meta { color: var(--muted); font-size: 0.9em; }
.notice { margin: 8px 0 0; color: var(--success); }
.error { margin: 8px 0 0; color: var(--danger); overflow-wrap: anywhere; }
.items { margin: 12px 0 0; padding: 0; list-style: none; }
.items li { display: flex; align-items: flex-start; gap: 6px; padding: 6px 0; border-top: 1px solid var(--border); }
.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.text { overflow-wrap: anywhere; white-space: pre-wrap; }
.meta { display: flex; gap: 8px; }
.pinned { color: var(--accent); font-weight: 600; }
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
  min-width: 32px; min-height: 32px; padding: 0; border: none; border-radius: var(--radius-md);
  cursor: pointer; background: transparent; color: var(--muted);
}
.icon-btn:hover:not(:disabled) { background: var(--code-bg); color: var(--text); }
.icon-btn.on { color: var(--accent); }
.icon-btn:disabled { cursor: default; opacity: 0.5; }
.note { margin: 8px 0 0; }
.add { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; margin-top: 14px; }
.add label { font-weight: 600; }
.add textarea {
  box-sizing: border-box; width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--bg); color: var(--text); font: inherit; resize: vertical;
}
.add textarea:focus { border-color: var(--accent); }
@media (max-width: 767px) {
  .icon-btn { min-width: 44px; min-height: 44px; }
}
</style>
```

Notes for the implementer: the colour tokens `--success`, `--warning`, `--danger` come from `style.css` (assumption (d); if one is missing use the nearest token the other pages use). A warning that needs `--warning` text on `--surface` must keep 4.5:1 contrast in light and dark; if it does not, tint the icon with `--warning` and keep the text in `--text`. `StateMessage`'s retry button has class `chip` (the test relies on it).

- [x] **Step 4: Run, then commit**

Run: `pnpm exec vitest run src/features/chat/components/StackPanel.test.ts`, `pnpm exec vue-tsc -b`, then `pnpm test` (the radius and architecture tests).

```bash
git add apps/ember/src/features/chat/components/StackPanel.vue apps/ember/src/features/chat/components/StackPanel.test.ts
git commit -m "feat(ember): short-term memory panel with pin, remove, add, warning and Compact"
```

---

### Task 4: Header control, wiring, docs and roadmap

**Files:**
- Create: `apps/ember/src/features/chat/components/StackMenu.vue`, `StackMenu.test.ts`
- Modify: `components/ChatHeader.vue`, `components/ChatHeader.test.ts`, `views/ChatView.vue`
- Modify: roadmap row 20e; `apps/ember/README.md` only if it lists chat features.

**Interfaces:**
- Consumes: `useStackStore` (Task 2), `StackPanel` (Task 3), `useOutsideClose`, `useNarrow`.
- Produces: `StackMenu` with props `chatId: string | null`, `locked: boolean`; renders nothing when `chatId` is null. A button (`data-test="stack-button"`, `aria-haspopup="dialog"`, `aria-expanded`) labelled "Memory" with the count (`12/40`) once loaded; when the view is `warn` or `full` the button also shows the warning icon and the words "nearly full" or "full" (visible text, not colour alone). Opening shows `StackPanel` in a popover under the button (desktop) or a sheet above the rail (below 768px). `ChatHeader` gets an optional prop `chatId?: string | null` and renders `StackMenu` (only when `chatId` is set and `hasMessages`) before the context meter; `ChatView` passes `:chat-id="activeId"`.

- [x] **Step 1: Write the failing tests**

`StackMenu.test.ts`:

```ts
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { stackClient, type StackItem, type StackView } from "../api/StackClient";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { useStackStore } from "../stores/stack";
import StackMenu from "./StackMenu.vue";

vi.mock("../api/StackClient", () => ({
  stackClient: { view: vi.fn(), add: vi.fn(), setPinned: vi.fn(), remove: vi.fn(), compact: vi.fn() },
}));

const client = vi.mocked(stackClient);
const item = (id: number, text: string, pinned = false): StackItem => ({ id, text, pinned, source: "agent", at: "2026-01-01T00:00:00Z" });
const view = (items: StackItem[], extra: Partial<StackView> = {}): StackView => ({ items, used: items.length, limit: 40, warn: false, full: false, ...extra });

async function mountMenu(props: { chatId: string | null; locked?: boolean } = { chatId: "c-1" }) {
  setActivePinia(createPinia());
  useAuthStore().account = makeAccount({ username: "u", email: "u@example.com" });
  const w = mount(StackMenu, { props: { locked: false, ...props }, attachTo: document.body });
  await flushPromises();
  return w;
}

beforeEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = "";
  client.view.mockResolvedValue(view([item(1, "I live in Paris"), item(2, "Never email Bo", true)]));
});

describe("StackMenu", () => {
  it("renders nothing without a chat", async () => {
    const w = await mountMenu({ chatId: null });
    expect(w.find("[data-test=stack-button]").exists()).toBe(false);
    expect(client.view).not.toHaveBeenCalled();
  });

  it("loads the chat's stack and shows the count on the button", async () => {
    const w = await mountMenu();
    expect(client.view).toHaveBeenCalledWith("c-1");
    expect(w.get("[data-test=stack-button]").text()).toContain("Memory");
    expect(w.get("[data-test=stack-button]").text()).toContain("2/40");
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
  });

  it("says nearly full and full in words on the closed button", async () => {
    client.view.mockResolvedValue(view([item(1, "a")], { warn: true }));
    expect((await mountMenu()).get("[data-test=stack-button]").text()).toContain("nearly full");
    client.view.mockResolvedValue(view([item(1, "a")], { warn: true, full: true }));
    expect((await mountMenu()).get("[data-test=stack-button]").text()).toContain("full");
  });

  it("opens the panel, refreshes, and closes on Escape with focus back on the button", async () => {
    const w = await mountMenu();
    client.view.mockClear();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    expect(w.get("[data-test=stack-button]").attributes("aria-expanded")).toBe("true");
    expect(w.find("[data-test=stack-panel]").exists()).toBe(true);
    expect(client.view).toHaveBeenCalledTimes(1);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await flushPromises();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
    expect(document.activeElement).toBe(w.get("[data-test=stack-button]").element);
  });

  it("closes on a press outside", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await flushPromises();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
  });

  it("the panel's actions go through the store and show the server's list", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    client.setPinned.mockResolvedValue(item(1, "x", true));
    client.view.mockResolvedValue(view([item(1, "I live in Paris", true), item(2, "Never email Bo", true)]));
    await w.findAll("[data-test=pin]")[0]!.trigger("click");
    await flushPromises();
    expect(client.setPinned).toHaveBeenCalledWith("c-1", 1, true);
    expect(w.findAll("[data-test=pin]")[0]!.attributes("aria-pressed")).toBe("true");
    client.add.mockResolvedValue(item(3, "new"));
    client.view.mockResolvedValue(view([item(1, "a"), item(3, "new")]));
    await w.get("[data-test=add-text]").setValue("new");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(client.add).toHaveBeenCalledWith("c-1", "new");
    expect((w.get("[data-test=add-text]").element as HTMLTextAreaElement).value).toBe("");
  });

  it("a refused add keeps the text and shows the reason", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    client.add.mockRejectedValue(new ApiError(422, "An item holds at most 500 characters."));
    await w.get("[data-test=add-text]").setValue("too long");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(w.get("[data-test=add-error]").text()).toContain("at most 500");
    expect((w.get("[data-test=add-text]").element as HTMLTextAreaElement).value).toBe("too long");
  });

  it("Compact is off while an answer is written, and the list reloads when the answer ends", async () => {
    const w = await mountMenu({ chatId: "c-1", locked: true });
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    expect(w.get("[data-test=compact]").attributes("disabled")).toBeDefined();
    client.view.mockClear();
    client.view.mockResolvedValue(view([item(1, "saved by the agent during the answer")]));
    await w.setProps({ locked: false });
    await flushPromises();
    expect(client.view).toHaveBeenCalledTimes(1);
    expect(w.text()).toContain("saved by the agent during the answer");
    expect(w.get("[data-test=compact]").attributes("disabled")).toBeUndefined();
  });

  it("compacts through the store and shows the result", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    client.compact.mockResolvedValue({ ...view([item(9, "summary")]), compacted: true, replaced: 1 });
    await w.get("[data-test=compact]").trigger("click");
    await flushPromises();
    expect(client.compact).toHaveBeenCalledWith("c-1");
    expect(w.text()).toContain("Replaced 1 item with a summary.");
  });

  it("another chat shows its own memory and drops the old one", async () => {
    const w = await mountMenu();
    const store = useStackStore();
    client.view.mockResolvedValue(view([item(7, "other chat")]));
    await w.setProps({ chatId: "c-2" });
    await flushPromises();
    expect(client.view).toHaveBeenLastCalledWith("c-2");
    expect(store.entry("c-1").view).toBeNull();
  });

  it("forgets the chat when it goes away", async () => {
    const w = await mountMenu();
    const store = useStackStore();
    w.unmount();
    expect(store.entry("c-1").view).toBeNull();
  });
});
```

`ChatHeader.test.ts`: read the existing file and add two cases: with `chatId: "c-1"` and `hasMessages: true` the header renders `[data-test=stack-button]` (mock `StackClient` as in `StackMenu.test.ts` and install Pinia the way the existing header tests do); without `chatId`, or without messages, it does not. Every existing header test keeps passing without a `chatId`.

- [x] **Step 2: Run to see them fail**

Run: `pnpm exec vitest run src/features/chat/components/StackMenu.test.ts`
Expected: cannot find `./StackMenu.vue`.

- [x] **Step 3: Write `StackMenu.vue`**

```vue
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useTemplateRef, watch } from "vue";
import { useOutsideClose } from "../../../composables/useOutsideClose";
import { useStackStore } from "../stores/stack";
import StackPanel from "./StackPanel.vue";

/** The Memory control in the chat header: how much short-term memory the chat holds, and the panel to manage it.
 * A non-modal popover (a sheet above the nav bar on a phone): Esc or a press outside closes it. The memory is
 * private to the chat: it is dropped when the chat changes and when this control goes away. */
const props = defineProps<{ chatId: string | null; locked: boolean }>();

const store = useStackStore();
const open = ref(false);
const box = useTemplateRef<HTMLElement>("box");
const panel = useTemplateRef<InstanceType<typeof StackPanel>>("panel");

const shown = computed(() => (props.chatId ? store.entry(props.chatId) : null));
const view = computed(() => shown.value?.view ?? null);
const level = computed(() => (view.value?.full ? "full" : view.value?.warn ? "warn" : ""));
const countText = computed(() => (view.value ? `${view.value.used}/${view.value.limit}` : ""));

function close(): void {
  open.value = false;
}

function closeOnEscape(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  open.value = false;
  box.value?.querySelector<HTMLElement>("[data-test=stack-button]")?.focus();
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener("keydown", closeOnEscape);
    if (props.chatId) void store.load(props.chatId);
  } else {
    document.removeEventListener("keydown", closeOnEscape);
  }
});
useOutsideClose(box, open, close);

watch(() => props.chatId, (next, previous) => {
  if (previous) store.forget(previous);
  open.value = false;
  if (next) void store.load(next);
}, { immediate: true });

// Agents save to memory while they answer: look again when the answer is done.
watch(() => props.locked, (locked, wasLocked) => {
  if (wasLocked && !locked && props.chatId) void store.load(props.chatId);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", closeOnEscape);
  if (props.chatId) store.forget(props.chatId);
});

async function add(text: string): Promise<void> {
  if (props.chatId && (await store.add(props.chatId, text))) panel.value?.clearDraft();
}
</script>

<template>
  <div v-if="chatId && shown" ref="box" class="stack-box">
    <button
      type="button" class="stack-button" :class="level" data-test="stack-button" aria-haspopup="dialog" :aria-expanded="open"
      title="Short-term memory: the short facts saved for this chat" @click="open = !open"
    >
      <svg v-if="level" class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
      Memory
      <span v-if="countText" class="count">{{ countText }}</span>
      <span v-if="level === 'full'" class="level">full</span>
      <span v-else-if="level === 'warn'" class="level">nearly full</span>
    </button>
    <StackPanel
      v-if="open"
      ref="panel"
      class="panel"
      :status="shown.status === 'idle' ? 'loading' : shown.status"
      :view="view"
      :error="shown.error"
      :add-error="shown.addError"
      :pending="shown.pending"
      :compacting="shown.compacting"
      :notice="shown.notice"
      :locked="locked"
      @add="add"
      @pin="(id, pinned) => store.setPinned(chatId!, id, pinned)"
      @remove="(id) => store.remove(chatId!, id)"
      @compact="store.compact(chatId!)"
      @retry="store.load(chatId!)"
    />
  </div>
</template>

<style scoped>
.stack-box { position: relative; }
.stack-button {
  display: inline-flex; align-items: center; gap: 6px; padding: 2px 6px; border: none; border-radius: var(--radius-md);
  cursor: pointer; background: transparent; color: var(--muted); font: inherit; font-size: 0.8em;
}
.stack-button:hover, .stack-button[aria-expanded="true"] { background: var(--code-bg); }
.stack-button.warn { color: var(--warning); }
.stack-button.full { color: var(--danger); }
.count { font-variant-numeric: tabular-nums; }
.panel { position: absolute; top: calc(100% + 6px); right: 0; z-index: 30; }
@media (max-width: 767px) {
  .stack-button { min-width: 44px; min-height: 44px; justify-content: center; }
  .panel {
    position: fixed; top: auto; right: 0; left: 0; bottom: var(--rail-height); z-index: 40; width: auto;
    max-height: 70vh; border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }
}
</style>
```

Notes: the panel renders inside the header, so on a phone it must not be clipped by the header; `position: fixed` with `bottom: var(--rail-height)` places it over the content. If an ancestor with `transform` or `overflow: hidden` clips a fixed element, teleport the panel to `body` with `<Teleport to="body">` and keep `useOutsideClose` working by passing both elements (record what you did). Check the header colour contrast of the `--warning` text on `--bg` in light and dark; if it fails 4.5:1, keep the text in `--muted` and tint only the icon.

- [x] **Step 4: Wire the header and the view**

`ChatHeader.vue`: import `StackMenu`; add `chatId?: string | null` to `defineProps`; in the template, immediately before the `v-if="contextPercent !== null || breakdown"` context box, add `<StackMenu v-if="chatId && hasMessages" :chat-id="chatId" :locked="locked" />`. `ChatView.vue`: add `:chat-id="activeId"` to the `<ChatHeader ...>` element (`activeId` is the chat the page shows; assumption (a)). Make sure the header's `.spacer` keeps the new control on the right with the context meter, and that at 375px the header wraps rather than overflowing.

- [x] **Step 5: Run everything**

Run (from `apps/ember`): `pnpm exec vue-tsc -b`, then `pnpm test` (all unit tests, including `radiusScale.test.ts` and `architecture.test.ts`). Expected: pass; the count rises by the new tests only.

- [x] **Step 6: Docs and roadmap**

`apps/ember/README.md`: if it lists chat features, add one line: "Short-term memory: a Memory control in the chat header lists the chat's saved facts, with pin, remove, add and Compact, and warns when it is nearly full." If it lists none, skip and say so.

Roadmap: in `docs/superpowers/plans/2026-11-20-scope-roadmap.md` mark row 20e Written with a link to this plan and replace its text with: "Ember Memory control in the chat header: items with source, pin, remove, add, near-full and full warnings, Compact now; front end only (apps/ember)".

- [x] **Step 7: Commit**

```bash
git add -A apps/ember docs
git commit -m "feat(ember): Memory control in the chat header; docs and roadmap row 20e"
```

---

## Self-Review

**Spec coverage.** Short-term memory visible to the user (items): Tasks 3 and 4. Pin and remove: Tasks 2 and 3. "Near full, the user is warned that it needs compaction": the `warn` and `full` states on the closed button and in the panel, with the sentence "It is compacted when you send your next message, or compact it now". "Compacts on the next prompt, or the user compacts manually": the Compact button plus the text. "Overflow drops the oldest item and keeps pinned ones": the full-state text and the "Pinned items are never dropped" note. "Never visible to other chats": one entry per chat, forgotten on chat change. Add by the user: Tasks 2 and 3 (the route already accepts `source: user`).

**Placeholders.** None in code or tests. The Baseline block and "Changes found during work" are filled by the implementer, as in earlier plans.

**Type consistency.** `StackView`, `StackItem` and `CompactResult` (Task 1) are used with the same fields in the store (Task 2), the panel props (Task 3) and the tests. `StackEntry` fields (`status`, `view`, `error`, `addError`, `pending`, `compacting`, `notice`) match the panel's props one to one in `StackMenu` (Task 4). Store actions `add`, `setPinned`, `remove`, `compact`, `load`, `forget`, `entry` are the names `StackMenu` calls. Test ids (`stack-button`, `stack-panel`, `stack-item`, `pin`, `remove`, `compact`, `add-text`, `add-error`, `stack-warn`, `stack-full`, `stack-error`) are spelled the same in the component and every test.

## Out of scope

No backend change: the per-item character cap is not in the stack view, so the panel shows no counter and relies on the server's message when an item is too long (record this as the one gap a later backend change could close). No Ember Notes page, file browser or long-term memory UI (Plan 20f). No admin settings page for the limits (Plan 20f). No agent proposals from short-term to long-term (Plan 20f). No sharing UI for short-term items or files (Plan 20f). No change in `ember_web`. No automatic toast or sound when the stack becomes nearly full (the header button and the panel show it). No edit of an item's text (an item is added, pinned, unpinned or removed; to change one, remove it and add the corrected one).

## Known limits

- Removing an item is immediate with no confirmation: an item is one short fact the user can add again. If testing shows accidental removals, add the existing `ConfirmModal` pattern.
- The panel refreshes when it opens, when the chat changes and when an answer ends. Items an agent saves during an answer appear when it ends, not live.
- The Compact button is off while an answer is being written so it cannot race the turn's own compaction. The server also serialises them, but a quiet wait is clearer than an error.
- Compaction calls Legion's summarizer and can take longer than other calls; the button shows a busy state and no progress. It is bounded by the server's own timeout.
- A chat that is not saved on the server yet answers 404; the panel says to send a message first. The control only shows for a chat that has messages.
- Unverified until a live run: the panel against a real Stronghold with a real summarizer; narrow-phone and keyboard behaviour on a real device (the plan's tests cover the logic, not the layout).

## Changes found during work

### Assumptions

- (a) Confirmed chat IDs. `activeId` is the ID passed to the turn and conversation storage routes. The first question appears locally before the server confirms creation, so the stack can briefly return 404. The control refreshes when the answer ends.
- (b) Confirmed `apiRequest` returns `undefined` for 204 and uses FastAPI's string detail or validation messages in `ApiError`. Stronghold and Portcullis match the planned methods and response shapes. The compact call supplies no body argument and the existing client sends an empty JSON object.
- (c) Confirmed compact refusal is 429 with detail `You've reached your {reason}. It frees up in about {wait}.` and a `Retry-After` header. The store displays the detail.
- (d) Confirmed the shared button, link, screen-reader, busy spinner, and color and rail tokens in `style.css`.
- (e) Confirmed the shared-to-feature import restriction and token-only radius test. New code lives under the chat feature. Both checks passed in the full suite.
- (f) Confirmed the header tests use active Pinia and pass without a chat ID. Added two cases for Memory visibility. Existing expectations and test cases were preserved.
- (g) Confirmed `useNarrow()` uses `(max-width: 767px)` and the lockfile resolves Vue 3.5.43 with `useId`. CSS handles this breakpoint. The stack response omits the configured item character cap, so the add field uses server validation and has no counter.
- (h) Confirmed `busy` covers starting and server-running turns, including agent steps and approval waits. `working` covers other in-flight chat commands. The control disables Compact while locked and refreshes on unlock.

### Snippet adjustments

- Client test exercises both pin and unpin. Store uses a reactive map and always returns its proxied value from `own()`. Account changes clear it synchronously. Writes stay pending through their re-read and overlapping writes are guarded. Compact uses its returned server view and supersedes stale loads. Added a sign-out test with a reply still pending.
- Panel gives the label and error separate generated IDs, preserves the submitted draft while pending, and uses a token-based shadow. 44px minimum button targets include Retry, Add and Compact on narrow layouts.
- Contrast measured as light/dark ratios. Warning on surface was 4.11/8.81 and on background 4.44/9.60. Danger on surface was 3.98/7.03 and on background 4.30/7.66. On the hover fill, warning was 4.01/8.39 and danger 3.88/6.70. Warning and danger tint icons while the panel uses neutral text and the trigger uses muted text. The notice and errors also use neutral text. Muted text on normal/hover trigger fills measured 5.28/6.41 and 4.76/5.61. Panel text on surface measured 15.74/13.42.
- Source inspection found no transform or clipping ancestor between the chat header and the viewport. The panel stays in the header DOM with `useOutsideClose`. The desktop popover anchors to the header so a wrapped trigger cannot put the panel past the left edge. The mobile sheet accounts for the rail, safe areas, and existing visual viewport variables. Physical viewport checks are pending.
- Menu drops state on KeepAlive deactivation, re-reads on activation, and clears a submitted draft only on the originating panel. Tests clean up mounted menus, use the existing header test's DOM event pattern and cover inside press and sign-out.
- Ember README has no chat feature list. The worktree's roadmap row 20e uses the requested text and link, which were already present as an uncommitted edit in the main checkout.

### Verification

Each new suite failed first on its missing component/module. The new header presence case also failed before wiring.

| Check | Result |
|---|---|
| StackClient targeted | 5 passed |
| Stack store targeted | 16 passed |
| StackPanel plus radius guard | 15 passed (9 panel, 6 radius) |
| StackMenu plus ChatHeader | 32 passed (13 menu, 19 header) |
| `pnpm exec vue-tsc -b` | Passed |
| `pnpm test` | 187 files, 2,272 tests passed (+4 files, +45 tests from baseline) |

Tests ran from the worktree's `apps/ember`. No existing test expectations changed and no tests were removed. Live Stronghold and summarizer, real-phone and keyboard layout, and contrast beyond the measured pairs remain pending.

## Manual checks for the user (pending until done)

Desktop, 768px, 767px and 375px, light and dark. Open the Memory control in a chat with items: pin, unpin, remove, add; add an item that is too long and see the reason beside the field with the text kept; fill the stack to 80% and to full and read the warning on the closed button and in the panel; press Compact now (the busy state, then the result line); open it while an answer is being written (Compact is off, the list reloads afterwards); switch chats and see only that chat's items; press Esc and click outside; Tab through the panel; check the sheet sits above the bottom bar on a phone and that the last field stays reachable with the keyboard open.
