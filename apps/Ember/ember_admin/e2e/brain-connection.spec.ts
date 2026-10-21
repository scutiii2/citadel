import { expect, test } from "@playwright/test";
import { ADMIN_ACCOUNT, installFakeApi, newState } from "./fakeApi.ts";

test("Instance Brain connection uses explicit saves and preserves failed edits", async ({ page }) => {
  const state = newState(); state.permissions = [...ADMIN_ACCOUNT.permissions, "settings.manage"];
  await installFakeApi(page, state);
  await page.route("**/api/settings", route => route.fulfill({ json: { force_tool_approval: false } }));
  await page.route("**/api/settings/pages", route => route.fulfill({ json: { hidden: [] } }));
  let connection = { id: "instance", scope: "instance", label: "Shared vault", endpoint: "https://vault.lan", folder: "Inbox",
    enabled: true, allow_write: true, credential_configured: true, revision: 1, generation: "g", status: "configured" };
  let reject = true; const writes: Record<string, unknown>[] = [];
  await page.route("**/api/brains/connections/instance", route => {
    if (route.request().method() === "GET") return route.fulfill({ json: connection });
    if (reject) return route.fulfill({ status: 409, json: { detail: "Connection changed" } });
    const body = route.request().postDataJSON(); writes.push(body);
    connection = { ...connection, label: body.label, revision: 2 };
    return route.fulfill({ json: connection });
  });
  await page.goto("/admin/settings");
  const panel = page.getByRole("region", { name: "Instance Brain" });
  await expect(panel).toContainText("Every signed-in user");
  await expect(panel.getByLabel("API key", { exact: true })).toHaveValue("");
  await panel.getByLabel("Label", { exact: true }).fill("Updated shared vault");
  expect(writes).toHaveLength(0);
  await panel.getByRole("button", { name: "Save connection", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Connection changed");
  await expect(panel.getByLabel("Label", { exact: true })).toHaveValue("Updated shared vault");
  reject = false;
  await panel.getByRole("button", { name: "Save connection", exact: true }).click();
  await expect(panel.getByRole("status")).toContainText("Connection saved");
  expect(writes[0]).not.toHaveProperty("api_key");
  expect(state.unexpected).toEqual([]);
});
