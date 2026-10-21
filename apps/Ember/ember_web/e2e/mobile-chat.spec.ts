import { expect, test } from "@playwright/test";
import { ACCOUNT, ANSWER, installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("composer stays above a keyboard that only resizes the visual viewport", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript(() => {
    // Safari can keep the layout viewport full-height while the keyboard
    // shrinks and pans the visual viewport. Resizing the window misses this.
    const viewport = new EventTarget();
    Object.assign(viewport, { height: 812, offsetTop: 0, scale: 1 });
    Object.defineProperty(window, "visualViewport", { value: viewport });
  });
  await installFakeApi(page);
  await logIn(page);
  const input = page.getByPlaceholder(/Ask something/);
  await input.fill("Keep my draft visible");

  for (const [height, offsetTop, event] of [[480, 0, "resize"], [420, 60, "scroll"], [812, 0, "resize"]] as const) {
    await page.evaluate(({ height, offsetTop, event }) => {
      Object.assign(window.visualViewport!, { height, offsetTop });
      window.visualViewport!.dispatchEvent(new Event(event));
    }, { height, offsetTop, event });
    await expect.poll(async () => {
      const box = await input.boundingBox();
      return box!.y + box!.height;
    }).toBeLessThanOrEqual(offsetTop + height);
    await expect.poll(async () => {
      const box = await page.locator("#app").boundingBox();
      return Math.abs(box!.height - height);
    }).toBeLessThanOrEqual(1);
    await expect.poll(async () => {
      const box = await page.locator("#app").boundingBox();
      return Math.abs(box!.y - offsetTop);
    }).toBeLessThanOrEqual(1);
    const send = await page.getByRole("button", { name: "Send", exact: true }).boundingBox();
    expect(send!.y + send!.height).toBeLessThanOrEqual(offsetTop + height);
    await expect(input).toHaveValue("Keep my draft visible");
    await expect(input).toBeFocused();
  }

  // Zooming should magnify the full layout rather than squeeze it into the
  // smaller visual viewport, so the user can still pan around the page.
  await page.evaluate(() => {
    Object.assign(window.visualViewport!, { height: 406, offsetTop: 80, scale: 2 });
    window.visualViewport!.dispatchEvent(new Event("resize"));
  });
  await expect.poll(async () => (await page.locator("#app").boundingBox())!.height).toBe(812);
});

test("mobile layout still resizes without the Visual Viewport API", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript(() => {
    Object.defineProperty(window, "visualViewport", { value: undefined });
  });
  await installFakeApi(page);
  await logIn(page);
  await page.setViewportSize({ width: 375, height: 480 });
  await page.getByPlaceholder(/Ask something/).fill("Keep typing");
  const input = await page.getByPlaceholder(/Ask something/).boundingBox();
  expect(input!.y + input!.height).toBeLessThanOrEqual(480);
});

for (const theme of ["light", "dark"] as const) {
  test(`mobile chat and history remain usable in ${theme} mode`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.emulateMedia({ colorScheme: theme });
    await installFakeApi(page);
    await logIn(page);
    const tabs = page.getByRole("navigation", { name: "Main pages" });
    await expect(tabs.getByRole("link")).toHaveText(["Overview", "Capabilities", "Chat", "Usage", "Profile"]);
    const input = page.getByPlaceholder(/Ask something/);
    await input.fill("Plan my week");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText(ANSWER)).toBeVisible();
    const moreTools = page.getByRole("button", { name: "More message tools" });
    await moreTools.click();
    await page.getByRole("button", { name: "Saved prompts", exact: true }).click();
    const prompts = page.getByRole("dialog", { name: "Saved prompts" });
    await expect(prompts).toBeVisible();
    const promptBox = await prompts.boundingBox();
    expect(promptBox!.x).toBeGreaterThanOrEqual(0);
    expect(promptBox!.x + promptBox!.width).toBeLessThanOrEqual(375);
    await input.click();
    await expect(moreTools).toHaveAttribute("aria-expanded", "false");
    await page.getByRole("button", { name: "Chat settings", exact: true }).click();
    const settings = page.getByRole("group", { name: "Chat settings" });
    await expect(settings).toBeVisible();
    const settingsBox = await settings.boundingBox();
    expect(settingsBox!.x).toBeGreaterThanOrEqual(0);
    expect(settingsBox!.x + settingsBox!.width).toBeLessThanOrEqual(375);
    await settings.press("Escape");
    await page.locator(".mode-chip").click();
    const approval = page.getByRole("menu", { name: "Tool approval" });
    const approvalBox = await approval.boundingBox();
    expect(approvalBox!.x).toBeGreaterThanOrEqual(0);
    expect(approvalBox!.x + approvalBox!.width).toBeLessThanOrEqual(375);
    await approval.press("Escape");
    const composer = await page.locator(".composer").boundingBox();
    const nav = await tabs.boundingBox();
    expect(composer!.y + composer!.height).toBeLessThanOrEqual(nav!.y);
    for (const link of await tabs.getByRole("link").all()) {
      const box = await link.boundingBox();
      expect(box!.y).toBeGreaterThanOrEqual(nav!.y);
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    const history = page.getByRole("complementary").filter({ has: page.getByRole("heading", { name: "Conversations" }) });
    await expect(history).toBeHidden();
    const opener = page.getByRole("button", { name: "Chats", exact: true });
    await opener.click();
    await expect(history).toBeVisible();
    const close = history.getByRole("button", { name: "Close conversations" });
    await expect(close).toBeFocused();
    const sheet = await history.boundingBox();
    expect(sheet!.width).toBe(375);
    await expect.poll(async () => {
      const box = await history.boundingBox();
      return box!.y + box!.height;
    }).toBeLessThanOrEqual(nav!.y + 1);
    await close.press("Escape");
    await expect(history).toBeHidden();
    await expect(opener).toBeFocused();
    await opener.click();
    await history.getByRole("button", { name: "New chat", exact: true }).click();
    await expect(history).toBeHidden();
    await expect(input).toHaveValue("");
    // A shorter viewport represents the space left while the mobile keyboard is open.
    await page.setViewportSize({ width: 375, height: 480 });
    await input.fill("Follow up");
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test("saved prompts stay on screen without upload permission and remain available on desktop", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await installFakeApi(page);
  await page.route("**/api/auth/login", (route) => route.fulfill({
    json: { ...ACCOUNT, permissions: ACCOUNT.permissions.filter((permission) => permission !== "files.upload") },
  }));
  await logIn(page);
  await page.getByRole("button", { name: "More message tools" }).click();
  await expect(page.getByRole("button", { name: /Attach files/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Saved prompts", exact: true }).click();
  const prompts = page.getByRole("dialog", { name: "Saved prompts" });
  await expect(prompts).toBeVisible();
  const box = await prompts.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(375);
  await page.getByPlaceholder(/Ask something/).click();
  for (const width of [768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(".mobile-header")).toBeHidden();
    await expect(page.getByRole("button", { name: "More message tools" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Saved prompts", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
