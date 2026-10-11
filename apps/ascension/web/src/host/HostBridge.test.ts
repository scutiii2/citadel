import { afterEach, describe, expect, it, vi } from "vitest";
import { HostBridge } from "./HostBridge";

const origin = "http://127.0.0.1:5173";
function setup(hash = "#ticket=launch-value", response: unknown = { token: "session-value" }) {
  window.history.replaceState(null, "", "/" + hash);
  const postMessage = vi.fn();
  const fetchFn = vi.fn(async () => new Response(JSON.stringify(response), { status: 200 }));
  const parentWin = { postMessage } as unknown as Window;
  const bridge = new HostBridge({ fetchFn, hostOrigin: origin, win: window, parentWin });
  return { bridge, fetchFn, postMessage, parentWin };
}
afterEach(() => { window.history.replaceState(null, "", "/"); vi.restoreAllMocks(); });
describe("HostBridge", () => {
  it("clears the ticket before redemption completes and keeps bearer authentication in memory", async () => {
    const { bridge, fetchFn } = setup();
    const local = vi.spyOn(Storage.prototype, "setItem");
    const connected = bridge.connect();
    expect(window.location.hash).toBe("");
    expect(fetchFn).toHaveBeenCalledWith("/session/redeem", expect.objectContaining({ method: "POST", body: JSON.stringify({ ticket: "launch-value" }), credentials: "omit" }));
    expect(await connected).toBe("ready");
    expect(bridge.authHeader()).toEqual({ Authorization: "Bearer session-value" });
    expect(local).not.toHaveBeenCalled();
  });
  it("does not redeem without a ticket", async () => {
    const { bridge, fetchFn } = setup("");
    expect(await bridge.connect()).toBe("no-ticket");
    expect(bridge.authHeader()).toEqual({});
    expect(fetchFn).not.toHaveBeenCalled();
  });
  it.each([null, {}, { token: "" }, { token: 123 }])("rejects invalid redeem data %j", async data => {
    const { bridge } = setup("#ticket=x", data);
    expect(await bridge.connect()).toBe("failed");
    expect(bridge.authHeader()).toEqual({});
  });
  it("handles refused and unavailable redemption without keeping authentication", async () => {
    const { bridge, fetchFn } = setup();
    fetchFn.mockResolvedValueOnce(new Response("{}", { status: 401 }));
    expect(await bridge.connect()).toBe("failed");
    expect(bridge.authHeader()).toEqual({});
    const next = setup();
    next.fetchFn.mockRejectedValueOnce(new Error("offline"));
    expect(await next.bridge.connect()).toBe("failed");
  });
  it("posts ready, resize and close only to the configured host origin", () => {
    const { bridge, postMessage } = setup();
    bridge.notifyReady(); bridge.notifyResize(640); bridge.requestClose();
    expect(postMessage.mock.calls).toEqual([
      [{ source: "game", type: "ready" }, origin],
      [{ source: "game", type: "resize", height: 640 }, origin],
      [{ source: "game", type: "close" }, origin],
    ]);
  });
});

describe("host messages and session lifetime", () => {
  it("ignores foreign origins and windows and accepts a close only from its host", async () => {
    const { bridge, parentWin } = setup();
    await bridge.connect();
    const closed = vi.fn();
    const stop = bridge.listen(closed);
    const parent = parentWin;
    window.dispatchEvent(new MessageEvent("message", { origin: "https://foreign.example", source: parent, data: { source: "host", type: "close" } }));
    window.dispatchEvent(new MessageEvent("message", { origin, source: window, data: { source: "host", type: "close" } }));
    expect(closed).not.toHaveBeenCalled();
    window.dispatchEvent(new MessageEvent("message", { origin, source: parent, data: { source: "host", type: "close" } }));
    expect(closed).toHaveBeenCalledOnce();
    stop();
    window.dispatchEvent(new MessageEvent("message", { origin, source: parent, data: { source: "host", type: "close" } }));
    expect(closed).toHaveBeenCalledOnce();
  });
  it("does not redeem a spent ticket twice, even after session expiration", async () => {
    const { bridge, fetchFn } = setup();
    await Promise.all([bridge.connect(), bridge.connect()]);
    bridge.endSession();
    await bridge.connect();
    expect(fetchFn).toHaveBeenCalledOnce();
    expect(bridge.authHeader()).toEqual({});
  });
  it("does not post invalid sizes or use a wildcard host", () => {
    const { bridge, postMessage } = setup();
    bridge.notifyResize(NaN); bridge.notifyResize(-1); bridge.notifyResize(Infinity);
    expect(postMessage).not.toHaveBeenCalled();
    expect(() => new HostBridge({ fetchFn: fetch, win: window, parentWin: null, hostOrigin: "*" })).toThrow();
  });
});
