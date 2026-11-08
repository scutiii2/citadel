import { afterEach, describe, expect, it, vi } from "vitest";
import { newId } from "./uuid";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("newId", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns a v4 uuid without crypto.randomUUID (insecure context)", () => {
    vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) });
    const a = newId();
    expect(a).toMatch(UUID_V4);
    expect(newId()).not.toBe(a);
  });

  it("uses crypto.randomUUID when present", () => {
    expect(newId()).toMatch(UUID_V4);
  });
});
