// apps/treasury_admin/src/views/OutsideView.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import OutsideView from "./OutsideView.vue";

const view = { groups: [
  { service_id: "a".repeat(32), name: "bard", used_by: ["legion", "stronghold"],
    origins: [{ origin_id: "b".repeat(32), origin: "http://bard:29400" }, { origin_id: "c".repeat(32), origin: "http://bard2:29400" }] },
  { service_id: "d".repeat(32), name: "lens", used_by: [], origins: [{ origin_id: "e".repeat(32), origin: "http://lens:29403" }] },
] };
beforeEach(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
  vi.spyOn(treasuryAdminClient, "getOutside").mockResolvedValue(view);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("lists groups with their origins and users", async () => {
  const wrapper = mount(OutsideView);
  await flushPromises();
  expect(wrapper.findAll("tbody tr")).toHaveLength(2);
  const bard = wrapper.get('[data-test="group-bard"]').text();
  expect(bard).toContain("http://bard:29400");
  expect(bard).toContain("http://bard2:29400");
  expect(bard).toContain("legion");
  expect(wrapper.get('[data-test="group-lens"]').text()).toContain("Not used");
  wrapper.unmount();
});

it("renames a group and reloads", async () => {
  const renamed = { ...view.groups[0], name: "speech" };
  const rename = vi.spyOn(treasuryAdminClient, "renameOutside").mockResolvedValue(renamed);
  vi.mocked(treasuryAdminClient.getOutside).mockResolvedValueOnce(view)
    .mockResolvedValueOnce({ groups: [renamed, view.groups[1]] });
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-lens"] input').setValue("lens-draft");
  await wrapper.get('[data-test="group-bard"] input').setValue("speech");
  await wrapper.get('[data-test="group-bard"] form').trigger("submit");
  await flushPromises();
  expect(rename).toHaveBeenCalledWith("a".repeat(32), "speech");
  expect((wrapper.get('[data-test="group-speech"] input').element as HTMLInputElement).value).toBe("speech");
  expect((wrapper.get('[data-test="group-lens"] input').element as HTMLInputElement).value).toBe("lens-draft");
  expect(treasuryAdminClient.getOutside).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});

it("keeps the draft and shows Treasury's refusal on a bad rename", async () => {
  vi.spyOn(treasuryAdminClient, "renameOutside").mockRejectedValue(new Error("the name 'armory' is the name of a Citadel service"));
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-bard"] input').setValue("armory");
  await wrapper.get('[data-test="group-bard"] form').trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("Citadel service");
  expect((wrapper.get('[data-test="group-bard"] input').element as HTMLInputElement).value).toBe("armory");
  wrapper.unmount();
});

it("asks first, naming the users, then deletes a group", async () => {
  const remove = vi.spyOn(treasuryAdminClient, "deleteOutsideGroup").mockResolvedValue({ groups: [view.groups[1]] });
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-bard"] [data-test="delete-group"]').trigger("click");
  const modal = wrapper.getComponent(ConfirmModal);
  expect(modal.props("open")).toBe(true);
  expect(modal.props("message")).toContain("legion, stronghold");
  expect(remove).not.toHaveBeenCalled();
  await modal.get("button.confirm").trigger("click");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith("a".repeat(32));
  expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  wrapper.unmount();
});

it("deletes one origin after confirmation", async () => {
  const remove = vi.spyOn(treasuryAdminClient, "deleteOutsideOrigin").mockResolvedValue(view);
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-bard"] [data-test="delete-origin-' + "c".repeat(32) + '"]').trigger("click");
  const modal = wrapper.getComponent(ConfirmModal);
  expect(modal.props("message")).toContain("legion, stronghold");
  await modal.get("button.cancel").trigger("click");
  expect(remove).not.toHaveBeenCalled();
  await wrapper.get('[data-test="delete-origin-' + "c".repeat(32) + '"]').trigger("click");
  await modal.get("button.confirm").trigger("click");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith("c".repeat(32));
  wrapper.unmount();
});

it.each(["group", "origin"] as const)("shows a failed %s delete beside the attempted control", async (kind) => {
  const operation = kind === "group" ? "deleteOutsideGroup" : "deleteOutsideOrigin";
  vi.spyOn(treasuryAdminClient, operation).mockRejectedValue(new Error("Treasury is unreachable"));
  const wrapper = mount(OutsideView);
  await flushPromises();
  const row = wrapper.get('[data-test="group-bard"]');
  const selector = kind === "group" ? '[data-test="delete-group"]' : '[data-test="delete-origin-' + "c".repeat(32) + '"]';
  const button = row.get(selector);
  await button.trigger("click");
  const modal = wrapper.getComponent(ConfirmModal);
  await modal.get("button.confirm").trigger("click");
  await flushPromises();
  expect(modal.props("open")).toBe(false);
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
