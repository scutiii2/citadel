import { describe, expect, it } from "vitest";
import { formatBytes, plural } from "./format";

describe("formatBytes", () => {
  it.each([
    [512, "512 B"],
    [2048, "2 KB"],
    [1025, "2 KB"],
    [5 * 1024 * 1024, "5.0 MB"],
    [3.25 * 1024 * 1024, "3.3 MB"],
    [3 * 1024 ** 3, "3.00 GB"],
  ])("%d bytes is %j", (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });
});

describe("plural", () => {
  it("adds an s except for one", () => {
    expect(plural(1, "file")).toBe("1 file");
    expect(plural(2, "file")).toBe("2 files");
  });
});
