import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { expect, it, vi } from "vitest";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import { useAuthStore } from "../stores/auth";
import { useTheme } from "../composables/useTheme";
import LegionHeader from "./LegionHeader.vue";
import LegionNav from "./LegionNav.vue";

async function setup(permissions: string[]) {
  const pinia = createPinia();
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/agents", name: "agents", component: { template: "<div />" } },
  ] });
  await router.push("/agents");
  const auth = useAuthStore(pinia);
  auth.account = { id: 1, username: "admin", email: "admin@example.test", email_verified: true, roles: [], permissions };
  return { auth, global: { plugins: [pinia, router] } };
}

it("toggles navigation and keeps theme and logout inside Profile", async () => {
  const { auth, global } = await setup(["agents.manage"]);
  const logout = vi.spyOn(auth, "logout").mockResolvedValue();
  const wrapper = mount(LegionHeader, { props: { title: "Agents", expanded: true }, global });
  await wrapper.get('[aria-label="Collapse sidebar"]').trigger("click");
  expect(wrapper.emitted("toggle")).toHaveLength(1);
  expect(wrapper.get("h1").text()).toBe("Agents");
  expect(wrapper.find("select").exists()).toBe(false);
  await wrapper.get('[aria-label="Profile"]').trigger("click");
  await wrapper.get("select").setValue("dark");
  expect(useTheme().theme.value).toBe("dark");
  await wrapper.get(".header-popover button").trigger("click");
  expect(logout).toHaveBeenCalledOnce();
  const nav = mount(LegionNav, { props: { expanded: false }, global });
  expect(nav.get('[aria-label="Agents"]').attributes("aria-current")).toBe("page");
  expect(nav.find('[aria-label="Tuning"]').exists()).toBe(false);
  expect(nav.get('[aria-label="Admin shortcuts"]').findAll("a")).toHaveLength(4);
  nav.unmount();
  wrapper.unmount();
  useTheme().setTheme("system");
});

it("links only known offline agents and reports when status is unavailable", async () => {
  const fetch = vi.spyOn(agentsAdminClient, "live").mockResolvedValue({
    one: { status: "offline", tiers: [] }, two: { status: "disabled", tiers: [] },
  });
  const { global } = await setup(["agents.manage", "chat.use"]);
  const wrapper = mount(LegionHeader, { props: { title: "Agents", expanded: true }, global });
  await wrapper.get('[aria-label="Notifications"]').trigger("click");
  await flushPromises();
  expect(wrapper.get(".header-popover a").attributes("href")).toBe("/agents?status=offline");
  expect(wrapper.get(".header-popover a").text()).toBe("View 1 offline agent");
  await wrapper.get('[aria-label="Notifications"]').trigger("click");
  fetch.mockRejectedValue(new Error("Forbidden"));
  await wrapper.get('[aria-label="Notifications"]').trigger("click");
  await flushPromises();
  expect(wrapper.get(".header-popover").text()).toContain("Agent status unavailable");
  wrapper.unmount();
});
