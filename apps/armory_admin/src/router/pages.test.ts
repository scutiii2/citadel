import { describe, expect, it } from "vitest";
import { router } from "./index";
import { ARMORY_PAGES } from "./pages";

describe("Armory Admin navigation", () => {
  it("keeps Connections and omits the retired Brain page", () => {
    expect(ARMORY_PAGES.map((page) => page.to)).toContain("/connections");
    expect(ARMORY_PAGES.map((page) => page.to)).not.toContain("/brain");
    expect(router.hasRoute("brain")).toBe(false);
  });
});
