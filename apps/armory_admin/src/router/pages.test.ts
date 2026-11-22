import { describe, expect, it } from "vitest";
import { router } from "./index";
import { ARMORY_PAGES } from "./pages";

describe("Armory Admin navigation", () => {
  it("has no Connections page any more and omits the retired Brain page", () => {
    expect(ARMORY_PAGES.map((page) => page.to)).not.toContain("/connections");
    expect(ARMORY_PAGES.map((page) => page.to)).not.toContain("/brain");
    expect(router.hasRoute("connections")).toBe(false);
    expect(router.hasRoute("brain")).toBe(false);
    expect(router.resolve("/extensions").matched.some((record) => record.name === "connections")).toBe(false);
  });
});
