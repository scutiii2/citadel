import { describe, expect, it } from "vitest";
import { ANALYTICS_PERMISSIONS, pageTitle, STRONGHOLD_PAGES } from "./pages";

describe("Stronghold Admin navigation", () => {
  it("starts at Overview and titles each page", () => {
    expect(STRONGHOLD_PAGES[0]?.to).toBe("/overview");
    expect(pageTitle("/tool-services")).toBe("Tool services");
  });
  it("lists Analytics for an account holding only traffic.view", () => {
    const analytics = STRONGHOLD_PAGES.find((page) => page.to === "/analytics")!;
    expect(analytics.permission).toBe(ANALYTICS_PERMISSIONS);
    expect([analytics.permission].flat().some((name) => name === "traffic.view")).toBe(true);
  });
});
