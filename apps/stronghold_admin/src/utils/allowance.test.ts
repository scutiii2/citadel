import { afterEach, describe, expect, it, vi } from "vitest";
import { usageAllowanceClient } from "../api/UsageAllowanceClient";
import { blankForm, confirmText, formProblem, needsConfirm, resultMessage, sendAllowance, type AllowanceForm } from "./allowance";

const NOW = Date.parse("2026-03-15T10:00:00Z");
const LATER = "2099-01-01T00:00";
const EARLIER = "2000-01-01T00:00";
const chosen = (extra: Partial<AllowanceForm> = {}): AllowanceForm => ({ ...blankForm(), ids: [2], ...extra });
afterEach(() => vi.restoreAllMocks());

describe("formProblem", () => {
  it("asks for a recipient", () => {
    expect(formProblem("clear", blankForm(), NOW)).toContain("at least one user");
    expect(formProblem("clear", { ...blankForm(), all: true }, NOW)).toBe("");
  });
  it("keeps the reset count from 1 to 20", () => {
    for (const count of [0, 21, 1.5, ""]) expect(formProblem("resets", chosen({ count }), NOW)).toContain("1 to 20");
    expect(formProblem("resets", chosen({ count: 20 }), NOW)).toBe("");
  });
  it("needs a boost percent and a future end", () => {
    for (const percent of [0, 1001]) expect(formProblem("boost", chosen({ percent, until: LATER }), NOW)).toContain("1 to 1000");
    expect(formProblem("boost", chosen(), NOW)).toContain("ends");
    expect(formProblem("boost", chosen({ until: EARLIER }), NOW)).toContain("in the future");
    expect(formProblem("boost", chosen({ until: LATER }), NOW)).toBe("");
  });
  it("allows no expiry but not a past one", () => {
    expect(formProblem("resets", chosen(), NOW)).toBe("");
    expect(formProblem("resets", chosen({ until: EARLIER }), NOW)).toContain("expiry must be in the future");
  });
});

describe("confirmation", () => {
  it("is asked for a usage reset and for all users", () => {
    expect(needsConfirm("clear", chosen())).toBe(true);
    expect(needsConfirm("resets", chosen())).toBe(false);
    expect(needsConfirm("resets", chosen({ all: true }))).toBe(true);
  });
  it("names the number of accounts", () => {
    expect(confirmText("resets", chosen({ all: true, count: 2, windows: "both" }), 5))
      .toBe("Send 2 free 6-hour and weekly resets to all 5 enabled accounts?");
    expect(confirmText("clear", chosen({ windows: "weekly" }), 5))
      .toBe("Reset weekly usage of 1 account? This cannot be undone.");
    expect(confirmText("boost", chosen(), 5)).toBe("Boost 6-hour limits by 50% for 1 account?");
  });
});

it("says how many accounts were done and names the others", () => {
  expect(resultMessage("clear", { done: 2, failed: [] })).toEqual({ kind: "ok", text: "Usage reset for 2 accounts." });
  expect(resultMessage("resets", { done: 1, failed: ["bob"] }))
    .toEqual({ kind: "warning", text: "Resets sent to 1 account. Not done for: bob." });
  expect(resultMessage("boost", { done: 0, failed: ["bob"] }).kind).toBe("error");
});

it("builds each request body", async () => {
  const result = { done: 1, failed: [] };
  const grant = vi.spyOn(usageAllowanceClient, "grant").mockResolvedValue(result);
  const clear = vi.spyOn(usageAllowanceClient, "clear").mockResolvedValue(result);
  const boost = vi.spyOn(usageAllowanceClient, "boost").mockResolvedValue(result);
  const iso = new Date(LATER).toISOString();

  await sendAllowance("resets", chosen({ all: true, windows: "weekly", count: "3", until: LATER }));
  await sendAllowance("resets", chosen());
  await sendAllowance("clear", chosen({ windows: "both" }));
  await sendAllowance("boost", chosen({ percent: "20", until: LATER }));

  expect(grant.mock.calls).toEqual([
    [{ all: true, kind: "weekly", count: 3, expires_at: iso }],
    [{ account_ids: [2], kind: "six_hour", count: 1 }],
  ]);
  expect(clear).toHaveBeenCalledWith({ account_ids: [2], windows: ["six_hour", "weekly"] });
  expect(boost).toHaveBeenCalledWith({ account_ids: [2], windows: ["six_hour"], percent: 20, ends_at: iso });
});
