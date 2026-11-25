import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the capability drawer expands, scrolls its own body and returns focus to its row", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  await page.goto("/capabilities");
  const opener = page.getByRole("button", { name: "Open Fresh", exact: true });
  await opener.click();
  const drawer = page.getByRole("dialog", { name: "Fresh", exact: true });
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 600 });
    expect(await page.evaluate<string>("getComputedStyle(document.querySelector('dialog.record-drawer .drawer-body')).overflowY")).toBe("auto");
    expect(await page.evaluate<boolean>("document.documentElement.scrollHeight <= window.innerHeight")).toBe(true);
    const normal = (await drawer.boundingBox())!.width;
    await drawer.getByRole("button", { name: "Expand drawer" }).click();
    const wide = (await drawer.boundingBox())!.width;
    expect(Math.abs(wide - (width < 768 ? width : Math.max(normal, width * 0.9)))).toBeLessThanOrEqual(2);
    await drawer.getByRole("button", { name: "Expand drawer" }).click();
    expect((await drawer.boundingBox())!.width).toBe(normal);
  }
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(opener).toBeFocused();
  expect(state.unexpected).toEqual([]);
});
