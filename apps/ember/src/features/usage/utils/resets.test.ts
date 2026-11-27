import { expect, it } from "vitest";
import type { FreeReset, UsageOverview } from "../../../api/contracts/usage";
import { boostLines, cachedText, confirmText, resetGroups } from "./resets";

const reset = (id: string, kind: FreeReset["kind"], expires_at: string | null = null): FreeReset =>
  ({ id, kind, granted_at: "2026-11-01T00:00:00", expires_at });
const overview = (six: number, week: number): UsageOverview => ({
  six_hour: { used: six, limit: 100, reset_at: null }, weekly: { used: week, limit: 100, reset_at: null },
});

it("groups by kind and offers the first of each, which expires soonest", () => {
  const groups = resetGroups(
    [reset("r_soon", "six_hour", "2026-12-01T00:00:00"), reset("r_both", "both"), reset("r_later", "six_hour")],
    overview(10, 0),
  );

  expect(groups.map((g) => [g.kind, g.count, g.next.id])).toEqual([["six_hour", 2, "r_soon"], ["both", 1, "r_both"]]);
});

it("marks a reset that would clear nothing", () => {
  const groups = resetGroups([reset("a", "six_hour"), reset("b", "weekly"), reset("c", "both")], overview(0, 5));

  expect(groups.map((g) => g.clears)).toEqual([false, true, true]);
});

it("says what using one does", () => {
  expect(confirmText("six_hour")).toBe("Your 6-hour usage goes back to zero. The reset is used up.");
  expect(confirmText("both")).toBe("Your 6-hour and weekly usage go back to zero. The reset is used up.");
});

it("lists the active boosts", () => {
  const usage = overview(0, 0);
  usage.weekly.boost = { percent: 50, ends_at: "2099-06-15T00:00:00" }; // mid-year: the same year in every time zone

  const lines = boostLines(usage);

  expect(lines).toHaveLength(1);
  expect(lines[0]).toMatch(/^Weekly limit: \+50% until .+2099/);
});

it("mentions cached input only when it counts for less", () => {
  expect(cachedText(0.1)).toBe("Cached input counts at 10%.");
  expect(cachedText(1)).toBe("");
  expect(cachedText(undefined)).toBe("");
});
