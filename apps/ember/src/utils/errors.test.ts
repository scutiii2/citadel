import { describe, expect, it } from "vitest";
import { errorMessage } from "./errors";

describe("shared error formatting", () => {
  it.each([
    [new Error("Broken."), "Broken."],
    [new Error("boom"), "boom"],
    ["plain", "plain"],
    [null, "null"],
    [{ toString: (): string => "Service unavailable" }, "Service unavailable"],
  ])("preserves the message of %s", (error, expected) => {
    expect(errorMessage(error)).toBe(expected);
  });
});
