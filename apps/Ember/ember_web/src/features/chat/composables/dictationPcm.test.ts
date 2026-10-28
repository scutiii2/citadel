import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { expect, it } from "vitest";

it.each([16000, 44100, 48000])("resamples %s Hz across render quanta and flushes s16le audio", (rate) => {
  const frames: (ArrayBuffer | { type: string })[] = [];
  let Processor: new () => { process(inputs: Float32Array[][]): boolean;
    port: { onmessage: (event: { data: { type: string } }) => void } };
  runInNewContext(readFileSync("public/dictation-pcm.js", "utf8"), {
    sampleRate: rate,
    AudioWorkletProcessor: class {
      port = { postMessage: (data: ArrayBuffer | { type: string }) => frames.push(data), onmessage: null };
    },
    registerProcessor: (_name: string, ctor: typeof Processor) => { Processor = ctor; },
  });
  const processor = new Processor!();
  // Deliberately use a non-100ms length: the last fragment must not disappear on stop.
  const count = Math.round(rate * 0.275);
  for (let i = 0; i < count; i += 128) {
    const size = Math.min(128, count - i);
    processor.process([[new Float32Array(size).fill(0.5), new Float32Array(size).fill(-1)]]);
  }
  processor.port.onmessage({ data: { type: "flush" } });
  const pcm = frames.filter((frame): frame is ArrayBuffer => "byteLength" in frame);
  const sampleCount = pcm.reduce((sum, frame) => sum + frame.byteLength / 2, 0);
  expect(Math.abs(sampleCount - count * 16000 / rate)).toBeLessThanOrEqual(1);
  for (const frame of pcm) {
    expect(frame.byteLength).toBeLessThanOrEqual(3200);
    const samples = new DataView(frame);
    for (let i = 0; i < frame.byteLength; i += 2) expect(samples.getInt16(i, true)).toBe(-8192);
  }
  expect(frames.at(-1)).toEqual({ type: "flushed" });
});
