import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { brainSettingsClient } from "../api/BrainSettingsClient";
import { logsClient } from "../api/LogsClient";
import { ticketsAdminClient } from "../api/TicketsAdminClient";
import { toolServicesClient } from "../api/ToolServicesClient";
import { usageClient } from "../api/UsageClient";
import { usageSettingsClient } from "../api/UsageSettingsClient";
import { useAuthStore } from "../stores/auth";
import OverviewView from "./OverviewView.vue";

async function show(usageFails = false) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "ada", email: "a@b.c", email_verified: true, roles: [], permissions: ["usage.all.view", "logs.view", "tickets.manage", "settings.manage", "tool_services.manage"] };
  if (usageFails) vi.spyOn(usageClient, "allAccounts").mockRejectedValue(new Error("down"));
  else vi.spyOn(usageClient, "allAccounts").mockResolvedValue([{}, {}] as never);
  vi.spyOn(logsClient, "analytics").mockResolvedValue({ totals: { action: { current: 4, previous: 0 }, error: { current: 1, previous: 0 } } } as never);
  vi.spyOn(ticketsAdminClient, "stats").mockResolvedValue({ open: 3, urgent: 1, groups: 2 });
  vi.spyOn(toolServicesClient, "list").mockResolvedValue([{ enabled: true }, { enabled: false }, { enabled: true }] as never);
  vi.spyOn(usageSettingsClient, "get").mockResolvedValue({ stored: { usage: true, pricing: false } } as never);
  vi.spyOn(brainSettingsClient, "get").mockResolvedValue({ stored: { stack: false, long_term: false } } as never);
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
  await router.push("/overview");
  const wrapper = mount(OverviewView, { global: { plugins: [pinia, router] } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => vi.restoreAllMocks());

it("shows live counts and a shortcut per page", async () => {
  const wrapper = await show();
  expect(wrapper.findAll(".stat").map((s) => s.text())).toEqual([
    expect.stringContaining("Accounts with usage2"), expect.stringContaining("Log entries, 7 days5"), expect.stringContaining("Open tickets3"),
    expect.stringContaining("Enabled tool services2"), expect.stringContaining("Changed usage settings1"), expect.stringContaining("Changed brain settings0"),
  ]);
  expect(wrapper.findAll(".destination h3").map((h) => h.text())).toEqual(["Usage", "Analytics", "Tickets", "Usage settings", "Brain settings", "Tool services"]);
  expect(wrapper.find(".attention").exists()).toBe(false);
});

it("warns while Stronghold does not answer and shows a failed count as Unavailable", async () => {
  const wrapper = await show(true);
  expect(wrapper.get(".attention").text()).toContain("Stronghold does not answer");
  expect(wrapper.get(".stat").text()).toContain("Unavailable");
});
