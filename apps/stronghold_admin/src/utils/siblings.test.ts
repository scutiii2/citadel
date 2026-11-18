import { describe, expect, it } from "vitest";
import { ADMIN_APPS, adminAppUrl } from "./siblings";

describe("adminAppUrl", () => {
  it("keeps the host and swaps the port", () => {
    expect(adminAppUrl(26504, "http://127.0.0.1:26503/capabilities?x=1#y")).toBe("http://127.0.0.1:26504/");
  });
  it("lists each admin app once", () => {
    expect(new Set(ADMIN_APPS.map((a) => a.port)).size).toBe(ADMIN_APPS.length);
  });
});
