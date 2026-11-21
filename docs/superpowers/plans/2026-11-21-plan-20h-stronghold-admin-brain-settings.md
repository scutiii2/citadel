# Stronghold Admin Brain Settings Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Brain settings" page in the Stronghold Admin app where an administrator reads and changes the Brain's run-time limits (short-term memory, long-term memory, sharing) and sees where the brain files are kept.

**Architecture:** The backend already exists: Stronghold serves `GET` and `PUT /admin/brain-settings` (Plans 20b and 20d) and Portcullis passes them on as `/api/admin/stronghold-brain-settings` (permission `settings.manage`, action log entry `settings.brain`). Stronghold validates every value against its own ranges, saves it in its settings database and uses it at once. This plan adds only front end in `apps/stronghold_admin`, copying the pattern of the existing Usage settings page: a typed client, a view that takes its field ranges from the server's answer, a route and a nav entry. A save sends only the fields that changed, so a limit nobody touched keeps following the built-in default.

**Tech Stack:** Vue 3 + TypeScript, Vitest and `@vue/test-utils` (no Pinia store needed: the page keeps its own state like `UsageSettingsView.vue`).

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, section "Brain (Stronghold)": "Character limit 20,000, plus stack size, quota and brain root, are run-time settings in Stronghold's `settings.db`." Roadmap row 20h. Backend: `apps/stronghold/src/brain/admin_settings.py`, `limits.py`, `settings_routes.py`, `apps/portcullis/src/routes/stronghold_brain_settings.py`. UI rules: `.agents/skills/ember-frontend-design/SKILL.md` and `.agents/skills/ember-design-system/SKILL.md` (the root `AGENTS.md` names them for the admin apps too), and `apps/stronghold_admin/AGENTS.md`.

## Global Constraints

- Work only in `apps/stronghold_admin`. No backend, Portcullis, Stronghold or Ember change. Code is copied between the admin apps, not shared; import nothing from another app.
- All calls go through Portcullis with `apiRequest` from `src/api/http.ts`; never `fetch` or a hand-built URL elsewhere.
- Radius only through `--radius-*` tokens and colour only through the tokens in `style.css` (`radiusScale.test.ts` enforces it). Never add a reduced-motion setting, media query or test.
- Reuse the page shape of `UsageSettingsView.vue` (`PageLayout`, `infoPage.css`, the `card`, `chip`, `primary`, `muted`, `error` classes). Add a page with exactly one entry in `src/router/pages.ts`, one route in `src/router/index.ts` with `meta.permission`, and one view.
- The page needs `settings.manage`, the same permission as Usage settings; Portcullis enforces it, the router guard is only a UX gate.
- Every field's allowed range comes from the server's `ranges` in the answer, never copied into the page; Stronghold stays the only owner of the limits and checks them again. A server refusal (HTTP 400) is shown as it came.
- A save sends only the fields whose value changed, grouped by part (`stack`, `long_term`, `sharing`). Never send an untouched field: Stronghold marks a part as saved when it receives a value for it, and a saved part stops following a future change of the built-in default.
- The page never offers to change the brain folder: it is set by `STRONGHOLD_BRAIN_ROOT` or the `brain/root` setting and moving it needs a restart. It shows the path, read-only.
- Limits are numbers only. No file names, text or usernames are involved, so nothing private goes into a message or a test name.
- Touch targets and inputs are at least 44px high on narrow screens; every input has a visible label; a problem with a value is shown in words next to it and is linked with `aria-describedby`.
- Use `pnpm` (not npm). No new dependency. Keep each file's line endings.

---

## File Map

All paths under `apps/stronghold_admin/` unless noted.

- Create `src/api/BrainSettingsClient.ts` and `src/api/BrainSettingsClient.test.ts`.
- Create `src/views/BrainSettingsView.vue` and `src/views/BrainSettingsView.test.ts`.
- Modify `src/router/index.ts` (route `/brain-settings`), `src/router/pages.ts` (nav entry "Brain settings", after "Usage settings") and `src/router/index.test.ts` (route tests).
- Modify `README.md` and `AGENTS.md` (the page list and the call list).
- Roadmap row 20h: link this plan.

## Out of scope (note in the report, do not build)

A "reset to defaults" button (the server has no route to delete a saved value), changing the brain folder, any change to the account-level quotas (there are none beyond these limits), per-account overrides, a page in another admin app, any backend change. While reading `src/router/pages.ts` you will see the Analytics entry has `permission: "ANALYTICS_PERMISSIONS"` as a string instead of the constant of that name; do not fix it here, record it in your report.

## Assumptions to check at build time (record each result under "Changes found during work")

- (a) The answer shape of `GET` and `PUT`: read `apps/stronghold/src/brain/admin_settings.py` (`view`, `update`) and `settings_routes.py`. It is `{stack: {max_items, max_item_chars, compact_item_chars, warn_ratio}, long_term: {max_record_chars, max_files, max_total_bytes, search_limit}, sharing: {max_share_chars, max_pending_sent, max_inbox, max_global_queue}, ranges: {stack|long_term|sharing: {name: [low, high]}}, root, stored: {stack, long_term, sharing}}`; `sharing` and `stored.sharing` are present only when Stronghold's sharing is on (the page hides the Sharing card without them). `PUT` takes `{stack?, long_term?, sharing?}` with partial objects and answers the same shape; a refusal is HTTP 400 with a sentence such as "max_files must be a whole number from 1 to 5000." and nothing is saved.
- (b) What each limit does (for the labels and the notice): read `apps/stronghold/src/brain/stack.py`, `compaction.py`, `files.py` (`_check`, `_room`, `search`) and `shares.py` (`create`). In particular confirm that lowering a limit deletes nothing and what an account over a new limit can no longer do; adjust the plan's notice text to the real behaviour and record it.
- (c) `apiRequest` in `src/api/http.ts` for the admin app: signature `(method, path, body?)`, `ApiError` carries FastAPI `detail`. Read the rest of the file.
- (d) `infoPage.css` and `PageLayout.vue` provide the classes and props the page uses (`card`, `chip`, `primary`, `muted`, `error`, `help`; `title`, `description`). `help` and `title` are page-local in `UsageSettingsView.vue`: copy their scoped styles.
- (e) Tests that list the pages or route names (grep `STRONGHOLD_PAGES`, `usage-settings` and the nav labels in `src`); adding the entry may change one of them. List each.
- (f) Docs that name the pages or the call list: `README.md`, `AGENTS.md`, and grep `brain-settings` and `Brain settings` across `docs/`, `apps/stronghold/` and `apps/portcullis/` for a statement that says the page does not exist yet; update only statements this page makes false.
- (g) `radiusScale.test.ts` and any theme or contrast test the app has: new CSS uses tokens only.

## Baseline

`pnpm exec vue-tsc -b` passed. `pnpm test` passed 267 tests across 31 files. Both ran from `apps/stronghold_admin` in the Plan 20h worktree.

## Changes found during work

- (a) Confirmed GET and PUT return the same shape. Sharing values and the sharing stored flag are optional, but sharing ranges are always present. Stronghold validates all submitted fields before writing and returns HTTP 400 with its refusal text. `stored` reports whether that part has a persisted override, even if someone saved a value equal to a built-in default.
- (b) Confirmed that saving lower limits leaves data in place. On the next new stack item, Stronghold may evict as many oldest unpinned items as needed, or reject the add if pins leave no room. The per-item and summary limits apply to new text and compaction. The warning ratio controls the near-full flag. The file count blocks new files at capacity, the byte quota blocks writes that would increase usage past the limit (including retained originals), and the character cap applies to the file body. The search setting supplies the default when the caller does not provide a limit. Sharing checks the snapshot body and pending sender, recipient and global review counts on creation. Long-term limits also apply to the global files store. Updated the notice and field copy.
- (c) Confirmed the admin `apiRequest(method, path, body?)` wrapper preserves FastAPI's string `detail` in `ApiError.message`, which the view displays through `errorMessage`.
- (d) Confirmed `PageLayout` props, shared `infoPage.css` classes and the `--mono` token. Copied scoped title and help styles from Usage settings. Used a string-valued input event because Vue's number-input `v-model` can produce a number. The form owns validation with `novalidate` and uses `step="any"` for warning ratios, which the backend accepts anywhere in range. Added a Save-button test for `0.83` and corrected the `040` test name. Added a busy state and 44px minimum height to Save and retry.
- (e) Existing page and route expectations required no changes. Added two router cases. The unauthorized case also asserts route metadata because the catch-all already lands on Usage for that account. The authorized case went red by falling back to Usage settings. Analytics nav still has a quoted `"ANALYTICS_PERMISSIONS"`; its route uses the constant.
- (f) Updated the Stronghold Admin README and AGENTS page lists and endpoint descriptions. No live docs elsewhere claimed the page was missing. The source checkout already had the roadmap link as a local edit. Added only that link to the branch's own row.
- (g) The radius test checks radius tokens. Found no theme or contrast test in this app. New styles use existing color and radius tokens. No browser or device checks ran.

Automated results in the worktree: Task 1 client suite 2 passed. Task 2 view plus radius suite 18 passed (12 view, 6 radius), and type-check passed. Task 3 router suites 11 passed; type-check, full suite (283 tests across 33 files) and production build passed. No existing tests were weakened.

The final source review found no blocking issue. The last save confirmation remains visible when a new draft starts, as in the planned view. Field help and the byte hint are visible text; the input's accessible description links to validation errors.

---

### Task 1: Brain settings API client

**Files:**
- Create: `apps/stronghold_admin/src/api/BrainSettingsClient.ts`
- Test: `apps/stronghold_admin/src/api/BrainSettingsClient.test.ts`

**Interfaces:**
- Consumes: `apiRequest(method, path, body?)` (`src/api/http.ts`).
- Produces: types `Part` (`"stack" | "long_term" | "sharing"`), `StackLimits`, `LongTermLimits`, `SharingLimits`, `Ranges`, `BrainSettings`, `BrainSettingsChanges`; `brainSettingsClient` with `get()` and `save(changes)`.

- [x] **Step 1: Write the failing test**

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { brainSettingsClient } from "./BrainSettingsClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("brainSettingsClient", () => {
  it("reads the settings", async () => {
    await brainSettingsClient.get();
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/admin/stronghold-brain-settings");
  });

  it("saves only the changes it is given and returns the new settings", async () => {
    const view = { root: "/data/brain" };
    request.mockResolvedValueOnce(view as never);
    const changes = { long_term: { max_files: 50 }, stack: { warn_ratio: 0.9 } };
    expect(await brainSettingsClient.save(changes)).toBe(view);
    expect(request).toHaveBeenCalledExactlyOnceWith("PUT", "/api/admin/stronghold-brain-settings", changes);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run (from `apps/stronghold_admin`): `pnpm exec vitest run src/api/BrainSettingsClient.test.ts`
Expected: FAIL, the module `./BrainSettingsClient` does not exist.

- [x] **Step 3: Write the client**

```ts
import { apiRequest } from "./http";

export type Part = "stack" | "long_term" | "sharing";

/** Short-term memory, per chat. */
export interface StackLimits {
  max_items: number;
  max_item_chars: number;
  compact_item_chars: number;
  warn_ratio: number;
}

/** Long-term memory files, per account. */
export interface LongTermLimits {
  max_record_chars: number;
  max_files: number;
  max_total_bytes: number;
  search_limit: number;
}

/** Sharing between accounts and to the global brain. */
export interface SharingLimits {
  max_share_chars: number;
  max_pending_sent: number;
  max_inbox: number;
  max_global_queue: number;
}

/** [lowest, highest] allowed value of each setting, as Stronghold checks it. */
export type Ranges = Record<Part, Record<string, [number, number]>>;

export interface BrainSettings {
  stack: StackLimits;
  long_term: LongTermLimits;
  /** Present only when Stronghold's sharing is on. */
  sharing?: SharingLimits;
  ranges: Ranges;
  /** Where the account folders live. Set by STRONGHOLD_BRAIN_ROOT or the `brain/root` setting; read-only here. */
  root: string;
  /** Which part was changed from the built-in defaults. */
  stored: { stack: boolean; long_term: boolean; sharing?: boolean };
}

/** Only the settings that changed, grouped by part. */
export interface BrainSettingsChanges {
  stack?: Partial<StackLimits>;
  long_term?: Partial<LongTermLimits>;
  sharing?: Partial<SharingLimits>;
}

/** Portcullis's /api/admin/stronghold-brain-settings (needs settings.manage), passed on to Stronghold, which checks
 * every value and uses a change at once. */
export const brainSettingsClient = {
  get: () => apiRequest<BrainSettings>("GET", "/api/admin/stronghold-brain-settings"),
  save: (changes: BrainSettingsChanges) => apiRequest<BrainSettings>("PUT", "/api/admin/stronghold-brain-settings", changes),
};
```

- [x] **Step 4: Run the test to verify it passes**

Run: `pnpm exec vitest run src/api/BrainSettingsClient.test.ts`
Expected: PASS (2 tests).

- [x] **Step 5: Commit**

```bash
git add apps/stronghold_admin/src/api/BrainSettingsClient.ts apps/stronghold_admin/src/api/BrainSettingsClient.test.ts
git commit -m "feat(stronghold-admin): API client for the brain settings"
```

---

### Task 2: Brain settings view

**Files:**
- Create: `apps/stronghold_admin/src/views/BrainSettingsView.vue`
- Test: `apps/stronghold_admin/src/views/BrainSettingsView.test.ts`

**Interfaces:**
- Consumes: `brainSettingsClient` and types (Task 1); `PageLayout`, `errorMessage`, `infoPage.css`.
- Produces: the view `BrainSettingsView` (default export of the `.vue` file); every input has `data-test="<part>.<key>"` (for example `long_term.max_files`), every problem line `data-test="problem-<part>.<key>"`, the form `data-test="form"`, the save button `data-test="save"`, the notice `data-test="notice"`.

- [x] **Step 1: Write the failing test**

```ts
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { brainSettingsClient, type BrainSettings } from "../api/BrainSettingsClient";
import BrainSettingsView from "./BrainSettingsView.vue";

const SETTINGS: BrainSettings = {
  stack: { max_items: 40, max_item_chars: 500, compact_item_chars: 1500, warn_ratio: 0.8 },
  long_term: { max_record_chars: 20000, max_files: 500, max_total_bytes: 5000000, search_limit: 8 },
  sharing: { max_share_chars: 20000, max_pending_sent: 30, max_inbox: 100, max_global_queue: 200 },
  ranges: {
    stack: { max_items: [2, 200], max_item_chars: [20, 2000], compact_item_chars: [100, 6000], warn_ratio: [0.3, 0.95] },
    long_term: { max_record_chars: [200, 100000], max_files: [1, 5000], max_total_bytes: [10000, 100000000], search_limit: [1, 30] },
    sharing: { max_share_chars: [200, 100000], max_pending_sent: [1, 200], max_inbox: [1, 1000], max_global_queue: [1, 1000] },
  },
  root: "/data/brain",
  stored: { stack: false, long_term: true, sharing: false },
};

beforeEach(() => {
  vi.spyOn(brainSettingsClient, "get").mockResolvedValue(SETTINGS);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(BrainSettingsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
type Wrapper = Awaited<ReturnType<typeof mounted>>;
const field = (wrapper: Wrapper, name: string) => wrapper.get(`[data-test="${name}"]`);
const save = (wrapper: Wrapper) => wrapper.get('[data-test="save"]');
const submit = async (wrapper: Wrapper) => {
  await wrapper.get('[data-test="form"]').trigger("submit");
  await flushPromises();
};

describe("BrainSettingsView", () => {
  it("shows every limit with its range, where the files are kept, and keeps Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((field(wrapper, "long_term.max_files").element as HTMLInputElement).value).toBe("500");
    expect(field(wrapper, "long_term.max_files").attributes("min")).toBe("1");
    expect(field(wrapper, "long_term.max_files").attributes("max")).toBe("5000");
    expect((field(wrapper, "stack.warn_ratio").element as HTMLInputElement).value).toBe("0.8");
    expect((field(wrapper, "sharing.max_inbox").element as HTMLInputElement).value).toBe("100");
    expect(wrapper.text()).toContain("/data/brain");
    expect(wrapper.text()).toContain("STRONGHOLD_BRAIN_ROOT");
    expect(save(wrapper).attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("says which parts were changed from the defaults", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="state-long_term"]').text()).toContain("changed from the defaults");
    expect(wrapper.get('[data-test="state-stack"]').text()).toContain("defaults");
    expect(wrapper.get('[data-test="state-stack"]').text()).not.toContain("changed");
    wrapper.unmount();
  });

  it("shows the size a byte limit means", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="hint-long_term.max_total_bytes"]').text()).toContain("5.0 MB");
    await field(wrapper, "long_term.max_total_bytes").setValue("250000");
    expect(wrapper.get('[data-test="hint-long_term.max_total_bytes"]').text()).toContain("250 KB");
    wrapper.unmount();
  });

  it("sends only the field that changed", async () => {
    const send = vi.spyOn(brainSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await field(wrapper, "long_term.max_files").setValue("50");
    await submit(wrapper);
    expect(send).toHaveBeenCalledExactlyOnceWith({ long_term: { max_files: 50 } });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("Stronghold uses it now");
    wrapper.unmount();
  });

  it("sends changes from several parts, each with only its changed fields, and numbers not text", async () => {
    const send = vi.spyOn(brainSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await field(wrapper, "stack.warn_ratio").setValue("0.9");
    await field(wrapper, "stack.max_items").setValue("60");
    await field(wrapper, "sharing.max_inbox").setValue("50");
    await submit(wrapper);
    expect(send).toHaveBeenCalledExactlyOnceWith({ stack: { max_items: 60, warn_ratio: 0.9 }, sharing: { max_inbox: 50 } });
    wrapper.unmount();
  });

  it("does not count 05 for 5 as a change", async () => {
    const wrapper = await mounted();
    await field(wrapper, "stack.max_items").setValue("040");
    expect(save(wrapper).attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("shows what is wrong with a value, in words, and keeps Save off", async () => {
    const wrapper = await mounted();
    await field(wrapper, "stack.max_items").setValue("1");
    expect(wrapper.get('[data-test="problem-stack.max_items"]').text()).toContain("2 to 200");
    expect(field(wrapper, "stack.max_items").attributes("aria-invalid")).toBe("true");
    expect(field(wrapper, "stack.max_items").attributes("aria-describedby")).toContain("problem");
    expect(save(wrapper).attributes("disabled")).toBeDefined();
    await field(wrapper, "stack.max_items").setValue("2.5");
    expect(wrapper.get('[data-test="problem-stack.max_items"]').text()).toContain("whole number");
    await field(wrapper, "stack.max_items").setValue("");
    expect(wrapper.get('[data-test="problem-stack.max_items"]').text()).toContain("Enter a number");
    await field(wrapper, "stack.max_items").setValue("40");
    expect(wrapper.find('[data-test="problem-stack.max_items"]').exists()).toBe(false);
    await field(wrapper, "stack.warn_ratio").setValue("0.2");
    expect(wrapper.get('[data-test="problem-stack.warn_ratio"]').text()).toContain("0.3 to 0.95");
    await field(wrapper, "stack.warn_ratio").setValue("0.5");
    expect(wrapper.find('[data-test="problem-stack.warn_ratio"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows the server's refusal as it came and keeps the edits", async () => {
    vi.spyOn(brainSettingsClient, "save").mockRejectedValue(new Error("max_files must be a whole number from 1 to 5000."));
    const wrapper = await mounted();
    await field(wrapper, "long_term.max_files").setValue("50");
    await submit(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toBe("max_files must be a whole number from 1 to 5000.");
    expect((field(wrapper, "long_term.max_files").element as HTMLInputElement).value).toBe("50");
    expect(save(wrapper).attributes("disabled")).toBeUndefined();
    wrapper.unmount();
  });

  it("takes the server's answer as the new saved state", async () => {
    const after: BrainSettings = { ...SETTINGS, long_term: { ...SETTINGS.long_term, max_files: 50 }, stored: { stack: false, long_term: true, sharing: false } };
    vi.spyOn(brainSettingsClient, "save").mockResolvedValue(after);
    const wrapper = await mounted();
    await field(wrapper, "long_term.max_files").setValue("50");
    await submit(wrapper);
    expect((field(wrapper, "long_term.max_files").element as HTMLInputElement).value).toBe("50");
    expect(save(wrapper).attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("hides the Sharing card when Stronghold does not report sharing", async () => {
    const { sharing: _sharing, ...rest } = SETTINGS;
    vi.spyOn(brainSettingsClient, "get").mockResolvedValue({ ...rest, stored: { stack: false, long_term: true } });
    const wrapper = await mounted();
    expect(wrapper.find('[data-test="sharing.max_inbox"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="stack.max_items"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("a failed load shows the reason with a way to try again", async () => {
    vi.spyOn(brainSettingsClient, "get").mockRejectedValueOnce(new Error("Storage is unavailable"));
    const wrapper = await mounted();
    expect(wrapper.get('[role="alert"]').text()).toContain("Storage is unavailable");
    expect(wrapper.find('[data-test="form"]').exists()).toBe(false);
    await wrapper.get('[data-test="retry"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-test="form"]').exists()).toBe(true);
    wrapper.unmount();
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pnpm exec vitest run src/views/BrainSettingsView.test.ts`
Expected: FAIL, `./BrainSettingsView.vue` does not exist.

- [x] **Step 3: Write the view**

Replace the plan's notice wording in `NOTICE` below with what assumption (b) found if the real behaviour differs.

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { brainSettingsClient, type BrainSettings, type BrainSettingsChanges, type Part } from "../api/BrainSettingsClient";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** The Brain's run-time limits. Stronghold owns them: it checks every value against its own ranges (sent in the
 * answer, used here for the input limits), saves them in its settings database and uses a change at once. */
interface FieldSpec { key: string; label: string; help?: string; step?: string }
interface PartSpec { part: Part; title: string; intro: string; fields: FieldSpec[] }

const NOTICE = "Lowering a limit never deletes anything. An account or chat over the new limit cannot add more until it is back under.";

const PARTS: PartSpec[] = [
  {
    part: "stack", title: "Short-term memory", intro: "The short facts kept for one chat.",
    fields: [
      { key: "max_items", label: "Items per chat", help: "When it is full, adding an item drops the oldest unpinned one." },
      { key: "max_item_chars", label: "Characters per item" },
      { key: "compact_item_chars", label: "Characters per summary item", help: "The longest summary compaction may write." },
      { key: "warn_ratio", label: "Warn at this share of full (0 to 1)", step: "0.05" },
    ],
  },
  {
    part: "long_term", title: "Long-term memory", intro: "The Markdown files kept for one account.",
    fields: [
      { key: "max_record_chars", label: "Characters per file" },
      { key: "max_files", label: "Files per account" },
      { key: "max_total_bytes", label: "Bytes per account", help: "Counts the saved original text of edited files too." },
      { key: "search_limit", label: "Search results by default" },
    ],
  },
  {
    part: "sharing", title: "Sharing", intro: "Copies sent between accounts and to the global brain.",
    fields: [
      { key: "max_share_chars", label: "Characters per share" },
      { key: "max_pending_sent", label: "Waiting shares per sender" },
      { key: "max_inbox", label: "Waiting shares per account" },
      { key: "max_global_queue", label: "Shares waiting for review in the global brain" },
    ],
  },
];

const saved = ref<BrainSettings | null>(null);
const values = ref<Record<string, string>>({});
const loading = ref(true);
const saving = ref(false);
const loadError = ref("");
const error = ref("");
const notice = ref("");

const id = (part: Part, key: string) => `${part}.${key}`;
const parts = computed(() => PARTS.filter((spec) => saved.value?.[spec.part]));
const savedValue = (part: Part, key: string): number | undefined => (saved.value?.[part] as Record<string, number> | undefined)?.[key];
const rangeOf = (part: Part, key: string) => saved.value?.ranges[part]?.[key];

function apply(view: BrainSettings): void {
  saved.value = view;
  const next: Record<string, string> = {};
  for (const spec of PARTS) {
    for (const field of spec.fields) {
      const value = (view[spec.part] as Record<string, number> | undefined)?.[field.key];
      if (value !== undefined) next[id(spec.part, field.key)] = String(value);
    }
  }
  values.value = next;
}

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    apply(await brainSettingsClient.get());
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function problemOf(part: Part, key: string): string {
  const text = (values.value[id(part, key)] ?? "").trim();
  const number = Number(text);
  if (text === "" || !Number.isFinite(number)) return "Enter a number.";
  if (key !== "warn_ratio" && !Number.isInteger(number)) return "Use a whole number.";
  const range = rangeOf(part, key);
  if (range && (number < range[0] || number > range[1])) return `From ${range[0]} to ${range[1]}.`;
  return "";
}

function changedField(part: Part, key: string): boolean {
  const text = (values.value[id(part, key)] ?? "").trim();
  const before = savedValue(part, key);
  return text !== String(before) && Number(text) !== before;
}

const changes = computed<BrainSettingsChanges>(() => {
  const found: Record<string, Record<string, number>> = {};
  for (const spec of parts.value) {
    for (const field of spec.fields) {
      if (changedField(spec.part, field.key)) (found[spec.part] ??= {})[field.key] = Number(values.value[id(spec.part, field.key)]);
    }
  }
  return found as BrainSettingsChanges;
});
const anyProblem = computed(() => parts.value.some((spec) => spec.fields.some((field) => problemOf(spec.part, field.key) !== "")));
const canSave = computed(() => Object.keys(changes.value).length > 0 && !anyProblem.value && !saving.value);

function formatBytes(bytes: number): string {
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} KB`;
  if (bytes < 1_000_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
}
const bytesHint = (part: Part, key: string): string => {
  const text = (values.value[id(part, key)] ?? "").trim();
  return key === "max_total_bytes" && text !== "" && problemOf(part, key) === "" ? `About ${formatBytes(Number(text))}.` : "";
};

async function save(): Promise<void> {
  if (!canSave.value) return;
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await brainSettingsClient.save(changes.value));
    notice.value = "Saved. Stronghold uses it now.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <PageLayout
    class="info-content brain-settings"
    title="Brain settings"
    description="The limits of short-term memory, long-term memory and sharing. Stronghold is the only owner of them."
  >
    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="loadError" class="load-error" role="alert">
      <p class="error">{{ loadError }}</p>
      <button type="button" class="chip" data-test="retry" @click="load">Try again</button>
    </div>
    <form v-else-if="saved" class="form" data-test="form" @submit.prevent="save">
      <section class="card" aria-labelledby="root-title">
        <h2 id="root-title" class="title">Where the files are kept</h2>
        <p class="path" data-test="root">{{ saved.root }}</p>
        <p class="help">Set by STRONGHOLD_BRAIN_ROOT or the brain/root setting. Moving it needs a restart and a copy of the folder, so this page cannot change it.</p>
      </section>

      <section v-for="spec in parts" :key="spec.part" class="card" :aria-labelledby="`${spec.part}-title`">
        <h2 :id="`${spec.part}-title`" class="title">{{ spec.title }}</h2>
        <p class="help">{{ spec.intro }}</p>
        <p class="help" :data-test="`state-${spec.part}`">{{ saved.stored[spec.part] ? "Some values here are changed from the defaults." : "Using the defaults." }}</p>
        <div v-for="field in spec.fields" :key="field.key" class="field">
          <label :for="`f-${id(spec.part, field.key)}`">{{ field.label }}</label>
          <input
            :id="`f-${id(spec.part, field.key)}`" v-model="values[id(spec.part, field.key)]" type="number"
            :min="rangeOf(spec.part, field.key)?.[0]" :max="rangeOf(spec.part, field.key)?.[1]" :step="field.step ?? '1'"
            :disabled="saving" :data-test="id(spec.part, field.key)"
            :aria-invalid="problemOf(spec.part, field.key) ? 'true' : undefined"
            :aria-describedby="problemOf(spec.part, field.key) ? `problem-${id(spec.part, field.key)}` : undefined"
          />
          <p v-if="problemOf(spec.part, field.key)" :id="`problem-${id(spec.part, field.key)}`" class="problem" :data-test="`problem-${id(spec.part, field.key)}`">{{ problemOf(spec.part, field.key) }}</p>
          <p v-if="field.help" class="help">{{ field.help }}</p>
          <p v-if="bytesHint(spec.part, field.key)" class="help" :data-test="`hint-${id(spec.part, field.key)}`">{{ bytesHint(spec.part, field.key) }}</p>
        </div>
      </section>

      <p class="help">{{ NOTICE }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button type="submit" class="primary" data-test="save" :disabled="!canSave">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </PageLayout>
</template>

<style scoped>
.form { display: grid; gap: 16px; max-width: 720px; }
.card { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input { min-width: 0; min-height: 44px; width: 100%; }
.help, .path, .problem { margin: 0; font-size: 0.85em; }
.help { color: var(--muted); }
.path { font-family: var(--mono); overflow-wrap: anywhere; }
.problem { color: var(--text); font-weight: 600; }
.load-error { display: grid; gap: 8px; justify-items: start; }
.actions { display: flex; justify-content: flex-end; }
</style>
```

- [x] **Step 4: Run the test to verify it passes**

Run: `pnpm exec vitest run src/views/BrainSettingsView.test.ts src/radiusScale.test.ts` then `pnpm exec vue-tsc -b`
Expected: PASS and no type errors. Fix a snippet that does not fit the real components (for example a class name that exists only in the Ember copy of `infoPage.css`, or that `--mono` does not exist here: use the token the app has) and record it. The problem line must not rely on colour alone: it is bold text beside the field; if you add an icon, give it `aria-hidden`.

- [x] **Step 5: Commit**

```bash
git add apps/stronghold_admin/src/views/BrainSettingsView.vue apps/stronghold_admin/src/views/BrainSettingsView.test.ts
git commit -m "feat(stronghold-admin): Brain settings page"
```

---

### Task 3: Route, nav entry and docs

**Files:**
- Modify: `apps/stronghold_admin/src/router/index.ts`, `src/router/pages.ts`, `src/router/index.test.ts`
- Modify: `apps/stronghold_admin/README.md`, `apps/stronghold_admin/AGENTS.md`
- Modify: `docs/superpowers/plans/2026-11-20-scope-roadmap.md` (row 20h only, if it does not link this plan)

**Interfaces:**
- Consumes: Task 2 view.
- Produces: route `/brain-settings` (name `brain-settings`, `meta.permission: "settings.manage"`) and a nav entry "Brain settings" right after "Usage settings".

- [x] **Step 1: Write the failing route test**

Add to `src/router/index.test.ts`, inside `describe("router", ...)`:

```ts
  it("opens /brain-settings for an account with settings.manage", async () => {
    const router = await freshRouter(["settings.manage"]);
    await router.push("/brain-settings");
    expect(router.currentRoute.value.name).toBe("brain-settings");
  });
  it("sends an account without settings.manage away from /brain-settings", async () => {
    const router = await freshRouter(["usage.all.view"]);
    await router.push("/brain-settings");
    expect(router.currentRoute.value.name).toBe("usage");
  });
```

- [x] **Step 2: Run it to verify it fails**

Run: `pnpm exec vitest run src/router/index.test.ts`
Expected: FAIL (no such route: the page falls through to the catch-all redirect).

- [x] **Step 3: Add the route, the nav entry and the docs**

In `src/router/index.ts`, after the `usage-settings` route:

```ts
    { path: "/brain-settings", name: "brain-settings", component: () => import("../views/BrainSettingsView.vue"), meta: { permission: "settings.manage" } },
```

In `src/router/pages.ts`, after the "Usage settings" entry:

```ts
  {
    to: "/brain-settings",
    label: "Brain settings",
    icon: ["M12 18V5", "M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4", "M17.6 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.6 1.5 4 4 0 0 0-2.8 5.6 4 4 0 0 0 .6 6.9A4 4 0 0 0 12 20a4 4 0 0 0 7.8-1 4 4 0 0 0 .6-6.9 4 4 0 0 0-2.8-5.6"],
    permission: "settings.manage",
  },
```

In `README.md` change the page list to "Usage, Analytics (…), Tickets, Usage settings, Brain settings, and Tool services" and add `/api/admin/stronghold-brain-settings` to the call list; add one short paragraph under it: "**Brain settings** (`settings.manage`) shows the limits of short-term memory, long-term memory and sharing. Stronghold checks every value against its own ranges and uses a change at once. A save sends only the fields you changed. The brain folder is shown but not editable here." In `AGENTS.md` do the same for its page sentence. Check assumption (f) for other statements made false and update only those.

- [x] **Step 4: Run all checks**

Run: `pnpm exec vitest run src/router`, then `pnpm exec vue-tsc -b`, `pnpm test` and `pnpm run build`.
Expected: all PASS; the build succeeds. List any existing test whose expectation changed (assumption (e)).

- [x] **Step 5: Roadmap**

Check that roadmap row 20h links this plan (`[Written](2026-11-21-plan-20h-stronghold-admin-brain-settings.md)`); fix only that.

- [x] **Step 6: Commit**

```bash
git add apps/stronghold_admin docs/superpowers/plans
git commit -m "feat(stronghold-admin): Brain settings route, nav entry and docs"
```

---

## Manual checklist (the user runs it; Codex copies it into the report as pending)

- Start Stronghold, Portcullis and the admin app (`pnpm dev`, port 26504) and log in as an administrator. Open **Brain settings**: three cards (Short-term memory, Long-term memory, Sharing) and the brain folder path.
- An account without `settings.manage` does not see the entry and is sent away from `/brain-settings`.
- Change **Files per account** to a small number and Save: "Saved. Stronghold uses it now."; in Ember create files until the limit and read the refusal; raise it and create again with no restart.
- Change one limit in each card and Save: the page now says the part is "changed from the defaults"; a limit you did not touch is not stored (check `settings.db` or run the page again after a default change if you have one).
- Type a value out of range, a decimal in a whole-number field and an empty field: each shows its words next to it and Save stays off; the server refuses a value too if you force one (for example with the dev tools).
- Check the action log shows "Changed Stronghold brain settings" with no values.
- Narrow window (375px): inputs are 44px high and the cards fit; light and dark themes.

Unverified by the work above: a real Stronghold with real accounts over their old limits (what an account above a lowered limit sees in Ember), a restart after changing the brain root, and contrast beyond what the app's own tests compute.
