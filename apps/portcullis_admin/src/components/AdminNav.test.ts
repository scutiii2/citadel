import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useConfigIssuesStore } from "../stores/configIssues";
import { useNavPrefsStore } from "../stores/navPrefs";
import AdminNav from "./AdminNav.vue";

beforeEach(() => {
  localStorage.clear();
});

async function show(permissions: string[], path = "/overview", expanded = false) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.account = { id: 1, username: "ada", email: "ada@example.com", email_verified: true, roles: [], permissions };
  const router = createRouter({ history: createMemoryHistory(), routes: ["/", "/overview", "/config-issues", "/admin/accounts", "/admin/roles", "/admin/invites", "/admin/settings"].map((p) => ({ path: p, component: { template: "<div />" } })) });
  await router.push(path);
  const wrapper = mount(AdminNav, { props: { expanded }, global: { plugins: [pinia, router] } });
  await flushPromises();
  return wrapper;
}

const labels = (w: Awaited<ReturnType<typeof show>>) => w.findAll("nav[aria-label='Admin sections'] a").map((a) => a.attributes("aria-label"));

it("names icon-only links and marks the current page", async () => {
  const w = await show(["invites.manage", "settings.manage", "accounts.view"]);
  const links = w.findAll("nav[aria-label='Admin sections'] a");
  expect(labels(w)).toEqual(["Overview", "Accounts", "Workspace settings", "Invites"]);
  expect(links.every((a) => a.text() === "" && a.find("svg").exists())).toBe(true);
  expect(w.get("a[aria-label='Overview']").attributes("aria-current")).toBe("page");
});

it("shows labels when expanded", async () => {
  const w = await show(["invites.manage"], "/overview", true);
  expect(w.get("a[aria-label='Invites']").text()).toBe("Invites");
});

it("marks only the current administration page", async () => {
  const w = await show(["accounts.view", "roles.view", "invites.manage", "settings.manage"], "/admin/roles");
  expect(w.findAll("nav[aria-label='Admin sections'] a[aria-current='page']").map((a) => a.attributes("aria-label"))).toEqual(["Roles & permissions"]);
});

it("lists the pages in the default arrangement after Overview", async () => {
  const w = await show(["accounts.manage", "roles.manage", "invites.manage", "settings.manage"]);
  expect(labels(w)).toEqual(["Overview", "Roles & permissions", "Accounts", "Workspace settings", "Invites"]);
});

it("follows the saved order and hidden pages", async () => {
  const w = await show(["accounts.manage", "invites.manage", "settings.manage"]);
  useNavPrefsStore().update({ order: ["/admin/invites", "/admin/accounts", "/admin/settings"], pinned: [], hidden: ["/admin/settings"] });
  await flushPromises();
  expect(labels(w)).toEqual(["Overview", "Invites", "Accounts"]);
});

it("offers only the permitted pages", async () => {
  const w = await show(["invites.manage"]);
  expect(labels(w)).toEqual(["Overview", "Invites"]);
});

it("links Config issues with its counts only while there are issues", async () => {
  const w = await show(["config.issues.view"]);
  expect(labels(w)).toEqual(["Overview"]);
  useConfigIssuesStore().issues = [{ file: "a.json", key: "k", severity: "error", message: "m" }, { file: "b.json", key: "k", severity: "warning", message: "m" }];
  await flushPromises();
  expect(labels(w)).toEqual(["Overview", "Config issues: 1 error, 1 warning"]);
  expect(w.get("a.alert .count").text()).toBe("2");
});

it("links to the other admin apps, not to itself", async () => {
  const w = await show(["roles.view"]);
  const links = w.findAll("nav[aria-label='Other admin apps'] a");
  expect(links.map((a) => a.attributes("aria-label"))).toEqual(["Legion Admin", "Armory Admin", "Stronghold Admin", "Treasury Admin"]);
  expect(links.map((a) => new URL(a.attributes("href")!).port)).toEqual(["26500", "26503", "26504", "26505"]);
});
