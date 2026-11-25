import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("a search box shows one focus ring on its wrapper, not a second one on the input", async ({ page }) => {
  await installFakeApi(page, newState());
  await page.goto("/tickets");
  const input = page.getByRole("searchbox").first();
  await expect(input).toBeVisible();
  await input.focus();
  const wrapper = input.locator("xpath=..");
  expect(await wrapper.evaluate((el) => { const c = el.ownerDocument.defaultView!.getComputedStyle(el); return `${c.outlineStyle} ${c.outlineWidth} ${c.outlineOffset}`; })).toBe("solid 2px 2px");
  expect(await input.evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).outlineStyle)).toBe("none");
  if (process.env.PROBE_FOCUS) {
    const box = (await wrapper.boundingBox())!;
    await page.screenshot({ path: process.env.PROBE_FOCUS, clip: { x: Math.max(0, box.x - 10), y: Math.max(0, box.y - 10), width: box.width + 20, height: box.height + 20 } });
  }
});
