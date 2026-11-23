import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { capabilitiesAdminClient } from "../api/CapabilitiesAdminClient";
import { useAuthStore } from "../stores/auth";
import ArmoryHeader from "./ArmoryHeader.vue";
import ArmoryNav from "./ArmoryNav.vue";

async function show(up: boolean, component: typeof ArmoryHeader | typeof ArmoryNav = ArmoryHeader, permissions = ["capabilities.manage", "tickets.manage"]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "ada", email: "ada@example.com", email_verified: true, roles: [], permissions };
  if (up) vi.spyOn(capabilitiesAdminClient, "list").mockResolvedValue([]);
  else vi.spyOn(capabilitiesAdminClient, "list").mockRejectedValue(new Error("down"));
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
  await router.push("/overview");
  const wrapper = mount(component as typeof ArmoryHeader, { props: { title: "Overview", expanded: true }, attachTo: document.body, global: { plugins: [pinia, router] } });
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

it("notifies only while Armory does not answer, and Escape returns focus to the icon", async () => {
  const down = await show(false);
  expect(down.find(".indicator").exists()).toBe(true);
  const bell = down.get('button[aria-label="Notifications"]');
  await bell.trigger("click");
  await flushPromises();
  expect(down.get(".notice").text()).toContain("Armory does not answer");
  await down.get(".armory-header").trigger("keydown", { key: "Escape" });
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

it("lists the permitted pages with Overview first and no Armory shortcut", async () => {
  const nav = await show(true, ArmoryNav);
  expect(nav.findAll('nav[aria-label="Armory sections"] a').map((a) => a.attributes("aria-label"))).toEqual(["Overview", "Capabilities", "Ticket settings", "Settings", "Limits", "Email"]);
  expect(nav.findAll('nav[aria-label="Other admin apps"] a').map((a) => a.attributes("aria-label"))).not.toContain("Armory Admin");
  nav.unmount();
  const tickets = await show(true, ArmoryNav, ["tickets.manage"]);
  expect(tickets.findAll('nav[aria-label="Armory sections"] a').map((a) => a.attributes("aria-label"))).toEqual(["Overview", "Ticket settings"]);
  tickets.unmount();
});
