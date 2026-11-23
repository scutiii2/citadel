import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("every page fits desktop, tablet and mobile in both themes", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  for (const scheme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    for (const [path, title] of [["/overview", "Overview"], ["/usage", "Usage"], ["/analytics", "Analytics"], ["/tickets", "Tickets"], ["/usage-settings", "Usage settings"], ["/brain-settings", "Brain settings"], ["/tool-services", "Tool services"]] as const) {
      for (const width of [1280, 768, 375]) {
        await page.setViewportSize({ width, height: 800 });
        await page.goto(path);
        await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
        await expect(page.getByRole("button", { name: /^About / }).first()).toBeVisible();
        expect(await page.evaluate<boolean>("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
      }
    }
  }
  expect(state.unexpected).toEqual([]);
});
