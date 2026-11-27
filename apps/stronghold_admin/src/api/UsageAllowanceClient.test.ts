import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { usageAllowanceClient } from "./UsageAllowanceClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it("calls the allowance routes with the recipients and fields", async () => {
  await usageAllowanceClient.list();
  await usageAllowanceClient.grant({ all: true, kind: "both", count: 2 });
  await usageAllowanceClient.clear({ account_ids: [2], windows: ["weekly"] });
  await usageAllowanceClient.boost({ account_ids: [2], windows: ["six_hour"], percent: 50, ends_at: "2099-01-01T00:00:00.000Z" });
  await usageAllowanceClient.removeReset(2, "r_1");
  await usageAllowanceClient.removeBoost(2, "b_1");

  expect(vi.mocked(apiRequest).mock.calls).toEqual([
    ["GET", "/api/admin/usage-allowances"],
    ["POST", "/api/admin/usage-allowances/resets", { all: true, kind: "both", count: 2 }],
    ["POST", "/api/admin/usage-allowances/clear", { account_ids: [2], windows: ["weekly"] }],
    ["POST", "/api/admin/usage-allowances/boosts", { account_ids: [2], windows: ["six_hour"], percent: 50, ends_at: "2099-01-01T00:00:00.000Z" }],
    ["DELETE", "/api/admin/usage-allowances/2/resets/r_1"],
    ["DELETE", "/api/admin/usage-allowances/2/boosts/b_1"],
  ]);
});
