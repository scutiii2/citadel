import { expect, test, type WebSocketRoute } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test.use({ launchOptions: { args: ["--use-fake-device-for-media-stream"] }, permissions: ["microphone"] });

for (const width of [1280, 768, 375]) {
  test(`dictation captures WebM and appends editable draft text at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => {
      localStorage.clear();
      const contexts: AudioContext[] = [];
      const Original = window.AudioContext;
      window.AudioContext = class extends Original {
        constructor(options?: AudioContextOptions) { super(options); contexts.push(this); }
      };
      Object.assign(window, { dictationAudioContexts: contexts });
    });
    await page.routeWebSocket("**/api/attachments/dictate/stream", (socket) => socket.close({ code: 1011, reason: "Test upload fallback" }));
    const api = await installFakeApi(page);
    await page.route("**/api/attachments/dictate/partial", (route) => route.fulfill({ status: 503, json: { detail: "Test upload fallback" } }));
    await logIn(page);
    const input = page.getByRole("textbox", { name: "Message", exact: true });
    await input.fill("Existing draft");
    if (width < 768) await page.getByRole("button", { name: "More message tools" }).click();
    const composerBefore = await page.locator(".composer").boundingBox();
    await page.getByRole("button", { name: "Dictate message", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Recording" })).toBeVisible();
    await expect(page.locator(".dictation-waveform span")).toHaveCount(24);
    await expect(page.locator(".dictation-timer")).toHaveText("0:01 / 2:30", { timeout: 5000 });
    // The browser's fake microphone still goes through the real AudioContext graph.
    await expect.poll(() => page.locator(".dictation-waveform span").evaluateAll((bars) =>
      bars.some((bar) => Number.parseFloat((bar as HTMLElement).style.height) > 2))).toBe(true);
    const stop = page.getByRole("button", { name: "Stop dictation", exact: true });
    const bounds = await stop.boundingBox();
    expect(bounds!.height).toBeGreaterThanOrEqual(44);
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    expect((await page.locator(".composer").boundingBox())!.height).toBe(composerBefore!.height);
    for (const theme of ["light", "dark"]) {
      await page.evaluate((theme) => { document.documentElement.style.colorScheme = theme; }, theme);
      await page.locator(".composer").screenshot({ path: `test-results/dictation-${width}-${theme}.png` });
    }
    await expect(page.locator(".dictation-status")).toContainText("Live text is unavailable", { timeout: 10000 });
    await expect(page.locator(".locked-hint")).toBeVisible();
    await expect(page.locator(".locked-hint")).toContainText("Live text is unavailable");
    let finishTranscribing!: () => void;
    const pending = new Promise<void>((resolve) => { finishTranscribing = resolve; });
    await page.route("**/api/attachments/dictate", async (route) => { await pending; await route.fallback(); });
    const recorded = page.waitForRequest("**/api/attachments/dictate");
    await page.getByRole("button", { name: "Stop dictation", exact: true }).click();
    const request = (await recorded).postDataJSON() as { filename: string; data: string };
    expect(request.filename).toBe("dictation.webm");
    expect(Buffer.from(request.data, "base64").length).toBeGreaterThan(20);
    await expect(page.getByRole("button", { name: "Transcribing…", exact: true })).toBeDisabled();
    await expect.poll(() => page.evaluate(() =>
      (window as unknown as { dictationAudioContexts: AudioContext[] }).dictationAudioContexts.every((context) => context.state === "closed"))).toBe(true);
    await page.locator(".composer").screenshot({ path: `test-results/dictation-${width}-transcribing.png` });
    finishTranscribing();
    await expect(input).toHaveValue("Existing draft\nDictated words ready to edit.");
    await input.fill("Edited transcript");
    expect(api.turns).toHaveLength(0);
    expect(api.unexpected).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

for (const width of [1280, 768, 375]) {
  for (const mode of ["stream", "partial", "cancel"] as const) {
    test(`live dictation ${mode} preserves and unlocks the draft at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      let socket!: WebSocketRoute;
      let partialCalls = 0;
      await page.routeWebSocket("**/api/attachments/dictate/stream", (connection) => {
        socket = connection;
        if (mode === "partial") { connection.close({ code: 1013, reason: "Test stream session cap fallback" }); return; }
        let started = false;
        connection.onMessage((message) => {
          if (typeof message === "string") {
            if (JSON.parse(message).type === "stop") connection.send(JSON.stringify({ type: "final", text: "Final streamed words" }));
          } else if (!started) {
            started = true;
            connection.send(JSON.stringify({ type: "partial", text: "First live hypothesis" }));
          }
        });
      });
      const api = await installFakeApi(page);
      await page.route("**/api/attachments/dictate/partial", (route) => {
        partialCalls++;
        return route.fulfill({ json: { text: "Periodic live words", duration_s: 1 } });
      });
      await logIn(page);
      const input = page.getByRole("textbox", { name: "Message", exact: true });
      await input.fill("Original draft");
      if (width < 768) await page.getByRole("button", { name: "More message tools" }).click();
      const before = await page.locator(".composer").boundingBox();
      await page.getByRole("button", { name: "Dictate message", exact: true }).click();
      await expect(input).toHaveAttribute("readonly", "");
      await expect(input).toHaveAttribute("aria-readonly", "true");
      await expect(input).toHaveValue(`Original draft\n${mode === "partial" ? "Periodic live words" : "First live hypothesis"}`, { timeout: 15000 });
      if (mode !== "partial") {
        socket.send(JSON.stringify({ type: "partial", text: "Corrected live words" }));
        await expect(input).toHaveValue("Original draft\nCorrected live words");
      } else {
        expect(partialCalls).toBeGreaterThan(0);
        await expect(page.locator(".dictation-status")).toContainText(/periodic|live|stream/i);
        await expect(page.locator(".locked-hint")).toBeVisible();
        await expect(page.locator(".locked-hint")).toContainText("periodic");
      }
      // No extra status row changes the composer geometry; the transcript may grow its field.
      expect((await page.getByRole("button", { name: "Cancel dictation", exact: true }).boundingBox())!.width).toBeGreaterThanOrEqual(44);
      await input.press("Enter");
      await expect(page.locator(".send")).toBeDisabled();
      if (mode === "cancel") {
        await page.getByRole("button", { name: "Cancel dictation", exact: true }).click();
        await expect(input).toHaveValue("Original draft");
        expect((await page.locator(".composer").boundingBox())!.height).toBe(before!.height);
      } else {
        await page.getByRole("button", { name: "Stop dictation", exact: true }).click();
        await expect(input).toHaveValue(`Original draft\n${mode === "stream" ? "Final streamed words" : "Dictated words ready to edit."}`);
      }
      await expect(input).not.toHaveAttribute("readonly", "");
      await input.fill("Ready for manual editing");
      expect(api.turns).toHaveLength(0);
      expect(api.unexpected).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  }
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
