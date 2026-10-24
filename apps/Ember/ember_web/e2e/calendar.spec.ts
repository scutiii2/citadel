import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("add a calendar, see its event, add and remove an alert, and dismiss an in-app alert", async ({ page }) => {
  const api = await installFakeApi(page, { calendar: true });
  await logIn(page);
  await page.goto("/calendar");

  await expect(page.getByRole("heading", { name: "Calendar", level: 2 })).toBeVisible();
  await expect(page.getByText("No calendars yet")).toBeVisible();

  await page.getByLabel("Label").fill("Work");
  await page.getByLabel("ICS link").fill("https://example.com/a.ics");
  await page.getByRole("button", { name: "Add calendar" }).click();
  await expect(page.getByLabel("Name of calendar Work")).toBeVisible();
  await expect(page.locator(".fc-event", { hasText: "Standup" })).toBeVisible();

  await page.locator(".fc-event", { hasText: "Standup" }).click();
  const dialog = page.getByRole("dialog", { name: "Standup" });
  await expect(dialog.getByText("Room 1")).toBeVisible();
  await dialog.getByRole("button", { name: /close/i }).click();

  await page.getByLabel("Type").selectOption("email");
  await page.getByLabel("When").selectOption("30");
  await page.getByRole("button", { name: "Add alert" }).click();
  await expect(page.getByRole("list", { name: "Alert rules" }).getByText("Email")).toBeVisible();
  await page.getByRole("button", { name: "Remove Email alert 30 minutes before" }).click();
  await expect(page.getByRole("list", { name: "Alert rules" }).getByText("Email")).toHaveCount(0);

  api.calendar.alerts.push({ id: "a1", title: "Design review", start_utc: new Date(Date.now() + 600_000).toISOString(), channel: "inapp", created_at: "x" });
  await page.reload();
  const toast = page.getByRole("region", { name: "Calendar alerts" });
  await expect(toast.getByText("Design review")).toBeVisible();
  await toast.getByRole("button", { name: "Dismiss alert for Design review" }).click();
  await expect(toast).toHaveCount(0);

  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  }
  expect(api.unexpected).toEqual([]);
});

test("a member without calendar.use cannot open the page", async ({ page }) => {
  await installFakeApi(page);
  await logIn(page);
  await page.goto("/calendar");
  await expect(page).not.toHaveURL(/\/calendar/);
});
