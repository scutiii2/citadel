import { forgeClient, type ForgeEvent } from "../api/ForgeClient";
import { reportUnauthorized, UnauthorizedError } from "../api/http";

/** How a watch ended. "gone": the group no longer exists. "aborted": the caller stopped it. */
export type ForgeWatchEnd = "gone" | "aborted";

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000];

/** Splits whole server-sent events off the front of `buffer`. A partial event stays in `rest`;
 * a keep-alive comment or a damaged block yields nothing. */
export function takeEvents(buffer: string): { events: ForgeEvent[]; rest: string } {
  const events: ForgeEvent[] = [];
  let rest = buffer;
  let boundary: number;
  while ((boundary = rest.indexOf("\n\n")) !== -1) {
    const block = rest.slice(0, boundary);
    rest = rest.slice(boundary + 2);
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6))
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as ForgeEvent);
    } catch {
      /* skip a damaged block */
    }
  }
  return { events, rest };
}

/** Follows a group's event stream until the group is gone or `signal` aborts. fetch() rather
 * than EventSource: it can be aborted, sees the 401/404 status, and resumes from the last
 * message `seq` after a dropped connection. */
export async function watchGroup(
  groupId: number,
  after: number,
  onEvent: (event: ForgeEvent) => void,
  signal: AbortSignal,
): Promise<ForgeWatchEnd> {
  let cursor = after;
  for (let attempt = 0; ; attempt += 1) {
    try {
      const outcome = await readStream(groupId, cursor, signal, (event) => {
        if (event.type === "message") cursor = Math.max(cursor, event.seq);
        attempt = 0;
        onEvent(event);
      });
      if (outcome === "gone") return "gone";
    } catch (err) {
      if (signal.aborted) return "aborted";
      if (err instanceof UnauthorizedError) throw err;
    }
    if (signal.aborted) return "aborted";
    const delay = RECONNECT_DELAYS_MS[attempt];
    if (delay === undefined) throw new Error("Lost the connection to ember_api");
    await sleep(delay, signal);
    if (signal.aborted) return "aborted";
  }
}

async function readStream(
  groupId: number,
  after: number,
  signal: AbortSignal,
  onEvent: (event: ForgeEvent) => void,
): Promise<"gone" | "dropped"> {
  const response = await fetch(forgeClient.eventsUrl(groupId, after), {
    credentials: "same-origin",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (response.status === 404) return "gone";
  if (response.status === 401) {
    reportUnauthorized();
    throw new UnauthorizedError(401, "Not logged in");
  }
  if (!response.ok || !response.body) return "dropped";

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return "dropped";
    const taken = takeEvents(buffer + value);
    buffer = taken.rest;
    for (const event of taken.events) {
      onEvent(event);
      if (event.type === "lagged") {
        await reader.cancel();
        return "dropped";
      }
    }
  }
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
