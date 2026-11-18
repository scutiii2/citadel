import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { treasuryAdminClient, type TreasuryView } from "../api/TreasuryAdminClient";
import InstancesView from "./InstancesView.vue";

const view = (over: Partial<TreasuryView> = {}): TreasuryView => ({
  reachable: true,
  instances: [{ name: "stronghold", connections: ["stronghold"] }, { name: "armory", connections: [] }],
  portcullis: { instance: "stronghold", connection: "stronghold" },
  ...over,
});

afterEach(() => vi.restoreAllMocks());

describe("InstancesView", () => {
  it("lists each instance with its connections and marks the one Portcullis uses", async () => {
    vi.spyOn(treasuryAdminClient, "get").mockResolvedValue(view());
    const wrapper = mount(InstancesView);
    await flushPromises();
    const cards = wrapper.findAll("li.card");
    expect(cards).toHaveLength(2);
    expect(cards[0]!.text()).toContain("Connections: stronghold");
    expect(cards[0]!.find("[data-test=portcullis]").exists()).toBe(true);
    expect(cards[1]!.text()).toContain("No connections");
    expect(cards[1]!.find("[data-test=portcullis]").exists()).toBe(false);
  });

  it("says so when Treasury does not answer", async () => {
    vi.spyOn(treasuryAdminClient, "get").mockResolvedValue(view({ reachable: false, instances: [] }));
    const wrapper = mount(InstancesView);
    await flushPromises();
    expect(wrapper.find("[role=alert]").text()).toContain("Treasury does not answer");
  });

  it("shows a failed load and refreshes on request", async () => {
    const get = vi.spyOn(treasuryAdminClient, "get").mockRejectedValueOnce(new Error("boom")).mockResolvedValue(view());
    const wrapper = mount(InstancesView);
    await flushPromises();
    expect(wrapper.find("[role=alert]").exists()).toBe(true);
    await wrapper.find("button").trigger("click");
    await flushPromises();
    expect(get).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll("li.card")).toHaveLength(2);
  });
});
