import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("notes: write one, edit it, and delete it after a confirmation", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);

  await page.goto("/notes");
  await expect(page.getByText("You have no notes yet.")).toBeVisible();

  // Create: Save stays off until there is a title.
  await page.getByRole("button", { name: "New note" }).click();
  const save = page.getByRole("button", { name: "Save", exact: true });
  await expect(save).toBeDisabled();
  await page.getByLabel("Title").fill("Groceries");
  await page.getByLabel("Note text").fill("milk");
  await save.click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  expect([...api.notes.values()].map((n) => [n.title, n.body])).toEqual([["Groceries", "milk"]]);
  const list = page.getByRole("list", { name: "Notes" });
  await expect(list.getByRole("button", { name: /Groceries/ })).toBeVisible();

  // Edit: an unsaved change is flagged, and saving stores it.
  await page.getByLabel("Note text").fill("milk, eggs");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await save.click();
  await expect(page.getByText("Unsaved changes")).toHaveCount(0);
  expect([...api.notes.values()][0]?.body).toBe("milk, eggs");

  // Delete: Cancel keeps it, Delete note removes it.
  await page.getByRole("button", { name: "Delete this note" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete this note?" });
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(api.notes.size).toBe(1);
  await page.getByRole("button", { name: "Delete this note" }).click();
  await dialog.getByRole("button", { name: "Delete note" }).click();
  await expect(page.getByText("You have no notes yet.")).toBeVisible();
  expect(api.notes.size).toBe(0);

  expect(api.unexpected).toEqual([]);
});

test("notes: leaving unsaved changes asks first", async ({ page }) => {
  const api = await installFakeApi(page);
  api.notes.set("0".repeat(31) + "1", {
    id: "0".repeat(31) + "1", title: "First", body: "one", created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00",
  });
  api.notes.set("0".repeat(31) + "2", {
    id: "0".repeat(31) + "2", title: "Second", body: "two", created_at: "2026-01-02T00:00:00", updated_at: "2026-01-02T00:00:00",
  });
  await logIn(page);
  await page.goto("/notes");

  const list = page.getByRole("list", { name: "Notes" });
  await list.getByRole("button", { name: /First/ }).click();
  await page.getByLabel("Note text").fill("changed");
  await list.getByRole("button", { name: /Second/ }).click();

  const dialog = page.getByRole("dialog", { name: "Discard your changes?" });
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByLabel("Note text")).toHaveValue("changed");

  await list.getByRole("button", { name: /Second/ }).click();
  await dialog.getByRole("button", { name: "Discard" }).click();
  await expect(page.getByLabel("Note text")).toHaveValue("two");
  expect(api.notes.get("0".repeat(31) + "1")?.body).toBe("one");
});
