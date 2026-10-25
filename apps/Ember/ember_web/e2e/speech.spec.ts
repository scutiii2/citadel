import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test.use({ launchOptions: { args: ["--use-fake-device-for-media-stream"] }, permissions: ["microphone"] });

for (const width of [1280, 768, 375]) {
  test(`dictation captures WebM and appends editable draft text at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const api = await installFakeApi(page);
    await logIn(page);
    const input = page.getByRole("textbox", { name: "Message", exact: true });
    await input.fill("Existing draft");
    if (width < 768) await page.getByRole("button", { name: "More message tools" }).click();
    await page.getByRole("button", { name: "Dictate message", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Recording" })).toBeVisible();
    const recorded = page.waitForRequest("**/api/attachments/dictate");
    await page.getByRole("button", { name: "Stop dictation", exact: true }).click();
    const request = (await recorded).postDataJSON() as { filename: string; data: string };
    expect(request.filename).toBe("dictation.webm");
    expect(Buffer.from(request.data, "base64").length).toBeGreaterThan(20);
    await expect(input).toHaveValue("Existing draft\nDictated words ready to edit.");
    await input.fill("Edited transcript");
    expect(api.turns).toHaveLength(0);
    expect(api.unexpected).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("reads every batch through audio, stops, and asks for a voice again", async ({ page }) => {
  const api = await installFakeApi(page, { admin: true });
  const content = "This is a sentence to read aloud. ".repeat(240);
  api.chats.set("speech-chat", { id: "speech-chat", title: "Speech check", agent_id: "agent-1", running: false,
    messages: [{ role: "user", content: "Read a long answer" }, { role: "assistant", content }] });
  const requests: { text: string; voice: string }[] = [];
  page.on("request", (request) => { if (request.url().endsWith("/api/bard/speak")) requests.push(request.postDataJSON()); });
  await logIn(page);
  await page.goto("/chat/speech-chat");
  await page.evaluate(() => {
    const events: string[] = [];
    Object.assign(window, { speechEvents: events });
    document.addEventListener("play", () => events.push("play"), true);
    document.addEventListener("ended", () => events.push("ended"), true);
  });
  await page.getByRole("button", { name: "Read aloud", exact: true }).click();
  await page.getByRole("menuitem", { name: "another-voice", exact: true }).click();
  await expect.poll(() => requests.length).toBe(3);
  await expect(page.getByRole("button", { name: "Read aloud", exact: true })).toBeVisible();
  expect(requests.every((body) => body.voice === "another-voice" && body.text.length <= 3500)).toBe(true);
  expect(requests.map((body) => body.text).join(" ")).toBe(content.trim());
  expect(await page.evaluate(() => (window as unknown as { speechEvents: string[] }).speechEvents)).toEqual(["play", "ended", "play", "ended", "play", "ended"]);
  await expect(page.locator(".bard-audio")).toHaveCount(0);
  await page.getByRole("button", { name: "Read aloud", exact: true }).click();
  await expect(page.getByRole("menu", { name: "Choose a voice" })).toBeVisible();
  await page.getByRole("menuitem", { name: "test-voice", exact: true }).click();
  await page.getByRole("button", { name: "Stop reading aloud", exact: true }).click();
  await expect(page.getByRole("button", { name: "Read aloud", exact: true })).toBeVisible();
  expect(await page.locator(".read-aloud audio").evaluate((el) => (el as HTMLAudioElement).paused && !el.hasAttribute("src"))).toBe(true);
  expect(api.unexpected).toEqual([]);
});
