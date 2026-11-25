import { describe, expect, it } from "vitest";
import { timeLeft } from "./timeLeft";

describe("timeLeft", () => {
  it("counts down in seconds, then minutes, then says expired", () => {
    expect(timeLeft(61_000 * 30, 0)).toBe("31 min left");
    expect(timeLeft(60_000, 0)).toBe("1 min left");
    expect(timeLeft(45_000, 0)).toBe("45 s left");
    expect(timeLeft(1_000, 1_000)).toBe("expired");
    expect(timeLeft(0, 5_000)).toBe("expired");
  });
});
