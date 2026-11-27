import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it, vi } from "vitest";
import { usageClient, type MyUsage } from "../api/UsageClient";
import type { UsageOverview } from "../../../api/contracts/usage";
import { useAuthStore } from "../../../stores/auth";
import { useUsageLimitsStore } from "./usageLimits";

vi.mock("../api/UsageClient", () => ({ usageClient: { mine: vi.fn(), spendReset: vi.fn(), setAutoReset: vi.fn() } }));

const overview = (used: number): UsageOverview => ({
  six_hour: { used, limit: 100, reset_at: null }, weekly: { used, limit: 0, reset_at: null }, resets: [], auto_use: false,
});
const report = (used: number): MyUsage => ({ ...overview(used), report: {} as MyUsage["report"] });
const account = (id: number) => ({ id, username: "alice", email: "a@example.com", email_verified: true, roles: [], permissions: [] });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = account(1);
  vi.resetAllMocks();
});

it("shows what a change answers with, and drops a read that started before it", async () => {
  const slow = deferred<MyUsage>();
  vi.mocked(usageClient.mine).mockReturnValue(slow.promise);
  vi.mocked(usageClient.spendReset).mockResolvedValue(overview(0));
  const store = useUsageLimitsStore();
  const reading = store.load();

  await store.spend("r_1");
  slow.resolve(report(90));
  await reading;

  expect(usageClient.spendReset).toHaveBeenCalledWith("r_1");
  expect(store.usage?.six_hour.used).toBe(0);
});

it("ignores the answer to a change made for an account that has signed out", async () => {
  const slow = deferred<UsageOverview>();
  vi.mocked(usageClient.setAutoReset).mockReturnValue(slow.promise);
  const store = useUsageLimitsStore();
  const saving = store.setAutoUse(true);

  useAuthStore().account = account(2);
  slow.resolve({ ...overview(5), auto_use: true });
  await saving;

  expect(store.usage).toBeNull();
});

it("passes a refusal to the caller and keeps what is shown", async () => {
  vi.mocked(usageClient.mine).mockResolvedValue(report(40));
  vi.mocked(usageClient.spendReset).mockRejectedValue(new Error("There is nothing to reset yet."));
  const store = useUsageLimitsStore();
  await store.load();

  await expect(store.spend("r_1")).rejects.toThrow("nothing to reset");
  expect(store.usage?.six_hour.used).toBe(40);
});
