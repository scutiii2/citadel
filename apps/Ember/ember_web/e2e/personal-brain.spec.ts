import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { flipSwitch, logIn } from "./helpers.ts";

test("Personal Brain tests a draft read-only and saves a private connection explicitly", async ({ page }) => {
  const api = await installFakeApi(page);
  let connection = { id: null as string | null, scope: "personal", label: "Personal Brain", endpoint: "", folder: "Inbox",
    enabled: false, allow_write: false, credential_configured: false, revision: 0, generation: null as string | null, status: "not_configured" };
  const writes: Record<string, unknown>[] = [];
  let tests = 0;
  await page.route("**/api/brains/connections/personal**", route => {
    if (new URL(route.request().url()).pathname.endsWith("/test")) {
      tests++; return route.fulfill({ json: { status: "connected", message: "Read-only connection test succeeded" } });
    }
    if (route.request().method() === "GET") return route.fulfill({ json: connection });
    const body = route.request().postDataJSON(); writes.push(body);
    connection = { ...connection, id: "personal-id", label: body.label, endpoint: body.endpoint,
      enabled: body.enabled, allow_write: body.allow_write, credential_configured: true, revision: 1, generation: "new-generation", status: "configured" };
    return route.fulfill({ json: connection });
  });
  await logIn(page); await page.goto("/settings");
  await expect(page.getByRole("region", { name: "Personal Brain" })).toHaveCount(0);
  await page.goto("/brains");
  const panel = page.getByRole("region", { name: "Personal Brain" });
  await panel.getByLabel("Label", { exact: true }).fill("My private vault");
  await panel.getByLabel("HTTPS endpoint").fill("https://vault.lan:27124");
  await panel.getByLabel("API key", { exact: true }).fill("private-test-key");
  await flipSwitch(page, "Enable connection");
  await panel.getByRole("button", { name: "Test connection", exact: true }).click();
  await expect(panel.getByRole("status")).toContainText("Read-only connection test succeeded");
  expect(tests).toBe(1); expect(writes).toHaveLength(0);
  for (const theme of ["light", "dark"]) {
    await page.evaluate(value => { document.documentElement.style.colorScheme = value; }, theme);
    await expect(panel.getByLabel("API key", { exact: true })).toBeVisible();
  }
  await panel.getByRole("button", { name: "Save connection", exact: true }).click();
  await expect(panel.getByRole("status")).toContainText("Connection saved");
  await expect(panel.getByLabel("API key", { exact: true })).toHaveValue("");
  expect(writes[0]).toMatchObject({ endpoint: "https://vault.lan:27124", enabled: true, expected_revision: 0 });
  expect(api.unexpected).toEqual([]);
});
