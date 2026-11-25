import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the generator's split-track slider follows the keyboard and the pointer", async ({ page }) => {
  await installFakeApi(page, newState());
  await page.goto("/generator");
  const slider = page.getByRole("slider").first();
  await expect(slider).toBeVisible();
  const root = slider.locator("xpath=..");
  const handle = root.locator(".handle");
  const before = (await handle.boundingBox())!;
  await slider.focus();
  await page.keyboard.press("End");
  const after = (await handle.boundingBox())!;
  expect(after.x).toBeGreaterThan(before.x + 50);
  // The visible handle sits on the native thumb's track end, inside the control.
  const box = (await root.boundingBox())!;
  expect(after.x + after.width).toBeLessThanOrEqual(box.x + box.width + 1);
  expect(await root.evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).getPropertyValue("--v").trim())).toBe("1");
  // A click in the middle moves the value near half.
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  const v = Number(await root.evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).getPropertyValue("--v")));
  expect(v).toBeGreaterThan(0.4);
  expect(v).toBeLessThan(0.6);
  await slider.focus();
  await page.keyboard.press("Tab"); await page.keyboard.press("Shift+Tab");
  await expect(root).toHaveCSS("outline-style", "solid");
  await root.screenshot({ path: process.env.PROBE_SLIDER ?? "test-results/slider.png" });
});
