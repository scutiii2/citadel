import { ConfirmModal } from "@citadel/ui";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { usageAllowanceClient } from "../../api/UsageAllowanceClient";
import type { AllowanceAction } from "../../utils/allowance";
import AllowanceDrawer from "./AllowanceDrawer.vue";

const accounts = [
  { account_id: 2, username: "alice", is_active: true, tokens: 0, turns: 0, last_used_at: null },
  { account_id: 3, username: "bob", is_active: false, tokens: 0, turns: 0, last_used_at: null },
];
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});
const grant = () => vi.mocked(usageAllowanceClient.grant);
const clear = () => vi.mocked(usageAllowanceClient.clear);
beforeEach(() => {
  vi.spyOn(usageAllowanceClient, "grant").mockResolvedValue({ done: 1, failed: [] });
  vi.spyOn(usageAllowanceClient, "clear").mockResolvedValue({ done: 1, failed: [] });
});
let wrapper: ReturnType<typeof show>;
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); });

const show = (action: AllowanceAction) => mount(AllowanceDrawer, { props: { action, accounts }, attachTo: document.body });
const asking = () => wrapper.findAllComponents(ConfirmModal).find((modal) => modal.props("open"));
const send = () => wrapper.get('[data-test="send"]');
const choose = (id: number) => wrapper.get(`[data-test="recipient-${id}"]`).setValue(true);
const everyone = () => wrapper.findAll("button").find((button) => button.text() === "All users")!.trigger("click");
const cancel = () => wrapper.get(".drawer-footer .chip").trigger("click");

it("sends to the chosen accounts without asking", async () => {
  wrapper = show("resets");
  expect(send().attributes("disabled")).toBeDefined();
  await choose(2);
  await send().trigger("click");
  await flushPromises();
  expect(grant()).toHaveBeenCalledWith({ account_ids: [2], kind: "six_hour", count: 1 });
  expect(wrapper.emitted("done")).toEqual([[{ kind: "ok", text: "Resets sent to 1 account." }]]);
});

it("asks before all users and names the enabled accounts", async () => {
  wrapper = show("resets");
  await everyone();
  await send().trigger("click");
  expect(asking()!.props("message")).toContain("all 1 enabled account?");
  expect(grant()).not.toHaveBeenCalled();
  asking()!.vm.$emit("confirm");
  await flushPromises();
  expect(grant()).toHaveBeenCalledWith({ all: true, kind: "six_hour", count: 1 });
});

it("always asks before resetting usage, and dismissing sends nothing", async () => {
  wrapper = show("clear");
  await choose(2);
  await send().trigger("click");
  asking()!.vm.$emit("close");
  await flushPromises();
  expect(asking()).toBeUndefined();
  expect(clear()).not.toHaveBeenCalled();
});

it("keeps the form and shows the refusal", async () => {
  grant().mockRejectedValueOnce(new Error("An account does not exist."));
  wrapper = show("resets");
  await choose(2);
  await send().trigger("click");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("does not exist");
  expect(wrapper.emitted("done")).toBeUndefined();
  expect((wrapper.get('[data-test="recipient-2"]').element as HTMLInputElement).checked).toBe(true);
});

it("closes an untouched form at once and asks before discarding a changed one", async () => {
  wrapper = show("boost");
  await cancel();
  expect(wrapper.emitted("close")).toHaveLength(1);
  await choose(2);
  await cancel();
  expect(wrapper.emitted("close")).toHaveLength(1);
  expect(asking()!.props("title")).toBe("Discard changes?");
  asking()!.vm.$emit("confirm");
  expect(wrapper.emitted("close")).toHaveLength(2);
});

it("starts blank each time it opens", async () => {
  wrapper = show("resets");
  await choose(2);
  await wrapper.setProps({ action: null });
  await wrapper.setProps({ action: "resets" });
  expect((wrapper.get('[data-test="recipient-2"]').element as HTMLInputElement).checked).toBe(false);
});
