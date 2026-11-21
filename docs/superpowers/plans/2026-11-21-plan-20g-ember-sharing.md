# Ember Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the Ember Windows app a person can share a copy of a file, one section of a file, a skill or a short-term memory item with another account or with the global brain; see what was sent to them and keep, decline or block it; withdraw what they sent; and manage the accounts they blocked.

**Architecture:** The backend already exists (Plan 20d): Portcullis serves `POST /api/brain/shares`, `GET /api/brain/shares/inbox`, `GET /api/brain/shares/sent`, `GET/DELETE /api/brain/shares/{id}`, `POST /api/brain/shares/{id}/accept`, `POST /api/brain/shares/{id}/decline` and `GET/PUT/DELETE /api/brain/blocks`. This plan adds only front end in `apps/ember`, in a new feature folder `features/sharing/`: a typed client, a Pinia store (inbox, sent, blocks; late replies ignored; dropped on sign-out and unmount), a `ShareDialog` (send a copy), a `ShareReview` dialog (read what arrived, keep, decline, block) and a `SharesView` page behind a new `/shares` route and nav entry. Share buttons are added to the Notes editor (file or one section), the Skills editor and the short-term memory panel. Nothing is sent or kept without the person pressing the button that says so.

**Tech Stack:** Vue 3 + TypeScript, Pinia, Vitest and `@vue/test-utils`, Tauri shell (untouched).

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, section "Brain (Stronghold)", "Sharing fragments" (a fragment is a file, a section, a skill or a short-term item; the sender picks a fragment and a recipient found by username or the global brain; the recipient imports or declines; nothing lands without consent; imported text is untrusted; per-recipient block list). Roadmap row 20g. Backend: `docs/superpowers/plans/2026-11-21-plan-20d-global-brain-and-sharing.md`. UI rules: `.agents/skills/ember-frontend-design/SKILL.md`, `mobile-ui.md` and `.agents/skills/ember-design-system/SKILL.md` (read all three before Task 3).

## Global Constraints

- Work only in `apps/ember` (the Windows app). `apps/ember_web` is reference only; do not copy anything there. No backend, Portcullis, Stronghold or Legion change.
- Never call `fetch` or build an `/api` URL by hand outside `apiRequest` (`src/api/http.ts`). The client uses `apiRequest` only.
- Radius only through `--radius-*` tokens, colour only through tokens, no hex and no literal radius (`radiusScale.test.ts` fails on one). Never add a reduced-motion setting, media query or test. Animations always play.
- Reuse the shared pieces: `PageLayout`, `BaseModal`, `ConfirmModal`, `StateMessage`, `SearchField` if needed, `useUnsavedGuard` is not needed here; the global `pill-btn`, `pill-btn primary`, `pill-btn ghost`, `link-btn`, `chip`, `status-badge` classes. Do not write a page-local empty, load-error or counter style.
- A change that calls the server stays pending until the server answers; never show unconfirmed state. Status (waiting, kept, declined, withdrawn, not approved; untrusted text) uses words and, where it warns, an icon, never colour alone.
- Hit areas of at least 44 by 44 CSS px on touch (below 768px); visible focus ring; every icon-only control has an `aria-label`.
- Nothing is sent until the person presses Send in the share dialog. Nothing is kept until the person presses Keep in the review dialog. Opening a share to read it changes nothing.
- Shared text is untrusted: another account wrote it. Show it as plain text only (interpolation, `white-space: pre-wrap`); never `v-html`, never turn it into links, never run it. The review dialog shows the server's `notice` sentence beside it.
- The dialog must not reveal whether a username exists: the server answers one text ("No such recipient.") for an unknown, inactive, own or blocking recipient; show it as received and add nothing.
- Private content (the text of a share being read, titles and names in the lists) is dropped when the sharing page unmounts, when the review dialog closes and when the account signs out; a late reply must never show after that.
- Share text, titles and usernames never go into a console message, an error message built by this code, a test name or a snapshot.
- Use `pnpm` (not npm). No new dependency. Keep each file's line endings.

---

## File Map

All paths under `apps/ember/src/` unless noted.

- Create `features/sharing/api/SharingClient.ts` and `SharingClient.test.ts`.
- Create `features/sharing/stores/sharing.ts` and `sharing.test.ts`.
- Create `features/sharing/utils/headings.ts` and `headings.test.ts`.
- Create `features/sharing/components/ShareDialog.vue` and `ShareDialog.test.ts`.
- Create `features/sharing/components/ShareReview.vue` and `ShareReview.test.ts`.
- Create `features/sharing/SharesView.vue` and `SharesView.test.ts`.
- Modify `router/index.ts` (route `/shares`), `router/pages.ts` (nav entry "Shares", after "Skills") and every existing test whose expectation lists the nav pages (assumption (e)).
- Modify `features/notes/components/FileEditor.vue` and `FileEditor.test.ts` (a "Share" section and the `share` event), `features/notes/NotesView.vue` and `NotesView.test.ts` (opens the dialog).
- Modify `features/skills/SkillsView.vue` and `SkillsView.test.ts` (a "Share a copy" button).
- Modify `features/chat/components/StackPanel.vue`, `StackMenu.vue` and their tests (a share button per item).
- Modify `apps/ember/README.md` only if it lists pages (grep first; skip and say so if not).
- Roadmap row 20g is already linked to this plan.

## Out of scope (note in the report, do not build)

The global brain pages (browse, write, review queue; roadmap row 20k), an unread count or badge on the nav entry, notifications, sending to several accounts at once, sharing several files at once, username search or autocomplete (the server gives one generic refusal on purpose), a diff against an existing file, opening the kept file directly from the Shares page (it links to the Notes or Skills page only), the legacy `/memory` page, outside clients.

## Assumptions to check at build time (record each result under "Changes found during work")

- (a) Shapes and refusals: read `apps/stronghold/src/brain/share_routes.py`, `shares.py` (`view()`, `create`, `accept`, `revoke`, `decline`, `block`), `apps/portcullis/src/routes/brain_sharing.py`. A share row is `{id, kind, title, status, sender, recipient, created_at, decided_at, result_id, chars}`; the detail adds `body`, `skill` and `notice`. `GET inbox` answers only pending shares. Refusals: 404 "No such recipient."; 409 for "N shares waiting for an answer", "already shared and waiting", "cannot receive shares right now", "already decided", a full brain or a duplicate skill title on accept; 422 for a share over the size limit or a bad request. Times are `...Z` strings.
- (b) `apiRequest` resolves with `undefined` for 204 (`DELETE /api/brain/blocks/{uid}`) and returns the share row for `DELETE /api/brain/shares/{id}`; every POST sends a JSON body (`{}` when none). Read `src/api/http.ts`.
- (c) Section headings: `headingsOf` (Task 3) must match `extract_section` and `_HEADING` in `apps/stronghold/src/brain/fragments.py`: ATX headings `#` to `######` followed by a space, not inside a fenced code block, trailing `#` marks removed, whitespace collapsed, matched case-insensitively, the first match wins.
- (d) The shared components behave as the plan uses them: `BaseModal` (props `open`, `title`, `wide`; default slot; `close` event; native `<dialog>`), `ConfirmModal`, `PageLayout`, `StateMessage` kinds, `formatUtc`; the global classes exist in `style.css` and `infoPage.css`. `pill-btn primary`, `pill-btn ghost`, `link-btn danger`, `chip`, `status-badge`, `sr-only`, `line-icon`.
- (e) Tests that list the nav pages or their order: grep `NavRail.test.ts`, `OverviewView.test.ts`, `router` tests and anything that matches `"Skills"`, `"Brains"` or `NAV_PAGES`. Adding "Shares" after "Skills" changes those expectations; update them and list each under "Changes found during work".
- (f) `SkillsView.test.ts`, `StackMenu.test.ts` and `FileEditor.test.ts` mount without or with Pinia: `ShareDialog` must only be created when a target is set (`v-if`), so tests that never share need no Pinia. Check how each test mounts before you add the dialog.
- (g) `architecture.test.ts` forbids shared code (`api`, `stores`, `composables`, `utils`, `components` except `components/layout`) from importing a feature; a feature importing another feature is not forbidden, and `features/notes`, `features/skills` and `features/chat` import `features/sharing/components/ShareDialog.vue`, while `features/sharing` imports `folderProblem` and `normalizeFolder` from `features/notes/api/BrainClient.ts`. If the repo's own convention forbids that, move `normalizeFolder` and `folderProblem` to `src/utils/folder.ts` with their tests and say so. Also read `radiusScale.test.ts` and `themeContrast.test.ts`; compute the contrast of any `--warning` or `--danger` text on `--surface` and `--bg` in light and dark (Plans 20e and 20f found both under 4.5:1 in the light theme); if a pair fails, tint only the icon and keep the text on `--text` or `--muted`.
- (h) Vue 3.5 (`useId`), jsdom lacks `<dialog>.showModal` and `.close` (copy the polyfill from `features/notes/NotesView.test.ts`), and `RouterLink` needs a router in tests (stub it with `global.stubs`).
- (i) After a stack item share, the stack's own routes are unchanged (a share is a copy). Confirm no stack route needs the chat id to exist beyond what Plan 20e already shows (a chat that is not saved yet has no stack, so no items to share).

## Baseline

- Baseline at `8b6fcd1f` in the Plan 20g worktree. `pnpm exec vue-tsc -b` exited 0. `pnpm test --reporter=dot` passed 188 files and 2,264 tests. Both used `--config.verify-deps-before-run=false` with the existing Ember install and identical lockfile after the registry could not resolve.

## Changes found during work

### Assumption checks

- (a) Stronghold and Portcullis match the client shapes, pending-only inbox, status values and UTC timestamps. The server uses the same 404 `No such recipient.` for unusable recipients. Pending limits, duplicate waiting shares, already-decided shares and landing conflicts use 409. Validation and oversize text use 422. The UI displays server refusal text as received.
- (b) `apiRequest` supplies JSON for every POST and resolves 204 as `undefined`. Withdrawal returns the share row. Unblock returns 204.
- (c) `headingsOf` mirrors Stronghold's LF splitting, heading and fence matching, lowercase comparison, whitespace normalization and first-match behavior. It omits normalized headings longer than the 200-code-point request limit.
- (d) Shared `BaseModal`, `ConfirmModal`, `PageLayout`, `StateMessage`, `formatUtc` and global CSS classes work in Ember. Withdrawal uses the shared confirmation and its real button in the tests.
- (e) Changed page order expectations in `NavRail.test.ts`, `OverviewView.test.ts`, `AccountView.test.ts` and `SidebarEditor.test.ts`. Added route checks to `router/index.test.ts`.
- (f) `FileEditor` and `SkillsView` mount without Pinia. `NotesView` and `StackMenu` already set up Pinia. The send dialog mounts only when a target exists. Sharing cases use stubs in the view tests. The FileEditor fixture supplies its two new props.
- (g) The architecture check permits feature-to-feature imports, so ShareReview reuses the Notes folder helpers. Architecture, radius and theme suites pass. On `--surface` / `--bg`, light warning is 4.11 / 4.44 and danger 3.98 / 4.30. Dark warning is 8.81 / 9.60 and danger 7.03 / 7.66. Light neutral text is 15.74 / 17.00 and muted text 4.89 / 5.28. Dark neutral text is 13.42 / 14.62 and muted text 5.89 / 6.41. New messages use neutral text. Warning and destructive icons carry the status tint.
- (h) Vue 3.5 provides `useId`. Dialog tests use the Notes-style jsdom modal polyfill. SharesView tests use `RouterLinkStub` to check the landing link.
- (i) Stack sharing sends the saved chat ID and item ID through the sharing client. The existing StackClient routes are untouched, the panel requires a saved chat with messages, and the test checks that sharing dispatches no stack mutation.

### Adjustments and verification

- Share mutations refresh the three lists only after the Shares page has requested them. Sending from an editor leaves them unloaded.
- The send and review dialogs invalidate replies and clear private state on dismissal and account changes. The Shares page also clears drafts, confirmations and results on account change or unmount.
- `ShareTarget` is a type export in the ordinary script block of `ShareDialog.vue`. The send-success message uses the selected destination mode. The section parser follows Stronghold's exact whitespace and line rules.
- The review result links to Notes or Skills after Keep. Private share content appears only as escaped text. The withdrawal dialog retains the tinted icon with neutral label text.
- Added sharing cases to `FileEditor.test.ts`, `NotesView.test.ts`, `SkillsView.test.ts`, `StackPanel.test.ts` and `StackMenu.test.ts`. FileEditor fixture props were the only existing integration test setup change. StackMenu exercises Escape followed by the native dialog cancel event, which jsdom does not emit on its own.
- Ember README has no page list. Brought the existing roadmap split from the main checkout into this branch, including linked row 20g and the global brain UI in 20k.
- Observed missing implementations or missing controls/routes in the failing runs for each task before implementing. The original 74 cases in the five integration suites passed before adding their implementations.
- Code review found stale actions when a share was decided elsewhere, a missing retry after a refresh failure, missing native close on conditional modal removal, an overly broad link-removal claim, and mismatched skill title and mobile link sizes. The final task commit includes these fixes and five additional regression cases. The Ember `BaseModal` now closes a mounted native dialog before unmount so the browser can restore focus.
- Stronghold snapshots the current saved source when Send arrives. Another session or an agent can save a newer revision while the sender has a file open. The sharing API accepts an ID and optional heading without a revision. Stronghold removes private Markdown links and leaves HTML links and bare paths as text.
- Initial focused runs passed 6 client, 12 store, 18 headings and dialog, and 170 sharing, navigation and guardrail tests. After review fixes, the Notes, Skills, Chat and Sharing run passed 1,259 tests in 81 files. Final type check exited 0 and the full suite passed 2,339 tests in 194 files, up from 2,264 tests in 188 files. Commands ran in the worktree's `apps/ember` with `--config.verify-deps-before-run=false`.
- Pending vault updates are `Brain/Projects/ember.md` (sharing features and verification) and `Brain/Projects/Citadel.md` (20g implementation and 20k scope).

---

### Task 1: Sharing API client

**Files:**
- Create: `apps/ember/src/features/sharing/api/SharingClient.ts`
- Test: `apps/ember/src/features/sharing/api/SharingClient.test.ts`

**Interfaces:**
- Consumes: `apiRequest(method, path, body?)` (`src/api/http.ts`).
- Produces: types `ShareKind`, `ShareStatus`, `Share`, `ShareDetail`, `Block`, `ShareWhat`, `Recipient`, `NewShare`, `Landing`; constant `SHARE_NAME_MAX`; `sharingClient` with `create(share)`, `inbox()`, `sent()`, `get(id)`, `revoke(id)`, `accept(id, landing?)`, `decline(id)`, `blocks()`, `block(username)`, `unblock(uid)`. `inbox`, `sent`, `blocks` and `block` resolve with the plain arrays (not the `{shares}` or `{blocks}` wrappers).

- [x] **Step 1: Write the failing test**

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { sharingClient } from "./SharingClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("sharingClient", () => {
  it("creates a share for an account or for the global brain", async () => {
    await sharingClient.create({ kind: "file", file_id: "f1", recipient: "bo" });
    await sharingClient.create({ kind: "skill", skill_id: 3, to_global: true });
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/brain/shares", { kind: "file", file_id: "f1", recipient: "bo" });
    expect(request).toHaveBeenNthCalledWith(2, "POST", "/api/brain/shares", { kind: "skill", skill_id: 3, to_global: true });
  });

  it("lists the inbox and the sent shares as plain arrays", async () => {
    request.mockResolvedValueOnce({ shares: [{ id: "a" }] } as never).mockResolvedValueOnce({ shares: [{ id: "b" }] } as never);
    expect(await sharingClient.inbox()).toEqual([{ id: "a" }]);
    expect(await sharingClient.sent()).toEqual([{ id: "b" }]);
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/shares/inbox");
    expect(request).toHaveBeenNthCalledWith(2, "GET", "/api/brain/shares/sent");
  });

  it("reads, withdraws and declines one share", async () => {
    await sharingClient.get("s-1");
    await sharingClient.revoke("s-1");
    await sharingClient.decline("s-1");
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/shares/s-1");
    expect(request).toHaveBeenNthCalledWith(2, "DELETE", "/api/brain/shares/s-1");
    expect(request).toHaveBeenNthCalledWith(3, "POST", "/api/brain/shares/s-1/decline");
  });

  it("accepts with the title and folder the person chose, or with nothing", async () => {
    await sharingClient.accept("s-1", { title: "Tea", folder: "shared" });
    await sharingClient.accept("s-1");
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/brain/shares/s-1/accept", { title: "Tea", folder: "shared" });
    expect(request).toHaveBeenNthCalledWith(2, "POST", "/api/brain/shares/s-1/accept", {});
  });

  it("lists, adds and removes blocks", async () => {
    request.mockResolvedValueOnce({ blocks: [{ uid: "u1" }] } as never).mockResolvedValueOnce({ blocks: [{ uid: "u2" }] } as never);
    expect(await sharingClient.blocks()).toEqual([{ uid: "u1" }]);
    expect(await sharingClient.block("bo")).toEqual([{ uid: "u2" }]);
    await sharingClient.unblock("u/2");
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/blocks");
    expect(request).toHaveBeenNthCalledWith(2, "PUT", "/api/brain/blocks", { username: "bo" });
    expect(request).toHaveBeenNthCalledWith(3, "DELETE", "/api/brain/blocks/u%2F2");
  });

  it("encodes a share id", async () => {
    await sharingClient.get("a/b");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/brain/shares/a%2Fb");
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run (from `apps/ember`): `pnpm exec vitest run src/features/sharing/api/SharingClient.test.ts`
Expected: FAIL, the module `./SharingClient` does not exist.

- [x] **Step 3: Write the client**

```ts
import { apiRequest } from "../../../api/http";

export type ShareKind = "file" | "section" | "skill" | "stack_item";
export type ShareStatus = "pending" | "accepted" | "declined" | "revoked" | "rejected";

/** One share as the lists show it. The text is not in it. Times are `...Z` strings. */
export interface Share {
  id: string;
  kind: ShareKind;
  title: string;
  status: ShareStatus;
  /** The sender's username. */
  sender: string;
  /** The recipient's username, or "global brain". */
  recipient: string;
  created_at: string;
  decided_at: string | null;
  /** What the share became once accepted: a file id or a skill id. */
  result_id: string | null;
  chars: number;
}

/** One share with its text, for the person who sent or received it. The text is another account's: untrusted. */
export interface ShareDetail extends Share {
  body: string;
  skill: { when_to_use: string; steps: string; tools: string } | null;
  /** The server's sentence about untrusted text. */
  notice: string;
}

export interface Block {
  uid: string;
  username: string;
  created_at: string;
}

/** What is shared. */
export type ShareWhat =
  | { kind: "file"; file_id: string }
  | { kind: "section"; file_id: string; heading: string }
  | { kind: "skill"; skill_id: number }
  | { kind: "stack_item"; chat_id: string; item_id: number };

/** Who gets it: one account by username, or the global brain's review queue. */
export type Recipient = { recipient: string } | { to_global: true };

export type NewShare = ShareWhat & Recipient;

/** Where an accepted file lands. A skill takes only the title. */
export interface Landing {
  title?: string;
  folder?: string;
}

export const SHARE_NAME_MAX = 80;

const path = (id: string) => `/api/brain/shares/${encodeURIComponent(id)}`;

/** Portcullis's /api/brain/shares and /api/brain/blocks routes (chat.use), passed on to Stronghold. */
export const sharingClient = {
  create: (share: NewShare) => apiRequest<Share>("POST", "/api/brain/shares", share),
  /** Waiting for the person's answer, newest first. */
  inbox: async () => (await apiRequest<{ shares: Share[] }>("GET", "/api/brain/shares/inbox")).shares,
  /** Everything the person sent, newest first, with its status. */
  sent: async () => (await apiRequest<{ shares: Share[] }>("GET", "/api/brain/shares/sent")).shares,
  get: (id: string) => apiRequest<ShareDetail>("GET", path(id)),
  /** The sender takes a share back before it is decided. */
  revoke: (id: string) => apiRequest<Share>("DELETE", path(id)),
  accept: (id: string, landing: Landing = {}) => apiRequest<Share>("POST", `${path(id)}/accept`, landing),
  decline: (id: string) => apiRequest<Share>("POST", `${path(id)}/decline`),
  blocks: async () => (await apiRequest<{ blocks: Block[] }>("GET", "/api/brain/blocks")).blocks,
  /** Blocking also declines what that account already sent. */
  block: async (username: string) => (await apiRequest<{ blocks: Block[] }>("PUT", "/api/brain/blocks", { username })).blocks,
  unblock: (uid: string) => apiRequest<void>("DELETE", `/api/brain/blocks/${encodeURIComponent(uid)}`),
};
```

- [x] **Step 4: Run the test to verify it passes**

Run: `pnpm exec vitest run src/features/sharing/api/SharingClient.test.ts`
Expected: PASS (6 tests).

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/sharing/api/SharingClient.ts apps/ember/src/features/sharing/api/SharingClient.test.ts
git commit -m "feat(ember): API client for sharing and blocks"
```

---

### Task 2: Sharing store

**Files:**
- Create: `apps/ember/src/features/sharing/stores/sharing.ts`
- Test: `apps/ember/src/features/sharing/stores/sharing.test.ts`

**Interfaces:**
- Consumes: `sharingClient` and types (Task 1); `useAuthStore().account`; `errorMessage`.
- Produces: `useSharingStore()` with refs `status` (`"idle" | "loading" | "ready" | "error"`), `error`, `inbox` (`Share[]`), `sent` (`Share[]`), `blocks` (`Block[]`); actions `load()`, `create(share)`, `accept(id, landing?)`, `decline(id)`, `revoke(id)`, `block(username)`, `unblock(uid)`, `forget()`. Every mutating action resolves with what the client resolved (`create`, `accept`, `decline`, `revoke` the `Share`) and rethrows the `ApiError` so a dialog can show the server's reason. After a success the three lists are loaded again.

- [x] **Step 1: Write the failing test**

```ts
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { sharingClient, type Block, type Share } from "../api/SharingClient";
import { useSharingStore } from "./sharing";

vi.mock("../api/SharingClient", () => ({
  sharingClient: {
    create: vi.fn(), inbox: vi.fn(), sent: vi.fn(), get: vi.fn(), revoke: vi.fn(), accept: vi.fn(), decline: vi.fn(),
    blocks: vi.fn(), block: vi.fn(), unblock: vi.fn(),
  },
}));

const client = vi.mocked(sharingClient);

const share = (id: string, extra: Partial<Share> = {}): Share => ({
  id, kind: "file", title: `share ${id}`, status: "pending", sender: "bo", recipient: "me",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 5, ...extra,
});
const block = (uid: string): Block => ({ uid, username: `user ${uid}`, created_at: "2026-01-01T00:00:00Z" });

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useSharingStore() };
}

const later = <T>() => {
  let done!: (value: T) => void;
  const promise = new Promise<T>((resolve) => { done = resolve; });
  return { promise, done };
};

beforeEach(() => {
  vi.clearAllMocks();
  client.inbox.mockResolvedValue([share("a"), share("b")]);
  client.sent.mockResolvedValue([share("s1", { sender: "me", recipient: "bo" })]);
  client.blocks.mockResolvedValue([block("u1")]);
});

describe("load", () => {
  it("shows the inbox, the sent shares and the blocks", async () => {
    const { store } = setup();
    expect(store.status).toBe("idle");
    const loading = store.load();
    expect(store.status).toBe("loading");
    await loading;
    expect(store.status).toBe("ready");
    expect(store.inbox.map((s) => s.id)).toEqual(["a", "b"]);
    expect(store.sent.map((s) => s.id)).toEqual(["s1"]);
    expect(store.blocks.map((b) => b.uid)).toEqual(["u1"]);
  });

  it("does nothing without an account", async () => {
    const { auth, store } = setup();
    auth.account = null;
    await store.load();
    expect(client.inbox).not.toHaveBeenCalled();
  });

  it("a first failure is an error state; a later one keeps the lists", async () => {
    const { store } = setup();
    client.inbox.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("error");
    expect(store.error).toBe("Storage is unavailable");
    await store.load();
    client.sent.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.inbox).toHaveLength(2);
    expect(store.error).toBe("Storage is unavailable");
  });

  it("a newer load wins over an older reply that arrives late", async () => {
    const { store } = setup();
    const slow = later<Share[]>();
    client.inbox.mockReturnValueOnce(slow.promise);
    const first = store.load();
    client.inbox.mockResolvedValueOnce([share("new")]);
    await store.load();
    slow.done([share("old")]);
    await first;
    expect(store.inbox.map((s) => s.id)).toEqual(["new"]);
  });

  it("a reply that arrives after forget shows nothing", async () => {
    const { store } = setup();
    const slow = later<Share[]>();
    client.inbox.mockReturnValueOnce(slow.promise);
    const loading = store.load();
    store.forget();
    slow.done([share("late")]);
    await loading;
    expect(store.inbox).toEqual([]);
    expect(store.status).toBe("idle");
  });
});

describe("changes", () => {
  it("create sends the share, returns it and looks again", async () => {
    const { store } = setup();
    await store.load();
    client.create.mockResolvedValue(share("n", { recipient: "bo" }));
    const made = await store.create({ kind: "file", file_id: "f1", recipient: "bo" });
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "file", file_id: "f1", recipient: "bo" });
    expect(made.id).toBe("n");
    expect(client.sent).toHaveBeenCalledTimes(2);
  });

  it("accept passes the landing, decline and revoke pass the id, and each looks again", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockResolvedValue(share("a", { status: "accepted", result_id: "f9" }));
    client.decline.mockResolvedValue(share("b", { status: "declined" }));
    client.revoke.mockResolvedValue(share("s1", { status: "revoked" }));
    expect((await store.accept("a", { title: "Tea", folder: "shared" })).result_id).toBe("f9");
    await store.decline("b");
    await store.revoke("s1");
    expect(client.accept).toHaveBeenCalledExactlyOnceWith("a", { title: "Tea", folder: "shared" });
    expect(client.decline).toHaveBeenCalledExactlyOnceWith("b");
    expect(client.revoke).toHaveBeenCalledExactlyOnceWith("s1");
    expect(client.inbox).toHaveBeenCalledTimes(4);
  });

  it("a refused change passes the server's reason on and changes nothing", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockRejectedValue(new ApiError(409, "You have reached the limit of 500 files."));
    await expect(store.accept("a", {})).rejects.toMatchObject({ status: 409, message: "You have reached the limit of 500 files." });
    expect(store.inbox).toHaveLength(2);
    expect(client.inbox).toHaveBeenCalledTimes(1);
  });

  it("block and unblock call the server and look again", async () => {
    const { store } = setup();
    await store.load();
    client.block.mockResolvedValue([block("u1"), block("u2")]);
    await store.block("bo");
    expect(client.block).toHaveBeenCalledExactlyOnceWith("bo");
    client.unblock.mockResolvedValue(undefined);
    await store.unblock("u2");
    expect(client.unblock).toHaveBeenCalledExactlyOnceWith("u2");
    expect(client.blocks).toHaveBeenCalledTimes(3);
  });

  it("a change that finishes after forget does not bring the lists back", async () => {
    const { store } = setup();
    await store.load();
    const slow = later<Share>();
    client.decline.mockReturnValueOnce(slow.promise);
    const declining = store.decline("a");
    store.forget();
    slow.done(share("a", { status: "declined" }));
    await declining;
    expect(store.inbox).toEqual([]);
    expect(client.inbox).toHaveBeenCalledTimes(1);
  });
});

describe("private data", () => {
  it("signing out clears everything", async () => {
    const { auth, store } = setup();
    await store.load();
    auth.account = null;
    expect(store.inbox).toEqual([]);
    expect(store.sent).toEqual([]);
    expect(store.blocks).toEqual([]);
    expect(store.status).toBe("idle");
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pnpm exec vitest run src/features/sharing/stores/sharing.test.ts`
Expected: FAIL, the module `./sharing` does not exist.

- [x] **Step 3: Write the store**

```ts
import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { sharingClient, type Block, type Landing, type NewShare, type Share } from "../api/SharingClient";

/** What the account sent, what waits for its answer and whom it blocked, as the server holds them. The text of a
 * share is not kept here (the review dialog asks for it). Everything is private: `forget()` and a change of account
 * drop it, and a reply that arrives after that, or after a newer load, is ignored. Changes show only after the
 * server answered; every success looks at the three lists again. */
export const useSharingStore = defineStore("sharing", () => {
  const auth = useAuthStore();
  const status = ref<"idle" | "loading" | "ready" | "error">("idle");
  const error = ref("");
  const inbox = ref<Share[]>([]);
  const sent = ref<Share[]>([]);
  const blocks = ref<Block[]>([]);
  let loads = 0;
  let epoch = 0; // raised by forget(): a change that started before it must not write after it

  async function load(): Promise<void> {
    if (!auth.account) return;
    const run = ++loads;
    if (status.value !== "ready") status.value = "loading";
    try {
      const [received, delivered, blocked] = await Promise.all([sharingClient.inbox(), sharingClient.sent(), sharingClient.blocks()]);
      if (run !== loads) return;
      inbox.value = received;
      sent.value = delivered;
      blocks.value = blocked;
      status.value = "ready";
      error.value = "";
    } catch (err) {
      if (run !== loads) return;
      error.value = errorMessage(err);
      status.value = status.value === "ready" ? "ready" : "error";
    }
  }

  /** Runs a change. Errors go to the caller, who shows the server's reason. */
  async function change<T>(work: () => Promise<T>): Promise<T> {
    const started = epoch;
    const result = await work();
    if (started === epoch) await load();
    return result;
  }

  const create = (share: NewShare) => change(() => sharingClient.create(share));
  const accept = (id: string, landing?: Landing) => change(() => sharingClient.accept(id, landing));
  const decline = (id: string) => change(() => sharingClient.decline(id));
  const revoke = (id: string) => change(() => sharingClient.revoke(id));
  const block = (username: string) => change(() => sharingClient.block(username));
  const unblock = (uid: string) => change(() => sharingClient.unblock(uid));

  function forget(): void {
    epoch++;
    loads++;
    status.value = "idle";
    error.value = "";
    inbox.value = [];
    sent.value = [];
    blocks.value = [];
  }

  watch(() => auth.account?.id, forget, { flush: "sync" });

  return { status, error, inbox, sent, blocks, load, create, accept, decline, revoke, block, unblock, forget };
});
```

- [x] **Step 4: Run the test to verify it passes**

Run: `pnpm exec vitest run src/features/sharing/stores/sharing.test.ts`
Expected: PASS. If `watch` on `auth.account?.id` does not fire for `auth.account = null` the way it does in `features/notes/stores/brain.ts` (Plan 20f), copy that watch exactly.

- [x] **Step 5: Commit**

```bash
git add apps/ember/src/features/sharing/stores/sharing.ts apps/ember/src/features/sharing/stores/sharing.test.ts
git commit -m "feat(ember): store for shares and blocks with late replies ignored"
```

---

### Task 3: Section headings and the share dialog

**Files:**
- Create: `apps/ember/src/features/sharing/utils/headings.ts`, `headings.test.ts`
- Create: `apps/ember/src/features/sharing/components/ShareDialog.vue`, `ShareDialog.test.ts`

**Interfaces:**
- Consumes: Tasks 1 and 2; `BaseModal` (assumption (d)).
- Produces: `headingsOf(body: string): string[]` (the headings of a Markdown text that can be shared as a section, in order, first of each); `ShareDialog` with props `open: boolean` and `target: ShareTarget | null`, emitting `close`; type `ShareTarget`:

```ts
export type ShareTarget =
  | { kind: "file"; fileId: string; label: string; headings: string[] }
  | { kind: "skill"; skillId: number; label: string }
  | { kind: "stack_item"; chatId: string; itemId: number; label: string };
```

  `ShareTarget` is exported from `ShareDialog.vue` through a `<script lang="ts">` block next to `<script setup>`, or from a small `components/shareTarget.ts` file; choose the one the repo already uses for shared types and record it.

- [x] **Step 1: Write the failing headings test**

```ts
import { describe, expect, it } from "vitest";
import { headingsOf } from "./headings";

describe("headingsOf", () => {
  it("lists the headings in order, at any level", () => {
    expect(headingsOf("# One\ntext\n## Two\n### Three")).toEqual(["One", "Two", "Three"]);
  });

  it("needs a space after the marks", () => {
    expect(headingsOf("#hashtag\n####### seven\n# Real")).toEqual(["Real"]);
  });

  it("drops closing marks and extra spaces", () => {
    expect(headingsOf("##   Brewing   tea  ##")).toEqual(["Brewing tea"]);
  });

  it("skips headings inside fenced code, however the fence is written", () => {
    const body = "# A\n```\n# not one\n```\n~~~js\n# nor this\n~~~\n## B\n````\n```\n# still code\n````\n# C";
    expect(headingsOf(body)).toEqual(["A", "B", "C"]);
  });

  it("keeps the first of repeated headings, ignoring case and spacing", () => {
    expect(headingsOf("# Notes\n## notes\n#  NOTES \n# Other")).toEqual(["Notes", "Other"]);
  });

  it("copes with Windows line ends and an empty text", () => {
    expect(headingsOf("# One\r\ntext\r\n## Two\r\n")).toEqual(["One", "Two"]);
    expect(headingsOf("")).toEqual([]);
  });
});
```

- [x] **Step 2: Run it to verify it fails**

Run: `pnpm exec vitest run src/features/sharing/utils/headings.test.ts`
Expected: FAIL, `./headings` does not exist.

- [x] **Step 3: Write `headings.ts`**

```ts
const HEADING = /^(#{1,6})[ \t]+(.+?)[ \t#]*$/;
const FENCE = /^(`{3,}|~{3,})(.*)/;

/** The headings of a Markdown text that can be shared as a section, in order: the first of each (the server cuts the
 * section at the first heading that matches, ignoring case and spacing). Same rules as `extract_section` in
 * apps/stronghold/src/brain/fragments.py: `#` to `######` and a space, outside fenced code. */
export function headingsOf(body: string): string[] {
  const seen = new Set<string>();
  const found: string[] = [];
  let fence = "";
  for (const raw of body.split("\n")) {
    const line = raw.replace(/\r$/, "");
    const marker = FENCE.exec(line.trimStart());
    if (fence) {
      if (marker && marker[1]![0] === fence[0] && marker[1]!.length >= fence.length && marker[2]!.trim() === "") fence = "";
      continue;
    }
    if (marker) {
      fence = marker[1]!;
      continue;
    }
    const heading = HEADING.exec(line);
    if (!heading) continue;
    const text = heading[2]!.split(/\s+/).filter(Boolean).join(" ");
    const key = text.toLowerCase();
    if (text && !seen.has(key)) {
      seen.add(key);
      found.push(text);
    }
  }
  return found;
}
```

- [x] **Step 4: Run it to verify it passes**

Run: `pnpm exec vitest run src/features/sharing/utils/headings.test.ts`
Expected: PASS (6 tests). Compare the rules with `fragments.py` once more (assumption (c)) and record the result.

- [x] **Step 5: Write the failing ShareDialog test**

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { sharingClient, type Share } from "../api/SharingClient";
import ShareDialog, { type ShareTarget } from "./ShareDialog.vue";

vi.mock("../api/SharingClient", () => ({
  sharingClient: {
    create: vi.fn(), inbox: vi.fn().mockResolvedValue([]), sent: vi.fn().mockResolvedValue([]), blocks: vi.fn().mockResolvedValue([]),
  },
}));

const client = vi.mocked(sharingClient);
const sentShare = (recipient: string): Share => ({
  id: "s1", kind: "file", title: "Tea", status: "pending", sender: "me", recipient,
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 3,
});
const file: ShareTarget = { kind: "file", fileId: "f1", label: "Tea notes", headings: ["Brewing", "Storage"] };

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.inbox.mockResolvedValue([]);
  client.sent.mockResolvedValue([]);
  client.blocks.mockResolvedValue([]);
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

async function mountDialog(target: ShareTarget = file, open = true) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(ShareDialog, { props: { open, target }, attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const send = (w: VueWrapper) => w.findAll("button").find((b) => b.text() === "Send")!;
const toAccount = (w: VueWrapper, name: string) => w.get('input[aria-label="Username"]').setValue(name);

describe("ShareDialog", () => {
  it("says what is shared and that it is a copy the other side decides about", async () => {
    const w = await mountDialog();
    expect(w.text()).toContain("Tea notes");
    expect(w.text()).toContain("a copy");
    expect(w.text()).toContain("withdraw");
  });

  it("sends a whole file to an account and then says who has it", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const w = await mountDialog();
    expect(send(w).attributes("disabled")).toBeDefined();
    await toAccount(w, "  bo ");
    await send(w).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "file", file_id: "f1", recipient: "bo" });
    expect(w.text()).toContain("Sent to bo.");
  });

  it("sends one section when that is chosen", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const w = await mountDialog();
    await w.get('input[type="radio"][value="section"]').setValue(true);
    await w.get("select").setValue("Storage");
    await toAccount(w, "bo");
    await send(w).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "section", file_id: "f1", heading: "Storage", recipient: "bo" });
  });

  it("offers no section choice for a file without headings", async () => {
    const w = await mountDialog({ ...file, headings: [] });
    expect(w.find('input[type="radio"][value="section"]').exists()).toBe(false);
  });

  it("sends to the global brain without a username and says it is reviewed first", async () => {
    client.create.mockResolvedValue(sentShare("global brain"));
    const w = await mountDialog();
    await w.get('input[type="radio"][value="global"]').setValue(true);
    expect(w.text()).toContain("reviewed");
    expect(w.find('input[aria-label="Username"]').exists()).toBe(false);
    await send(w).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "file", file_id: "f1", to_global: true });
    expect(w.text()).toContain("review queue");
  });

  it("sends a skill and a short-term item", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const skill = await mountDialog({ kind: "skill", skillId: 7, label: "Reboot an app" });
    await toAccount(skill, "bo");
    await send(skill).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenLastCalledWith({ kind: "skill", skill_id: 7, recipient: "bo" });
    skill.unmount();
    const item = await mountDialog({ kind: "stack_item", chatId: "c-1", itemId: 4, label: "a short-term item" });
    await toAccount(item, "bo");
    await send(item).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenLastCalledWith({ kind: "stack_item", chat_id: "c-1", item_id: 4, recipient: "bo" });
  });

  it("shows the server's reason as it came, keeps the form, and sends nothing twice", async () => {
    client.create.mockRejectedValue(new ApiError(404, "No such recipient."));
    const w = await mountDialog();
    await toAccount(w, "nobody");
    await send(w).trigger("click");
    await flushPromises();
    expect(w.get('[role="alert"]').text()).toBe("No such recipient.");
    expect((w.get('input[aria-label="Username"]').element as HTMLInputElement).value).toBe("nobody");
    expect(client.create).toHaveBeenCalledTimes(1);
  });

  it("ignores a second press while the first is on its way", async () => {
    let finish!: (share: Share) => void;
    client.create.mockReturnValue(new Promise<Share>((resolve) => { finish = resolve; }));
    const w = await mountDialog();
    await toAccount(w, "bo");
    await send(w).trigger("click");
    await send(w).trigger("click");
    expect(client.create).toHaveBeenCalledTimes(1);
    finish(sentShare("bo"));
    await flushPromises();
  });

  it("asks to close from the close button", async () => {
    const w = await mountDialog();
    await w.get('button[aria-label="Close"]').trigger("click");
    expect(w.emitted("close")).toHaveLength(1);
  });

  it("starts clean when it opens again", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const w = await mountDialog();
    await toAccount(w, "bo");
    await send(w).trigger("click");
    await flushPromises();
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    await flushPromises();
    expect(w.text()).not.toContain("Sent to bo.");
    expect((w.get('input[aria-label="Username"]').element as HTMLInputElement).value).toBe("");
  });
});
```

- [x] **Step 6: Run it to verify it fails**

Run: `pnpm exec vitest run src/features/sharing/components/ShareDialog.test.ts`
Expected: FAIL, `./ShareDialog.vue` does not exist.

- [x] **Step 7: Write `ShareDialog.vue`**

```vue
<script lang="ts">
export type ShareTarget =
  | { kind: "file"; fileId: string; label: string; headings: string[] }
  | { kind: "skill"; skillId: number; label: string }
  | { kind: "stack_item"; chatId: string; itemId: number; label: string };
</script>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import { errorMessage } from "../../../utils/errors";
import { SHARE_NAME_MAX, type NewShare, type Recipient, type Share } from "../api/SharingClient";
import { useSharingStore } from "../stores/sharing";

/** Send a copy of one thing to another account or to the global brain. Nothing is sent until Send is pressed. The
 * recipient (or, for the global brain, a reviewer) decides whether to keep it; the sender can withdraw it until then.
 * Render this only while there is a target (`v-if`): it needs the sharing store. */
const props = defineProps<{ open: boolean; target: ShareTarget | null }>();
const emit = defineEmits<{ close: [] }>();

const store = useSharingStore();
const mode = ref<"account" | "global">("account");
const username = ref("");
const what = ref<"file" | "section">("file");
const heading = ref("");
const sending = ref(false);
const error = ref("");
const done = ref<Share | null>(null);
let run = 0; // an answer that arrives after the dialog was closed or reopened is dropped

function reset(): void {
  run++;
  mode.value = "account";
  username.value = "";
  what.value = "file";
  heading.value = props.target?.kind === "file" ? (props.target.headings[0] ?? "") : "";
  sending.value = false;
  error.value = "";
  done.value = null;
}
watch(() => props.open, (isOpen) => { if (isOpen) reset(); }, { immediate: true });
watch(() => props.target, reset);

const headings = computed(() => (props.target?.kind === "file" ? props.target.headings : []));
const valid = computed(() => mode.value === "global" || username.value.trim() !== "");

function request(): NewShare | null {
  const target = props.target;
  if (!target) return null;
  const to: Recipient = mode.value === "global" ? { to_global: true } : { recipient: username.value.trim() };
  if (target.kind === "file") {
    return what.value === "section" && heading.value
      ? { kind: "section", file_id: target.fileId, heading: heading.value, ...to }
      : { kind: "file", file_id: target.fileId, ...to };
  }
  if (target.kind === "skill") return { kind: "skill", skill_id: target.skillId, ...to };
  return { kind: "stack_item", chat_id: target.chatId, item_id: target.itemId, ...to };
}

async function send(): Promise<void> {
  const share = request();
  if (!share || !valid.value || sending.value) return;
  const mine = run;
  sending.value = true;
  error.value = "";
  try {
    const made = await store.create(share);
    if (mine === run) done.value = made;
  } catch (err) {
    if (mine === run) error.value = errorMessage(err);
  } finally {
    if (mine === run) sending.value = false;
  }
}
</script>

<template>
  <BaseModal :open="open" title="Share a copy" @close="emit('close')">
    <template v-if="target">
      <div v-if="done" class="result" role="status">
        <p v-if="done.recipient === 'global brain'">Sent to the global brain review queue. A reviewer decides; if it is approved, every account and its agents can read it. You can withdraw it from Shares until then.</p>
        <p v-else>Sent to {{ done.recipient }}. They can keep or decline it. You can withdraw it from Shares until they answer.</p>
        <div class="buttons"><button type="button" class="pill-btn primary" @click="emit('close')">Close</button></div>
      </div>
      <form v-else class="share-form" @submit.prevent="send">
        <p>You are sharing a copy of <strong>{{ target.label }}</strong>. Later changes to the original are not sent.</p>
        <fieldset v-if="headings.length" class="group" :disabled="sending">
          <legend>What to share</legend>
          <label><input v-model="what" type="radio" name="what" value="file" /> Whole file</label>
          <label><input v-model="what" type="radio" name="what" value="section" /> One section</label>
          <select v-if="what === 'section'" v-model="heading" aria-label="Section">
            <option v-for="name in headings" :key="name" :value="name">{{ name }}</option>
          </select>
        </fieldset>
        <fieldset class="group" :disabled="sending">
          <legend>Who gets it</legend>
          <label><input v-model="mode" type="radio" name="who" value="account" /> Another account</label>
          <input v-if="mode === 'account'" v-model="username" type="text" aria-label="Username" placeholder="Their username" :maxlength="SHARE_NAME_MAX" autocomplete="off" />
          <label><input v-model="mode" type="radio" name="who" value="global" /> The global brain</label>
        </fieldset>
        <p v-if="mode === 'global'" class="note" role="note">Global shares are reviewed first. If approved, every account and every agent can read the text. Do not share private data.</p>
        <p v-else class="note" role="note">They see the text and choose whether to keep it. Tags and links to your private files are removed. You can withdraw it from Shares until they answer.</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="buttons">
          <button type="button" class="pill-btn ghost" :disabled="sending" @click="emit('close')">Cancel</button>
          <button type="submit" class="pill-btn primary" :disabled="!valid || sending" :aria-busy="sending">Send</button>
        </div>
      </form>
    </template>
  </BaseModal>
</template>

<style scoped>
.share-form, .result { display: flex; flex-direction: column; gap: 14px; }
p { margin: 0; overflow-wrap: anywhere; }
.group { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.group legend { padding: 0 6px; font-size: .85em; color: var(--muted); }
.group label { display: flex; align-items: center; gap: 8px; }
.group input[type="text"], .group select { width: 100%; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.note { font-size: .85em; color: var(--muted); }
.buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
@media (max-width: 767px) {
  .group label, .buttons button { min-height: 44px; }
  .group input[type="text"], .group select { min-height: 44px; font-size: max(1em, 16px); }
}
</style>
```

- [x] **Step 8: Run both test files, the radius test and the type check**

Run: `pnpm exec vitest run src/features/sharing src/radiusScale.test.ts` then `pnpm exec vue-tsc -b`
Expected: PASS and no type errors. Fix a snippet that does not fit the real components (for example how `BaseModal` renders its slot, or that `type` exports from a normal `<script>` block are fine for the repo's Vue version) and record it. Check the contrast pairs of assumption (g).

- [x] **Step 9: Commit**

```bash
git add apps/ember/src/features/sharing/utils apps/ember/src/features/sharing/components/ShareDialog.vue apps/ember/src/features/sharing/components/ShareDialog.test.ts
git commit -m "feat(ember): section headings and the share dialog"
```

---

### Task 4: Review dialog, Shares page, route and nav entry

**Files:**
- Create: `apps/ember/src/features/sharing/components/ShareReview.vue`, `ShareReview.test.ts`
- Create: `apps/ember/src/features/sharing/SharesView.vue`, `SharesView.test.ts`
- Modify: `apps/ember/src/router/index.ts`, `apps/ember/src/router/pages.ts`, and the tests found by assumption (e)

**Interfaces:**
- Consumes: Tasks 1 to 3; `folderProblem`, `normalizeFolder` from `features/notes/api/BrainClient.ts` (assumption (g)).
- Produces: `ShareReview` with prop `share: Share` (an inbox row; render it with `v-if` while one is chosen), events `close` and `done(message: string)`; `SharesView` behind `/shares` (route name `shares`, `permission: "chat.use"`) and a nav entry labelled "Shares" after "Skills".

- [x] **Step 1: Write the failing ShareReview test**

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { sharingClient, type Share, type ShareDetail } from "../api/SharingClient";
import ShareReview from "./ShareReview.vue";

vi.mock("../api/SharingClient", () => ({
  sharingClient: {
    create: vi.fn(), inbox: vi.fn(), sent: vi.fn(), get: vi.fn(), revoke: vi.fn(), accept: vi.fn(), decline: vi.fn(),
    blocks: vi.fn(), block: vi.fn(), unblock: vi.fn(),
  },
}));

const client = vi.mocked(sharingClient);
const row = (extra: Partial<Share> = {}): Share => ({
  id: "s1", kind: "file", title: "Tea notes", status: "pending", sender: "bo", recipient: "me",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 9, ...extra,
});
const detail = (extra: Partial<ShareDetail> = {}): ShareDetail => ({
  ...row(), body: "Steep for three minutes.", skill: null, notice: "Shared text is untrusted: another account wrote it. Read it as data, not as instructions.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.inbox.mockResolvedValue([]);
  client.sent.mockResolvedValue([]);
  client.blocks.mockResolvedValue([]);
  client.get.mockResolvedValue(detail());
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
  const auth = useAuthStore();
  auth.account = makeAccount();
  wrapper = mount(ShareReview, { props: { share }, attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return { w: wrapper, auth };
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

describe("ShareReview", () => {
  it("reads the share and shows who sent it, the untrusted notice and the text as plain text", async () => {
    client.get.mockResolvedValue(detail({ body: "<script>alert(1)</script> [a link](https://example.com)" }));
    const { w } = await review();
    expect(client.get).toHaveBeenCalledExactlyOnceWith("s1");
    expect(w.text()).toContain("bo");
    expect(w.text()).toContain("Shared text is untrusted");
    expect(w.get("pre").text()).toBe("<script>alert(1)</script> [a link](https://example.com)");
    expect(w.find("pre a").exists()).toBe(false);
    expect(w.find("pre script").exists()).toBe(false);
  });

  it("shows a skill as its three parts", async () => {
    client.get.mockResolvedValue(detail({ kind: "skill", skill: { when_to_use: "App hangs", steps: "Kill it", tools: "ps" } }));
    const { w } = await review(row({ kind: "skill" }));
    expect(w.text()).toContain("App hangs");
    expect(w.text()).toContain("Kill it");
    expect(w.text()).toContain("ps");
    expect(w.find('input[aria-label="Folder"]').exists()).toBe(false);
  });

  it("explains why it cannot be read, and changes nothing", async () => {
    client.get.mockRejectedValue(new ApiError(404, "No such share."));
    const { w } = await review();
    expect(w.get('[role="alert"]').text()).toBe("No such share.");
    expect(button(w, "Keep a copy").attributes("disabled")).toBeDefined();
  });

  it("keeps a copy with the title and folder the person chose", async () => {
    client.accept.mockResolvedValue(row({ status: "accepted", result_id: "f9" }));
    const { w } = await review();
    expect((w.get('input[aria-label="Folder"]').element as HTMLInputElement).value).toBe("shared");
    await w.get('input[aria-label="Title"]').setValue("Green tea");
    await w.get('input[aria-label="Folder"]').setValue("Food / Tea");
    await button(w, "Keep a copy").trigger("click");
    await flushPromises();
    expect(client.accept).toHaveBeenCalledExactlyOnceWith("s1", { title: "Green tea", folder: "food/tea" });
    expect(w.emitted("done")![0]![0]).toContain("Notes page");
  });

  it("keeps a skill with only a title, and says it waits for approval", async () => {
    client.get.mockResolvedValue(detail({ kind: "skill", skill: { when_to_use: "a", steps: "b", tools: "" } }));
    client.accept.mockResolvedValue(row({ kind: "skill", status: "accepted", result_id: "4" }));
    const { w } = await review(row({ kind: "skill" }));
    await button(w, "Keep a copy").trigger("click");
    await flushPromises();
    expect(client.accept).toHaveBeenCalledExactlyOnceWith("s1", { title: "Tea notes" });
    expect(w.emitted("done")![0]![0]).toContain("Skills page");
  });

  it("a folder the server would refuse keeps Keep off and says why", async () => {
    const { w } = await review();
    await w.get('input[aria-label="Folder"]').setValue("a/b/c/d");
    expect(button(w, "Keep a copy").attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("A folder is up to 3 levels");
  });

  it("shows the server's reason when keeping is refused, and stays open", async () => {
    client.accept.mockRejectedValue(new ApiError(409, "You have reached the limit of 500 files."));
    const { w } = await review();
    await button(w, "Keep a copy").trigger("click");
    await flushPromises();
    expect(w.get('[role="alert"]').text()).toBe("You have reached the limit of 500 files.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("declines, and blocks the sender", async () => {
    client.decline.mockResolvedValue(row({ status: "declined" }));
    client.block.mockResolvedValue([]);
    const { w } = await review();
    await button(w, "Decline").trigger("click");
    await flushPromises();
    expect(client.decline).toHaveBeenCalledExactlyOnceWith("s1");
    expect(w.emitted("done")![0]![0]).toBe("Declined.");
    await button(w, "Block sender").trigger("click");
    await flushPromises();
    expect(client.block).toHaveBeenCalledExactlyOnceWith("bo");
    expect(w.emitted("done")![1]![0]).toContain("Blocked bo");
  });

  it("closes without changing anything, and closes itself when the account changes", async () => {
    const { w, auth } = await review();
    await button(w, "Close").trigger("click");
    expect(w.emitted("close")).toHaveLength(1);
    expect(client.accept).not.toHaveBeenCalled();
    expect(client.decline).not.toHaveBeenCalled();
    auth.account = null;
    await flushPromises();
    expect(w.emitted("close")).toHaveLength(2);
  });
});
```

- [x] **Step 2: Run it to verify it fails**

Run: `pnpm exec vitest run src/features/sharing/components/ShareReview.test.ts`
Expected: FAIL, `./ShareReview.vue` does not exist.

- [x] **Step 3: Write `ShareReview.vue`**

```vue
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import { folderProblem, normalizeFolder } from "../../notes/api/BrainClient";
import { sharingClient, type Share, type ShareDetail, type ShareKind } from "../api/SharingClient";
import { useSharingStore } from "../stores/sharing";

/** What arrived: who sent it, the text as plain text, and the three answers (keep a copy, decline, block the sender).
 * Opening it changes nothing. Render it only while a share is chosen (`v-if`). The text is another account's, so it is
 * never shown as markup and is dropped when this closes. */
const props = defineProps<{ share: Share }>();
const emit = defineEmits<{ close: []; done: [message: string] }>();

const KIND: Record<ShareKind, string> = { file: "File", section: "Section of a file", skill: "Skill", stack_item: "Short-term memory item" };

const store = useSharingStore();
const auth = useAuthStore();
const detail = ref<ShareDetail | null>(null);
const loadError = ref("");
const title = ref(props.share.title);
const folder = ref("shared");
const busy = ref(false);
const error = ref("");
let closed = false;

const isSkill = computed(() => props.share.kind === "skill");
const cleanFolder = computed(() => normalizeFolder(folder.value));
const problem = computed(() => (isSkill.value ? "" : folderProblem(cleanFolder.value)));
const canKeep = computed(() => detail.value !== null && title.value.trim() !== "" && problem.value === "" && !busy.value);

onMounted(async () => {
  try {
    const found = await sharingClient.get(props.share.id);
    if (closed) return;
    detail.value = found;
    title.value = found.title;
  } catch (err) {
    if (!closed) loadError.value = errorMessage(err);
  }
});
onBeforeUnmount(() => { closed = true; detail.value = null; });
watch(() => auth.account?.id, () => emit("close"));

async function answer(work: () => Promise<string>): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const message = await work();
    if (!closed) emit("done", message);
  } catch (err) {
    if (!closed) error.value = errorMessage(err);
  } finally {
    if (!closed) busy.value = false;
  }
}

const keep = () => answer(async () => {
  const landing = isSkill.value ? { title: title.value.trim() } : { title: title.value.trim(), folder: cleanFolder.value };
  await store.accept(props.share.id, landing);
  return isSkill.value
    ? "Kept as a proposed skill. Approve it on the Skills page before it is used."
    : `Kept as a file${cleanFolder.value ? ` in ${cleanFolder.value}` : ""}. Open it on the Notes page.`;
});
const decline = () => answer(async () => { await store.decline(props.share.id); return "Declined."; });
const blockSender = () => answer(async () => {
  await store.block(props.share.sender);
  return `Blocked ${props.share.sender}. Their waiting shares were declined.`;
});
</script>

<template>
  <BaseModal :open="true" title="Review a share" wide @close="emit('close')">
    <div class="review">
      <p class="meta">From <strong>{{ share.sender }}</strong> · {{ KIND[share.kind] }} · {{ formatUtc(share.created_at) }}</p>
      <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
      <p v-else-if="!detail" class="muted" role="status">Loading …</p>
      <template v-else>
        <p class="untrusted" role="note">
          <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
          {{ detail.notice }}
        </p>
        <template v-if="detail.skill">
          <h4>When to use</h4><pre class="text">{{ detail.skill.when_to_use }}</pre>
          <h4>Steps</h4><pre class="text">{{ detail.skill.steps }}</pre>
          <template v-if="detail.skill.tools"><h4>Tools</h4><pre class="text">{{ detail.skill.tools }}</pre></template>
        </template>
        <pre v-else class="text">{{ detail.body }}</pre>
        <label class="field"><span class="label">Title</span><input v-model="title" type="text" aria-label="Title" maxlength="200" :disabled="busy" /></label>
        <label v-if="!isSkill" class="field"><span class="label">Keep it in folder</span><input v-model="folder" type="text" aria-label="Folder" maxlength="130" :disabled="busy" /></label>
        <p v-if="problem" class="error" role="alert">{{ problem }}</p>
      </template>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="buttons">
        <button type="button" class="pill-btn ghost" :disabled="busy" @click="emit('close')">Close</button>
        <button type="button" class="link-btn danger" :disabled="busy || !detail" @click="blockSender">Block sender</button>
        <button type="button" class="pill-btn ghost" :disabled="busy || !detail" @click="decline">Decline</button>
        <button type="button" class="pill-btn primary" :disabled="!canKeep" :aria-busy="busy" @click="keep">Keep a copy</button>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.review { display: flex; flex-direction: column; gap: 12px; }
p, h4 { margin: 0; overflow-wrap: anywhere; }
h4 { font-size: .85em; color: var(--muted); }
.meta { font-size: .9em; color: var(--muted); }
.untrusted { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border: 1px solid var(--warning); border-radius: var(--radius-md); font-size: .85em; }
.untrusted .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.text { margin: 0; max-height: 40dvh; overflow: auto; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--code-bg); font: inherit; font-size: .9em; white-space: pre-wrap; overflow-wrap: anywhere; }
.field { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: .85em; color: var(--muted); }
.field input { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 8px; }
@media (max-width: 767px) {
  .field input { min-height: 44px; font-size: max(1em, 16px); }
  .buttons button { min-height: 44px; }
}
</style>
```

- [x] **Step 4: Run it to verify it passes**

Run: `pnpm exec vitest run src/features/sharing/components/ShareReview.test.ts`
Expected: PASS. Fix a snippet that does not fit (for example the folder default or the `notice` wording the server really sends) and record it.

- [x] **Step 5: Write the failing SharesView test**

```ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import { makeAccount } from "../../testing/account";
import { sharingClient, type Block, type Share } from "./api/SharingClient";
import SharesView from "./SharesView.vue";
import { useSharingStore } from "./stores/sharing";

vi.mock("./api/SharingClient", () => ({
  sharingClient: {
    create: vi.fn(), inbox: vi.fn(), sent: vi.fn(), get: vi.fn(), revoke: vi.fn(), accept: vi.fn(), decline: vi.fn(),
    blocks: vi.fn(), block: vi.fn(), unblock: vi.fn(),
  },
}));
vi.mock("./components/ShareReview.vue", () => ({
  default: {
    props: ["share"],
    emits: ["close", "done"],
    template: '<div data-test="review"><button class="done" @click="$emit(\'done\', \'Kept as a file.\')">done</button><button class="close" @click="$emit(\'close\')">close</button>{{ share.title }}</div>',
  },
}));

const client = vi.mocked(sharingClient);
const share = (id: string, extra: Partial<Share> = {}): Share => ({
  id, kind: "file", title: `share ${id}`, status: "pending", sender: "bo", recipient: "me",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 5, ...extra,
});
const blocked = (uid: string): Block => ({ uid, username: `user-${uid}`, created_at: "2026-01-01T00:00:00Z" });

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

async function setup(lists: { inbox?: Share[]; sent?: Share[]; blocks?: Block[] } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  client.inbox.mockResolvedValue(lists.inbox ?? []);
  client.sent.mockResolvedValue(lists.sent ?? []);
  client.blocks.mockResolvedValue(lists.blocks ?? []);
  wrapper = mount(SharesView, { attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const section = (w: VueWrapper, name: string) => w.get(`section[aria-label="${name}"]`);
const buttonIn = (el: ReturnType<typeof section>, text: string) => el.findAll("button").find((b) => b.text() === text)!;
const confirm = () => document.body.querySelector<HTMLButtonElement>("dialog[open] .confirm");

beforeEach(() => {
  vi.clearAllMocks();
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

describe("SharesView", () => {
  it("lists what is waiting, what was sent and who is blocked", async () => {
    const w = await setup({
      inbox: [share("a", { kind: "skill", sender: "bo" })],
      sent: [share("s1", { sender: "me", recipient: "cy", status: "accepted" }), share("s2", { sender: "me", recipient: "global brain" })],
      blocks: [blocked("u1")],
    });
    expect(section(w, "Waiting for you").text()).toContain("share a");
    expect(section(w, "Waiting for you").text()).toContain("bo");
    expect(section(w, "Waiting for you").text()).toContain("Skill");
    expect(section(w, "Sent by you").text()).toContain("cy");
    expect(section(w, "Sent by you").text()).toContain("Kept");
    expect(section(w, "Sent by you").text()).toContain("global brain");
    expect(section(w, "Blocked accounts").text()).toContain("user-u1");
  });

  it("says each list is empty", async () => {
    const w = await setup();
    expect(section(w, "Waiting for you").text()).toContain("Nothing is waiting for you.");
    expect(section(w, "Sent by you").text()).toContain("You have not shared anything.");
    expect(section(w, "Blocked accounts").text()).toContain("You have not blocked anyone.");
  });

  it("opens the review dialog for a share and shows what it reports", async () => {
    const w = await setup({ inbox: [share("a")] });
    await buttonIn(section(w, "Waiting for you"), "Review").trigger("click");
    expect(w.get('[data-test="review"]').text()).toContain("share a");
    await w.get(".done").trigger("click");
    expect(w.find('[data-test="review"]').exists()).toBe(false);
    expect(w.get('[role="status"]').text()).toContain("Kept as a file.");
  });

  it("leaving the review closes it without a message", async () => {
    const w = await setup({ inbox: [share("a")] });
    await buttonIn(section(w, "Waiting for you"), "Review").trigger("click");
    await w.get(".close").trigger("click");
    expect(w.find('[data-test="review"]').exists()).toBe(false);
    expect(w.find('[role="status"]').exists()).toBe(false);
  });

  it("withdraws a waiting share after asking, and only a waiting one has the button", async () => {
    const w = await setup({ sent: [share("s1", { sender: "me", recipient: "cy" }), share("s2", { sender: "me", recipient: "cy", status: "declined" })] });
    const sent = section(w, "Sent by you");
    expect(sent.findAll("button").filter((b) => b.text() === "Withdraw")).toHaveLength(1);
    await buttonIn(sent, "Withdraw").trigger("click");
    await flushPromises();
    expect(client.revoke).not.toHaveBeenCalled();
    client.revoke.mockResolvedValue(share("s1", { status: "revoked" }));
    confirm()!.click();
    await flushPromises();
    expect(client.revoke).toHaveBeenCalledExactlyOnceWith("s1");
    expect(w.text()).toContain("Share withdrawn.");
  });

  it("shows why a withdrawal was refused", async () => {
    const w = await setup({ sent: [share("s1", { sender: "me", recipient: "cy" })] });
    await buttonIn(section(w, "Sent by you"), "Withdraw").trigger("click");
    await flushPromises();
    client.revoke.mockRejectedValue(new ApiError(409, "That share is already decided."));
    confirm()!.click();
    await flushPromises();
    expect(w.get('[role="alert"]').text()).toBe("That share is already decided.");
  });

  it("blocks an account by username and shows the server's one refusal as it came", async () => {
    const w = await setup();
    client.block.mockRejectedValueOnce(new ApiError(404, "No such recipient."));
    await w.get('input[aria-label="Username to block"]').setValue(" nobody ");
    await buttonIn(section(w, "Blocked accounts"), "Block").trigger("click");
    await flushPromises();
    expect(client.block).toHaveBeenCalledWith("nobody");
    expect(section(w, "Blocked accounts").get('[role="alert"]').text()).toBe("No such recipient.");
    client.block.mockResolvedValueOnce([blocked("u1")]);
    client.blocks.mockResolvedValue([blocked("u1")]);
    await buttonIn(section(w, "Blocked accounts"), "Block").trigger("click");
    await flushPromises();
    expect(section(w, "Blocked accounts").text()).toContain("user-u1");
    expect((w.get('input[aria-label="Username to block"]').element as HTMLInputElement).value).toBe("");
  });

  it("unblocks an account", async () => {
    const w = await setup({ blocks: [blocked("u1")] });
    client.unblock.mockResolvedValue(undefined);
    client.blocks.mockResolvedValue([]);
    await buttonIn(section(w, "Blocked accounts"), "Unblock").trigger("click");
    await flushPromises();
    expect(client.unblock).toHaveBeenCalledExactlyOnceWith("u1");
    expect(section(w, "Blocked accounts").text()).toContain("You have not blocked anyone.");
  });

  it("a failed load shows the reason with a way to try again", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().account = makeAccount();
    client.inbox.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    client.sent.mockResolvedValue([]);
    client.blocks.mockResolvedValue([]);
    wrapper = mount(SharesView, { attachTo: document.body, global: { plugins: [pinia] } });
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Storage is unavailable");
    client.inbox.mockResolvedValue([share("a")]);
    await wrapper.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect(section(wrapper, "Waiting for you").text()).toContain("share a");
  });

  it("drops the lists when the page goes away", async () => {
    const w = await setup({ inbox: [share("a")] });
    const store = useSharingStore();
    expect(store.inbox).toHaveLength(1);
    w.unmount();
    wrapper = null;
    expect(store.inbox).toEqual([]);
  });
});
```

- [x] **Step 6: Run it to verify it fails**

Run: `pnpm exec vitest run src/features/sharing/SharesView.test.ts`
Expected: FAIL, `./SharesView.vue` does not exist.

- [x] **Step 7: Write `SharesView.vue`, the route and the nav entry**

```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import "../../components/layout/infoPage.css";
import PageLayout from "../../components/layout/PageLayout.vue";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import { errorMessage } from "../../utils/errors";
import { formatUtc } from "../../utils/time";
import { SHARE_NAME_MAX, type Share, type ShareKind, type ShareStatus } from "./api/SharingClient";
import ShareReview from "./components/ShareReview.vue";
import { useSharingStore } from "./stores/sharing";

/** Copies sent to the person and by the person. Reading, keeping, declining and blocking happen in the review dialog;
 * a waiting share can be withdrawn here; blocked accounts are listed and can be unblocked. */
const KIND: Record<ShareKind, string> = { file: "File", section: "Section", skill: "Skill", stack_item: "Short-term item" };
const STATUS: Record<ShareStatus, string> = { pending: "Waiting for an answer", accepted: "Kept", declined: "Declined", revoked: "Withdrawn", rejected: "Not approved" };

const store = useSharingStore();
const reviewing = ref<Share | null>(null);
const withdrawing = ref<Share | null>(null);
const notice = ref("");
const actionError = ref("");
const busy = ref(false);
const username = ref("");
const blockError = ref("");

onMounted(() => void store.load());
onBeforeUnmount(() => store.forget());

function reviewed(message: string): void {
  reviewing.value = null;
  notice.value = message;
}

async function withdraw(): Promise<void> {
  const share = withdrawing.value;
  if (!share || busy.value) return;
  busy.value = true;
  actionError.value = "";
  try {
    await store.revoke(share.id);
    notice.value = "Share withdrawn.";
  } catch (err) {
    actionError.value = errorMessage(err);
  } finally {
    busy.value = false;
    withdrawing.value = null;
  }
}

async function block(): Promise<void> {
  const name = username.value.trim();
  if (!name || busy.value) return;
  busy.value = true;
  blockError.value = "";
  try {
    await store.block(name);
    username.value = "";
    notice.value = "Account blocked. Its waiting shares were declined.";
  } catch (err) {
    blockError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function unblock(uid: string): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  blockError.value = "";
  try {
    await store.unblock(uid);
  } catch (err) {
    blockError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <PageLayout class="shares info-content" title="Shares" description="Copies of files, skills and memory items: what was sent to you and what you sent.">
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
    <StateMessage v-if="store.status === 'idle' || store.status === 'loading'" kind="loading">Loading …</StateMessage>
    <StateMessage v-else-if="store.status === 'error'" kind="error" @retry="store.load()">Could not load your shares: {{ store.error }}</StateMessage>
    <template v-else>
      <p v-if="store.error" class="error" role="alert">Could not refresh: {{ store.error }}</p>

      <section aria-label="Waiting for you" class="block">
        <h3>Waiting for you</h3>
        <StateMessage v-if="store.inbox.length === 0" kind="empty">Nothing is waiting for you.</StateMessage>
        <ul v-else class="rows">
          <li v-for="share in store.inbox" :key="share.id" class="row">
            <div class="what">
              <span class="title">{{ share.title }}</span>
              <span class="muted">From {{ share.sender }} · {{ KIND[share.kind] }} · {{ formatUtc(share.created_at) }}</span>
            </div>
            <button type="button" class="pill-btn primary" :disabled="busy" @click="reviewing = share">Review</button>
          </li>
        </ul>
      </section>

      <section aria-label="Sent by you" class="block">
        <h3>Sent by you</h3>
        <StateMessage v-if="store.sent.length === 0" kind="empty">You have not shared anything.</StateMessage>
        <ul v-else class="rows">
          <li v-for="share in store.sent" :key="share.id" class="row">
            <div class="what">
              <span class="title">{{ share.title }}</span>
              <span class="muted">To {{ share.recipient }} · {{ KIND[share.kind] }} · {{ formatUtc(share.created_at) }}</span>
              <span class="status-badge">{{ STATUS[share.status] }}</span>
            </div>
            <button v-if="share.status === 'pending'" type="button" class="pill-btn ghost" :disabled="busy" @click="withdrawing = share">Withdraw</button>
          </li>
        </ul>
      </section>

      <section aria-label="Blocked accounts" class="block">
        <h3>Blocked accounts</h3>
        <p class="muted hint">A blocked account cannot send you shares. Blocking also declines what it already sent.</p>
        <StateMessage v-if="store.blocks.length === 0" kind="empty">You have not blocked anyone.</StateMessage>
        <ul v-else class="rows">
          <li v-for="entry in store.blocks" :key="entry.uid" class="row">
            <div class="what"><span class="title">{{ entry.username }}</span></div>
            <button type="button" class="pill-btn ghost" :disabled="busy" @click="unblock(entry.uid)">Unblock</button>
          </li>
        </ul>
        <form class="add" @submit.prevent="block">
          <input v-model="username" type="text" aria-label="Username to block" placeholder="Username to block" :maxlength="SHARE_NAME_MAX" autocomplete="off" :disabled="busy" />
          <button type="submit" class="pill-btn ghost" :disabled="busy || username.trim() === ''">Block</button>
        </form>
        <p v-if="blockError" class="error" role="alert">{{ blockError }}</p>
      </section>
    </template>

    <ShareReview v-if="reviewing" :share="reviewing" @close="reviewing = null" @done="reviewed" />
    <ConfirmModal
      :open="withdrawing !== null"
      title="Withdraw this share?"
      message="They will no longer be able to keep it."
      confirm-label="Withdraw"
      danger
      :busy="busy"
      @confirm="withdraw"
      @close="withdrawing = null"
    />
  </PageLayout>
</template>

<style scoped>
.block { display: flex; flex-direction: column; gap: 8px; margin-bottom: 28px; }
.block h3 { margin: 0; }
.hint, .notice { margin: 0; font-size: .85em; }
.rows { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); }
.what { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; min-width: 0; }
.title { font-weight: 600; overflow-wrap: anywhere; }
.what .muted { font-size: .85em; overflow-wrap: anywhere; }
.add { display: flex; gap: 8px; }
.add input { flex: 1; min-width: 0; }
@media (max-width: 767px) {
  .row { flex-direction: column; align-items: stretch; }
  .row button, .add button { min-height: 44px; }
  .add input { min-height: 44px; font-size: max(1em, 16px); }
}
</style>
```

Add the route in `router/index.ts` next to the Skills route:

```ts
{ path: "/shares", name: "shares", component: () => import("../features/sharing/SharesView.vue"), meta: { permission: "chat.use" } },
```

Add the nav entry in `router/pages.ts` right after the "Skills" entry:

```ts
{
  to: "/shares",
  label: "Shares",
  icon: ["M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8", "m16 6-4-4-4 4", "M12 2v13"],
  description: "Copies of files, skills and memory items sent to you and by you.",
  permission: "chat.use",
},
```

- [x] **Step 8: Run the tests, then fix the nav tests**

Run: `pnpm exec vitest run src/features/sharing` then `pnpm test`
Expected: the sharing tests PASS; tests that list the nav pages (assumption (e)) fail because "Shares" is new. Update only their expected lists, keep what they check, and list each under "Changes found during work". Then `pnpm exec vue-tsc -b` and `pnpm exec vitest run src/radiusScale.test.ts src/architecture.test.ts src/themeContrast.test.ts` must pass.

- [x] **Step 9: Commit**

```bash
git add apps/ember/src/features/sharing apps/ember/src/router
git commit -m "feat(ember): Shares page with the review dialog, route and nav entry"
```

---

### Task 5: Share buttons in Notes, Skills and the short-term memory panel

**Files:**
- Modify: `apps/ember/src/features/notes/components/FileEditor.vue`, `FileEditor.test.ts`, `apps/ember/src/features/notes/NotesView.vue`, `NotesView.test.ts`
- Modify: `apps/ember/src/features/skills/SkillsView.vue`, `SkillsView.test.ts`
- Modify: `apps/ember/src/features/chat/components/StackPanel.vue`, `StackPanel.test.ts`, `StackMenu.vue`, `StackMenu.test.ts`
- Modify: `apps/ember/README.md` only if it lists pages (grep; skip and say so if not)

**Interfaces:**
- Consumes: `ShareDialog`, `ShareTarget` (Task 3); `headingsOf` (Task 3).
- Produces: `FileEditor` gets props `canShare: boolean` and `shareHint: string` and emits `share`; `StackPanel` emits `share: [id: number]`; each page renders `<ShareDialog v-if="shareTarget" :open="true" :target="shareTarget" @close="shareTarget = null" />`.

- [x] **Step 1: Write the failing tests**

Add to `FileEditor.test.ts` (and add `canShare: true, shareHint: ""` to the `mountEditor` default props, since the props become required):

```ts
  it("offers Share for a saved file and asks the page to open the dialog", async () => {
    const w = mountEditor();
    const button = w.findAll("button").find((b) => b.text() === "Share a copy…")!;
    expect(button.attributes("disabled")).toBeUndefined();
    await button.trigger("click");
    expect(w.emitted("share")).toHaveLength(1);
  });

  it("keeps Share off, with the reason, until the file is saved and unchanged", () => {
    const w = mountEditor({ canShare: false, shareHint: "Save your changes first. A share sends the saved file." });
    expect(w.findAll("button").find((b) => b.text() === "Share a copy…")!.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("Save your changes first.");
    expect(mountEditor({ file: null }).text()).not.toContain("Share a copy…");
  });
```

Add to `NotesView.test.ts` (stub the dialog at the top with `vi.mock("../sharing/components/ShareDialog.vue", () => ({ default: { props: ["open", "target"], template: '<div data-test="share-dialog">{{ target.kind }} {{ target.fileId }} {{ target.headings.join("|") }}</div>' } }))`):

```ts
  it("shares the saved file, listing its headings for a section", async () => {
    client.get.mockResolvedValue(full("a", "Tea", "# Brewing\nSteep.\n## Storage\nDry."));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await buttonByText(w, "Share a copy…")!.trigger("click");
    expect(w.get('[data-test="share-dialog"]').text()).toBe("file a Brewing|Storage");
  });

  it("does not offer to share while there are unsaved changes", async () => {
    client.get.mockResolvedValue(full("a", "Tea", "Body"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await text(w).setValue("Edited");
    expect(buttonByText(w, "Share a copy…")!.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("Save your changes first.");
  });
```

Add to `SkillsView.test.ts`. This test file mounts without Pinia, so stub the dialog at the top, next to its other `vi.mock`:

```ts
vi.mock("../sharing/components/ShareDialog.vue", () => ({
  default: { props: ["open", "target"], template: '<div data-test="share-dialog">{{ target.kind }} {{ target.skillId }}</div>' },
}));
```

and add inside `describe("SkillsView", ...)`:

```ts
  it("shares a saved skill", async () => {
    await setup([skill(1, "active")]);
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
    expect(button("Share a copy…").attributes("disabled")).toBeUndefined();
    expect(wrapper.find('[data-test="share-dialog"]').exists()).toBe(false);
    await button("Share a copy…").trigger("click");
    expect(wrapper.get('[data-test="share-dialog"]').text()).toBe("skill 1");
  });

  it("keeps Share off, with the reason, while the draft is unsaved", async () => {
    await setup([skill(1, "active")]);
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
    await wrapper.get('textarea[aria-label="Title"]').setValue("Changed title");
    expect(button("Share a copy…").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Save your changes first.");
  });
```

Add to `StackPanel.test.ts`, inside `describe("StackPanel", ...)`:

```ts
  it("each item has a Share button that names no text and asks to share that item", async () => {
    const w = mountPanel();
    const buttons = w.findAll("[data-test=share]");
    expect(buttons).toHaveLength(3);
    expect(buttons[1]!.attributes("aria-label")).toBe("Share item");
    await buttons[1]!.trigger("click");
    expect(w.emitted("share")).toEqual([[2]]);
  });

  it("keeps Share off while a change is running", () => {
    const w = mountPanel({ pending: true });
    for (const button of w.findAll("[data-test=share]")) expect(button.attributes("disabled")).toBeDefined();
  });
```

Add to `StackMenu.test.ts`: stub the dialog at the top, next to its other `vi.mock`:

```ts
vi.mock("../../sharing/components/ShareDialog.vue", () => ({
  default: {
    props: ["open", "target"],
    emits: ["close"],
    template: '<div data-test="share-dialog">{{ target.kind }} {{ target.chatId }} {{ target.itemId }}<button class="stub-close" @click="$emit(\'close\')">x</button></div>',
  },
}));
```

and add inside `describe("StackMenu", ...)`:

```ts
  it("sharing an item opens the dialog for that chat and item; Escape does not close the panel behind it", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    await w.findAll("[data-test=share]")[1]!.trigger("click");
    expect(w.get('[data-test="share-dialog"]').text()).toContain("stack_item c-1 2");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await flushPromises();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(true);
    await w.get(".stub-close").trigger("click");
    expect(w.find('[data-test="share-dialog"]').exists()).toBe(false);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await flushPromises();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
  });
```

- [x] **Step 2: Run them to verify they fail**

Run: `pnpm exec vitest run src/features/notes src/features/skills src/features/chat/components/StackPanel.test.ts src/features/chat/components/StackMenu.test.ts`
Expected: the new cases FAIL (no Share buttons yet); the existing ones PASS.

- [x] **Step 3: Implement**

`FileEditor.vue`: add `canShare: boolean; shareHint: string` to the props, `share: []` to the emits, and a section after "Original text" and before "Manage file":

```vue
      <details v-if="file" class="share-tools">
        <summary><span>Share</span><span aria-hidden="true">›</span></summary>
        <div class="field">
          <p class="muted hint">Send a copy of the saved file, or one section of it, to another account or to the global brain. They decide whether to keep it.</p>
          <div><button type="button" class="chip" :disabled="!canShare || disabled" @click="$emit('share')">Share a copy…</button></div>
          <p v-if="shareHint" class="muted hint">{{ shareHint }}</p>
        </div>
      </details>
```

`NotesView.vue`: import `ShareDialog` from `../sharing/components/ShareDialog.vue` and `headingsOf` from `../sharing/utils/headings`; add

```ts
const shareTarget = ref<ShareTarget | null>(null);
const canShare = computed(() => opened.value !== null && !dirty.value && !busy.value && conflict.value === null);
const shareHint = computed(() => (opened.value && dirty.value ? "Save your changes first. A share sends the saved file." : ""));
function share(): void {
  const file = opened.value;
  if (file && canShare.value) shareTarget.value = { kind: "file", fileId: file.id, label: file.title, headings: headingsOf(file.body) };
}
```

(import the type with `import ShareDialog, { type ShareTarget } from "../sharing/components/ShareDialog.vue"`), pass `:can-share="canShare" :share-hint="shareHint" @share="share"` to `FileEditor`, close the dialog in the existing reset-on-sign-out path, and add `<ShareDialog v-if="shareTarget" :open="true" :target="shareTarget" @close="shareTarget = null" />` next to the confirm dialogs.

`SkillsView.vue`: in the "Manage skill" actions add `<button type="button" class="link-btn" :disabled="busy || dirty" @click="shareTarget = { kind: 'skill', skillId: editing.id, label: editing.title }">Share a copy…</button>` and, under it, `<p v-if="dirty" class="muted">Save your changes first. A share sends the saved skill.</p>`; add `const shareTarget = ref<ShareTarget | null>(null)`, close it when the open skill changes, and render the same `v-if` dialog.

`StackPanel.vue`: add `share: [id: number]` to the emits and, in each item's button group next to pin and remove, a button with `data-test="share"`, `:aria-label="`Share item`"` (no item text in the label), `:disabled="busy"`, emitting `share` with the item id; give it the same 44px rule below 768px as the pin and remove buttons.

`StackMenu.vue`: add `const shareTarget = ref<ShareTarget | null>(null)`, handle `@share="(id) => (shareTarget = { kind: 'stack_item', chatId: chatId!, itemId: id, label: 'a short-term memory item' })"` on `StackPanel`, render `<ShareDialog v-if="shareTarget" :open="true" :target="shareTarget" @close="shareTarget = null" />` inside the root element (so a press inside the dialog is not an outside press), set `shareTarget = null` in `close()` and on chat change, and make `closeOnEscape` return without closing the popover while `shareTarget` is set (the dialog handles that Escape itself).

- [x] **Step 4: Run the tests and the checks**

Run: `pnpm exec vitest run src/features/notes src/features/skills src/features/chat src/features/sharing`, then `pnpm exec vue-tsc -b` and `pnpm test`.
Expected: PASS everywhere. Existing tests that mount `FileEditor` without the new props must be updated (list them). If a Skills or StackMenu test fails because the dialog needs Pinia, check that the dialog is only rendered under `v-if` and that the new tests stub it as the plan says.

- [x] **Step 5: Docs and roadmap**

Grep `apps/ember/README.md` for a list of pages; add "Shares" if it has one, otherwise skip and say so in the report. Check that roadmap row 20g links this plan.

- [x] **Step 6: Commit**

```bash
git add -A apps/ember/src docs/superpowers/plans
git commit -m "feat(ember): share buttons in Notes, Skills and the short-term memory panel"
```

---

## Manual checklist (the user runs it; Codex copies it into the report as pending)

- Desktop, 768px, 767px and 375px, light and dark.
- Notes: save a file, Share a copy to a second account; the button is off while there are unsaved changes and says why. Share one section of a file with headings (a heading inside a code block is not listed). Share the same file again before an answer and read the server's "already shared" text.
- Skills: share a skill; short-term memory: share an item from the panel, press Escape once (dialog closes) and again (panel closes).
- Second account: open Shares, review a file share (the text is plain, no links, the untrusted notice and its icon show), change title and folder, Keep a copy, then find it on the Notes page with the sender shown. Review a skill share and see it on the Skills page as waiting for approval.
- Decline one, block a sender (their waiting shares are declined), try to send to the blocker from the first account and read the same refusal as for an unknown name; unblock.
- Send to the global brain and read the review-queue text; withdraw a waiting share; check the status words in Sent by you.
- Fill the recipient's inbox limit or your pending limit and read the server's reason in the dialog.
- Tab through every dialog; Esc closes it; buttons are 44px on a phone; sign out with a dialog open and see it close.

Unverified by the work above: two real accounts end to end against a real Stronghold, the global brain review (row 20k), layout on a real phone with the keyboard open, light and dark contrast beyond the pairs computed.
