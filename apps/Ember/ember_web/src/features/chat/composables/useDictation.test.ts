import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { effectScope } from "vue";
import { useDictation } from "./useDictation";

class Recorder {
  static isTypeSupported = () => true;
  static last: Recorder;
  state = "inactive";
  ondataavailable?: (event: { data: Blob }) => void;
  onstop?: () => void;
  onerror?: () => void;
  constructor() { Recorder.last = this; }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["speech"]) });
    this.onstop?.();
  }
}
const stopTrack = vi.fn();
const stream = { getTracks: () => [{ stop: stopTrack }] };
const getUserMedia = vi.fn();
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("MediaRecorder", Recorder);
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  getUserMedia.mockResolvedValue(stream);
  stopTrack.mockClear();
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it("records, stops on second click and delivers editable text", async () => {
  const scope = effectScope();
  const transcribe = vi.fn().mockResolvedValue({ text: "hello", duration_s: 1 });
  const insert = vi.fn();
  const d = scope.run(() => useDictation(insert, transcribe))!;
  await d.toggle();
  expect(d.state.value).toBe("recording");
  await d.toggle();
  await vi.waitFor(() => expect(insert).toHaveBeenCalledWith("hello"));
  expect(d.state.value).toBe("idle");
  expect(stopTrack).toHaveBeenCalled();
  scope.stop();
});

it("auto stops at 150 seconds", async () => {
  const scope = effectScope();
  const insert = vi.fn();
  const d = scope.run(() => useDictation(insert, vi.fn().mockResolvedValue({ text: "timed", duration_s: 150 })))!;
  await d.toggle();
  await vi.advanceTimersByTimeAsync(149999);
  expect(d.state.value).toBe("recording");
  await vi.advanceTimersByTimeAsync(1);
  expect(insert).toHaveBeenCalledWith("timed");
  scope.stop();
});

it("shows microphone denial and transcription failure inline", async () => {
  const scope = effectScope();
  getUserMedia.mockRejectedValueOnce(new DOMException("Denied", "NotAllowedError"));
  const d = scope.run(() => useDictation(vi.fn(), vi.fn().mockRejectedValue(new Error("Scribe is unavailable"))))!;
  await d.toggle();
  expect(d.state.value).toBe("error");
  expect(d.error.value).toMatch(/permission/i);
  await d.toggle();
  await d.toggle();
  await vi.waitFor(() => expect(d.error.value).toContain("Scribe is unavailable"));
  scope.stop();
});

it("releases a late microphone grant after disposal", async () => {
  const scope = effectScope();
  let grant!: (value: unknown) => void;
  getUserMedia.mockReturnValueOnce(new Promise((resolve) => { grant = resolve; }));
  const d = scope.run(() => useDictation(vi.fn(), vi.fn()))!;
  const starting = d.toggle();
  scope.stop();
  grant(stream);
  await starting;
  expect(stopTrack).toHaveBeenCalled();
  expect(d.state.value).toBe("idle");
});

it("cancels transcription and ignores late responses", async () => {
  const scope = effectScope();
  const insert = vi.fn();
  let resolve!: (value: { text: string; duration_s: number }) => void;
  let signal: AbortSignal | undefined;
  const transcribe = (_blob: Blob, s?: AbortSignal) => { signal = s; return new Promise<{ text: string; duration_s: number }>((r) => { resolve = r; }); };
  const d = scope.run(() => useDictation(insert, transcribe))!;
  await d.toggle(); await d.toggle();
  scope.stop();
  resolve({ text: "late", duration_s: 1 });
  await Promise.resolve();
  expect(signal?.aborted).toBe(true);
  expect(insert).not.toHaveBeenCalled();
});
