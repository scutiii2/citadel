import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { treasuryAdminClient, type TreasuryView } from "../api/TreasuryAdminClient";
import { useNoticesStore } from "../stores/notices";
import InstancesView from "./InstancesView.vue";

const view = (over: Partial<TreasuryView> = {}): TreasuryView => ({
  reachable: true,
  instances: [{ name: "stronghold", connections: ["stronghold"] }, { name: "armory", connections: [] }],
  portcullis: { instance: "stronghold", connection: "stronghold" },
  ...over,
});

beforeEach(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
  setActivePinia(createPinia());
});
afterEach(() => vi.restoreAllMocks());

const mounted = async () => {
  const wrapper = mount(InstancesView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
};

describe("InstancesView", () => {
  it("lists each instance with its connections and marks the one Portcullis uses in its drawer", async () => {
    vi.spyOn(treasuryAdminClient, "get").mockResolvedValue(view());
    const wrapper = await mounted();
    const rows = wrapper.findAll('[data-test="instance"]');
    expect(rows).toHaveLength(2);
    expect(rows[0]!.text()).toContain("stronghold");
    expect(rows[1]!.text()).toContain("No connections");
    await rows[0]!.get("button").trigger("click");
    expect(wrapper.find("[data-test=portcullis]").exists()).toBe(true);
    wrapper.unmount();
  });

  it("searches instance and connection names", async () => {
    vi.spyOn(treasuryAdminClient, "get").mockResolvedValue(view());
    const wrapper = await mounted();
    await wrapper.get('input[type="search"]').setValue("nothing");
    expect(wrapper.text()).toContain("No instances match your search.");
    wrapper.unmount();
  });

  it("says so when Treasury does not answer and shares that with the notices", async () => {
    vi.spyOn(treasuryAdminClient, "get").mockResolvedValue(view({ reachable: false, instances: [] }));
    const wrapper = await mounted();
    expect(wrapper.find("[role=alert]").text()).toContain("Treasury does not answer");
    expect(useNoticesStore().reachable).toBe(false);
    wrapper.unmount();
  });

  it("shows a failed load and refreshes on request", async () => {
    const get = vi.spyOn(treasuryAdminClient, "get").mockRejectedValueOnce(new Error("boom")).mockResolvedValue(view());
    const wrapper = await mounted();
    expect(wrapper.find("[role=alert]").exists()).toBe(true);
    await wrapper.get('[data-test="refresh"]').trigger("click");
    await flushPromises();
    expect(get).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll('[data-test="instance"]')).toHaveLength(2);
    wrapper.unmount();
  });
});
