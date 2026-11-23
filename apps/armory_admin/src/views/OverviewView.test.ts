import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { capabilitiesAdminClient } from "../api/CapabilitiesAdminClient";
import { emailSettingsClient } from "../api/EmailSettingsClient";
import { environmentClient } from "../api/EnvironmentClient";
import { limitsClient } from "../api/LimitsClient";
import { ticketSettingsClient } from "../api/TicketSettingsClient";
import { useAuthStore } from "../stores/auth";
import OverviewView from "./OverviewView.vue";

async function show(capsFail = false) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "ada", email: "a@b.c", email_verified: true, roles: [], permissions: ["capabilities.manage", "tickets.manage"] };
  if (capsFail) vi.spyOn(capabilitiesAdminClient, "list").mockRejectedValue(new Error("down"));
  else vi.spyOn(capabilitiesAdminClient, "list").mockResolvedValue([{ name: "a", enabled: true }, { name: "b", enabled: false }, { name: "c", enabled: true }] as never);
  vi.spyOn(ticketSettingsClient, "get").mockResolvedValue({ tags: { x: "", y: "" } } as never);
  vi.spyOn(environmentClient, "get").mockResolvedValue({ settings: [{ stored: true }, { stored: false }] } as never);
  vi.spyOn(limitsClient, "get").mockResolvedValue({ pdf_merger: { stored: true }, media_downloader: { stored: false } } as never);
  vi.spyOn(emailSettingsClient, "get").mockResolvedValue({ configured: true, to: ["a@b.c"] });
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
    expect.stringContaining("Capabilities3"), expect.stringContaining("Ticket tags2"), expect.stringContaining("Changed values1"),
    expect.stringContaining("Changed limits1"), expect.stringContaining("Email recipients1"),
  ]);
  expect(wrapper.findAll(".destination h3").map((h) => h.text())).toEqual(["Capabilities", "Ticket settings", "Settings", "Limits", "Email"]);
  expect(wrapper.text()).toContain("2 of 3 capabilities online");
  expect(wrapper.find(".attention").exists()).toBe(false);
});

it("warns while Armory does not answer and shows a failed count as Unavailable", async () => {
  const wrapper = await show(true);
  expect(wrapper.get(".attention").text()).toContain("Armory does not answer");
  expect(wrapper.get(".stat").text()).toContain("Unavailable");
});
