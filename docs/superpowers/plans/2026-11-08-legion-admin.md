# legion_admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `apps/legion_admin`, an admin-only Vue frontend for Legion whose first page is Agents.

**Architecture:** Standalone Vue 3 app copied from `ember_admin`'s stack and its Agents page closure. It talks only to `ember_api` (`/api/auth/*`, `/api/admin/agents*`) through a Vite `/api` proxy. A pure `resolveGuard` function limits every page to accounts holding `agents.manage`.

**Tech Stack:** Vue 3, TypeScript, Vite, Pinia, vue-router, vitest + jsdom, pnpm, nginx (Docker).

**Spec:** `docs/superpowers/specs/2026-11-08-legion-admin-design.md`

## Global Constraints

- All paths are relative to `D:\User\Documents\Programming\Applications\Citadel` (the "Citadel root"). Source app: `apps/ember_admin`. New app: `apps/legion_admin`.
- No new backend routes. `ember_api` is not modified.
- Use `pnpm`, never `npm` (workspace skill `use-pnpm`).
- Colors only through `style.css` tokens; radius only through `--radius-*` tokens (`radiusScale.test.ts` enforces it).
- Never add a reduced-motion setting, `prefers-reduced-motion` query or test.
- No PWA: no `vite-plugin-pwa`, no `workbox-window`, no `PwaStatus`, no manifest.
- Dev port `26500` (block `26500-26999`); recheck it is unused before Task 4.
- A switch that calls the server stays pending until the server answers (inherited from copied components; do not change).
- Commits: the repo has many unrelated pending changes (`apps/Ember/*` moves). Stage only the paths named in each commit step, and only commit if the user has approved committing.
- Copy, do not import: nothing under `apps/legion_admin` may import from `ember_admin` or `ember_web`.

## File Structure

```
apps/legion_admin/
  package.json, vite.config.ts, tsconfig.json, tsconfig.app.json, tsconfig.node.json
  index.html, public/favicon.svg, Dockerfile, nginx.conf, .gitignore
  AGENTS.md, CLAUDE.md, README.md
  src/main.ts, App.vue, style.css
  src/router/   index.ts (routes+install), guard.ts (pure), pages.ts, redirect.ts, guard.test.ts
  src/stores/   auth.ts, auth.test.ts
  src/api/      http.ts, AuthClient.ts, AgentsAdminClient.ts, CapabilitiesAdminClient.ts,
                CommandsClient.ts, AttachmentsClient.ts          (copied)
  src/views/    LoginView.vue, NoAccessView.vue, AgentsAdminView.vue (+ .test.ts)
  src/components/ LegionNav.vue (new), AuthCard, PasswordInput, PageLayout, BaseModal, DeleteButton,
                SettingRow, ToggleSwitch, infoPage.css, pageLayout.css, admin/*  (copied)
  src/composables/useTheme.ts, src/utils/{errors,dragImage,routerPolicy}.ts  (copied)
```
Other `ember_admin` files are NOT copied.

---

### Task 1: Scaffold, auth store and admin-only guard

**Files:**
- Create: `apps/legion_admin/package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `index.html`, `.gitignore`, `public/favicon.svg`
- Create: `src/api/http.ts`, `src/api/AuthClient.ts` (copied), `src/stores/auth.ts`, `src/router/pages.ts`, `src/router/guard.ts`, `src/router/redirect.ts`
- Test: `src/router/guard.test.ts`, `src/stores/auth.test.ts`

**Interfaces:**
- Produces: `LEGION_PAGES: LegionPage[]`; `resolveGuard(to: GuardTarget, auth: GuardAuth): true | RouteLocationRaw`; `useAuthStore()` with `account`, `hasPermission(name)`, `ensureLoaded()`, `login(u,p)`, `logout()`; `safeRedirect(value: unknown): string`.

- [ ] **Step 1: Copy tooling and boring files**

```bash
cd /d/User/Documents/Programming/Applications/Citadel/apps
mkdir -p legion_admin/src/{api,stores,router,views,components,composables,utils} legion_admin/public
cd ember_admin
cp tsconfig.json tsconfig.app.json tsconfig.node.json .gitignore ../legion_admin/
cp public/favicon.svg ../legion_admin/public/
cp src/api/http.ts src/api/AuthClient.ts ../legion_admin/src/api/
cp src/router/redirect.ts ../legion_admin/src/router/
cp src/composables/useTheme.ts ../legion_admin/src/composables/
```
Then in `legion_admin/src/composables/useTheme.ts` change `"ember_admin.theme"` to `"legion_admin.theme"`.

- [ ] **Step 2: Write `package.json`**

```json
{
  "name": "legion_admin",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "packageManager": "pnpm@12.16.1",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "pinia": "^4.0.3",
    "vue": "^3.5.42",
    "vue-router": "^5.3.1"
  },
  "devDependencies": {
    "@types/node": "^24.13.3",
    "@vitejs/plugin-vue": "^6.0.8",
    "@vue/test-utils": "^2.5.1",
    "@vue/tsconfig": "^0.9.1",
    "jsdom": "^29.1.1",
    "typescript": "~6.0.2",
    "vite": "^8.3.0",
    "vitest": "^5.0.2",
    "vue-tsc": "^3.3.11"
  }
}
```

- [ ] **Step 3: Write `vite.config.ts`**

```ts
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// legion_admin: everything under /api goes to ember_api, so the browser sees one origin:
// the SameSite=Strict session cookie works and no CORS is involved.
// xfwd: ember_api trusts X-Forwarded-For only from loopback, so logins are rate-limited per real client.
const apiProxy = {
  '/api': { target: `http://127.0.0.1:${process.env.EMBER_API_PORT ?? 8030}`, xfwd: true },
}

const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ')

export default defineConfig({
  plugins: [vue()],
  build: {
    // style.css colors are light-dark() tokens; older targets make the minifier rewrite them
    // into prefers-color-scheme queries, which the theme toggle cannot override.
    cssTarget: ['chrome123', 'firefox120', 'safari17.5'],
  },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'], restoreMocks: true },
  server: {
    port: Number(process.env.LEGION_ADMIN_PORT ?? 26500),
    strictPort: true,
    host: '127.0.0.1',
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
    headers: {
      'Content-Security-Policy': contentSecurityPolicy,
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
    },
  },
})
```

- [ ] **Step 4: Write `index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, interactive-widget=resizes-content" />
    <meta name="robots" content="noindex, nofollow" />
    <meta name="theme-color" content="#e8590c" />
    <title>Legion Admin</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 5: Write the failing guard test** — `src/router/guard.test.ts`

```ts
import { describe, expect, it } from "vitest";
import { resolveGuard, type GuardAuth } from "./guard";

const admin: GuardAuth = { signedIn: true, hasPermission: (p) => p === "agents.manage" };
const plain: GuardAuth = { signedIn: true, hasPermission: () => false };
const anon: GuardAuth = { signedIn: false, hasPermission: () => false };
const agentsPage = { name: "agents", fullPath: "/agents", permission: "agents.manage" };

describe("resolveGuard", () => {
  it("sends a guest to login with a redirect back", () => {
    expect(resolveGuard(agentsPage, anon)).toEqual({ name: "login", query: { redirect: "/agents" } });
  });
  it("lets a guest open the login page", () => {
    expect(resolveGuard({ name: "login", fullPath: "/login", guestOnly: true }, anon)).toBe(true);
  });
  it("lets an agents.manage account open Agents", () => {
    expect(resolveGuard(agentsPage, admin)).toBe(true);
  });
  it("sends an account without the permission to no-access", () => {
    expect(resolveGuard(agentsPage, plain)).toEqual({ path: "/no-access" });
  });
  it("shows no-access to an account without the permission", () => {
    expect(resolveGuard({ name: "no-access", fullPath: "/no-access" }, plain)).toBe(true);
  });
  it("moves an admin off login and no-access to the first page", () => {
    expect(resolveGuard({ name: "login", fullPath: "/login", guestOnly: true }, admin)).toEqual({ path: "/agents" });
    expect(resolveGuard({ name: "no-access", fullPath: "/no-access" }, admin)).toEqual({ path: "/agents" });
  });
});
```

- [ ] **Step 6: Install and run the test to verify it fails**

Run: `cd apps/legion_admin && pnpm install && pnpm exec vitest run src/router/guard.test.ts`
Expected: FAIL, cannot resolve `./guard`.

- [ ] **Step 7: Write `src/router/pages.ts`**

```ts
/** The pages of the Legion admin app, in nav order, with the ember_api permission each needs.
 * One list, so the nav, the router and the guard cannot drift. */
export interface LegionPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  permission: string;
}

export const LEGION_PAGES: LegionPage[] = [
  {
    to: "/agents",
    label: "Agents",
    icon: ["M3 21v-3a5 5 0 0 1 5-5h3a5 5 0 0 1 5 5v3M20 21v-3a5 5 0 0 0-3-4", "M13.5 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0"],
    permission: "agents.manage",
  },
];
```

- [ ] **Step 8: Write `src/router/guard.ts`**

```ts
import type { RouteLocationRaw } from "vue-router";
import { LEGION_PAGES } from "./pages";

export interface GuardTarget {
  name?: string | symbol | null;
  fullPath: string;
  guestOnly?: boolean;
  permission?: string;
}

export interface GuardAuth {
  signedIn: boolean;
  hasPermission(name: string): boolean;
}

/** UX gate only: ember_api enforces every permission itself. Admin-only means agents.manage. */
export function resolveGuard(to: GuardTarget, auth: GuardAuth): true | RouteLocationRaw {
  if (!auth.signedIn) {
    return to.guestOnly ? true : { name: "login", query: to.fullPath === "/" ? {} : { redirect: to.fullPath } };
  }
  const home = LEGION_PAGES.find((p) => auth.hasPermission(p.permission));
  const away: RouteLocationRaw = { path: home?.to ?? "/no-access" };
  if (to.guestOnly) return away;
  if (to.permission && !auth.hasPermission(to.permission)) return away;
  if (to.name === "no-access" && home) return away;
  return true;
}
```

- [ ] **Step 9: Run guard test to verify it passes**

Run: `pnpm exec vitest run src/router/guard.test.ts`
Expected: PASS, 6 tests.

- [ ] **Step 10: Write the failing auth store test** — `src/stores/auth.test.ts`

```ts
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authClient, type Account } from "../api/AuthClient";
import { useAuthStore } from "./auth";

const base: Account = { id: 1, username: "a", email: "a@x", email_verified: true, roles: [], permissions: ["agents.manage"] };

beforeEach(() => setActivePinia(createPinia()));

describe("auth store", () => {
  it("grants a held permission", async () => {
    vi.spyOn(authClient, "me").mockResolvedValue(base);
    const auth = useAuthStore();
    await auth.ensureLoaded();
    expect(auth.hasPermission("agents.manage")).toBe(true);
    expect(auth.hasPermission("other.thing")).toBe(false);
  });
  it("grants nothing while the email is unverified and verification is required", async () => {
    vi.spyOn(authClient, "me").mockResolvedValue({ ...base, email_verified: false });
    const auth = useAuthStore();
    await auth.ensureLoaded();
    expect(auth.hasPermission("agents.manage")).toBe(false);
  });
  it("is signed out when /me fails", async () => {
    vi.spyOn(authClient, "me").mockRejectedValue(new Error("down"));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const auth = useAuthStore();
    await auth.ensureLoaded();
    expect(auth.account).toBeNull();
  });
});
```

- [ ] **Step 11: Run it to verify it fails**

Run: `pnpm exec vitest run src/stores/auth.test.ts`
Expected: FAIL, cannot resolve `./auth`.

- [ ] **Step 12: Write `src/stores/auth.ts`**

```ts
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authClient, type Account } from "../api/AuthClient";
import { onUnauthorized, UnauthorizedError } from "../api/http";

/** Who is logged in (ember_api's session). */
export const useAuthStore = defineStore("auth", () => {
  const account = ref<Account | null>(null);
  let loaded: Promise<void> | null = null;

  // Any 401 from ember_api means the session is gone.
  onUnauthorized(() => {
    account.value = null;
  });

  const permissions = computed(() => new Set(account.value?.permissions ?? []));

  // Mirrors ember_api: an unverified email holds no permissions, unless verification is switched off there.
  const needsVerification = computed(
    () => account.value !== null && !account.value.email_verified && account.value.email_verification_required !== false,
  );

  function hasPermission(name: string): boolean {
    return account.value !== null && !needsVerification.value && permissions.value.has(name);
  }

  /** Asks ember_api once per page load who is logged in (the router guard awaits it). */
  function ensureLoaded(): Promise<void> {
    loaded ??= authClient
      .me()
      .then((me) => {
        account.value = me;
      })
      .catch((err: unknown) => {
        if (!(err instanceof UnauthorizedError)) console.warn("legion_admin: /me failed", err);
        account.value = null;
      });
    return loaded;
  }

  async function login(username: string, password: string): Promise<void> {
    account.value = await authClient.login(username, password);
  }

  async function logout(): Promise<void> {
    try {
      await authClient.logout();
    } finally {
      account.value = null;
    }
  }

  return { account, needsVerification, hasPermission, ensureLoaded, login, logout };
});
```

- [ ] **Step 13: Run all tests to verify they pass**

Run: `pnpm test`
Expected: PASS (guard 6, auth 3).

- [ ] **Step 14: Commit**

```bash
git add apps/legion_admin
git commit -m "feat(legion_admin): scaffold app with auth store and admin-only guard"
```

---

### Task 2: Agents page (copied closure)

**Files:**
- Create (copied from `apps/ember_admin/src`, same relative path): `api/AgentsAdminClient.ts`, `api/CapabilitiesAdminClient.ts`, `api/CommandsClient.ts`, `api/AttachmentsClient.ts`, `components/{PageLayout,BaseModal,DeleteButton,SettingRow,ToggleSwitch}.vue`, `components/infoPage.css`, `components/admin/{AgentAdminCard,AgentForm,AgentGatewayList,ConfirmModal,RouterPolicyForm,SharedPromptsModal,ToolScopePicker}.vue`, `utils/{errors,dragImage,routerPolicy}.ts`, `views/AgentsAdminView.vue`, `style.css`
- Copy tests: `views/AgentsAdminView.test.ts`, `components/admin/{RouterPolicyForm,SharedPromptsModal}.test.ts`, `components/PageLayout.test.ts`, `radiusScale.test.ts`
- Create: `apps/legion_admin/src/components/pageLayout.css` (copied from `apps/ember_web/src/components/layout/pageLayout.css`)
- Modify: `src/style.css` line 1

**Interfaces:**
- Consumes: Task 1 `http.ts`. 
- Produces: `views/AgentsAdminView.vue` (default export, no props), the route target for `/agents`.

- [ ] **Step 1: Copy the closure**

```bash
cd /d/User/Documents/Programming/Applications/Citadel/apps
E=ember_admin/src; L=legion_admin/src
mkdir -p $L/components/admin
for f in api/AgentsAdminClient.ts api/CapabilitiesAdminClient.ts api/CommandsClient.ts api/AttachmentsClient.ts \
  components/PageLayout.vue components/BaseModal.vue components/DeleteButton.vue components/SettingRow.vue components/ToggleSwitch.vue components/infoPage.css \
  components/admin/AgentAdminCard.vue components/admin/AgentForm.vue components/admin/AgentGatewayList.vue components/admin/ConfirmModal.vue \
  components/admin/RouterPolicyForm.vue components/admin/SharedPromptsModal.vue components/admin/ToolScopePicker.vue \
  utils/errors.ts utils/dragImage.ts utils/routerPolicy.ts views/AgentsAdminView.vue style.css \
  views/AgentsAdminView.test.ts components/admin/RouterPolicyForm.test.ts components/admin/SharedPromptsModal.test.ts \
  components/PageLayout.test.ts radiusScale.test.ts; do cp "$E/$f" "$L/$f"; done
cp ember_web/src/components/layout/pageLayout.css $L/components/pageLayout.css
```

- [ ] **Step 2: Remove the `ember_web` import from `style.css`**

In `legion_admin/src/style.css` replace line 1
`@import "../../ember_web/src/components/layout/pageLayout.css";` with
`@import "./components/pageLayout.css";`.
Then run `grep -rn "ember_web\|ember_admin" legion_admin/src --include=*.vue --include=*.ts --include=*.css`. Rewrite comments that name those apps only if they make a false claim; any `import` hit must be fixed (copy the file locally).

- [ ] **Step 3: Run the copied tests** (type check waits for Task 3, which adds `main.ts`, `App.vue` and the router)

Run: `cd apps/legion_admin && pnpm test`
Expected: PASS for the copied suites. If a copied test fails because it imports a missing sibling (e.g. an `ember_admin` helper), copy that single file and re-run; do not edit test expectations. If `radiusScale.test.ts` reports a literal radius, replace it with a `--radius-*` token.

- [ ] **Step 4: Commit**

```bash
git add apps/legion_admin
git commit -m "feat(legion_admin): copy Agents page and its components"
```

---

### Task 3: App shell, nav, login and no-access views

**Files:**
- Create: `src/router/index.ts`, `src/App.vue`, `src/components/LegionNav.vue`, `src/components/AuthCard.vue` + `PasswordInput.vue` (copied), `src/views/LoginView.vue` (copied, text edited), `src/views/NoAccessView.vue`
- Test: `src/router/index.test.ts`

**Interfaces:**
- Consumes: `resolveGuard`, `LEGION_PAGES`, `useAuthStore`, `safeRedirect`, `AgentsAdminView`.
- Produces: `router` (named export) with route names `login`, `no-access`, `agents`.

- [ ] **Step 1: Copy shared pieces**

```bash
cd /d/User/Documents/Programming/Applications/Citadel/apps
cp ember_admin/src/components/AuthCard.vue ember_admin/src/components/PasswordInput.vue legion_admin/src/components/
cp ember_admin/src/components/PasswordInput.test.ts legion_admin/src/components/
cp ember_admin/src/views/LoginView.vue legion_admin/src/views/
```
In `LoginView.vue` change the subtitle `"Welcome back to Ember."` to `"Legion administration. Use your Ember account."`.

- [ ] **Step 2: Write the failing router test** — `src/router/index.test.ts`

```ts
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authClient, type Account } from "../api/AuthClient";
import { router } from "./index";

const account = (permissions: string[]): Account => ({ id: 1, username: "a", email: "a@x", email_verified: true, roles: [], permissions });

beforeEach(() => setActivePinia(createPinia()));

describe("router", () => {
  it("opens /agents for an agents.manage account", async () => {
    vi.spyOn(authClient, "me").mockResolvedValue(account(["agents.manage"]));
    await router.push("/agents");
    expect(router.currentRoute.value.name).toBe("agents");
  });
  it("sends an account without the permission to no-access", async () => {
    vi.spyOn(authClient, "me").mockResolvedValue(account([]));
    await router.push("/agents");
    expect(router.currentRoute.value.name).toBe("no-access");
  });
});
```
Note: the router and store are module singletons, so `ensureLoaded` runs once per test file load. Order the tests so the second test uses a fresh module: add `vi.resetModules()` in `beforeEach` and `await import("./index")` inside each test instead of the top-level import if the second case sees the first case's account.

- [ ] **Step 3: Run it to verify it fails**

Run: `pnpm exec vitest run src/router/index.test.ts`
Expected: FAIL, cannot resolve `./index`.

- [ ] **Step 4: Write `src/router/index.ts`**

```ts
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { resolveGuard } from "./guard";

declare module "vue-router" {
  interface RouteMeta {
    /** Reachable without logging in (login). */
    guestOnly?: boolean;
    /** The ember_api permission the page needs. */
    permission?: string;
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/agents" },
    { path: "/agents", name: "agents", component: () => import("../views/AgentsAdminView.vue"), meta: { permission: "agents.manage" } },
    { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { guestOnly: true } },
    { path: "/no-access", name: "no-access", component: () => import("../views/NoAccessView.vue") },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.ensureLoaded();
  return resolveGuard(
    { name: to.name, fullPath: to.fullPath, guestOnly: to.meta.guestOnly, permission: to.meta.permission },
    { signedIn: auth.account !== null, hasPermission: auth.hasPermission },
  );
});
```

- [ ] **Step 5: Write `src/views/NoAccessView.vue`**

```vue
<script setup lang="ts">
import AuthCard from "../components/AuthCard.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
</script>

<template>
  <AuthCard
    title="No access"
    subtitle="Legion administration needs the agents.manage permission. Ask an admin to give your account a role that has it, and verify your email in Ember."
  >
    <button type="button" @click="auth.logout()">Log out</button>
  </AuthCard>
</template>
```

- [ ] **Step 6: Write `src/components/LegionNav.vue`**

```vue
<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useTheme } from "../composables/useTheme";
import { LEGION_PAGES } from "../router/pages";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const { theme, next, cycle } = useTheme();
const LABELS = { system: "System", light: "Light", dark: "Dark" } as const;
const pages = computed(() => LEGION_PAGES.filter((p) => auth.hasPermission(p.permission)));
const themeLabel = computed(() => `Theme: ${LABELS[theme.value]}. Switch to ${LABELS[next()]}`);
</script>

<template>
  <aside class="rail" aria-label="Legion Admin">
    <span class="wordmark" role="img" aria-label="Legion Admin">L</span>
    <nav v-if="pages.length" class="pages" aria-label="Legion sections">
      <RouterLink v-for="page in pages" :key="page.to" :to="page.to" :data-label="page.label" :aria-label="page.label" :aria-current="route.path === page.to ? 'page' : undefined">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path v-for="d in page.icon" :key="d" :d="d" /></svg>
      </RouterLink>
    </nav>
    <div class="bottom">
      <button type="button" :data-label="themeLabel" :aria-label="themeLabel" @click="cycle">
        <svg v-if="theme === 'light'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
        <svg v-else-if="theme === 'dark'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></svg>
        <svg v-else viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
      </button>
      <button v-if="auth.account" type="button" data-label="Log out" aria-label="Log out" @click="auth.logout()">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></svg>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 52px;
  flex-shrink: 0;
  padding: 10px 0;
  border-right: 1px solid var(--border);
  background: var(--surface);
  position: relative;
  z-index: 30;
}
.pages, .bottom { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.pages { margin-top: 8px; }
.bottom { margin-top: auto; }
.wordmark { display: grid; place-items: center; width: 36px; height: 36px; font-weight: 700; color: var(--accent); }
.pages a, button {
  position: relative;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--muted);
  background: transparent;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
}
.pages a:hover, button:hover { color: var(--text); background: var(--bg); }
a[aria-current="page"] { color: var(--text); background: var(--bg); box-shadow: inset 2px 0 0 var(--accent); }
svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
[data-label]:hover::after, [data-label]:focus-visible::after {
  content: attr(data-label);
  position: absolute;
  left: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%);
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  white-space: nowrap;
  font-size: 0.85rem;
  color: var(--text);
  background: var(--surface);
  pointer-events: none;
}
@media (max-width: 767px) {
  .rail { flex-direction: row; width: 100%; height: var(--rail-height); padding: 0 4px env(safe-area-inset-bottom, 0px); gap: 4px; border-right: none; border-top: 1px solid var(--border); }
  .wordmark { width: 28px; height: 28px; flex-shrink: 0; }
  .pages { flex: 1; min-width: 0; margin: 0; flex-direction: row; justify-content: flex-start; overflow-x: auto; scrollbar-width: none; gap: 0; }
  .bottom { flex-direction: row; flex-shrink: 0; margin: 0; gap: 0; }
  .pages a, button { width: 44px; height: 44px; flex-shrink: 0; }
  a[aria-current="page"] { box-shadow: inset 0 -2px 0 var(--accent); }
  [data-label]::after { display: none; }
}
</style>
```
If `useTheme()` does not return `{ theme, next, cycle }` exactly as used here, read `src/composables/useTheme.ts` and adapt the three names (the ember_admin nav uses these same names, so they should match).

- [ ] **Step 7: Write `src/App.vue`**

```vue
<script setup lang="ts">
import { storeToRefs } from "pinia";
import { watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import LegionNav from "./components/LegionNav.vue";
import { useAuthStore } from "./stores/auth";

const { account } = storeToRefs(useAuthStore());
const route = useRoute();
const router = useRouter();

// The session can end mid-page (expired, or logged out elsewhere): any 401
// clears the account, and this sends the user back to the login page.
watch(account, (now) => {
  if (!now && !route.meta.guestOnly) void router.replace({ name: "login" });
});
</script>

<template>
  <div class="shell">
    <LegionNav v-if="account && $route.name !== 'no-access'" />
    <main class="page"><RouterView :key="account?.id ?? 'guest'" /></main>
  </div>
</template>

<style scoped>
.shell { display: flex; flex: 1; min-height: 0; }
.page { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
@media (max-width: 767px) { .shell { flex-direction: column-reverse; } }
</style>
```

- [ ] **Step 7b: Write `src/main.ts`**

```ts
import { createApp } from "vue";
import { createPinia } from "pinia";
import "./style.css";
import { initTheme } from "./composables/useTheme";
import App from "./App.vue";
import { router } from "./router";

initTheme();

createApp(App).use(createPinia()).use(router).mount("#app");
```

- [ ] **Step 8: Run all tests, type check and build**

Run: `pnpm test && pnpm exec vue-tsc -b && pnpm build`
Expected: all PASS; build succeeds. Fix any missing bare-package import by adding that package to `package.json` (`pnpm add <pkg>`), and any missing local file by copying it from `ember_admin/src`.

- [ ] **Step 9: Commit**

```bash
git add apps/legion_admin
git commit -m "feat(legion_admin): app shell, nav, login and no-access views"
```

---

### Task 4: Docker, compose, agent docs

**Files:**
- Create: `apps/legion_admin/Dockerfile`, `nginx.conf`, `AGENTS.md`, `CLAUDE.md`, `README.md`
- Modify: `docker-compose.yml` (add service before `networks:`)

**Interfaces:** none.

- [ ] **Step 1: Confirm port 26500 is free**

Run: `grep -rn "26500" docker-compose*.yml apps/*/vite.config.ts apps/*/package.json ../../AGENTS.md`
Expected: no match except the port-block line in the workspace `AGENTS.md`. If taken, use the next free port in `26500-26999` everywhere below and in `vite.config.ts`.

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1
# Build context is apps/legion_admin (self-contained: nothing imported from other apps).
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . ./
RUN pnpm run build

FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 3: Copy `nginx.conf` and fix the comment**

```bash
cp apps/ember_admin/nginx.conf apps/legion_admin/nginx.conf
```
Change its first comment line to `# Serves the built legion_admin and sends /api to ember_api, so the browser`. Keep the rest (CSP, `/api/` proxy to `ember_api:8030`, SPA fallback).

- [ ] **Step 4: Add the compose service** in `docker-compose.yml`, after the `ember_admin` service:

```yaml
  legion_admin:
    build: ./apps/legion_admin
    restart: unless-stopped
    ports:
      - "127.0.0.1:26500:80"
    depends_on: [ember_api]
    networks: [core]
```
Also extend the stack comment on line 1 of the file: `legion_admin` joins `ember_web / ember_admin` as a client of `ember_api`. Do not touch the existing `apps/Ember/...` paths.

- [ ] **Step 5: Write `AGENTS.md`**

```markdown
# legion_admin

Project note: `Brain/Projects/legion_admin.md` in the Obsidian vault (`../../../../Brain/` from this folder).

Vue 3 + TypeScript admin app for Legion, only for accounts holding `agents.manage`. Talks only to `ember_api` through the Vite `/api` proxy (no backend of its own). First page: Agents.

## Rules
- Code is copied from `ember_admin`, not shared. Nothing here imports from `ember_admin` or `ember_web`. Apply future fixes in both while both pages exist.
- Add a page: one entry in `src/router/pages.ts`, one route in `src/router/index.ts` with `meta.permission`, one view.
- Radius only through `--radius-*` tokens, colors only through `style.css` tokens (`radiusScale.test.ts` enforces it).
- A switch that calls the server stays pending until the server answers.
- Never add reduced-motion code.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`. Dev: `pnpm dev` (port 26500; `EMBER_API_PORT` sets the proxy target, default 8030).
```
`CLAUDE.md` is exactly `@AGENTS.md`. `README.md`: three lines: what it is, `pnpm install && pnpm dev`, and "needs ember_api running and an account with `agents.manage`".

- [ ] **Step 6: Verify the image builds**

Run: `cd apps/legion_admin && docker build -t legion_admin:test .`
Expected: build succeeds. If Docker is unavailable, say so in the report and skip; `pnpm build` from Task 3 is the fallback evidence.

- [ ] **Step 7: Commit**

```bash
git add apps/legion_admin docker-compose.yml
git commit -m "feat(legion_admin): Dockerfile, compose service and agent docs"
```

---

### Task 5: Verify in a browser and add the vault note

**Files:**
- Create: `Brain/Projects/legion_admin.md` (workspace root `D:\User\Documents\Programming\Brain\Projects\`)

- [ ] **Step 1: Run the app**

Start `ember_api` (see `apps/ember_api/README.md`) then `cd apps/legion_admin && pnpm dev`. Open `http://127.0.0.1:26500`.

- [ ] **Step 2: Check behavior in the browser**

Expected: signed out, `/agents` redirects to `/login?redirect=%2Fagents`. Logging in as an `agents.manage` account shows the Agents list and nav; logging in as an account without it shows "No access" and no nav. `/agents` card list matches `ember_admin`'s `/agents`. Report anything you could not check (for example no admin account available).

- [ ] **Step 3: Run the full checks**

Run: `cd apps/legion_admin && pnpm exec vue-tsc -b && pnpm test && pnpm build`
Expected: all PASS.

- [ ] **Step 4: Add the vault note**

Use the `project-sync` skill (rules in `Brain/AGENTS.md`) to create `Brain/Projects/legion_admin.md` from `apps/legion_admin/AGENTS.md` and README. Link it from `Brain/Projects/Citadel.md` if that note lists components.

- [ ] **Step 5: Commit** (only what is staged for these paths, vault files via the vault's own hook rules)

```bash
git add apps/legion_admin
git commit -m "chore(legion_admin): verify build"
```
Skip this commit if Step 3 changed nothing.
