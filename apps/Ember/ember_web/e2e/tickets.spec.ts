import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("ticket workspace preserves drafts through responsive layouts and keeps Send reachable", async ({ page }) => {
  const api = await installFakeApi(page, { tickets: true });
  api.tickets.set(7, {
    id: 7, type: "bug", title: "Photo upload stalls on mobile", description: "A long report. ".repeat(100) + "x".repeat(300), status: "in_progress", has_unread: true,
    created_at: "2026-10-20T10:00:00Z", updated_at: "2026-10-21T02:24:00Z", closed_at: null,
    comments: [{ id: 1, ticket_id: 7, author: "support", author_role: "staff", body: "Which browser are you using?", created_at: "2026-10-21T02:24:00Z" }],
  });
  await logIn(page);
  await page.goto("/tickets/7");
  const detail = page.getByRole("region", { name: "Ticket #7", exact: true });
  await detail.getByLabel("Reply", { exact: true }).fill("A reply in progress");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 });
      await expect(detail.getByRole("button", { name: "Send", exact: true })).toBeInViewport();
      await expect(detail.getByLabel("Reply", { exact: true })).toHaveValue("A reply in progress");
      await expect(page.getByRole("list", { name: "Your ticket list", exact: true })).toBeVisible({ visible: width >= 768 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      expect(await detail.locator(".conversation").evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
    }
  }
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  const form = page.getByRole("dialog", { name: "New ticket", exact: true });
  await form.getByLabel("Title", { exact: true }).fill("A feature idea");
  await form.getByLabel("Description", { exact: true }).fill("Keep this draft while I check a ticket.");
  expect(await form.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
  await form.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(detail.getByLabel("Reply", { exact: true })).toHaveValue("A reply in progress");
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  await expect(form.getByLabel("Title", { exact: true })).toHaveValue("A feature idea");
  await form.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "All tickets" }).click();
  await page.getByRole("searchbox", { name: "Search ticket titles" }).fill("photo");
  await expect(page.getByRole("list", { name: "Your ticket list", exact: true })).toBeVisible();
  await page.getByRole("button").filter({ hasText: "Photo upload stalls on mobile" }).click();
  await expect(detail.getByRole("heading", { name: "Photo upload stalls on mobile" })).toBeVisible();
  expect(api.unexpected).toEqual([]);
});

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
    const detail = page.getByRole("region", { name: "Ticket #7", exact: true });
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
    if (width < 768) await page.getByRole("button", { name: "All tickets" }).click();
    else await detail.getByRole("button", { name: "Close", exact: true }).click();
    await expect(page).toHaveURL(/\/tickets$/);
    await expect(page.getByRole("button", { name: "Closed (1)", exact: true })).toBeVisible();
    await expect(page.getByText("Support replied", { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.goto("/tickets/404");
    await expect(page.getByRole("alert")).toContainText("No ticket 404.");
    expect(api.unexpected).toEqual([]);
  });
}
