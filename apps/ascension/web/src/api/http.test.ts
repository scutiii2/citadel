import { describe, expect, it, vi } from "vitest";
import { HttpClient, ApiError, UnauthorizedError } from "./http";
import { HostBridge } from "../host/HostBridge";

async function connected() {
  window.history.replaceState(null, "", "/#ticket=launch");
  const bridge = new HostBridge({ fetchFn: async () => new Response(JSON.stringify({ token: "bearer-value" })), hostOrigin: "http://127.0.0.1:5173", win: window, parentWin: null });
  await bridge.connect();
  return bridge;
}
describe("game HTTP", () => {
  it("adds the current bearer token to JSON requests and never sends cookies", async () => {
    const bridge = await connected();
    const fetchFn = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ owner: "42" })));
    const http = new HttpClient(fetchFn, bridge, () => {});
    expect(await http.request("POST", "/ascension/profile", { starter_ascended_id: "guardian" }, { "Idempotency-Key": "action" })).toEqual({ owner: "42" });
    expect(fetchFn).toHaveBeenCalledWith("/ascension/profile", expect.objectContaining({ credentials: "omit", redirect: "error", body: JSON.stringify({ starter_ascended_id: "guardian" }), headers: { Authorization: "Bearer bearer-value", "Idempotency-Key": "action", "Content-Type": "application/json" } }));
    bridge.endSession();
    await http.request("GET", "/ascension/catalog");
    expect(fetchFn.mock.calls[1]?.[1]).toMatchObject({ headers: {} });
  });
  it("ends the session on 401 and displays the game API error without redeeming again", async () => {
    const bridge = await connected(); const ended = vi.fn();
    const http = new HttpClient(async () => new Response(JSON.stringify({ error: "Not signed in" }), { status: 401 }), bridge, ended);
    await expect(http.request("GET", "/ascension/profile")).rejects.toBeInstanceOf(UnauthorizedError);
    expect(bridge.authHeader()).toEqual({}); expect(ended).toHaveBeenCalledOnce();
  });
  it("preserves game errors and empty successful responses", async () => {
    const bridge = await connected();
    const http = new HttpClient(async () => new Response(JSON.stringify({ error: "Battle is active" }), { status: 409 }), bridge, () => {});
    await expect(http.request("POST", "/ascension/profile/reset")).rejects.toMatchObject({ status: 409, message: "Battle is active" });
    const empty = new HttpClient(async () => new Response(null, { status: 204 }), bridge, () => {});
    expect(await empty.request("DELETE", "/ascension/profile")).toBeUndefined();
    expect(ApiError).toBeDefined();
  });
});
