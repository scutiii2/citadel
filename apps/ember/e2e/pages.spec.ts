import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("every page fits desktop, tablet and mobile in both themes and has its help", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  for (const scheme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    for (const [path, title] of [["/overview", "Overview"], ["/capabilities", "Capabilities"], ["/agents", "Agents"], ["/usage", "Usage"], ["/tickets", "Tickets"], ["/settings", "Settings"], ["/account", "Account"]] as const) {
      for (const width of [1280, 768, 375]) {
        await page.setViewportSize({ width, height: 800 });
        await page.goto(path);
        await expect(page.getByRole("heading", { name: title, level: 2 }).first()).toBeVisible();
        // The page's help: the header's Help button on wide screens (or a panel's own icon), the page's icon on narrow ones.
        await expect(page.getByRole("button", { name: /^(Help$|About )/ }).first()).toBeVisible();
        expect(await page.evaluate<boolean>("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
      }
    }
  }
  expect(state.unexpected).toEqual([]);
});
