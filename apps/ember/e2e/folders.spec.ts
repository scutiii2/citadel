import { expect, test } from "@playwright/test";
import { ACCOUNT, installFakeApi, newState } from "./fakeApi.ts";

for (const width of [1280, 910, 768, 375]) test(`the Temp folders page creates a folder with a real click at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 800 });
  const state = newState();
  await installFakeApi(page, state);
  const folders: unknown[] = [];
  const posted: unknown[] = [];
  // Registered after the shared fake, so these win for their paths.
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...ACCOUNT, permissions: [...ACCOUNT.permissions, "folders.use"] }) }));
  await page.route("**/api/shared-folders", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      const body = request.postDataJSON() as { name: string; minutes: number };
      posted.push(body);
      folders.push({
        id: 1, name: body.name, token: "t".repeat(43), created_at: "2026-11-25T10:00:00Z",
        expires_at: new Date(Date.now() + body.minutes * 60_000).toISOString(), files: [],
      });
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(folders[0]) });
    }
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(folders) });
  });

  await page.goto("/folders");
  const create = page.getByRole("button", { name: "Create folder" });
  await expect(create).toBeEnabled();
  await page.getByLabel("Folder name").fill("Trip");
  await page.getByRole("button", { name: "15 min" }).click();
  await expect(create).toBeEnabled();
  await create.click();

  await expect(page.getByRole("region", { name: "Trip" })).toBeVisible();
  expect(posted).toEqual([{ name: "Trip", minutes: 15 }]);
  expect(state.unexpected).toEqual([]);
});
