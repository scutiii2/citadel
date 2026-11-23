import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { usageClient } from "../api/UsageClient";
import { useAuthStore } from "../stores/auth";
import StrongholdHeader from "./StrongholdHeader.vue";
import StrongholdNav from "./StrongholdNav.vue";

async function show(up: boolean, component: typeof StrongholdHeader | typeof StrongholdNav = StrongholdHeader, permissions = ["usage.all.view", "tickets.manage", "traffic.view", "settings.manage", "tool_services.manage"]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "ada", email: "ada@example.com", email_verified: true, roles: [], permissions };
  if (up) vi.spyOn(usageClient, "allAccounts").mockResolvedValue([]);
  else vi.spyOn(usageClient, "allAccounts").mockRejectedValue(new Error("down"));
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
  await router.push("/overview");
  const wrapper = mount(component as typeof StrongholdHeader, { props: { title: "Overview", expanded: true }, attachTo: document.body, global: { plugins: [pinia, router] } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => { document.body.innerHTML = ""; });

it("puts theme and Log out in Profile, with no Ember link", async () => {
  const wrapper = await show(true);
  await wrapper.get('button[aria-label="Profile"]').trigger("click");
  expect(wrapper.get(".account-menu").text()).toContain("ada@example.com");
  expect(wrapper.find(".account-menu select").exists()).toBe(true);
  expect(wrapper.get(".account-menu .logout").text()).toBe("Log out");
  expect(wrapper.text()).not.toContain("Ember");
  wrapper.unmount();
});

it("notifies only while Stronghold does not answer, and Escape returns focus to the icon", async () => {
  const down = await show(false);
  expect(down.find(".indicator").exists()).toBe(true);
  const bell = down.get('button[aria-label="Notifications"]');
  await bell.trigger("click");
  await flushPromises();
  expect(down.get(".notice").text()).toContain("Stronghold does not answer");
  await down.get(".stronghold-header").trigger("keydown", { key: "Escape" });
  expect(down.find(".header-popover").exists()).toBe(false);
  expect(document.activeElement).toBe(bell.element);
  down.unmount();
  const up = await show(true);
  expect(up.find(".indicator").exists()).toBe(false);
  await up.get('button[aria-label="Notifications"]').trigger("click");
  await flushPromises();
  expect(up.get(".header-popover").text()).toContain("all caught up");
  up.unmount();
});

it("lists the permitted pages with Overview first, Analytics for traffic.view, and no Stronghold shortcut", async () => {
  const nav = await show(true, StrongholdNav);
  expect(nav.findAll('nav[aria-label="Stronghold sections"] a').map((a) => a.attributes("aria-label"))).toEqual(["Overview", "Usage", "Analytics", "Tickets", "Usage settings", "Brain settings", "Tool services"]);
  expect(nav.findAll('nav[aria-label="Other admin apps"] a').map((a) => a.attributes("aria-label"))).not.toContain("Stronghold Admin");
  nav.unmount();
  const traffic = await show(true, StrongholdNav, ["traffic.view"]);
  expect(traffic.findAll('nav[aria-label="Stronghold sections"] a').map((a) => a.attributes("aria-label"))).toEqual(["Overview", "Analytics"]);
  traffic.unmount();
});
