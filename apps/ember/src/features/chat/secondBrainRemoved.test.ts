import { describe, expect, it } from "vitest";
import { router } from "../../router";
import { NAV_PAGES } from "../../router/pages";

describe("retired Brains page", () => {
  it("has no route or navigation entry", () => {
    expect(router.getRoutes().some((route) => route.path === "/brains")).toBe(false);
    expect(NAV_PAGES.some((page) => page.to === "/brains")).toBe(false);
  });
});
