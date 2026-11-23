// apps/treasury_admin/src/views/OutsideView.test.ts
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import OutsideView from "./OutsideView.vue";

const view = { groups: [
  { service_id: "a".repeat(32), name: "bard", used_by: ["legion", "stronghold"],
    origins: [{ origin_id: "b".repeat(32), origin: "http://bard:29400" }, { origin_id: "c".repeat(32), origin: "http://bard2:29400" }] },
  { service_id: "d".repeat(32), name: "lens", used_by: [], origins: [{ origin_id: "e".repeat(32), origin: "http://lens:29403" }] },
] };
const BARD = "a".repeat(32);
const LENS = "d".repeat(32);
const ORIGIN = "c".repeat(32);

beforeEach(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
  vi.spyOn(treasuryAdminClient, "getOutside").mockResolvedValue(view);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function mounted() {
  const wrapper = mount(OutsideView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const open = async (wrapper: VueWrapper, name: string) => { await wrapper.get(`[data-test="group-${name}"] button`).trigger("click"); await flushPromises(); };
const openModal = (wrapper: VueWrapper) => wrapper.findAllComponents(ConfirmModal).find((c) => c.props("open"))!;

it("lists groups with their origins and users, and searches them", async () => {
  const wrapper = await mounted();
  expect(wrapper.findAll("tbody tr")).toHaveLength(2);
  const bard = wrapper.get('[data-test="group-bard"]').text();
  expect(bard).toContain("http://bard:29400");
  expect(bard).toContain("http://bard2:29400");
  expect(bard).toContain("legion");
  expect(wrapper.get('[data-test="group-lens"]').text()).toContain("Not used");
  await wrapper.get('input[type="search"]').setValue("lens");
  expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  wrapper.unmount();
});

it("renames a group and reloads, keeping another group's draft", async () => {
  const renamed = { ...view.groups[0], name: "speech" };
  const rename = vi.spyOn(treasuryAdminClient, "renameOutside").mockResolvedValue(renamed);
  vi.mocked(treasuryAdminClient.getOutside).mockResolvedValueOnce(view)
    .mockResolvedValueOnce({ groups: [renamed, view.groups[1]] });
  const wrapper = await mounted();
  await open(wrapper, "lens");
  await wrapper.get("#name-" + LENS).setValue("lens-draft");
  await open(wrapper, "bard");
  await wrapper.get("#name-" + BARD).setValue("speech");
  await wrapper.get(".rename").trigger("submit");
  await flushPromises();
  expect(rename).toHaveBeenCalledWith(BARD, "speech");
  expect((wrapper.get("#name-" + BARD).element as HTMLInputElement).value).toBe("speech");
  await open(wrapper, "lens");
  expect((wrapper.get("#name-" + LENS).element as HTMLInputElement).value).toBe("lens-draft");
  expect(treasuryAdminClient.getOutside).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});

it("keeps the draft and shows Treasury's refusal on a bad rename", async () => {
  vi.spyOn(treasuryAdminClient, "renameOutside").mockRejectedValue(new Error("the name 'armory' is the name of a Citadel service"));
  const wrapper = await mounted();
  await open(wrapper, "bard");
  await wrapper.get("#name-" + BARD).setValue("armory");
  await wrapper.get(".rename").trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("Citadel service");
  expect((wrapper.get("#name-" + BARD).element as HTMLInputElement).value).toBe("armory");
  wrapper.unmount();
});

it("asks first, naming the users, then deletes a group", async () => {
  const remove = vi.spyOn(treasuryAdminClient, "deleteOutsideGroup").mockResolvedValue({ groups: [view.groups[1]] });
  const wrapper = await mounted();
  await open(wrapper, "bard");
  await wrapper.get('[data-test="delete-group"]').trigger("click");
  const modal = openModal(wrapper);
  expect(modal.props("message")).toContain("legion, stronghold");
  expect(remove).not.toHaveBeenCalled();
  await modal.get("button.confirm").trigger("click");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith(BARD);
  expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  wrapper.unmount();
});

it("deletes one origin after confirmation", async () => {
  const remove = vi.spyOn(treasuryAdminClient, "deleteOutsideOrigin").mockResolvedValue(view);
  const wrapper = await mounted();
  await open(wrapper, "bard");
  await wrapper.get('[data-test="delete-origin-' + ORIGIN + '"]').trigger("click");
  let modal = openModal(wrapper);
  expect(modal.props("message")).toContain("legion, stronghold");
  await modal.get("button.cancel").trigger("click");
  expect(remove).not.toHaveBeenCalled();
  await wrapper.get('[data-test="delete-origin-' + ORIGIN + '"]').trigger("click");
  modal = openModal(wrapper);
  await modal.get("button.confirm").trigger("click");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith(ORIGIN);
  wrapper.unmount();
});

it.each(["group", "origin"] as const)("shows a failed %s delete beside the attempted control", async (kind) => {
  const operation = kind === "group" ? "deleteOutsideGroup" : "deleteOutsideOrigin";
  vi.spyOn(treasuryAdminClient, operation).mockRejectedValue(new Error("Treasury is unreachable"));
  const wrapper = await mounted();
  await open(wrapper, "bard");
  const selector = kind === "group" ? '[data-test="delete-group"]' : '[data-test="delete-origin-' + ORIGIN + '"]';
  await wrapper.get(selector).trigger("click");
  const modal = openModal(wrapper);
  await modal.get("button.confirm").trigger("click");
  await flushPromises();
  const button = wrapper.get(selector);
  expect(button.element.parentElement?.querySelector('[role="alert"]')?.textContent?.trim()).toBe("Treasury is unreachable");
  expect(wrapper.findAll("tbody tr")).toHaveLength(2);
  wrapper.unmount();
});

it("sends confirm=true on both deletion requests", async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify(view)));
  vi.stubGlobal("fetch", fetch);

  const groupId = view.groups[0].service_id;
  const originId = view.groups[0].origins[0].origin_id;
  await treasuryAdminClient.deleteOutsideGroup(groupId);
  await treasuryAdminClient.deleteOutsideOrigin(originId);

  expect(fetch).toHaveBeenNthCalledWith(1, "/api/admin/treasury/outside/" + groupId + "?confirm=true",
    expect.objectContaining({ method: "DELETE" }));
  expect(fetch).toHaveBeenNthCalledWith(2, "/api/admin/treasury/outside/origins/" + originId + "?confirm=true",
    expect.objectContaining({ method: "DELETE" }));
});
