import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { configIssuesClient } from "../api/ConfigIssuesClient";
import { useTheme } from "../composables/useTheme";
import { useAuthStore } from "../stores/auth";
import { useConfigIssuesStore } from "../stores/configIssues";
import PortcullisHeader from "./PortcullisHeader.vue";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

async function show(permissions: string[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  vi.spyOn(configIssuesClient, "list").mockResolvedValue([]);
  const auth = useAuthStore();
  auth.account = { id: 1, username: "ada", email: "ada@example.com", email_verified: true, roles: [], permissions };
  const router = createRouter({ history: createMemoryHistory(), routes: ["/", "/profile", "/settings", "/config-issues"].map((p) => ({ path: p, component: { template: "<div />" } })) });
  await router.push("/");
  const wrapper = mount(PortcullisHeader, { props: { title: "Accounts", expanded: true }, attachTo: document.body, global: { plugins: [pinia, router] } });
  await flushPromises();
  return { wrapper, auth };
}

it("shows the title, toggles the sidebar and keeps theme and logout inside Profile", async () => {
  const { wrapper, auth } = await show([]);
  const logout = vi.spyOn(auth, "logout").mockResolvedValue(undefined as never);
  expect(wrapper.get("h1").text()).toBe("Accounts");
  await wrapper.get('[aria-label="Collapse sidebar"]').trigger("click");
  expect(wrapper.emitted("toggle")).toHaveLength(1);
  expect(wrapper.find("select").exists()).toBe(false);
  expect(wrapper.find(".logout").exists()).toBe(false);
  await wrapper.get('[aria-label="Profile"]').trigger("click");
  expect(wrapper.get(".identity").text()).toContain("ada@example.com");
  expect(wrapper.findAll(".account-menu nav a").map((a) => a.text())).toEqual(["Profile", "Settings", "Ember"]);
  await wrapper.get("select").setValue("light");
  expect(localStorage.getItem("ember_admin.theme")).toBe("light");
  await wrapper.get(".logout").trigger("click");
  expect(logout).toHaveBeenCalledOnce();
  useTheme().setTheme("system");
  wrapper.unmount();
});

it("closes on Escape and returns focus to the control that opened it", async () => {
  const { wrapper } = await show([]);
  const profile = wrapper.get('[aria-label="Profile"]');
  await profile.trigger("click");
  await wrapper.get(".header-popover").trigger("keydown", { key: "Escape" });
  expect(wrapper.find(".header-popover").exists()).toBe(false);
  expect(document.activeElement).toBe(profile.element);
  wrapper.unmount();
});

it("hides config notifications without permission and links real issues with it", async () => {
  const none = await show([]);
  await none.wrapper.get('[aria-label="Notifications"]').trigger("click");
  expect(none.wrapper.get(".header-popover").text()).toContain("Nothing to report");
  expect(none.wrapper.find(".header-popover a").exists()).toBe(false);
  none.wrapper.unmount();

  const { wrapper } = await show(["config.issues.view"]);
  const list = vi.mocked(configIssuesClient.list);
  list.mockResolvedValue([{ file: "config_app.json", key: "port", severity: "error", message: "bad" }]);
  await wrapper.get('[aria-label="Notifications"]').trigger("click");
  await flushPromises();
  expect(wrapper.get(".header-popover a").attributes("href")).toBe("/config-issues");
  expect(wrapper.get(".header-popover a").text()).toBe("Config issues: 1 error");
  wrapper.unmount();
});

it("tells a failed check apart from an empty result", async () => {
  const { wrapper } = await show(["config.issues.view"]);
  const store = useConfigIssuesStore();
  vi.mocked(configIssuesClient.list).mockRejectedValue(new Error("Portcullis unreachable"));
  await wrapper.get('[aria-label="Notifications"]').trigger("click");
  await flushPromises();
  expect(store.error).toContain("unreachable");
  expect(wrapper.get(".header-popover").text()).toContain("Configuration check failed");
  expect(wrapper.get(".header-popover").text()).not.toContain("No config issues");
  wrapper.unmount();
});
