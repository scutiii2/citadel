import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { flipSwitch, logIn } from "./helpers.ts";

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
    id: "0".repeat(31) + "1", title: "First", body: "one", tags: [], agent_readable: false, last_editor: "user",
    created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00",
  });
  api.notes.set("0".repeat(31) + "2", {
    id: "0".repeat(31) + "2", title: "Second", body: "two", tags: [], agent_readable: false, last_editor: "user",
    created_at: "2026-01-02T00:00:00", updated_at: "2026-01-02T00:00:00",
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

test("notes: tags and the agent switch are saved, with a warning while agents can read", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);
  await page.goto("/notes");

  await page.getByRole("button", { name: "New note" }).click();
  await page.getByLabel("Title").fill("Wifi");
  const tagBox = page.getByLabel("Add a tag");
  await tagBox.fill("Home Network");
  await tagBox.press("Enter");
  await tagBox.fill("it");
  await tagBox.press(",");
  const chips = page.getByRole("list", { name: "Tags" });
  await expect(chips.getByRole("listitem")).toHaveCount(2);
  await expect(chips).toContainText("home-network");

  // The switch is off at first; turning it on shows the warning, turning it off removes it.
  const agents = page.getByRole("switch", { name: "Let agents read this note" });
  await expect(agents).not.toBeChecked();
  await expect(page.getByRole("note")).toHaveCount(0);
  await flipSwitch(page, "Let agents read this note");
  await expect(agents).toBeChecked();
  await expect(page.getByRole("note")).toContainText("Agents can read this note");
  await flipSwitch(page, "Let agents read this note");
  await expect(page.getByRole("note")).toHaveCount(0);
  await flipSwitch(page, "Let agents read this note");

  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  expect([...api.notes.values()].map((n) => [n.tags, n.agent_readable])).toEqual([[["home-network", "it"], true]]);
  const list = page.getByRole("list", { name: "Notes" });
  await expect(list.getByText("Agents can read")).toBeVisible();
  await expect(list.getByText("home-network")).toBeVisible();

  // Removing a tag is an unsaved change until saved.
  await page.getByRole("button", { name: "Remove tag it" }).click();
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Unsaved changes")).toHaveCount(0);
  expect([...api.notes.values()][0]?.tags).toEqual(["home-network"]);
  expect(api.unexpected).toEqual([]);
});

test("notes: Suggest tags offers existing tags that fit, and nothing is added until one is picked", async ({ page }) => {
  const api = await installFakeApi(page);
  api.notes.set("0".repeat(31) + "1", {
    id: "0".repeat(31) + "1", title: "Budget", body: "rent", tags: ["money", "garden"], agent_readable: false, last_editor: "user",
    created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00",
  });
  await logIn(page);
  await page.goto("/notes");

  await page.getByRole("button", { name: "New note" }).click();
  const suggest = page.getByRole("button", { name: "Suggest tags" });
  await expect(suggest).toBeDisabled(); // nothing written yet
  await page.getByLabel("Title").fill("Pay the money I owe");
  await suggest.click();

  await expect(page.getByText("Laya suggests:")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add suggested tag garden" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Tags" })).toHaveCount(0);
  await page.getByRole("button", { name: "Add suggested tag money" }).click();
  await expect(page.getByRole("list", { name: "Tags" })).toContainText("money");
  await expect(page.getByRole("button", { name: "Add suggested tag money" })).toHaveCount(0);

  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  expect([...api.notes.values()].find((n) => n.title === "Pay the money I owe")?.tags).toEqual(["money"]);
  expect(api.unexpected).toEqual([]);
});

test("notes: a note an agent changed is marked until you save it yourself", async ({ page }) => {
  const api = await installFakeApi(page);
  api.notes.set("0".repeat(31) + "1", {
    id: "0".repeat(31) + "1", title: "Sci-fi picks", body: "Arrival", tags: ["movies"], agent_readable: true,
    last_editor: "agent", created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00",
  });
  await logIn(page);
  await page.goto("/notes");

  const list = page.getByRole("list", { name: "Notes" });
  await expect(list.getByText("Agent edit")).toBeVisible();
  await list.getByRole("button", { name: /Sci-fi picks/ }).click();
  await expect(page.getByText("An agent last changed this note")).toBeVisible();
  await expect(page.getByText("Unsaved changes")).toHaveCount(0);

  await page.getByLabel("Note text").fill("Arrival, Primer");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  await expect(page.getByText("An agent last changed this note")).toHaveCount(0);
  await expect(list.getByText("Agent edit")).toHaveCount(0);
  expect(api.notes.get("0".repeat(31) + "1")?.last_editor).toBe("user");
  expect(api.unexpected).toEqual([]);
});

test("notes: a save over a change an agent made meanwhile asks what to do", async ({ page }) => {
  const api = await installFakeApi(page);
  const id = "0".repeat(31) + "1";
  api.notes.set(id, {
    id, title: "Sci-fi picks", body: "Arrival", tags: [], agent_readable: true, last_editor: "user",
    created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00",
  });
  await logIn(page);
  await page.goto("/notes");
  const list = page.getByRole("list", { name: "Notes" });
  const behindTheirBack = () =>
    Object.assign(api.notes.get(id)!, { body: "Arrival\nPrimer", last_editor: "agent", updated_at: "2026-01-01T00:05:00" });

  // 1. Keep mine: the panel names the agent, the editor keeps the text, Save is off until a choice.
  await list.getByRole("button", { name: /Sci-fi picks/ }).click();
  await page.getByLabel("Note text").fill("Arrival, mine");
  behindTheirBack();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const panel = page.locator(".conflict");
  await expect(panel).toContainText("An agent changed this note after you opened it.");
  await expect(page.getByLabel("Note text")).toHaveValue("Arrival, mine");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  expect(api.notes.get(id)?.body).toBe("Arrival\nPrimer"); // nothing was overwritten yet
  await panel.getByRole("button", { name: "Save mine anyway" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  await expect(panel).toHaveCount(0);
  expect(api.notes.get(id)).toMatchObject({ body: "Arrival, mine", last_editor: "user" });

  // 2. Show theirs: the agent writes again; the user's new edit is dropped for the agent's text.
  Object.assign(api.notes.get(id)!, { body: "Arrival, mine\nTenet", last_editor: "agent", updated_at: "2026-01-01T00:10:00" });
  await page.getByLabel("Note text").fill("something I will lose");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: /Show their version/ }).click();
  await expect(panel).toHaveCount(0);
  await expect(page.getByLabel("Note text")).toHaveValue("Arrival, mine\nTenet");
  await expect(page.getByText("Unsaved changes")).toHaveCount(0);
  await expect(page.getByText("An agent last changed this note")).toBeVisible();
  expect(api.notes.get(id)?.body).toBe("Arrival, mine\nTenet");
  expect(api.unexpected).toEqual([]);
});

test("notes: leaving the page with unsaved text asks first", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);
  await page.goto("/notes");

  await page.getByRole("button", { name: "New note" }).click();
  await page.getByLabel("Title").fill("Draft");
  await page.getByRole("link", { name: "Capabilities", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "Leave without saving?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page).toHaveURL(/notes$/);
  await expect(page.getByLabel("Title")).toHaveValue("Draft");

  await page.getByRole("link", { name: "Capabilities", exact: true }).click();
  await dialog.getByRole("button", { name: "Leave page", exact: true }).click();
  await expect(page).toHaveURL(/capabilities$/);
  expect(api.notes.size).toBe(0);
  expect(api.unexpected).toEqual([]);
});
