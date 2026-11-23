import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import { useAuthStore } from "../stores/auth";
import TreasuryHeader from "./TreasuryHeader.vue";
import TreasuryNav from "./TreasuryNav.vue";

async function show(reachable: boolean, component: typeof TreasuryHeader | typeof TreasuryNav = TreasuryHeader) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "ada", email: "ada@example.com", email_verified: true, roles: [], permissions: ["settings.manage"] };
  vi.spyOn(treasuryAdminClient, "get").mockResolvedValue({ reachable, instances: [], portcullis: { instance: "a", connection: "a" } });
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
  await router.push("/instances");
  const wrapper = mount(component as typeof TreasuryHeader, { props: { title: "Instances", expanded: true }, attachTo: document.body, global: { plugins: [pinia, router] } });
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

it("notifies only while Treasury does not answer, and Escape returns focus to the icon", async () => {
  const down = await show(false);
  expect(down.find(".indicator").exists()).toBe(true);
  const bell = down.get('button[aria-label="Notifications"]');
  await bell.trigger("click");
  await flushPromises();
  expect(down.get(".notice").text()).toContain("Treasury does not answer");
  await down.get(".treasury-header").trigger("keydown", { key: "Escape" });
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

it("lists the permitted pages with Overview first and no Treasury shortcut", async () => {
  const nav = await show(true, TreasuryNav);
  expect(nav.findAll('nav[aria-label="Treasury sections"] a').map((a) => a.attributes("aria-label"))).toEqual(["Overview", "Instances", "Connections", "Services", "Outside services"]);
  expect(nav.findAll('nav[aria-label="Other admin apps"] a').map((a) => a.attributes("aria-label"))).not.toContain("Treasury Admin");
  nav.unmount();
});
