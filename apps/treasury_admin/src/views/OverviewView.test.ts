import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import { useAuthStore } from "../stores/auth";
import OverviewView from "./OverviewView.vue";

async function show(reachable = true) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "ada", email: "a@b.c", email_verified: true, roles: [], permissions: ["settings.manage"] };
  vi.spyOn(treasuryAdminClient, "get").mockResolvedValue({ reachable, instances: [{ name: "a", connections: [] }, { name: "b", connections: [] }], portcullis: { instance: "a", connection: "a" } });
  vi.spyOn(treasuryAdminClient, "connections").mockResolvedValue({ connections: [{ name: "data" }, { name: "main" }, { name: "x" }], default_cache: { ttl_seconds: 1, max_entries: 1, negative_ttl_seconds: 1 }, default_cache_stored: false } as never);
  vi.spyOn(treasuryAdminClient, "getServices").mockResolvedValue({ services: [{ name: "armory" }] } as never);
  vi.spyOn(treasuryAdminClient, "getOutside").mockResolvedValue({ groups: [] });
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
    expect.stringContaining("Instances2"), expect.stringContaining("Connections3"), expect.stringContaining("Services1"), expect.stringContaining("Outside services0"),
  ]);
  expect(wrapper.findAll(".destination h3").map((h) => h.text())).toEqual(["Instances", "Connections", "Services", "Outside services"]);
  expect(wrapper.find(".attention").exists()).toBe(false);
});

it("warns while Treasury does not answer and shows a failed count as Unavailable", async () => {
  const wrapper = await show(false);
  expect(wrapper.get(".attention").text()).toContain("Treasury does not answer");
  vi.restoreAllMocks();
  vi.spyOn(treasuryAdminClient, "get").mockRejectedValue(new Error("down"));
  vi.spyOn(treasuryAdminClient, "connections").mockResolvedValue({ connections: [], default_cache: { ttl_seconds: 1, max_entries: 1, negative_ttl_seconds: 1 }, default_cache_stored: false });
  vi.spyOn(treasuryAdminClient, "getServices").mockResolvedValue({ services: [] });
  vi.spyOn(treasuryAdminClient, "getOutside").mockResolvedValue({ groups: [] });
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
  await router.push("/overview");
  const failed = mount(OverviewView, { global: { plugins: [createPinia(), router] } });
  await flushPromises();
  expect(failed.get(".stat").text()).toContain("Unavailable");
});
