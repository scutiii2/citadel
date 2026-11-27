import { ConfirmModal } from "@citadel/ui";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { usageAllowanceClient, type AccountAllowance } from "../../api/UsageAllowanceClient";
import AccountAllowances from "./AccountAllowances.vue";

const ALICE: AccountAllowance = {
  account_id: 2, username: "alice", auto_use: false,
  resets: [{ id: "r_1", kind: "both", granted_at: "2026-03-01T00:00:00", expires_at: null }],
  boosts: [{ id: "b_1", windows: ["weekly"], percent: 50, granted_at: "2026-03-01T00:00:00", ends_at: "2099-01-01T00:00:00" }],
};
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});
const list = () => vi.mocked(usageAllowanceClient.list);
beforeEach(() => {
  vi.spyOn(usageAllowanceClient, "list").mockResolvedValue([ALICE]);
  vi.spyOn(usageAllowanceClient, "removeReset").mockResolvedValue(undefined);
  vi.spyOn(usageAllowanceClient, "removeBoost").mockResolvedValue(undefined);
});
let wrapper: Awaited<ReturnType<typeof show>>;
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); });

async function show(accountId = 2) {
  const mounted = mount(AccountAllowances, { props: { accountId, username: "alice" }, attachTo: document.body });
  await flushPromises();
  return mounted;
}
const asking = () => wrapper.findAllComponents(ConfirmModal).find((modal) => modal.props("open"));

it("lists the unused resets and active boosts", async () => {
  wrapper = await show();
  expect(wrapper.text()).toContain("6-hour and weekly reset");
  expect(wrapper.text()).toContain("no expiry");
  expect(wrapper.text()).toContain("+50% weekly");
});

it("removes a reset after asking, then reads the list again", async () => {
  wrapper = await show();
  await wrapper.get('[data-test="remove-reset"]').trigger("click");
  expect(usageAllowanceClient.removeReset).not.toHaveBeenCalled();
  list().mockResolvedValue([{ ...ALICE, resets: [] }]);
  asking()!.vm.$emit("confirm");
  await flushPromises();
  expect(usageAllowanceClient.removeReset).toHaveBeenCalledWith(2, "r_1");
  expect(wrapper.text()).toContain("No unused resets.");
  expect(wrapper.emitted("changed")).toHaveLength(1);
});

it("ends a boost after asking", async () => {
  wrapper = await show();
  await wrapper.get('[data-test="end-boost"]').trigger("click");
  asking()!.vm.$emit("confirm");
  await flushPromises();
  expect(usageAllowanceClient.removeBoost).toHaveBeenCalledWith(2, "b_1");
});

it("shows an account with nothing", async () => {
  wrapper = await show(3);
  expect(wrapper.text()).toContain("No unused resets.");
  expect(wrapper.text()).toContain("No active boosts.");
});

it("offers a retry when the list cannot be read", async () => {
  list().mockRejectedValueOnce(new Error("Down"));
  wrapper = await show();
  expect(wrapper.text()).toContain("Down");
  await wrapper.get('[data-test="allowance-retry"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("6-hour and weekly reset");
});

it("says why a removal failed and reads the list again", async () => {
  vi.mocked(usageAllowanceClient.removeReset).mockRejectedValueOnce(new Error("That reset is not available."));
  wrapper = await show();
  await wrapper.get('[data-test="remove-reset"]').trigger("click");
  asking()!.vm.$emit("confirm");
  await flushPromises();
  expect(wrapper.text()).toContain("not available");
  expect(list()).toHaveBeenCalledTimes(2);
  expect(wrapper.emitted("changed")).toBeUndefined();
});
