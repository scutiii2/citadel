import { describe, expect, it } from "vitest";
import { router } from "./index";
import { ARMORY_PAGES, pageTitle } from "./pages";

describe("Armory Admin navigation", () => {
  it("starts at Overview, has no Connections or Brain page, and titles each page", () => {
    expect(ARMORY_PAGES[0]?.to).toBe("/overview");
    expect(ARMORY_PAGES.map((page) => page.to)).not.toContain("/connections");
    expect(ARMORY_PAGES.map((page) => page.to)).not.toContain("/brain");
    expect(router.hasRoute("connections")).toBe(false);
    expect(router.hasRoute("brain")).toBe(false);
    expect(router.resolve("/extensions").matched.some((record) => record.name === "connections")).toBe(false);
    expect(pageTitle("/limits")).toBe("Limits");
    expect(new Set(ARMORY_PAGES.map((page) => page.icon.join())).size).toBe(ARMORY_PAGES.length);
  });
});
