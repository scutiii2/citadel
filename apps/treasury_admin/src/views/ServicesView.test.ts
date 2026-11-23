import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import ServicesView from "./ServicesView.vue";

const view = { services: [
  { name: "armory", url: "http://armory:29600", source: "registered" as const, registered: "http://armory:29600", pinned: null },
  { name: "legion", url: "http://legion:29603", source: "pinned" as const, registered: null, pinned: "http://legion:29603" },
  { name: "stronghold", url: "http://127.0.0.1:29650", source: "default" as const, registered: null, pinned: null },
] };
beforeEach(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
  vi.spyOn(treasuryAdminClient, "getServices").mockResolvedValue(view);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(ServicesView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const open = async (wrapper: VueWrapper, name: string) => { await wrapper.get(`[data-test="row-${name}"] button`).trigger("click"); await flushPromises(); };
const confirm = async (wrapper: VueWrapper) => {
  await wrapper.findAllComponents(ConfirmModal).find((c) => c.props("open"))!.get("button.confirm").trigger("click");
  await flushPromises();
};

it("shows service addresses and their sources, and filters by source", async () => {
  const wrapper = await mounted();
  expect(wrapper.findAll("tbody tr")).toHaveLength(3);
  expect(wrapper.get('[data-test="row-armory"]').text()).toContain("Registered");
  expect(wrapper.get('[data-test="row-legion"]').text()).toContain("Pinned");
  expect(wrapper.get('[data-test="row-stronghold"]').text()).toContain("Default");
  await wrapper.findAll(".filters button").find((b) => b.text().startsWith("Pinned"))!.trigger("click");
  expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  wrapper.unmount();
});

it("pins an address after confirming and uses the registered address after unpinning", async () => {
  const put = vi.spyOn(treasuryAdminClient, "putService").mockResolvedValue(view);
  const remove = vi.spyOn(treasuryAdminClient, "deleteService").mockResolvedValue(view);
  const wrapper = await mounted();
  await open(wrapper, "armory");
  await wrapper.get('[data-test="edit"]').trigger("click");
  await wrapper.get("#pin-armory").setValue("http://armory.lan:29600");
  await wrapper.get('[data-test="pin"]').trigger("click");
  expect(put).not.toHaveBeenCalled();
  await confirm(wrapper);
  expect(put).toHaveBeenCalledWith("armory", "http://armory.lan:29600");
  await open(wrapper, "legion");
  await wrapper.get('[data-test="unpin"]').trigger("click");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith("legion");
  wrapper.unmount();
});

it("shows Treasury refusal and preserves the draft", async () => {
  vi.spyOn(treasuryAdminClient, "putService").mockRejectedValue(new Error("an address looks like http://host:port"));
  const wrapper = await mounted();
  await open(wrapper, "armory");
  await wrapper.get('[data-test="edit"]').trigger("click");
  await wrapper.get("#pin-armory").setValue("bad");
  await wrapper.get('[data-test="pin"]').trigger("click");
  await confirm(wrapper);
  expect(wrapper.get('[role="alert"]').text()).toContain("an address looks like");
  expect((wrapper.get("#pin-armory").element as HTMLInputElement).value).toBe("bad");
  wrapper.unmount();
});

it("keeps a pending draft when search hides its row", async () => {
  const wrapper = await mounted();
  await open(wrapper, "armory");
  await wrapper.get('[data-test="edit"]').trigger("click");
  await wrapper.get("#pin-armory").setValue("http://draft:1");
  await wrapper.get('input[type="search"]').setValue("legion");
  expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  expect((wrapper.get("#pin-armory").element as HTMLInputElement).value).toBe("http://draft:1");
  wrapper.unmount();
});
