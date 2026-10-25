import { afterEach, expect, it, vi } from "vitest";
import { bardClient } from "./BardClient";

afterEach(() => vi.unstubAllGlobals());
it("loads only installed voices and posts the selected voice with cancellation", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ voices: ["v1", "v2"] })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ file_id: "abc", voice: "v2", duration_s: 1 })));
  vi.stubGlobal("fetch", fetcher);
  const controller = new AbortController();
  expect(await bardClient.voices(controller.signal)).toEqual({ voices: ["v1", "v2"] });
  expect(await bardClient.speak("hello", "v2", controller.signal)).toEqual({ file_id: "abc", voice: "v2", duration_s: 1 });
  expect(fetcher).toHaveBeenLastCalledWith("/api/bard/speak", expect.objectContaining({
    signal: controller.signal, credentials: "same-origin", body: JSON.stringify({ text: "hello", voice: "v2" }),
  }));
});
it("surfaces synthesis errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Voice unavailable" }), { status: 400 })));
  await expect(bardClient.speak("hi", "missing")).rejects.toThrow("Voice unavailable");
});
