import { describe, expect, it } from "vitest";
import { axisLabel, bucketTitle, formatCount, niceCeil } from "./logAnalytics";

describe("formatCount", () => {
  it("writes small numbers whole and big ones compact", () => {
    expect(formatCount(0)).toBe("0");
    expect(formatCount(1284)).toBe("1,284");
    expect(formatCount(12_900)).toBe("12.9K");
    expect(formatCount(20_000)).toBe("20K");
    expect(formatCount(1_240_000)).toBe("1.2M");
  });
});

describe("niceCeil", () => {
  it("rounds up to a clean number with a whole half", () => {
    expect([0, 1, 2, 3, 5, 7, 10, 12, 45, 61, 99, 101, 450].map(niceCeil)).toEqual([
      2, 2, 2, 4, 6, 8, 10, 20, 60, 80, 100, 200, 600,
    ]);
    for (const n of [3, 13, 77, 123, 9999]) expect(niceCeil(n) % 2).toBe(0);
  });
});

describe("bucket labels", () => {
  it("shows the hour for hourly buckets and the date for daily ones, in UTC", () => {
    expect(axisLabel("2026-10-05T13:00:00", "hour")).toBe("13:00");
    expect(axisLabel("2026-10-05T00:00:00", "day")).toBe("Oct 5");
    expect(bucketTitle("2026-10-05T13:00:00", "hour")).toBe("Mon, Oct 5, 13:00 UTC");
    expect(bucketTitle("2026-10-05T00:00:00", "day")).toBe("Mon, Oct 5");
  });
});
