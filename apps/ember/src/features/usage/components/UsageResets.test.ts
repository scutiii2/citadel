import { ConfirmModal } from "@citadel/ui";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { usageClient, type MyUsage } from "../api/UsageClient";
import type { UsageOverview } from "../../../api/contracts/usage";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { useUsageLimitsStore } from "../stores/usageLimits";
import UsageResets from "./UsageResets.vue";

vi.mock("../api/UsageClient", () => ({ usageClient: { mine: vi.fn(), spendReset: vi.fn(), setAutoReset: vi.fn() } }));

const overview = (extra: Partial<UsageOverview> = {}): UsageOverview => ({
  six_hour: { used: 50, limit: 100, reset_at: null },
  weekly: { used: 0, limit: 150, reset_at: null, boost: { percent: 50, ends_at: "2099-01-01T00:00:00" } },
  resets: [
    { id: "r_1", kind: "six_hour", granted_at: "2026-11-01T00:00:00", expires_at: "2099-02-01T00:00:00" },
    { id: "r_2", kind: "six_hour", granted_at: "2026-11-02T00:00:00", expires_at: null },
    { id: "r_3", kind: "weekly", granted_at: "2026-11-02T00:00:00", expires_at: null },
  ],
  auto_use: false,
  cached_token_weight: 0.1,
  ...extra,
});

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});
let wrapper: Awaited<ReturnType<typeof show>>;
beforeEach(() => {
  vi.resetAllMocks();
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "alice", email: "a@example.com", email_verified: true, roles: [], permissions: [] };
});
afterEach(() => wrapper?.unmount());

async function show(usage: UsageOverview = overview()) {
  vi.mocked(usageClient.mine).mockResolvedValue({ ...usage, report: {} as MyUsage["report"] });
  await useUsageLimitsStore().load();
  const mounted = mount(UsageResets, { attachTo: document.body });
  await flushPromises();
  return mounted;
}
const asking = () => wrapper.findAllComponents(ConfirmModal).find((modal) => modal.props("open"));
const button = (kind: string) => wrapper.get<HTMLButtonElement>(`[data-test="use-${kind}"]`);
const auto = () => wrapper.get<HTMLInputElement>('[data-test="auto-reset"]');

it("lists resets by kind, the boost and the cached share", async () => {
  wrapper = await show();

  expect(wrapper.text()).toContain("6-hour reset ×2");
  expect(wrapper.text()).toContain("Next expires");
  expect(wrapper.text()).toContain("Weekly limit: +50% until");
  expect(wrapper.text()).toContain("Cached input counts at 10%.");
});

it("turns Use off when nothing would be cleared", async () => {
  wrapper = await show();

  expect(button("six_hour").element.disabled).toBe(false);
  expect(button("weekly").element.disabled).toBe(true);
  expect(wrapper.text()).toContain("Nothing to clear yet.");
});

it("asks, then spends the soonest reset and reports the change", async () => {
  vi.mocked(usageClient.spendReset).mockResolvedValue(overview({ resets: [] }));
  wrapper = await show();

  await button("six_hour").trigger("click");
  expect(usageClient.spendReset).not.toHaveBeenCalled();
  asking()!.vm.$emit("confirm");
  await flushPromises();

  expect(usageClient.spendReset).toHaveBeenCalledWith("r_1");
  expect(wrapper.text()).toContain("You have no free resets.");
  expect(wrapper.emitted("changed")).toHaveLength(1);
});

it("says why a reset was refused and reads the numbers again", async () => {
  vi.mocked(usageClient.spendReset).mockRejectedValue(new ApiError(404, "That reset is not available."));
  wrapper = await show();

  await button("six_hour").trigger("click");
  asking()!.vm.$emit("confirm");
  await flushPromises();

  expect(wrapper.get('[role="alert"]').text()).toContain("not available");
  expect(usageClient.mine).toHaveBeenCalledTimes(2);
  expect(wrapper.emitted("changed")).toBeUndefined();
});

it("keeps the switch on its saved value until the server answers", async () => {
  let answer!: (value: UsageOverview) => void;
  vi.mocked(usageClient.setAutoReset).mockReturnValue(new Promise((resolve) => (answer = resolve)));
  wrapper = await show();

  await auto().setValue(true);
  expect(usageClient.setAutoReset).toHaveBeenCalledWith(true);
  expect(auto().element.checked).toBe(false);
  expect(auto().element.disabled).toBe(true);

  answer(overview({ auto_use: true }));
  await flushPromises();
  expect(auto().element.checked).toBe(true);
  expect(auto().element.disabled).toBe(false);
});

it("leaves the switch off when saving fails", async () => {
  vi.mocked(usageClient.setAutoReset).mockRejectedValue(new Error("Stronghold is unavailable"));
  wrapper = await show();

  await auto().setValue(true);
  await flushPromises();

  expect(auto().element.checked).toBe(false);
  expect(wrapper.get('[role="alert"]').text()).toContain("unavailable");
});

it("shows nothing for a server without resets", async () => {
  wrapper = await show({ six_hour: { used: 1, limit: 10, reset_at: null }, weekly: { used: 1, limit: 10, reset_at: null } });

  expect(wrapper.find("section").exists()).toBe(false);
});
