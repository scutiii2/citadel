import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { effectScope, ref } from "vue";
import { useReadAloud } from "./useReadAloud";

let audio: HTMLAudioElement;
beforeEach(() => {
  audio = document.createElement("audio");
  vi.spyOn(audio, "play").mockResolvedValue();
  vi.spyOn(audio, "pause").mockImplementation(() => {});
  vi.spyOn(audio, "load").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());
const clip = (id: string) => ({ file_id: id, voice: "v2", duration_s: 1 });

it("pipelines one batch ahead, keeps voice fixed and plays in order", async () => {
  const scope = effectScope();
  const synth = vi.fn().mockResolvedValueOnce(clip("first")).mockResolvedValueOnce(clip("second")).mockResolvedValueOnce(clip("third"));
  const queue = scope.run(() => useReadAloud(ref(audio), synth))!;
  const run = queue.start(["One.", "Two.", "Three."], "v2");
  await vi.waitFor(() => expect(queue.state.value).toBe("playing"));
  expect(audio.getAttribute("src")).toBe("/api/bard/audio/first");
  expect(synth).toHaveBeenCalledTimes(2);
  audio.dispatchEvent(new Event("ended"));
  await vi.waitFor(() => expect(audio.getAttribute("src")).toBe("/api/bard/audio/second"));
  expect(synth).toHaveBeenCalledTimes(3);
  audio.dispatchEvent(new Event("ended"));
  await vi.waitFor(() => expect(audio.getAttribute("src")).toBe("/api/bard/audio/third"));
  audio.dispatchEvent(new Event("ended"));
  await run;
  expect(queue.state.value).toBe("idle");
  expect(synth.mock.calls.map((c) => c[1])).toEqual(["v2", "v2", "v2"]);
  scope.stop();
});

it("stop aborts pending work and late responses never resume audio", async () => {
  const scope = effectScope();
  let resolve!: (value: ReturnType<typeof clip>) => void;
  const synth = vi.fn().mockImplementation(() => new Promise((r) => { resolve = r; }));
  const queue = scope.run(() => useReadAloud(ref(audio), synth))!;
  const run = queue.start(["One"], "v2");
  queue.stop();
  expect(synth.mock.calls[0]![2].aborted).toBe(true);
  resolve(clip("late")); await run;
  expect(audio.play).not.toHaveBeenCalled();
  expect(audio.hasAttribute("src")).toBe(false);
  expect(queue.state.value).toBe("idle");
  scope.stop();
});

it("stop interrupts playing audio and aborts its prefetch", async () => {
  const scope = effectScope();
  const synth = vi.fn().mockResolvedValueOnce(clip("first")).mockImplementation(() => new Promise(() => {}));
  const queue = scope.run(() => useReadAloud(ref(audio), synth))!;
  const run = queue.start(["One", "Two"], "v2");
  await vi.waitFor(() => expect(queue.state.value).toBe("playing"));
  queue.stop(); await run;
  expect(audio.pause).toHaveBeenCalled();
  expect(synth.mock.calls[1]![2].aborted).toBe(true);
  expect(queue.state.value).toBe("idle");
  scope.stop();
});

it("reports a failed prefetch after the current clip without an unhandled rejection", async () => {
  const scope = effectScope();
  const synth = vi.fn().mockResolvedValueOnce(clip("first")).mockRejectedValueOnce(new Error("Bard is down"));
  const queue = scope.run(() => useReadAloud(ref(audio), synth))!;
  const run = queue.start(["One", "Two"], "v2");
  await vi.waitFor(() => expect(queue.state.value).toBe("playing"));
  audio.dispatchEvent(new Event("ended")); await run;
  expect(queue.state.value).toBe("error");
  expect(queue.error.value).toBe("Bard is down");
  scope.stop();
});

it("surfaces playback rejection and cleans up on disposal", async () => {
  const scope = effectScope();
  vi.mocked(audio.play).mockRejectedValue(new Error("Playback blocked"));
  const queue = scope.run(() => useReadAloud(ref(audio), vi.fn().mockResolvedValue(clip("first"))))!;
  await queue.start(["One"], "v2");
  expect(queue.error.value).toContain("Playback blocked");
  scope.stop();
  expect(audio.hasAttribute("src")).toBe(false);
});
