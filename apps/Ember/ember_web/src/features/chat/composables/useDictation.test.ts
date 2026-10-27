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
let amplitude = 128;
class AudioContextMock {
  static last: AudioContextMock;
  state = "running";
  source = { connect: vi.fn(), disconnect: vi.fn() };
  analyser = { fftSize: 0, disconnect: vi.fn(), getByteTimeDomainData: (data: Uint8Array) => data.fill(amplitude) };
  createMediaStreamSource = vi.fn(() => this.source);
  createAnalyser = () => this.analyser;
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn().mockResolvedValue(undefined);
  constructor() { AudioContextMock.last = this; }
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("MediaRecorder", Recorder);
  vi.stubGlobal("AudioContext", AudioContextMock);
  amplitude = 128;
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  getUserMedia.mockResolvedValue(stream);
  stopTrack.mockClear();
});

it("scrolls real microphone levels to the right and measures elapsed time", async () => {
  const scope = effectScope();
  const d = scope.run(() => useDictation(vi.fn(), vi.fn()))!;
  await d.toggle();
  await vi.advanceTimersByTimeAsync(100);
  expect(d.levels.value.every((level) => level === 0)).toBe(true);
  amplitude = 160;
  await vi.advanceTimersByTimeAsync(100);
  expect(d.levels.value.at(-1)).toBeGreaterThan(0);
  expect(d.levels.value[0]).toBe(0);
  expect(AudioContextMock.last.createMediaStreamSource).toHaveBeenCalledWith(stream);
  await vi.advanceTimersByTimeAsync(1200);
  expect(d.elapsedMs.value).toBeGreaterThanOrEqual(1300);
  scope.stop();
});

it.each(["stop", "cancel", "dispose", "error"])("releases the audio graph and frame loop on %s", async (action) => {
  const scope = effectScope();
  const d = scope.run(() => useDictation(vi.fn(), () => new Promise(() => {})))!;
  await d.toggle();
  await vi.advanceTimersByTimeAsync(100);
  const context = AudioContextMock.last;
  if (action === "stop") await d.toggle();
  if (action === "cancel") d.cancel();
  if (action === "dispose") scope.stop();
  if (action === "error") Recorder.last.onerror?.();
  expect(context.close).toHaveBeenCalledTimes(1);
  expect(context.source.disconnect).toHaveBeenCalledTimes(1);
  expect(context.analyser.disconnect).toHaveBeenCalledTimes(1);
  expect(stopTrack).toHaveBeenCalledTimes(1);
  const elapsed = d.elapsedMs.value;
  const levels = [...d.levels.value];
  await vi.advanceTimersByTimeAsync(2000);
  expect(d.elapsedMs.value).toBe(elapsed);
  expect(d.levels.value).toEqual(levels);
  expect(vi.getTimerCount()).toBe(0);
  scope.stop();
});

it("keeps recording and timing if the browser cannot create an audio graph", async () => {
  vi.stubGlobal("AudioContext", class { constructor() { throw new Error("Audio unavailable"); } });
  const scope = effectScope();
  const d = scope.run(() => useDictation(vi.fn(), () => new Promise(() => {})))!;
  await d.toggle();
  await vi.advanceTimersByTimeAsync(1200);
  expect(d.state.value).toBe("recording");
  expect(d.elapsedMs.value).toBeGreaterThanOrEqual(1100);
  expect(d.levels.value.every((level) => level === 0)).toBe(true);
  await d.toggle();
  expect(d.state.value).toBe("transcribing");
  expect(stopTrack).toHaveBeenCalledTimes(1);
  scope.stop();
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
