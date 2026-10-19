import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import AdminNav from "./AdminNav.vue";
import { useNavPrefsStore } from "../stores/navPrefs";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.style.colorScheme = "";
});

async function show(permissions: string[] | null, path = "/overview") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  if (permissions) auth.account = { id: 1, username: "ada", email: "ada@example.com", email_verified: true, roles: [], permissions };
  const router = createRouter({ history: createMemoryHistory(), routes: ["/", "/profile", "/settings", "/capabilities", "/extensions", "/agents", "/analytics", "/usage", "/overview", "/admin/accounts", "/admin/roles", "/admin/invites", "/admin/settings"].map(path => ({ path, component: { template: "<div />" } })) });
  await router.push(path);
  const w = mount(AdminNav, { global: { plugins: [pinia, router] } });
  await flushPromises();
  return w;
}

it("names icon-only links and marks the current page", async () => {
  const w = await show(["capabilities.manage", "extensions.manage", "accounts.view"]);
  const links = w.findAll("nav[aria-label='Admin sections'] a");
  expect(links.map(a => a.attributes("aria-label"))).toEqual(["Accounts", "Capabilities", "Extensions"]);
  expect(links.every(a => a.text() === "" && a.find("svg").exists())).toBe(true);
  expect(w.get("a.wordmark[aria-label='Overview']").attributes("aria-current")).toBe("page");
  expect(w.find("nav a[aria-label='Overview']").exists()).toBe(false);
});

it("marks only the current administration page in the main rail", async () => {
  const w = await show(["accounts.view", "roles.view", "invites.manage", "settings.manage"], "/admin/roles");
  expect(w.findAll('nav a[aria-current="page"]').map(a => a.attributes('aria-label'))).toEqual(['Roles & permissions']);
  expect(w.get("a[aria-label='Overview']").attributes('aria-current')).toBeUndefined();
  expect(w.findAll('nav a').map(a => a.attributes('aria-label'))).toEqual(['Roles & permissions', 'Accounts', 'Workspace settings', 'Invites']);
});

it("lists the pages in the default arrangement", async () => {
  const w = await show(["accounts.manage", "roles.manage", "invites.manage", "settings.manage", "capabilities.manage", "extensions.manage", "agents.manage", "tickets.manage", "usage.all.view", "traffic.view"]);
  expect(w.findAll("nav[aria-label='Admin sections'] a").map(a => a.attributes("aria-label"))).toEqual([
    "Roles & permissions", "Accounts", "Capabilities", "Extensions", "Agents", "Analytics", "Usage", "Workspace settings", "Invites", "Tickets",
  ]);
});

it("lets an extension manager reach Extensions without offering other pages", async () => {
  const w = await show(["extensions.manage"]);
  expect(w.findAll("nav[aria-label='Admin sections'] a").map(a => a.attributes("aria-label"))).toEqual(["Extensions"]);
});

it("lets visitors cycle and save their theme", async () => {
  const w = await show(null);
  expect(w.find("nav[aria-label='Admin sections']").exists()).toBe(false);
  const button = w.get("button[aria-label^='Theme:']");
  await button.trigger("click");
  expect(document.documentElement.style.colorScheme).toBe("light");
  expect(localStorage.getItem("ember_admin.theme")).toBe("light");
  await button.trigger("click");
  expect(document.documentElement.style.colorScheme).toBe("dark");
  await button.trigger("click");
  expect(document.documentElement.style.colorScheme).toBe("light dark");
});

it("keeps personal pages reachable without admin grants, in the account menu", async () => {
  const w = await show([], "/profile");
  await w.get("button.account").trigger("click");
  expect(w.get(".menu .email").text()).toBe("ada@example.com");
  expect(w.findAll(".menu a.row").map(a => [a.text(), a.attributes("href")])).toEqual([["Profile", "/profile"], ["Settings", "/settings"]]);
  expect(w.get(".menu a.router-link-exact-active").text()).toBe("Profile");
  expect(w.find("nav a[aria-label='Settings']").exists()).toBe(false);
});

it("opens the account menu with Theme and Log out, and closes it on Escape", async () => {
  const w = await show([]);
  expect(w.find(".menu").exists()).toBe(false);
  await w.get("button.account").trigger("click");
  expect(w.get(".theme-row").text()).toContain("Theme");
  await w.get(".theme-row").trigger("click");
  expect(localStorage.getItem("ember_admin.theme")).toBe("light");
  await w.get(".menu").trigger("keydown", { key: "Escape" });
  expect(w.find(".menu").exists()).toBe(false);
});

it("logs out from the account menu", async () => {
  const w = await show([]);
  const auth = useAuthStore();
  const logout = vi.spyOn(auth, "logout").mockResolvedValue(undefined as never);
  await w.get("button.account").trigger("click");
  await w.get("button.logout").trigger("click");
  expect(logout).toHaveBeenCalled();
  expect(w.find(".menu").exists()).toBe(false);
});

it("keeps Overview reachable when every administration page is hidden", async () => {
  const w = await show(["extensions.manage"]);
  useNavPrefsStore().update({ order: ["/extensions"], pinned: [], hidden: ["/extensions"] });
  await flushPromises();
  expect(w.find("nav").exists()).toBe(false);
  expect(w.get("a[aria-label='Overview']").attributes("href")).toBe("/overview");
  expect(w.find("button.account").exists()).toBe(true);
});

it("exposes Usage and Overview to a usage-only observer", async () => {
  const w = await show(["usage.all.view"], "/usage");
  expect(w.get("a[aria-label='Usage']").attributes("aria-current")).toBe("page");
  expect(w.get("a[aria-label='Overview']").attributes("href")).toBe("/overview");
  expect(w.find("a[aria-label='Accounts']").exists()).toBe(false);
});

it("links the wordmark to the canonical overview and marks it current", async () => {
  const wrapper = await show(["roles.view"], "/overview");
  expect(wrapper.get("a.wordmark").attributes("href")).toBe("/overview");
  expect(wrapper.get("a.wordmark").attributes("aria-current")).toBe("page");
});
