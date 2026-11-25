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
  // The create flipped the page's busy flag while the closed confirm dialog held its Delete button: it must still open full size.
  await page.getByRole("button", { name: "Delete folder" }).click();
  const confirm = page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true });
  await expect(confirm).toBeVisible();
  expect((await confirm.boundingBox())!.width).toBeGreaterThan(50);
  // The bin icon sits left of the label, not on top of it (a page-wide .danger rule once reset the padding).
  const bin = (await confirm.locator(".bin").boundingBox())!;
  const label = (await confirm.locator(".label").boundingBox())!;
  expect(bin.x + bin.width).toBeLessThanOrEqual(label.x + 1);
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  expect(posted).toEqual([{ name: "Trip", minutes: 15 }]);
  expect(state.unexpected).toEqual([]);
});
