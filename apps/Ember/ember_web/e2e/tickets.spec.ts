import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

for (const width of [1280, 768, 375]) {
  test(`ticket deep link, unread receipt, reopen and reply at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const api = await installFakeApi(page, { tickets: true });
    api.tickets.set(7, {
      id: 7, type: "bug", title: "Email fails", description: "It does not send.", status: "resolved",
      has_unread: true, created_at: "2026-10-10T10:00:00Z", updated_at: "2026-10-12T10:00:00Z", closed_at: "2026-10-12T10:00:00Z",
      comments: [{ id: 1, ticket_id: 7, author: "support", author_role: "staff", body: "Please try the fix.", created_at: "2026-10-12T10:00:00Z" }],
    });
    await logIn(page);
    await page.goto("/tickets/7");
    const detail = page.getByRole("dialog", { name: "Ticket #7", exact: true });
    await expect(detail.getByRole("heading", { name: "Email fails" })).toBeVisible();
    await expect(detail.getByText("Please try the fix.")).toBeVisible();
    await expect(detail.getByLabel("Ticket status timeline")).toBeVisible();
    await detail.getByRole("button", { name: "Reopen ticket", exact: true }).click();
    await expect(detail.getByText("Ticket reopened by the reporter.")).toBeVisible();
    await detail.getByLabel("Reply", { exact: true }).fill("Still failing.");
    await detail.getByRole("button", { name: "Send", exact: true }).click();
    await expect(detail.getByText("Still failing.")).toBeVisible();
    await detail.getByRole("button", { name: "Close ticket", exact: true }).click();
    await page.getByRole("dialog", { name: "Close this ticket?", exact: true }).getByRole("button", { name: "Close the ticket", exact: true }).click();
    await expect(detail.getByRole("button", { name: "Reopen ticket", exact: true })).toBeVisible();
    await detail.getByRole("button", { name: "Close", exact: true }).click();
    await expect(page).toHaveURL(/\/tickets$/);
    await expect(page.getByRole("button", { name: "Closed (1)", exact: true })).toBeVisible();
    await expect(page.getByText("Support replied", { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.goto("/tickets/404");
    await expect(page.getByRole("alert")).toContainText("No ticket 404.");
    expect(api.unexpected).toEqual([]);
  });
}
