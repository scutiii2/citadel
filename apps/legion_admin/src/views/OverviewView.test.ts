import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import { useAuthStore } from "../stores/auth";
import OverviewView from "./OverviewView.vue";

async function show(permissions: string[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "ada", email: "a@b.c", email_verified: true, roles: [], permissions };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
  await router.push("/overview");
  const wrapper = mount(OverviewView, { global: { plugins: [pinia, router] } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => vi.restoreAllMocks());

it("counts agents by live status, flags offline ones and links to each permitted page", async () => {
  vi.spyOn(agentsAdminClient, "list").mockResolvedValue([{ id: "a" }, { id: "b" }, { id: "c", enabled: false }] as never);
  vi.spyOn(agentsAdminClient, "live").mockResolvedValue({ a: { status: "running" }, b: { status: "offline" } } as never);
  vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({ one: {}, two: {} } as never);
  const wrapper = await show(["agents.manage"]);
  expect(wrapper.findAll(".stat").map((s) => s.text().replace(/\s+/g, " "))).toEqual([
    expect.stringContaining("Agents3"), expect.stringContaining("Running1"), expect.stringContaining("Offline1"), expect.stringContaining("MCP servers2"),
  ]);
  expect(wrapper.get(".attention").text()).toContain("1 agent is offline");
  expect(wrapper.findAll(".destination").map((d) => d.get("h3").text())).toEqual(["Agents", "Connections"]);
});

it("shows a failed count as unavailable and fetches nothing without agents.manage", async () => {
  const list = vi.spyOn(agentsAdminClient, "list").mockRejectedValue(new Error("down"));
  vi.spyOn(agentsAdminClient, "live").mockResolvedValue({} as never);
  vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({} as never);
  expect((await show(["agents.manage"])).get(".stat").text()).toContain("Unavailable");
  list.mockClear();
  const tuningOnly = await show(["tuning.manage"]);
  expect(list).not.toHaveBeenCalled();
  expect(tuningOnly.find(".stats").exists()).toBe(false);
  expect(tuningOnly.findAll(".destination").map((d) => d.get("h3").text())).toEqual(["Tuning"]);
});
