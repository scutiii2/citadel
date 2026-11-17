import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import ServicesView from "./ServicesView.vue";

const view = { services: [
  { name: "armory", url: "http://armory:29600", source: "registered" as const, registered: "http://armory:29600", pinned: null },
  { name: "legion", url: "http://legion:29603", source: "pinned" as const, registered: null, pinned: "http://legion:29603" },
  { name: "stronghold", url: "http://127.0.0.1:29650", source: "default" as const, registered: null, pinned: null },
] };
beforeEach(() => vi.spyOn(treasuryAdminClient, "getServices").mockResolvedValue(view));
afterEach(() => vi.restoreAllMocks());

it("shows service addresses and their sources", async () => {
  const wrapper = mount(ServicesView);
  await flushPromises();
  expect(wrapper.findAll("tbody tr")).toHaveLength(3);
  expect(wrapper.get('[data-test="row-armory"]').text()).toContain("Registered");
  expect(wrapper.get('[data-test="row-legion"]').text()).toContain("Pinned");
  expect(wrapper.get('[data-test="row-stronghold"]').text()).toContain("Default");
  wrapper.unmount();
});

it("pins an address and uses the registered address after unpinning", async () => {
  const put = vi.spyOn(treasuryAdminClient, "putService").mockResolvedValue(view);
  const remove = vi.spyOn(treasuryAdminClient, "deleteService").mockResolvedValue(view);
  const wrapper = mount(ServicesView);
  await flushPromises();
  await wrapper.get('[data-test="row-armory"] input').setValue("http://armory.lan:29600");
  await wrapper.get('[data-test="row-armory"] form').trigger("submit");
  await flushPromises();
  expect(put).toHaveBeenCalledWith("armory", "http://armory.lan:29600");
  await wrapper.get('[data-test="row-legion"] [data-test="unpin"]').trigger("click");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith("legion");
  wrapper.unmount();
});

it("shows Treasury refusal and preserves the draft", async () => {
  vi.spyOn(treasuryAdminClient, "putService").mockRejectedValue(new Error("an address looks like http://host:port"));
  const wrapper = mount(ServicesView);
  await flushPromises();
  await wrapper.get('[data-test="row-armory"] input').setValue("bad");
  await wrapper.get('[data-test="row-armory"] form').trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("an address looks like");
  expect((wrapper.get('[data-test="row-armory"] input').element as HTMLInputElement).value).toBe("bad");
  wrapper.unmount();
});
