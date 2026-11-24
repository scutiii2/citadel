import { afterEach, expect, it, vi } from "vitest";
import { readStored, writeStored } from "./storage";

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

it("round-trips a value", () => {
  writeStored("k", "v");
  expect(readStored("k")).toBe("v");
  expect(readStored("missing")).toBeNull();
});

it("falls back when storage throws", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
  expect(readStored("k")).toBeNull();
  expect(() => writeStored("k", "v")).not.toThrow();
});
