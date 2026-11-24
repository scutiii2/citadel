import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the drawer expands, scrolls its own body and returns focus to the opener", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  await page.goto("/agents");
  const opener = page.getByRole("button", { name: "Open EMBER", exact: true });
  await opener.click();
  const drawer = page.getByRole("dialog", { name: "EMBER", exact: true });
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 600 });
    expect(await page.evaluate<string>("getComputedStyle(document.querySelector('dialog.record-drawer .drawer-body')).overflowY")).toBe("auto");
    expect(await page.evaluate<boolean>("document.documentElement.scrollHeight <= window.innerHeight")).toBe(true);
    const normal = (await drawer.boundingBox())!.width;
    await drawer.getByRole("button", { name: "Expand drawer" }).click();
    const wide = (await drawer.boundingBox())!.width;
    expect(Math.abs(wide - (width < 768 ? width : Math.max(normal, width * 0.9)))).toBeLessThanOrEqual(2);
    await drawer.getByRole("button", { name: "Restore drawer size" }).click();
    expect((await drawer.boundingBox())!.width).toBe(normal);
  }
  await drawer.getByRole("button", { name: "Close", exact: true }).click();
  await expect(drawer).toBeHidden();
  await expect(opener).toBeFocused();
  expect(state.unexpected).toEqual([]);
});
