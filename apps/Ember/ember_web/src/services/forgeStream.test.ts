import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ForgeEvent } from "../api/ForgeClient";
import { takeEvents, watchGroup } from "./forgeStream";

const message = (seq: number): ForgeEvent => ({ type: "message", seq, sender: "user", kind: "text", body: { text: `m${seq}` }, created_at: "2026-10-18T10:00:00" });
const frame = (event: ForgeEvent) => `${event.type === "message" ? `id: ${event.seq}\n` : ""}data: ${JSON.stringify(event)}\n\n`;

function streamOf(...chunks: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("takeEvents", () => {
  it("returns whole events and keeps the partial rest", () => {
    const text = frame(message(1)) + ": ping\n\n" + frame({ type: "turn", running: true }) + 'data: {"type":"mess';

    const { events, rest } = takeEvents(text);

    expect(events).toEqual([message(1), { type: "turn", running: true }]);
    expect(rest).toBe('data: {"type":"mess');
  });

  it("skips a damaged block", () => {
    expect(takeEvents("data: {nope\n\n" + frame(message(2))).events).toEqual([message(2)]);
  });
});

describe("watchGroup", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("delivers events and resumes from the last message after the stream drops", async () => {
    fetchMock
      .mockResolvedValueOnce(streamOf(frame(message(1)), frame(message(2))))
      .mockResolvedValueOnce(new Response("", { status: 404 }));
    const seen: ForgeEvent[] = [];

    const end = watchGroup(7, 0, (event) => seen.push(event), new AbortController().signal);
    await vi.advanceTimersByTimeAsync(600);

    expect(await end).toBe("gone");
    expect(seen.map((e) => (e.type === "message" ? e.seq : e.type))).toEqual([1, 2]);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/forge/groups/7/events?after=0",
      "/api/forge/groups/7/events?after=2",
    ]);
  });

  it("sends the cookie and asks for an event stream", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 404 }));

    await watchGroup(7, 3, () => {}, new AbortController().signal);

    expect(fetchMock.mock.calls[0]![1]).toMatchObject({ credentials: "same-origin", headers: { Accept: "text/event-stream" } });
  });

  it("stops when aborted", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => init.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))),
    );

    const end = watchGroup(7, 0, () => {}, controller.signal);
    controller.abort();

    expect(await end).toBe("aborted");
  });

  it("gives up after the reconnect delays run out", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new TypeError("network down")));

    const end = watchGroup(7, 0, () => {}, new AbortController().signal);
    const outcome = end.then(() => "returned", (error: Error) => error.message);
    await vi.advanceTimersByTimeAsync(20_000);

    expect(await outcome).toBe("Lost the connection to ember_api");
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("reports a 401 and throws", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 401 }));

    await expect(watchGroup(7, 0, () => {}, new AbortController().signal)).rejects.toThrow("Not logged in");
  });
});
