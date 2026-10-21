import { expect, test, type Page } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

async function installBrain(page: Page) {
  const api = await installFakeApi(page);
  const requests: { scope: string; operation: string; path: string; query: string }[] = [];
  await page.route("**/api/brains/browse", route => {
    const body = route.request().postDataJSON();
    requests.push(body);
    if (body.operation === "status") return route.fulfill({ json: { status: "connected", index_status: "ready" } });
    if (body.operation === "list") return route.fulfill({ json: { entries: body.path === "" ? [
      { path: "Inbox", kind: "folder" }, { path: "Start.md", kind: "file" }
    ] : [{ path: "Inbox/Guide.md", kind: "file" }, { path: "Inbox/Empty.md", kind: "file" }] } });
    if (body.operation === "read") return route.fulfill({ json: { content: body.path.endsWith("Empty.md") ? "" : `# ${body.scope === "personal" ? "Personal guide" : "A useful guide"}\n\n` + "A useful paragraph.\n\n".repeat(40) + "Long path: " + "x".repeat(300) } });
    return route.fulfill({ json: { refreshing: true, failures: [{ scope: "instance", message: "Shared vault offline" }], hits: [
      { scope: "personal", path: "Inbox/Guide.md", heading: "Private guide", content: "A private search excerpt", connection_label: "My vault", refresh_status: "ready" }
    ] } });
  });
  return { api, requests };
}

test("Brains keeps folders beside the reader and supports mobile reading in both themes", async ({ page }) => {
  const { api } = await installBrain(page);
  await logIn(page);
  await page.goto("/brains");
  await page.getByRole("button", { name: "Inbox", exact: true }).click();
  await page.getByRole("button", { name: "Inbox/Guide.md", exact: true }).click();
  await expect(page.getByRole("heading", { name: "A useful guide", exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Brain documents" })).toContainText("Empty.md");
  await page.getByRole("button", { name: "Check connection", exact: true }).click();
  await expect(page.getByRole("heading", { name: "A useful guide", exact: true })).toBeVisible();
  await expect(page.locator(".connection-status")).toContainText("connected");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(page.getByRole("heading", { name: "A useful guide", exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "All documents" })).toBeVisible({ visible: width < 768 });
      await expect(page.getByRole("list", { name: "Brain documents" })).toBeVisible({ visible: width >= 768 });
    }
  }
  await page.getByRole("button", { name: "All documents" }).click();
  await expect(page.getByRole("list", { name: "Brain documents" })).toBeVisible();
  await page.getByRole("button", { name: "Inbox/Empty.md", exact: true }).click();
  await expect(page.getByText("This document is empty.")).toBeVisible();
  await page.getByRole("button", { name: "Personal connection", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Personal connection", exact: true });
  await settings.getByLabel("Label", { exact: true }).fill("My vault draft");
  expect(await settings.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
  await settings.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: "Personal connection", exact: true }).click();
  await expect(settings.getByLabel("Label", { exact: true })).toHaveValue("My vault draft");
  expect(api.unexpected).toEqual([]);
});

test("Brains searches both scopes and opens partial results in the correct private brain", async ({ page }) => {
  const { api, requests } = await installBrain(page);
  await logIn(page);
  await page.goto("/brains");
  await page.getByRole("button", { name: "Both brains", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search brains" }).fill("guide");
  await page.getByRole("search").getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Instance Brain: Shared vault offline")).toBeVisible();
  await expect(page.getByText("Indexing is in progress. Results use completed documents.")).toBeVisible();
  await expect(page.locator(".scope-badge")).toHaveText("Personal Brain · Only you");
  await page.getByRole("button", { name: "Private guide", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Personal guide", exact: true })).toBeVisible();
  await expect(page.locator(".reader-audience")).toHaveText("Only you");
  expect(requests.at(-1)).toMatchObject({ scope: "personal", operation: "read", path: "Inbox/Guide.md" });
  await page.getByRole("button", { name: "Instance", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Personal guide", exact: true })).toHaveCount(0);
  expect(api.unexpected).toEqual([]);
});

test("Brains follows personal document links and recovers from a failed folder request", async ({ page }) => {
  const { api } = await installBrain(page);
  await logIn(page);
  await page.goto("/brains?scope=personal&path=Inbox/Guide.md");
  await expect(page.getByRole("heading", { name: "Personal guide", exact: true })).toBeVisible();
  let offline = true;
  await page.route("**/api/brains/browse", route => {
    if (offline) return route.fulfill({ status: 503, json: { detail: "Vault temporarily offline" } });
    return route.fulfill({ json: { entries: [] } });
  });
  await page.getByRole("button", { name: "Vault", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Vault temporarily offline");
  await expect(page.getByRole("heading", { name: "Personal guide", exact: true })).toBeVisible();
  offline = false;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByText("This folder is empty.")).toBeVisible();
  expect(api.unexpected).toEqual([]);
});
