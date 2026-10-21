import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { flipSwitch, logIn } from "./helpers.ts";

test("Notes promotion reviews shared audience, keeps failed draft and preserves the Note", async ({ page }) => {
  const api = await installFakeApi(page);
  let reject = true;
  const publications: Record<string, unknown>[] = [];
  await page.route("**/api/brains/destinations", route => route.fulfill({ json: ["personal", "instance"].map(scope => ({
    id: scope, scope, label: `${scope} vault`, enabled: true, writable: true, folder: "Inbox", revision: 1, generation: "generation", status: "configured" })) }));
  await page.route("**/api/brains/notes/*/review", route => {
    const note = [...api.notes.values()][0]!;
    return route.fulfill({ json: { note_id: note.id, title: note.title, body: note.body,
      source_hash: "a".repeat(64), source_revision: note.updated_at, agent_readable: false } });
  });
  await page.route("**/api/brains/notes/*/promote", route => {
    if (reject) return route.fulfill({ status: 412, json: { detail: "Destination changed. Review again." } });
    publications.push(route.request().postDataJSON());
    return route.fulfill({ json: { id: "promotion", note_id: [...api.notes.keys()][0], scope: "instance", path: publications[0]!.path, status: "published" } });
  });
  await logIn(page); await page.goto("/notes");
  await page.getByRole("button", { name: "New note", exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill("Deployment procedure");
  await page.getByLabel("Note text", { exact: true }).fill("Reusable deployment steps");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("button", { name: "Promote to Obsidian", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Review Obsidian publication" });
  await expect(dialog).toBeVisible();
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await dialog.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
  }
  await dialog.getByLabel("Destination", { exact: true }).selectOption("instance");
  const publish = dialog.getByRole("button", { name: "Publish document", exact: true });
  await expect(publish).toBeDisabled();
  await flipSwitch(page, "I reviewed the shared audience");
  await dialog.getByLabel("Publication Markdown").fill("# Reviewed shared procedure\nSteps");
  await publish.click();
  await expect(dialog.getByRole("alert")).toContainText("Destination changed");
  await expect(dialog.getByLabel("Publication Markdown")).toHaveValue("# Reviewed shared procedure\nSteps");
  reject = false; await publish.click();
  await expect(dialog).not.toBeVisible();
  expect(publications[0]).toMatchObject({ scope: "instance", shared_audience_reviewed: true });
  expect([...api.notes.values()][0]!.body).toBe("Reusable deployment steps");
  expect(api.unexpected).toEqual([]);
});
