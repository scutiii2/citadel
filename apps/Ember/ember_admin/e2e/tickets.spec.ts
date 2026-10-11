import { expect, test, type Page } from "@playwright/test";

async function installTicketsApi(page: Page) {
  const tickets = [
    { id: 142, title: "Login fails after session expires", description: "Signing in again returns a blank screen instead of the chat.", status: "open", effective_priority: "urgent", assignee: null, reporter: "maria", tags: ["authentication", "bug"], group_id: 12 },
    { id: 139, title: "Assistant response stops mid-stream", description: "Long replies end before the answer is complete.", status: "open", effective_priority: "high", assignee: null, reporter: "alex", tags: ["chat", "bug"], group_id: 9, possible_group_id: 12 },
    { id: 136, title: "Reconnect interrupted chat streams", description: "Resume the reply when a connection briefly drops.", status: "in_progress", effective_priority: "high", assignee: "alex", reporter: "sam", tags: ["chat", "bug"], group_id: 9 },
    { id: 124, title: "Keep theme preference after reload", description: "The selected appearance now persists across visits.", status: "resolved", effective_priority: "normal", assignee: "sam", reporter: "alex", tags: ["ui", "bug"], group_id: 3 },
    { id: 115, title: "Improve contrast on disabled buttons", description: "Updated controls remain legible in both themes.", status: "closed", effective_priority: "low", assignee: "sam", reporter: "maria", tags: ["ui", "bug"], group_id: 3 },
  ].map(row => ({ type: "bug", priority: "normal", source: "user", context: {}, possible_group_id: null, created_at: "2026-10-10T10:00:00+00:00", updated_at: "2026-10-11T10:00:00+00:00", closed_at: null, comments: [] as { id: number; ticket_id: number; author: string; author_role: string; body: string; created_at: string }[], ...row }));
  const groups = [
    { id: 12, title: "Session & sign-in", priority: "urgent", tags: ["authentication"] },
    { id: 9, title: "Streaming responses", priority: "high", tags: ["chat"] },
    { id: 3, title: "Appearance settings", priority: "normal", tags: ["ui"] },
  ].map(row => ({ priority_pinned: false, ticket_count: 2, open_count: 1, recent_count: 1, last_activity: "2026-10-11T10:00:00+00:00", ...row }));
  const unexpected: string[] = [];
  let failUpdate = false;
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/auth/me") return json({ id: 1, username: "ada", email: "ada@example.com", email_verified: true, roles: ["Administrator"], permissions: ["tickets.manage"] });
    if (url.pathname === "/api/admin/ticket-groups") return json({ groups });
    if (url.pathname === "/api/admin/tickets") {
      const params = url.searchParams;
      return json({ tickets: tickets.filter(t =>
        (!params.has("status") || t.status === params.get("status")) &&
        (!params.has("priority") || t.effective_priority === params.get("priority")) &&
        (!params.has("tag") || t.tags.includes(params.get("tag")!)) &&
        (!params.has("group_id") || t.group_id === Number(params.get("group_id"))) &&
        (!params.has("possible") || t.possible_group_id !== null)) });
    }
    const match = /^\/api\/admin\/tickets\/(\d+)(\/comments)?$/.exec(url.pathname);
    if (match) {
      const ticket = tickets.find(t => t.id === Number(match[1]));
      if (!ticket) return json({ detail: "Ticket not found" }, 404);
      if (request.method() === "PATCH") {
        if (failUpdate) return json({ detail: "Status could not be saved" }, 502);
        Object.assign(ticket, request.postDataJSON());
      }
      if (match[2] && request.method() === "POST") {
        const { body } = request.postDataJSON() as { body: string };
        ticket.comments!.push({ id: 1, ticket_id: ticket.id, author: "ada", author_role: "staff", body, created_at: ticket.updated_at });
      }
      return json({ ticket });
    }
    unexpected.push(`${request.method()} ${url.pathname}`);
    return json({ detail: "Not faked" }, 404);
  });
  return { unexpected, failNextUpdates: () => { failUpdate = true; } };
}

test("staff triage tickets on the board, search, drag, reply and navigate between views", async ({ page }, testInfo) => {
  const api = await installTicketsApi(page);
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto("/tickets");
  await expect(page.getByRole("heading", { name: "Tickets", exact: true })).toBeVisible();
  await expect(page.locator(".kanban-column")).toHaveCount(4);
  await expect(page.locator(".ticket-card")).toHaveCount(5);
  const titleBox = await page.locator(".page-title").boundingBox();
  expect(titleBox!.y).toBeLessThan(40);
  await page.evaluate(() => { document.documentElement.style.colorScheme = "dark"; });
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("tickets-desktop-dark.png") });
  await page.evaluate(() => { document.documentElement.style.colorScheme = "light"; });
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("tickets-desktop-light.png") });
  await page.getByLabel("Search tickets", { exact: true }).fill("maria");
  await expect(page.locator(".ticket-card")).toHaveCount(2);
  await page.getByLabel("Search tickets", { exact: true }).fill("");

  const firstCard = page.getByRole("button", { name: "Ticket 142: Login fails after session expires", exact: true });
  await firstCard.dragTo(page.locator('[data-status="in_progress"] .column-head'));
  await expect(page.locator('[data-status="in_progress"] [data-ticket-id="142"]')).toBeVisible();
  await expect(page.getByRole("status")).toContainText("moved to In progress");

  await firstCard.click();
  const drawer = page.getByRole("dialog", { name: "Ticket #142", exact: true });
  await expect(drawer).toBeVisible();
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("tickets-drawer.png") });
  await drawer.getByLabel("Reply", { exact: true }).fill("We are looking into this.");
  await drawer.getByRole("button", { name: "Reply", exact: true }).click();
  await expect(drawer.locator(".thread")).toContainText("We are looking into this.");
  for (let i = 0; i < 16; i++) {
    await page.keyboard.press("Tab");
    const focus = await drawer.evaluate(el => ({ inside: el.contains(document.activeElement), modal: el.matches(":modal"), browserChrome: document.activeElement === document.body }));
    // Native dialogs make the background inert; Tab can also visit browser chrome.
    expect(focus.modal).toBe(true);
    expect(focus.inside || focus.browserChrome).toBe(true);
  }
  await drawer.getByRole("button", { name: "Close", exact: true }).focus();
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();

  await page.getByLabel("Priority filter", { exact: true }).selectOption("urgent");
  await expect(page.locator(".ticket-card")).toHaveCount(1);
  await expect(page).toHaveURL(/priority=urgent/);
  await page.reload();
  await expect(page.getByLabel("Priority filter", { exact: true })).toHaveValue("urgent");
  await page.getByLabel("Priority filter", { exact: true }).selectOption("all");
  await page.getByRole("button", { name: "Groups", exact: true }).click();
  await expect(page).toHaveURL(/mode=groups/);
  await page.getByRole("button", { name: /Session & sign-in.*Group 12/ }).click();
  await expect(page.locator(".group-tickets")).toContainText("Login fails after session expires");
  await page.getByRole("button", { name: "Needs review", exact: true }).click();
  await expect(page.locator(".review")).toContainText("May belong to group 12");
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(page.locator(".ticket-card")).toHaveCount(5);

  api.failNextUpdates();
  await page.getByRole("button", { name: "Ticket 139: Assistant response stops mid-stream", exact: true }).dragTo(page.locator('[data-status="resolved"] .column-head'));
  await expect(page.getByRole("alert")).toContainText("Status could not be saved");
  await expect(page.locator('[data-status="open"] [data-ticket-id="139"]')).toBeVisible();
  expect(api.unexpected).toEqual([]);
});

test("the board fits desktop, tablet and mobile, with a touch accessible detail drawer", async ({ page }, testInfo) => {
  const api = await installTicketsApi(page);
  await page.goto("/tickets");
  await expect(page.locator(".ticket-card")).toHaveCount(5);
  for (const width of [1440, 768, 375]) {
    await page.setViewportSize({ width, height: 850 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const titleBox = await page.locator(".page-title").boundingBox();
    expect(titleBox!.y).toBeGreaterThanOrEqual(0);
    await expect(page.locator(".page-title")).toBeVisible();
  }
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("tickets-mobile.png") });
  await page.getByLabel("Visible column", { exact: true }).selectOption("resolved");
  await expect(page.locator('[data-status="open"]')).not.toBeVisible();
  await expect(page.locator('[data-status="resolved"]')).toBeVisible();
  await page.getByRole("button", { name: "Ticket 124: Keep theme preference after reload", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "Ticket #124", exact: true });
  await expect(drawer).toBeVisible();
  const drawerBox = await drawer.boundingBox();
  expect(drawerBox!.y + drawerBox!.height).toBeLessThanOrEqual(798);
  await drawer.getByLabel("Status", { exact: true }).selectOption("closed");
  await expect(drawer.getByLabel("Status", { exact: true })).toHaveValue("closed");
  await drawer.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByLabel("Visible column", { exact: true }).selectOption("closed");
  await expect(page.locator('[data-status="closed"] [data-ticket-id="124"]')).toBeVisible();
  expect(api.unexpected).toEqual([]);
});
