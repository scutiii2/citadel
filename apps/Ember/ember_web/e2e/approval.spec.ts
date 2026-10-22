import { expect, test, type Page } from "@playwright/test";
import { ANSWER, installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

const chip = (page: Page) => page.locator(".mode-chip");
const menu = (page: Page) => page.getByRole("menu", { name: "Tool approval" });

/** Sends a question and waits until its answer is in and the chat is idle, so the next one is not typed
 * while the chat is busy. The fake keeps only the latest exchange of a chat. */
async function ask(page: Page, question: string, turns: number, api: { turns: unknown[] }): Promise<void> {
  const input = page.getByPlaceholder(/Ask something/);
  await input.fill(question);
  await input.press("Enter");
  await expect.poll(() => api.turns.length).toBe(turns);
  await expect(page.getByText(question).first()).toBeVisible();
  await expect(page.getByText(ANSWER)).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Stop" })).toHaveCount(0);
}

test("the approval mode chip: Allow all by default, Auto and Ask every time are sent with the question", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);

  // Nothing asks, as before the picker existed.
  await expect(chip(page)).toHaveText(/Allow all/);
  await ask(page, "first", 1, api);
  expect(api.turns[0]).not.toHaveProperty("ask_before_tools");

  // Auto: asks, and says read-only tools may run unasked.
  await chip(page).click();
  await expect(menu(page).getByRole("menuitemradio")).toHaveCount(3);
  await menu(page).getByRole("menuitemradio", { name: /Auto/ }).click();
  await expect(chip(page)).toHaveText(/Auto/);
  await expect(menu(page)).toHaveCount(0);
  await ask(page, "second", 2, api);
  expect(api.turns[1]).toMatchObject({ ask_before_tools: true, allow_read_only: true });

  // Ask every time: asks, and nothing is read-only.
  await chip(page).click();
  await menu(page).getByRole("menuitemradio", { name: /Ask every time/ }).click();
  await ask(page, "third", 3, api);
  expect(api.turns[2]).toMatchObject({ ask_before_tools: true });
  expect(api.turns[2]).not.toHaveProperty("allow_read_only");

  // The choice is remembered across a reload.
  await page.reload();
  await expect(chip(page)).toHaveText(/Ask every time/);
  expect(api.unexpected).toEqual([]);
});

test("the approval mode chip: Allow all asks for a confirmation, by keyboard too", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);
  await chip(page).click();
  await menu(page).getByRole("menuitemradio", { name: /Ask every time/ }).click();
  await expect(chip(page)).toHaveText(/Ask every time/);

  // Cancel keeps the mode.
  await chip(page).click();
  await page.keyboard.press("3");
  const dialog = page.getByRole("dialog", { name: "Allow every tool to run without asking?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(chip(page)).toHaveText(/Ask every time/);

  // Confirm takes it.
  await chip(page).click();
  await menu(page).getByRole("menuitemradio", { name: /Allow all/ }).click();
  await dialog.getByRole("button", { name: "Allow all" }).click();
  await expect(chip(page)).toHaveText(/Allow all/);

  // Escape closes the menu and leaves the page where it is.
  await chip(page).click();
  await expect(menu(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu(page)).toHaveCount(0);
  await expect(chip(page)).toBeFocused();
  expect(api.unexpected).toEqual([]);
});

test("the approval mode chip is locked to Ask every time while the administrator requires approval", async ({ page }) => {
  const api = await installFakeApi(page);
  api.settings.forceToolApproval = true;
  await logIn(page);

  await expect(chip(page)).toHaveText(/Ask every time/);
  await chip(page).click();
  const auto = menu(page).getByRole("menuitemradio", { name: /Auto/ });
  await expect(auto).toHaveAttribute("aria-disabled", "true");
  await expect(menu(page)).toContainText("Your administrator requires approval before every tool.");
  await auto.click({ force: true });
  await expect(chip(page)).toHaveText(/Ask every time/);

  await page.keyboard.press("Escape");
  await ask(page, "locked", 1, api);
  expect(api.turns[0]).toMatchObject({ ask_before_tools: true, allowed_tools: [] });
  expect(api.turns[0]).not.toHaveProperty("allow_read_only");
  expect(api.unexpected).toEqual([]);
});

test("Settings: the Ask before tools row picks the mode and applies it instantly", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);
  await page.goto("/settings");

  const row = page.locator('[data-setting-id="chat-ask-tools"], #chat-ask-tools').first();
  await expect(row).toContainText("No tool asks first.");
  await row.getByRole("button", { name: "Auto" }).click();
  await expect(row).toContainText("Tools that only read run on their own");
  await expect(page.getByText("Unsaved changes")).toHaveCount(0);

  await page.goto("/");
  await expect(chip(page)).toHaveText(/Auto/);
  expect(api.unexpected).toEqual([]);
});
